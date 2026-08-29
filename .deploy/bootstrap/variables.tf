variable "cloud_id" {
  type        = string
  description = "ID облака Yandex Cloud (tier-0)"
}

variable "infra_folder_id" {
  type        = string
  description = "ID папки infra из tier-0 — в ней живут shared-ресурсы (например, корневая DNS-зона)"
}

variable "wif_federation_id" {
  type        = string
  description = "ID WIF-федерации с OIDC-провайдером GitHub из tier-0"
}

variable "github_org" {
  type        = string
  description = "GitHub-организация или username, которому принадлежит репозиторий проекта"
}

variable "github_repo" {
  type        = string
  description = "Имя этого репозитория без префикса организации"
}

variable "project_key" {
  type        = string
  description = "Слаг проекта, используется в именах ресурсов (папка проекта, деплойный SA)"

  validation {
    condition     = can(regex("^[a-z0-9-]{1,20}$", var.project_key))
    error_message = "project_key должен состоять только из строчных латинских букв, цифр и дефисов, длиной от 1 до 20 символов (ограничения YC на именование ресурсов)."
  }
}

variable "project_name" {
  type        = string
  description = "Человекочитаемое имя проекта, используется только в описаниях ресурсов"
}

variable "project_domain" {
  type        = string
  description = "Домен проекта — единая точка входа. На него вешается CNAME на шлюз и им же задаётся custom_domains. Без завершающей точки: точка добавляется в ресурсе записи"

  validation {
    condition     = !endswith(var.project_domain, ".")
    error_message = "project_domain задаётся без завершающей точки (напр. app.example.com) — точка добавляется автоматически."
  }
}

variable "infra_dns_zone_name" {
  type        = string
  description = "Имя корневой DNS-зоны в каталоге infra — в ней создаётся CNAME проекта"
}

variable "infra_cert_name" {
  type        = string
  description = "Имя сертификата в Certificate Manager в каталоге infra. Должен покрывать project_domain, иначе шлюз не примет домен"
}
