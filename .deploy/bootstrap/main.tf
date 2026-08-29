# Конфигурация функции и бакета живёт в общем файле, который читает и этот модуль,
# и workflow (через jq). Единый источник правды: terraform и CI физически не могут
# разойтись в значениях, поэтому рантайм-поля функции не нуждаются в ignore_changes.
locals {
  fn = jsondecode(file("${path.module}/../function.json"))
}

resource "yandex_resourcemanager_folder" "project" {
  cloud_id = var.cloud_id
  name     = var.project_key

  labels = {
    project    = var.project_key
    managed-by = "terraform-tier1"
  }
}

# --- Идентичности -----------------------------------------------------------

resource "yandex_iam_service_account" "deploy" {
  folder_id   = yandex_resourcemanager_folder.project.id
  name        = "sa-${var.project_key}-deploy"
  description = "Deploy SA for ${var.project_name}: выкатывает версии функции и статику"
}

# Деплойный SA делает ровно две вещи и не больше: катит версии функции и заливает
# файлы в бакет. Примитивный editor здесь был бы шире необходимого, а storage.admin,
# certificate-manager.viewer и любые права на infra больше не нужны вовсе —
# бакет приватный, а сертификат и DNS потребляет этот модуль под учёткой человека.
resource "yandex_resourcemanager_folder_iam_member" "deploy_functions" {
  folder_id = yandex_resourcemanager_folder.project.id
  role      = "functions.editor"
  member    = "serviceAccount:${yandex_iam_service_account.deploy.id}"
}

# storage.editor, а не uploader: заливка с clear/skip-unchanged должна уметь
# перечислять и удалять объекты, одной записи не хватит.
resource "yandex_resourcemanager_folder_iam_member" "deploy_storage" {
  folder_id = yandex_resourcemanager_folder.project.id
  role      = "storage.editor"
  member    = "serviceAccount:${yandex_iam_service_account.deploy.id}"
}

# Доверие GitHub Actions -> деплойный SA через WIF. У провайдера yandex-cloud/yandex нет
# CEL-условий как в GCP: external_subject_id — точное совпадение с GitHub OIDC sub-claim.
# Здесь разрешена только ветка main; под другие ветки/окружения нужен ещё один такой ресурс
# с другим external_subject_id.
resource "yandex_iam_workload_identity_federated_credential" "deploy_github" {
  service_account_id  = yandex_iam_service_account.deploy.id
  federation_id       = var.wif_federation_id
  external_subject_id = "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/main"
}

# Отдельная идентичность для самого шлюза: под ней он читает приватный бакет.
# Держим её отдельно от деплойной — у них разные задачи и разный жизненный цикл.
resource "yandex_iam_service_account" "gateway" {
  folder_id   = yandex_resourcemanager_folder.project.id
  name        = "sa-${var.project_key}-gateway"
  description = "SA шлюза ${var.project_name}: чтение статики из приватного бакета"
}

resource "yandex_resourcemanager_folder_iam_member" "gateway_storage_viewer" {
  folder_id = yandex_resourcemanager_folder.project.id
  role      = "storage.viewer"
  member    = "serviceAccount:${yandex_iam_service_account.gateway.id}"
}

# --- Ресурсы из infra -------------------------------------------------------
# Оба читаются из общего каталога. Деплойному SA права на infra не выдаются:
# этот модуль применяет человек, у которого они уже есть.

data "yandex_cm_certificate" "cert" {
  folder_id = var.infra_folder_id
  name      = var.infra_cert_name
}

data "yandex_dns_zone" "root" {
  folder_id = var.infra_folder_id
  name      = var.infra_dns_zone_name
}

# --- Статика ----------------------------------------------------------------

# Бакет приватный: раздачей занимается шлюз под своим SA, поэтому ни публичного ACL,
# ни website-эндпоинта, ни https здесь нет. Имя больше не обязано совпадать с доменом.
resource "yandex_storage_bucket" "frontend" {
  bucket    = local.fn.bucket
  folder_id = yandex_resourcemanager_folder.project.id
}

# --- Функция ----------------------------------------------------------------

# Заглушка на первый apply: ignore_changes не действует при создании, поэтому какой-то
# код здесь быть обязан. Первый же прогон CI заменит его настоящей версией.
data "archive_file" "placeholder" {
  type                    = "zip"
  output_path             = "${path.module}/placeholder.zip"
  source_content          = "def lambda_handler(event, context):\n    return {'statusCode': 503, 'body': 'not deployed yet'}\n"
  source_content_filename = "app.py"
}

resource "yandex_function" "app" {
  name              = local.fn.name
  description       = "https://github.com/${var.github_org}/${var.github_repo}"
  runtime           = local.fn.runtime
  entrypoint        = local.fn.entrypoint
  memory            = local.fn.memory
  execution_timeout = local.fn.timeout
  user_hash         = data.archive_file.placeholder.output_sha256

  content {
    zip_filename = data.archive_file.placeholder.output_path
  }

  log_options {
    disabled  = false
    min_level = "ERROR"
  }

  # Игнорируется ТОЛЬКО код — он реализация и принадлежит CI. Рантайм-поля выше
  # игнорировать не нужно: и terraform, и workflow берут их из function.json,
  # поэтому после выкатки из CI план остаётся пустым.
  lifecycle {
    ignore_changes = [content, user_hash]
  }
}

# --- Точка входа ------------------------------------------------------------

resource "yandex_api_gateway" "gw" {
  name        = "gw-${var.project_key}"
  description = "Единая точка входа ${var.project_name}: статика и API"

  spec = templatefile("${path.module}/openapi.tftpl", {
    function_id   = yandex_function.app.id
    bucket        = yandex_storage_bucket.frontend.bucket
    gateway_sa_id = yandex_iam_service_account.gateway.id
  })

  custom_domains {
    fqdn           = var.project_domain
    certificate_id = data.yandex_cm_certificate.cert.id
  }

  log_options {
    disabled  = false
    min_level = "ERROR"
  }

  execution_timeout = "60"
}

# Запись создаётся здесь, а не в CI, потому что её значение — служебный домен шлюза,
# генерируемый при создании. Предвычислить его нельзя, поэтому шлюз и запись обязаны
# жить в одном графе. Как следствие деплойному SA не нужны никакие права на DNS.
resource "yandex_dns_recordset" "frontend" {
  zone_id = data.yandex_dns_zone.root.id
  name    = "${var.project_domain}."
  type    = "CNAME"
  ttl     = 600
  data    = [yandex_api_gateway.gw.domain]
}
