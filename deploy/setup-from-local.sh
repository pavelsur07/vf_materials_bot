#!/usr/bin/env bash
set -euo pipefail

# Run this script on your local machine.
# It asks for the root password once, connects to the server and sets up
# deploy_user, sudoers, project, dependencies, migrations and systemd.

SERVER_IP="109.73.204.179"
ROOT_USER="root"
DEPLOY_USER="deploy_user"
WORK_DIR="/opt/vf_materials_bot"
SERVICE_NAME="vf-materials-bot"

read -rsp "Enter root password for $SERVER_IP: " ROOT_PASSWORD

echo ""
echo ""

if ! command -v sshpass &>/dev/null; then
    echo "sshpass not found. Install it: sudo apt install sshpass"
    exit 1
fi

read -rp "Enter GitHub repository URL: " REPO_URL
if [[ -z "$REPO_URL" ]]; then
    echo "Repository URL is required"
    exit 1
fi

export SSHPASS="$ROOT_PASSWORD"

run_root() {
    sshpass -e ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$ROOT_USER@$SERVER_IP" "$@"
}

echo "==> Setting up sudoers..."
run_root 'rm -f /etc/sudoers.d/vf-materials-bot-deploy'
run_root 'echo "deploy_user ALL=(ALL) NOPASSWD: /bin/systemctl restart vf-materials-bot" > /etc/sudoers.d/vf-materials-bot-deploy'
run_root 'echo "deploy_user ALL=(ALL) NOPASSWD: /bin/systemctl status vf-materials-bot" >> /etc/sudoers.d/vf-materials-bot-deploy'
run_root 'echo "deploy_user ALL=(ALL) NOPASSWD: /bin/systemctl is-active vf-materials-bot" >> /etc/sudoers.d/vf-materials-bot-deploy'
run_root 'echo "deploy_user ALL=(ALL) NOPASSWD: /bin/journalctl" >> /etc/sudoers.d/vf-materials-bot-deploy'
run_root 'chmod 440 /etc/sudoers.d/vf-materials-bot-deploy'
run_root 'visudo -c'

echo "==> Ensuring deploy_user exists..."
run_root 'id -u deploy_user &>/dev/null || adduser --disabled-password deploy_user'

echo "==> Installing uv if needed..."
run_root 'if ! command -v uv &>/dev/null; then curl -LsSf https://astral.sh/uv/install.sh | sh; fi'

echo "==> Cloning repository..."
run_root "if [[ ! -d $WORK_DIR ]]; then git clone $REPO_URL $WORK_DIR; fi"

echo "==> Fixing project ownership..."
run_root "chown -R $DEPLOY_USER:$DEPLOY_USER $WORK_DIR"

echo "==> Syncing dependencies and applying migrations..."
run_root "cd $WORK_DIR && \$HOME/.local/bin/uv sync && \$HOME/.local/bin/uv run alembic upgrade head"

echo "==> Setting up systemd service..."
run_root "cp $WORK_DIR/deploy/vf-materials-bot.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable $SERVICE_NAME"

unset SSHPASS

echo ""
echo "==> Setup complete."
echo "Copy your .env file:"
echo "  deploy/update-env.sh"
echo "Or manually:"
echo "  scp -i ~/.ssh/vf_materials_bot_deploy .env $DEPLOY_USER@$SERVER_IP:$WORK_DIR/.env"
echo "Then start the service:"
echo "  ssh -i ~/.ssh/vf_materials_bot_deploy $DEPLOY_USER@$SERVER_IP 'sudo systemctl start $SERVICE_NAME'"
