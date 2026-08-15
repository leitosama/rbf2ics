terraform {
  required_version = ">= 1.5"
  required_providers {
    yandex = {
      source  = "yandex-cloud/yandex"
      version = "~> 0.220"
    }
  }
}

provider "yandex" {
  cloud_id = var.cloud_id
  # token не задаём — провайдер подхватит сессию yc CLI
}
