# Ваш Финдир — сервисы для бизнеса

Платформа сервисов для бизнеса: Telegram-бот, публичное API для интеграций,
веб-админка и фоновый воркер. Всё — в одном репозитории: общий конфиг `.env`,
общая SQLite (WAL) и единый автодеплой. Бот — один из каналов доставки.

Стек: Python 3.12+, aiogram 3.x, SQLite (SQLAlchemy 2.x async + Alembic),
uv, ruff, mypy, pytest. Правила разработки — в [AGENTS.md](AGENTS.md).

## Структура

```
bot/
├── __main__.py         # точка входа бота: polling или webhook — по MODE из .env
├── core/               # конфиг, DI-контейнер, исключения
│   ├── config.py
│   ├── container.py
│   └── exceptions.py
├── admin/              # веб-админ-панель (FastAPI), отдельный процесс: python -m bot.admin
├── api/                # публичное API для бизнес-интеграций: python -m bot.api
├── worker/             # фоновый воркер (очередь jobs): python -m bot.worker
├── modules/            # функциональные модули (mini-apps)
│   └── onboarding/     # сценарий старта и проверки подписки
├── agents/             # ИИ-агенты: интерфейс, регистр, оркестратор
├── knowledge/          # база знаний (RAG)
├── integrations/       # адаптеры для внешних API (Telegram, MOEX, ЦБ и др.)
├── services/           # кросс-модульная бизнес-логика
├── db/                 # модели, session factory, миграции Alembic
├── handlers/           # сборщик роутеров + общие error handlers
├── keyboards/          # общие клавиатуры (если появятся)
├── dialogs/            # общие диалоги/тексты (если появятся)
└── middlewares/        # db-сессия, DI

deploy/                 # nginx-конфиг и systemd-юнит для прода
tests/                  # зеркалит структуру bot/
```

## Быстрый старт (локально)

