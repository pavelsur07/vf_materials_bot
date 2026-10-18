#!/usr/bin/env bash
set -euo pipefail

# Run this script on the server as root to set up deployment user, sudoers,
# clone the project, install dependencies, apply migrations and start the service.

SERVICE_NAME="vf-materials-bot"
ADMIN_SERVICE_NAME="vf-materials-bot-admin"
API_SERVICE_NAME="vf-materials-api"
WORKER_SERVICE_NAME="vf-materials-worker"
WORK_DIR="/opt/vf_materials_bot"
REPO_URL="${1:-}"

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: run this script as root (sudo bash setup-server.sh)"
    exit 1
fi

if ! id -u deploy_user &>/dev/null; then
    echo "==> Creating deploy_user..."
    adduser --disabled-password deploy_user
fi
usermod -aG sudo deploy_user

echo "==> Setting up sudoers..."
rm -f /etc/sudoers.d/vf-materials-bot-deploy
{
    echo "deploy_user ALL=(ALL) NOPASSWD: /bin/systemctl restart ${SERVICE_NAME}"
    echo "deploy_user ALL=(ALL) NOPASSWD: /bin/systemctl status ${SERVICE_NAME}"
    echo "deploy_user ALL=(ALL) NOPASSWD: /bin/systemctl is-active ${SERVICE_NAME}"
    echo "deploy_user ALL=(ALL) NOPASSWD: /bin/systemctl restart ${ADMIN_SERVICE_NAME}"
    echo "deploy_user ALL=(ALL) NOPASSWD: /bin/systemctl status ${ADMIN_SERVICE_NAME}"
    echo "deploy_user ALL=(ALL) NOPASSWD: /bin/systemctl is-active ${ADMIN_SERVICE_NAME}"
    echo "deploy_user ALL=(ALL) NOPASSWD: /bin/systemctl restart ${API_SERVICE_NAME}"
    echo "deploy_user ALL=(ALL) NOPASSWD: /bin/systemctl status ${API_SERVICE_NAME}"
    echo "deploy_user ALL=(ALL) NOPASSWD: /bin/systemctl is-active ${API_SERVICE_NAME}"
    echo "deploy_user ALL=(ALL) NOPASSWD: /bin/systemctl restart ${WORKER_SERVICE_NAME}"
    echo "deploy_user ALL=(ALL) NOPASSWD: /bin/systemctl status ${WORKER_SERVICE_NAME}"
    echo "deploy_user ALL=(ALL) NOPASSWD: /bin/systemctl is-active ${WORKER_SERVICE_NAME}"
} > /etc/sudoers.d/vf-materials-bot-deploy
chmod 440 /etc/sudoers.d/vf-materials-bot-deploy
visudo -c

echo "==> Installing uv..."
if ! command -v uv &>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # shellcheck source=/dev/null
    source "$HOME/.local/bin/env"
fi

if [[ ! -d "$WORK_DIR" ]]; then
    if [[ -z "$REPO_URL" ]]; then
        echo "ERROR: project directory does not exist. Provide repository URL as argument."
        exit 1
    fi
    echo "==> Cloning repository..."
    git clone "$REPO_URL" "$WORK_DIR"
fi

cd "$WORK_DIR"

echo "==> Syncing dependencies..."
uv sync

echo "==> Applying migrations..."
uv run alembic upgrade head

echo "==> Setting up systemd services..."
cp "deploy/vf-materials-bot.service" /etc/systemd/system/
cp "deploy/vf-materials-bot-admin.service" /etc/systemd/system/
cp "deploy/vf-materials-api.service" /etc/systemd/system/
cp "deploy/vf-materials-worker.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
# Админка, API и воркер стартуют вручную/автодеплоем после появления
# ADMIN_*/API_*/WORKER_* в .env.
systemctl enable "$ADMIN_SERVICE_NAME"
systemctl enable "$API_SERVICE_NAME"
systemctl enable "$WORKER_SERVICE_NAME"

echo ""
echo "==> Setup complete."
echo "Now copy your .env file to $WORK_DIR/.env and run:"
echo "  systemctl start $SERVICE_NAME"
