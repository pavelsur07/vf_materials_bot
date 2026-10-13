#!/usr/bin/env bash
# Генерирует bcrypt-хэш пароля веб-админки и записывает его в .env.
#
# Usage:
#   deploy/admin-password.sh           # спросить пароль, обновить .env
#   deploy/admin-password.sh --print   # спросить пароль, только напечатать ADMIN_PASSWORD_HASH=...
set -euo pipefail

cd "$(dirname "$0")/.."

PRINT_ONLY=0
if [[ "${1:-}" == "--print" ]]; then
    PRINT_ONLY=1
fi

read -rsp "Пароль админки: " PASSWORD
echo
read -rsp "Повторите пароль: " PASSWORD_CONFIRM
echo

if [[ -z "$PASSWORD" ]]; then
    echo "ERROR: пароль не может быть пустым" >&2
    exit 1
fi
if [[ "$PASSWORD" != "$PASSWORD_CONFIRM" ]]; then
    echo "ERROR: пароли не совпадают" >&2
    exit 1
fi

# Пароль передаётся через stdin, а не argv — чтобы не светился в истории и ps.
HASH=$(printf '%s' "$PASSWORD" | uv run python -m bot.admin.hashpw)
unset PASSWORD PASSWORD_CONFIRM

if [[ "$PRINT_ONLY" == "1" ]]; then
    echo "ADMIN_PASSWORD_HASH=$HASH"
    exit 0
fi

if [[ ! -f .env ]]; then
    echo "ERROR: .env не найден в $(pwd). Сначала: cp .env.example .env" >&2
    exit 1
fi

# Хэш bcrypt не содержит '&' и '|', sed-замена безопасна.
if grep -q '^ADMIN_PASSWORD_HASH=' .env; then
    sed -i "s|^ADMIN_PASSWORD_HASH=.*|ADMIN_PASSWORD_HASH=$HASH|" .env
else
    printf 'ADMIN_PASSWORD_HASH=%s\n' "$HASH" >> .env
fi

echo "OK: ADMIN_PASSWORD_HASH обновлён в .env"
echo "Не забудьте задать ADMIN_SECRET_KEY (openssl rand -hex 32), если ещё не задан."