1. Установить [uv](https://docs.astral.sh/uv/):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. Создать `.env` и вписать токен от @BotFather:
   ```bash
   cp .env.example .env   # затем вписать BOT_TOKEN
   ```
3. Установить зависимости и применить миграции:
   ```bash
   uv sync
   uv run alembic upgrade head
   ```
4. Запустить бота (по умолчанию `MODE=polling`):
   ```bash
   uv run python -m bot
   ```

## Веб-админка

Минимальная админ-панель на FastAPI живёт в `bot/admin/` и запускается отдельным
процессом (`python -m bot.admin`). Авторизация — логин/пароль (bcrypt-хэш в `.env`),
сессия — подписанная кука, на формах — CSRF-токен.

1. В `.env` задать:
   ```bash
   deploy/admin-password.sh   # спросит пароль и сам запишет ADMIN_PASSWORD_HASH в .env
   ```
   и вписать (один раз):
   ```bash
   ADMIN_SECRET_KEY=$(openssl rand -hex 32)
   ADMIN_USERNAME=admin
   ```
   Альтернатива без обновления `.env`: `uv run python -m bot.admin.hashpw`
   (интерактивно или `printf '%s' 'пароль' | uv run python -m bot.admin.hashpw`).
2. Локально: `uv run python -m bot.admin` → http://127.0.0.1:8082/admin/
3. На сервере (первый раз): скопировать юнит и включить сервис, обновить nginx:
   ```bash
   sudo cp deploy/vf-materials-bot-admin.service /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now vf-materials-bot-admin
   ```
   Nginx проксирует `/admin/` → `127.0.0.1:8082` (см. `deploy/nginx-mybot.conf`).
   Дальше `deploy/deploy.sh` перезапускает оба сервиса автоматически.

Админка — самодостаточный островок: роуты тонкие, логика в `bot/services/`.
Удаление `bot/admin/` + юнита + блока nginx возвращает проект в исходное состояние.

## Публичное API (bot/api) и воркер (bot/worker)

Машинные endpoint'ы для бизнес-интеграций живут в отдельном процессе
`python -m bot.api` (порт 8083), а не в админке. Аутентификация — токен в
заголовке `x-api-token` (принимается и legacy `x-lead-token` с `LEAD_API_TOKEN`,
так что сайт-источник лидов интеграцию не меняет). Первый endpoint —
`POST /api/leads`: сайт шлёт готовый текст, сервис пересылает его в Telegram.
Nginx проксирует `/api/` → `127.0.0.1:8083`.

Воркер (`python -m bot.worker`) — отдельный процесс, который забирает задачи
из очереди `jobs` в общей SQLite: сервисы кладут (`enqueue_job` из
`bot/services/jobs.py`), воркер выполняет по реестру `bot/worker/handlers.py`
и отмечает done/failed. Включается флагом `WORKER_ENABLED=true` в `.env`
(тогда его перезапускает `deploy/deploy.sh`).

## Проверки перед коммитом

```bash
uv run ruff check --fix .
uv run ruff format --check
uv run mypy bot/
uv run pytest
```

## Деплой

Сервер: `109.73.204.179`. Бот lives в `/opt/vf_materials_bot`.

### Что обновляется автоматически, а что вручную

- **Код и инфраструктура** — автоматически. При пуше в `master` GitHub
  Actions запускает `deploy/deploy.sh` на сервере: он тянет код, синкает
  systemd-юниты, sudoers и nginx-конфиг из репозитория, ставит зависимости,
  применяет миграции и перезапускает сервисы по флагам в `.env`.
- **`.env`** — только вручную. `.env` не в репозитории, секреты не попадают в
  GitHub. Обновляй через `deploy/update-env.sh`.

### Первичная настройка сервера (один раз)

Запусти на локальной машине:

```bash
deploy/setup-from-local.sh
```

Скрипт спросит пароль root, настроит `deploy_user`, sudoers, склонирует репо,
установит зависимости, применит миграции и настроит systemd.

После этого скопируй `.env`:

```bash
deploy/update-env.sh
```

### Обновить `.env` на сервере

```bash
deploy/update-env.sh
```

Это копирует локальный `.env` на сервер и перезапускает сервис.

### Обновить код на сервере

Просто запушь в `main`:

```bash
git push origin main
```

GitHub Actions сам выполнит `git pull`, `uv sync`, миграции и перезапустит
сервис. Статус деплоя смотри во вкладке **Actions** репозитория.

Если хочешь обновить код вручную на сервере:

```bash
ssh -i ~/.ssh/vf_materials_bot_deploy deploy_user@109.73.204.179
sudo deploy/deploy.sh
```

### Проверить статус и логи

```bash
ssh -i ~/.ssh/vf_materials_bot_deploy deploy_user@109.73.204.179 'sudo systemctl is-active vf-materials-bot'
ssh -i ~/.ssh/vf_materials_bot_deploy deploy_user@109.73.204.179 'sudo journalctl -u vf-materials-bot -n 50 --no-pager'
```

### Настройка GitHub Actions

В репозитории → Settings → Secrets and variables → Actions добавь:

- `SSH_HOST` — `109.73.204.179`
- `SSH_USER` — `deploy_user`
- `SSH_PRIVATE_KEY` — приватный ключ `~/.ssh/vf_materials_bot_deploy`
- `SSH_PORT` — `22` (опционально)

Публичный ключ уже должен лежать в `~deploy_user/.ssh/authorized_keys` на
сервере (это делает `setup-from-local.sh`).

### Webhook

Для продакшена в `.env` на сервере должен быть:

```
MODE=webhook
WEBHOOK_HOST=https://mybots.vashfindir.ru
WEBHOOK_PATH=/vashfindir
WEBHOOK_SECRET=<случайная строка>
```

Nginx проксирует `https://mybots.vashfindir.ru/vashfindir` на
`127.0.0.1:8081`. Конфиг ведётся в `deploy/nginx-mybot.conf` — деплой сам
ставит его на сервер (`nginx -t` + reload, старая версия бэкапится в
`/etc/vf-materials-backup`). Руками конфиг на сервере не правим.

## Мониторинг ошибок (GlitchTip / Sentry)

Бот отправляет необработанные исключения в GlitchTip через `sentry-sdk`.
Чтобы включить, добавь в `.env`:

```
GLITCHTIP_DSN=https://xxxx@glitchtip.example.com/1
GLITCHTIP_ENVIRONMENT=production
GLITCHTIP_TRACES_SAMPLE_RATE=0.0
```

Если `GLITCHTIP_DSN` пустой, отправка ошибок отключается.

## Полезные команды

```bash
uv run alembic revision --autogenerate -m "..."   # новая миграция
uv run alembic upgrade head                       # применить миграции
uv run pytest                                     # тесты
```
