terraform {
  required_version = ">= 1.5"
  required_providers {
    yandex = {
      source  = "yandex-cloud/yandex"
      version = "~> 0.220"
    }
    github = {
      source  = "integrations/github"
      version = "~> 6.6"
    }
  }
}
