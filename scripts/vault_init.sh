#!/bin/sh
set -e

until wget --spider -q http://vault:8200/v1/sys/health; do
  echo "Waiting for Vault..."
  sleep 2
done

echo "Vault is up! Populating secrets..."

export VAULT_ADDR=http://vault:8200
export VAULT_TOKEN=${VAULT_ROOT_TOKEN:-your_vault_dev_token}

vault secrets enable -path=secret kv || true
vault kv put secret/app \
  llm_api_key="placeholder" \
  jwt_secret="dev-secret-change-me" \
  db_password="postgres" \
  minio_secret="minioadmin" \
  tracing_key="placeholder"

echo "Secrets populated successfully."
