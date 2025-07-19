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