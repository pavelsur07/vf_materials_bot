#!/usr/bin/env bash
set -euo pipefail

# One-time server-side setup for the admin panel (systemd unit, sudoers, nginx).
# Run ON THE SERVER, after the code with bot/admin/ is deployed:
#   sudo bash /opt/vf_materials_bot/deploy/setup-admin-server.sh
# Idempotent: safe to re-run.

ADMIN_SERVICE_NAME="vf-materials-bot-admin"
WORK_DIR="/opt/vf_materials_bot"
NGINX_SITE="/etc/nginx/sites-available/mybots"
SUDOERS_FILE="/etc/sudoers.d/vf-materials-bot-deploy"

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: run as root: sudo bash deploy/setup-admin-server.sh" >&2
    exit 1
fi

echo "==> Installing systemd unit $ADMIN_SERVICE_NAME"
cp "$WORK_DIR/deploy/vf-materials-bot-admin.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$ADMIN_SERVICE_NAME"

echo "==> Extending sudoers for deploy_user"
if ! grep -q "systemctl restart $ADMIN_SERVICE_NAME" "$SUDOERS_FILE"; then
    {
        echo "deploy_user ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart $ADMIN_SERVICE_NAME"
        echo "deploy_user ALL=(ALL) NOPASSWD: /usr/bin/systemctl status $ADMIN_SERVICE_NAME"
        echo "deploy_user ALL=(ALL) NOPASSWD: /usr/bin/systemctl is-active $ADMIN_SERVICE_NAME"
    } >> "$SUDOERS_FILE"
fi
visudo -c

echo "==> Adding nginx location /admin/"
if grep -q "location /admin/" "$NGINX_SITE"; then
    echo "    already present, skipping"
else
    NGINX_BLOCK=$(cat <<'EOF'
    location /admin/ {
        proxy_pass http://127.0.0.1:8082;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

EOF
)
    awk -v block="$NGINX_BLOCK" '/listen 443 ssl/ && !done {print block; done=1} {print}' \
        "$NGINX_SITE" > "$NGINX_SITE.tmp"
    mv "$NGINX_SITE.tmp" "$NGINX_SITE"
    nginx -t
    systemctl reload nginx
fi

echo "==> Starting admin service"
if grep -qE '^ADMIN_SECRET_KEY=.+' "$WORK_DIR/.env" 2>/dev/null; then
    systemctl restart "$ADMIN_SERVICE_NAME"
    systemctl is-active "$ADMIN_SERVICE_NAME"
else
    echo "    ADMIN_SECRET_KEY is missing in $WORK_DIR/.env — not starting."
    echo "    Update .env (deploy/update-env.sh), then: sudo systemctl restart $ADMIN_SERVICE_NAME"
fi

echo "==> Done. Admin panel: https://mybots.vashfindir.ru/admin/"
