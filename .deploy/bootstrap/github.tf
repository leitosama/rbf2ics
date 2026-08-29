# Шов между созданным проектом в YC и репозиторием, который в него катит.
# Оба значения ниже генерирует облако, а не человек, поэтому переносить их
# копипастой в Settings → Secrets and variables незачем: модуль знает и то,
# и другое, и проставляет сам. Токен провайдер берёт из GITHUB_TOKEN —
# его выставляет variables.sh через `gh auth token`, так что bootstrap
# по-прежнему применяется руками с ПК и никаких ключей в репозитории не заводит.

provider "github" {
  owner = var.github_org
}

# Variables, а не Secrets: секрета здесь нет. Доступ к облаку даёт не знание
# идентификаторов, а обмен OIDC-токена GitHub на IAM-токен по WIF — пускает
# federated credential с external_subject_id этого репозитория и ветки main
# (см. yandex_iam_workload_identity_federated_credential.deploy_github).
# Побочно: значения видны в логах прогонов и читаются обратно через
# `gh variable list`, поэтому дрейф заметен, а из Secrets значение не достать.
#
# Здесь ровно два значения — всё остальное (runtime, entrypoint, память,
# таймаут, имена функции и бакета) лежит в .deploy/function.json и читается
# оттуда и терраформом (jsondecode), и workflow (jq).

resource "github_actions_variable" "yc_sa_id" {
  repository    = var.github_repo
  variable_name = "YC_SA_ID"
  value         = yandex_iam_service_account.deploy.id
}

resource "github_actions_variable" "yc_folder_id" {
  repository    = var.github_repo
  variable_name = "YC_FOLDER_ID"
  value         = yandex_resourcemanager_folder.project.id
}
