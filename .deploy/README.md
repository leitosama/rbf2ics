# Terraform

## Environment variables
### Terraform S3 Backend
* AWS_ACCESS_KEY_ID - Access key for Terraform S3 Backend 
* AWS_SECRET_ACCESS_KEY - Secret key for Terraform S3 Backend

For more see [Загрузка состояний Terraform в Yandex Object Storage
|Yandex Cloud](https://yandex.cloud/ru/docs/tutorials/infrastructure-management/terraform-state-storage)

### Yandex Cloud 
* YC_CLOUD_ID - YC Cloud ID contained "ctfd" folder 
* YC_FOLDER_ID - YC Folder ID of "ctfd" folder
* YC_TOKEN - IAM Token of SA account to apply changes

For more see [Начало работы с Terraform|Yandex Cloud](https://yandex.cloud/ru/docs/tutorials/infrastructure-management/terraform-quickstart)

### Terraform variables
Export .env values to environment:  
```bash
set -a && source .env && set +a
```

```powershell
get-content test.env | foreach {
    $name, $value = $_.split('=')
    set-content env:\$name $value
}
```

## Usage
0. Setup terraform provider mirror in `~/.terraformrc` 
```
provider_installation {
  network_mirror {
    url = "https://terraform-mirror.yandexcloud.net/"
    include = ["registry.terraform.io/*/*"]
  }
  direct {
    exclude = ["registry.terraform.io/*/*"]
  }
}
```
1. `cp .env.sample .env` and setup [Environment variables](#environment-variables)
2. Init terraform backend
```bash
terraform init
```
3. Plan changes
```bash
terraform plan -out rbf2ics.tfplan
```
4. Apply changes
```bash
terraform apply rbf2ics.tfplan
```
5. You can destroy all the things we created by command
```bash
terraform destroy
```