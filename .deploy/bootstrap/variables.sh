#!/bin/bash

export YC_FOLDER_ID=$(yc config get folder-id)
export YC_CLOUD_ID=$(yc config get cloud-id)
export TF_VAR_project_key="rbf2ics"
export TF_VAR_project_name="${TF_VAR_project_key}"
export TF_VAR_github_org="leitosama"
export TF_VAR_github_repo="${TF_VAR_project_key}"
export TF_VAR_infra_folder_id=$(yc config get folder-id)
export TF_VAR_wif_federation_id=$(yc iam workload-identity oidc federation list --folder-id=$YC_FOLDER_ID --format json --jq ".[0].id")
export TF_VAR_infra_dns_zone_name=$(yc dns zone list --folder-id=$YC_FOLDER_ID --format json --jq ".[0].name")
export TF_VAR_infra_cert_name=$(yc certificate-manager certificate list --folder-id=$YC_FOLDER_ID --format json --jq ".[0].name")
export TF_VAR_project_domain="${TF_VAR_project_key}.yc.leito.tech"
export YC_TOKEN=$(yc iam create-token)