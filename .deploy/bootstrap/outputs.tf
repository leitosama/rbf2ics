output "project_folder_id" {
  value       = yandex_resourcemanager_folder.project.id
  description = "ID папки проекта, созданной этим модулем"
}

output "deploy_sa_id" {
  value       = yandex_iam_service_account.deploy.id
  description = "ID деплойного сервисного аккаунта"
}

output "gateway_domain" {
  value       = yandex_api_gateway.gw.domain
  description = "Служебный домен шлюза — цель CNAME. Генерируется при создании, поэтому запись создаётся здесь же"
}

output "project_url" {
  value       = "https://${var.project_domain}"
  description = "Единая точка входа проекта"
}

output "github_setup" {
  description = "Настройка GitHub Actions. Секретов нет: аутентификация идёт через WIF"
  value       = <<-EOT
    Добавить в Settings → Secrets and variables → Actions этого репозитория.

    Variables — ровно два значения, и только потому, что их генерирует YC,
    а не пишет человек. Всё остальное (runtime, entrypoint, память, таймаут,
    имена функции и бакета) лежит в .deploy/function.json и читается оттуда
    и терраформом, и workflow — синхронизировать руками нечего:

      YC_SA_ID     = ${yandex_iam_service_account.deploy.id}
      YC_FOLDER_ID = ${yandex_resourcemanager_folder.project.id}

    Secrets: не нужны. Если в репозитории остались TF_BACKEND_ACCESS_KEY и
    TF_BACKEND_SECRET_KEY от прежней схемы с terraform в CI — удалить,
    tier-2 больше не держит state.
  EOT
}
