terraform {
  required_providers {
    yandex = {
      source  = "yandex-cloud/yandex"
      version = ">= 0.47.0"
    }
  }
  backend "s3" {
    endpoints = {
      s3 = "https://storage.yandexcloud.net"
    }
    bucket = "tf-backend"
    region = "ru-central1"
    key    = "rbf2ics.tfstate"

    skip_region_validation      = true
    skip_credentials_validation = true
    skip_requesting_account_id  = true # Необходимая опция Terraform для версии 1.6.1 и старше.
    skip_s3_checksum            = true # Необходимая опция при описании бэкенда для Terraform версии 1.6.3 и старше.
 
  }
}

variable "defaultfolder_id" {
  description = "Folder contains your DNS zone"
}

variable "frontend_address" {
  description = "Frontend address for generating link"
}

data "yandex_cm_certificate" "cert" {
  folder_id = var.defaultfolder_id
  name = "yc-leito-tech"
}

data "yandex_dns_zone" "dns_zone" {
  name = "yc-leito-tech"
  folder_id = var.defaultfolder_id
}

data "yandex_resourcemanager_folder" "folder" {
  name = "rbf2ics"
}


# 3. Archive code
resource "archive_file" "content" {
  type = "zip"
  output_path = "${path.module}/content.zip"
  source_dir = "${path.module}/../rbf2ics"
}

# 4. Function
resource "yandex_function" "rbf2ics" {
  name               = "f-rbf2ics"
  description        = "https://github.com/leitosama/rbf2ics"
  user_hash          = archive_file.content.output_sha256
  runtime            = "python312"
  entrypoint         = "app.lambda_handler"
  memory             = "128"
  execution_timeout  = "10" 
  content {
    zip_filename = archive_file.content.output_path
  }
  log_options {
    disabled = false
    min_level    = "ERROR"
  }
}

resource "yandex_api_gateway" "gw" {
  name        = "gw-rbf2ics"
  description = ""
  log_options {
    disabled = false
    min_level    = "ERROR"
  }
  execution_timeout = "60"
  spec              = templatefile("${path.module}/openapi.tftpl", {
    function_id = yandex_function.rbf2ics.id
  })
}


# 2. Add some new resources
# resource "yandex_iam_service_account" "sa" {
#   name      = "sa-frontend"
# }

# resource "yandex_resourcemanager_folder_iam_member" "sa-editor" {
#   folder_id = data.yandex_resourcemanager_folder.folder.id
#   role      = "storage.editor"
#   member    = "serviceAccount:${yandex_iam_service_account.sa.id}"
# }

# resource "yandex_iam_service_account_static_access_key" "sa-static-key" {
#   service_account_id = yandex_iam_service_account.sa.id
#   description        = "static access key for object storage"
# }

resource "yandex_storage_bucket" "frontend-storage" {
  # depends_on = [ yandex_resourcemanager_folder_iam_member.sa-editor ]
  # access_key = yandex_iam_service_account_static_access_key.sa-static-key.access_key
  # secret_key = yandex_iam_service_account_static_access_key.sa-static-key.secret_key
  bucket     = var.frontend_address
  folder_id = data.yandex_resourcemanager_folder.folder.id
  acl        = "public-read"
  force_destroy = false
  https {
    certificate_id = data.yandex_cm_certificate.cert.id
  }
  
  website {
    index_document = "index.html"
  }
}

resource "yandex_dns_recordset" "frontend" {
  depends_on = [ yandex_storage_bucket.frontend-storage ]
  zone_id = data.yandex_dns_zone.dns_zone.id
  name    = "${var.frontend_address}."
  type    = "ANAME"
  ttl     = 600
  data    = ["${var.frontend_address}.website.yandexcloud.net"]
}