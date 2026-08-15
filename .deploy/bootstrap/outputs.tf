output "project_folder_id" {
  value       = yandex_resourcemanager_folder.project.id
  description = "ID папки проекта, созданной этим модулем"
}

output "deploy_sa_id" {
  value       = yandex_iam_service_account.deploy.id
  description = "ID деплойного сервисного аккаунта"
}

output "deploy_sa_name" {
  value       = yandex_iam_service_account.deploy.name
  description = "Имя деплойного сервисного аккаунта"
}

output "project_state_bucket" {
  value       = yandex_storage_bucket.project_state.bucket
  description = "Имя изолированного state-бакета tier-2 этого проекта (не общий бакет tier-0)"
}

output "deploy_sa_access_key" {
  value       = yandex_iam_service_account_static_access_key.deploy_backend_key.access_key
  description = "access_key деплойного SA для бэкенда tier-2 (не секрет сам по себе, но храним рядом с secret_key)"
}

output "deploy_sa_secret_key" {
  value       = yandex_iam_service_account_static_access_key.deploy_backend_key.secret_key
  description = "secret_key деплойного SA для бэкенда tier-2 — секрет, положить в GitHub Secrets и не светить в логах"
  sensitive   = true
}

output "github_setup" {
  description = "Инструкция по настройке GitHub Actions и backend.hcl tier-2 под деплойным SA"
  value       = <<-EOT
    Добавить в Settings → Secrets and variables → Actions этого репозитория.

    Variables (не секреты, это просто идентификаторы):
      YC_SA_ID     = ${yandex_iam_service_account.deploy.id}
      YC_FOLDER_ID = ${yandex_resourcemanager_folder.project.id}

    Secrets (свои для этого проекта, не общие с другими):
      TF_BACKEND_ACCESS_KEY = ${yandex_iam_service_account_static_access_key.deploy_backend_key.access_key}
      TF_BACKEND_SECRET_KEY = <terraform output -raw deploy_sa_secret_key>

    backend.hcl для .terraform/infra (свой бакет, не общий tier-0):
      bucket = "${yandex_storage_bucket.project_state.bucket}"
      key    = "infra/${var.project_key}/terraform.tfstate"

    Шаг аутентификации в workflow для tier-2:

      - uses: yc-actions/yc-iam-token@v1
        id: yc-token
        with:
          yc-sa-id: $${{ vars.YC_SA_ID }}

      - name: terraform apply
        env:
          YC_TOKEN: $${{ steps.yc-token.outputs.token }}
          AWS_ACCESS_KEY_ID: $${{ secrets.TF_BACKEND_ACCESS_KEY }}
          AWS_SECRET_ACCESS_KEY: $${{ secrets.TF_BACKEND_SECRET_KEY }}
          TF_VAR_folder_id: $${{ vars.YC_FOLDER_ID }}
        run: terraform -chdir=.terraform/infra apply -auto-approve
  EOT
}
