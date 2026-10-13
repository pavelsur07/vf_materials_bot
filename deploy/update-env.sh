#!/usr/bin/env bash
set -euo pipefail

# Update .env on the production server from the local .env file.
# Run from the project root on your local machine.

SERVER_IP="109.73.204.179"
DEPLOY_USER="deploy_user"
WORK_DIR="/opt/vf_materials_bot"
SERVICE_NAME="vf-materials-bot"
ADMIN_SERVICE_NAME="vf-materials-bot-admin"
LOCAL_ENV=".env"

if [[ ! -f "$LOCAL_ENV" ]]; then
    echo "ERROR: $LOCAL_ENV not found in current directory"
    exit 1
fi

echo "==> Copying $LOCAL_ENV to server..."
scp -i "~/.ssh/vf_materials_bot_deploy" "$LOCAL_ENV" "$DEPLOY_USER@$SERVER_IP:$WORK_DIR/.env"

echo "==> Restarting services..."
ssh -i "~/.ssh/vf_materials_bot_deploy" -o StrictHostKeyChecking=no "$DEPLOY_USER@$SERVER_IP" \
    "sudo systemctl restart $SERVICE_NAME && \
if grep -qE '^ADMIN_SECRET_KEY=.+' $WORK_DIR/.env; then sudo systemctl restart $ADMIN_SERVICE_NAME; fi && \
sudo systemctl is-active $SERVICE_NAME"

echo "==> .env updated and services restarted."
