resource "yandex_resourcemanager_folder" "project" {
  cloud_id = var.cloud_id
  name     = var.project_key

  labels = {
    project    = var.project_key
    managed-by = "terraform-tier1"
  }
}

resource "yandex_iam_service_account" "deploy" {
  folder_id   = yandex_resourcemanager_folder.project.id
  name        = "sa-${var.project_key}-deploy"
  description = "Terraform deploy SA for ${var.project_name}"
}

resource "yandex_resourcemanager_folder_iam_member" "deploy_editor" {
  folder_id = yandex_resourcemanager_folder.project.id
  role      = "editor"
  member    = "serviceAccount:${yandex_iam_service_account.deploy.id}"
}

# Публичный (анонимный) доступ к бакету через ACL public-read требует storage.admin:
# роль storage.editor из примитивного editor выше умеет создавать бакеты, но не
# управлять ACL и публичным доступом. Дополняет editor, не заменяет его.
resource "yandex_resourcemanager_folder_iam_member" "deploy_storage_admin" {
  folder_id = yandex_resourcemanager_folder.project.id
  role      = "storage.admin"
  member    = "serviceAccount:${yandex_iam_service_account.deploy.id}"
}

# Позволяет tier-2 читать корневую DNS-зону из infra и заводить в ней поддомены проекта.
# Прав на запись намеренно нет.
resource "yandex_resourcemanager_folder_iam_member" "deploy_dns_viewer" {
  folder_id = var.infra_folder_id
  role      = "dns.viewer"
  member    = "serviceAccount:${yandex_iam_service_account.deploy.id}"
}

# Tier-2 читает TLS-сертификат из infra (data.yandex_cm_certificate.cert), чтобы
# повесить https на бакет. Нужен доступ на чтение сертификатов в infra-папке.
resource "yandex_resourcemanager_folder_iam_member" "deploy_cert_viewer" {
  folder_id = var.infra_folder_id
  role      = "certificate-manager.viewer"
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

# Собственный state-бакет tier-2, изолированный от общего бакета tier-0. Пустой при
# создании — наполняет его `terraform init -backend-config` тир-2-модуля.
resource "yandex_storage_bucket" "project_state" {
  bucket    = "tfstate-${var.project_key}"
  folder_id = yandex_resourcemanager_folder.project.id
}

# Только деплойный SA может писать в этот бакет — остальным (включая sa-tf-backend) сюда
# доступа нет, это не общий бакет.
resource "yandex_storage_bucket_iam_binding" "project_state_uploader" {
  bucket = yandex_storage_bucket.project_state.bucket
  role   = "storage.uploader"

  members = [
    "serviceAccount:${yandex_iam_service_account.deploy.id}",
  ]
}

# Terraform-бэкенд s3 умеет только статические AWS-style креды, IAM-токен ему не передать —
# поэтому для tier-2 нужен статический ключ именно у деплойного SA, отдельный от ключа
# sa-tf-backend. Секрет уходит в state этого (tier-1) модуля, вывод помечен sensitive.
resource "yandex_iam_service_account_static_access_key" "deploy_backend_key" {
  service_account_id = yandex_iam_service_account.deploy.id
  description        = "Backend access key for tier-2 state bucket of ${var.project_name}"
}
