#!/usr/bin/env bash
# Deploy the talent matcher to Azure Container Apps (Consumption plan, scales to zero).
# Run in Azure Cloud Shell (Bash): portal.azure.com -> the >_ icon at the top.
# Usage:
#   export GITHUB_USER=your-github-username
#   export GEMINI_API_KEY=your-gemini-key
#   export GHCR_TOKEN=...                        # only if the image package is private
#   bash deploy.sh
set -euo pipefail

: "${GITHUB_USER:?Set GITHUB_USER to your GitHub username}"
: "${GEMINI_API_KEY:?Set GEMINI_API_KEY}"

RG=${RG:-talent-matcher-rg}
LOCATION=${LOCATION:-swedencentral}            # EU region; northeurope / westeurope also fine
ENV_NAME=${ENV_NAME:-talent-matcher-env}
APP=${APP:-talent-matcher}
IMAGE=${IMAGE:-ghcr.io/$(echo "$GITHUB_USER" | tr '[:upper:]' '[:lower:]')/talent-matcher:latest}

echo "==> Registering providers and the containerapp CLI extension (first time only)"
az extension add --name containerapp --upgrade --only-show-errors
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait

echo "==> Resource group $RG in $LOCATION"
az group create -n "$RG" -l "$LOCATION" -o none

echo "==> Container Apps environment (no Log Analytics, to avoid log ingestion charges)"
az containerapp env create -n "$ENV_NAME" -g "$RG" -l "$LOCATION" --logs-destination none -o none

SECRETS=("gemini-key=$GEMINI_API_KEY")
ENVVARS=("GEMINI_API_KEY=secretref:gemini-key")

REGISTRY_ARGS=()
if [[ -n "${GHCR_TOKEN:-}" ]]; then              # only needed if the GHCR package is private
  REGISTRY_ARGS=(--registry-server ghcr.io --registry-username "$GITHUB_USER" --registry-password "$GHCR_TOKEN")
fi

echo "==> Container app $APP from $IMAGE"
az containerapp create -n "$APP" -g "$RG" --environment "$ENV_NAME" \
  --image "$IMAGE" "${REGISTRY_ARGS[@]}" \
  --target-port 8080 --ingress external \
  --min-replicas 0 --max-replicas 1 \
  --cpu 0.5 --memory 1.0Gi \
  --secrets "${SECRETS[@]}" \
  --env-vars "${ENVVARS[@]}" \
  -o none

URL=$(az containerapp show -n "$APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)
echo
echo "Live at: https://$URL"
echo "First load after idle takes ~20-40 s while a replica starts (scale-to-zero)."
