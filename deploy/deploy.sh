#!/usr/bin/env bash
set -euo pipefail

# Fast deploy script for vf-materials-bot.
# Run on the production server from the project directory (or via SSH/GitHub Actions).

SERVICE_NAME="vf-materials-bot"
ADMIN_SERVICE_NAME="vf-materials-bot-admin"
WORK_DIR="/opt/vf_materials_bot"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<EOF
Usage: $0

Deploys the latest main branch to production:
  1. git pull --ff-only origin main
  2. uv sync
  3. alembic upgrade head
  4. systemctl restart vf-materials-bot
     (+ vf-materials-bot-admin, если в .env задан ADMIN_SECRET_KEY)

Requires:
  - repository cloned to $WORK_DIR
  - .env configured in $WORK_DIR
  - sudo access to systemctl restart $SERVICE_NAME

.env is NEVER updated by this script. Update it manually via:
  deploy/update-env.sh
EOF
    exit 0
fi

if [[ ! -d "$WORK_DIR" ]]; then
    log "ERROR: project directory $WORK_DIR does not exist"
    exit 1
fi

cd "$WORK_DIR"

if [[ ! -f ".env" ]]; then
    log "ERROR: .env not found in $WORK_DIR"
    log "Copy it manually: deploy/update-env.sh"
    exit 1
fi

log "Pulling latest changes..."
git pull --ff-only origin "$(git branch --show-current)"

log "Syncing dependencies..."
uv sync

log "Applying migrations..."
uv run alembic upgrade head

SERVICES=("$SERVICE_NAME")
if grep -qE '^ADMIN_SECRET_KEY=.+' .env; then
    SERVICES+=("$ADMIN_SERVICE_NAME")
else
    log "WARNING: ADMIN_SECRET_KEY is not set in .env, skipping $ADMIN_SERVICE_NAME"
    log "         To enable the admin panel, add ADMIN_* vars via deploy/update-env.sh"
fi

for service in "${SERVICES[@]}"; do
    log "Restarting service $service..."
    sudo -n systemctl restart "$service"
done

log "Waiting for services to start..."
sleep 2

for service in "${SERVICES[@]}"; do
    if sudo -n systemctl is-active --quiet "$service"; then
        log "SUCCESS: $service is active"
    else
        log "ERROR: $service failed to start"
        sudo -n systemctl is-active "$service" || true
        exit 1
    fi
done
