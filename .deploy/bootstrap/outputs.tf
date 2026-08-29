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
  description = "Что модуль проставил в GitHub Actions и что осталось сделать человеку"
  value       = <<-EOT
    Настройки Actions проставлены этим модулем, руками добавлять нечего:

      Variables: YC_SA_ID     = ${yandex_iam_service_account.deploy.id}
                 YC_FOLDER_ID = ${yandex_resourcemanager_folder.project.id}

    Секретов нет: аутентификация идёт через WIF, ключей не существует.
    Всё остальное (runtime, entrypoint, память, таймаут, имена функции и
    бакета) лежит в .deploy/function.json и читается оттуда и терраформом,
    и workflow — синхронизировать руками нечего.

    Единственное, чего модуль сделать не может, — убрать чужое. Если в
    репозитории остались YC_SA_ID/YC_FOLDER_ID в Secrets от прежней схемы
    или TF_BACKEND_ACCESS_KEY / TF_BACKEND_SECRET_KEY от времён terraform
    в CI — удалить руками (gh secret delete): терраформ не управляет тем,
    чего не создавал.
  EOT
}
