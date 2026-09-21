# Ваш Финдир — Telegram-бот

Чат-бот «Ваш Финдир»: ведёт пользователя по сценариям (меню, кнопки, диалоги)
по финансовой тематике.

Стек: Python 3.12+, aiogram 3.x, SQLite (SQLAlchemy 2.x async + Alembic),
uv, ruff, mypy, pytest. Правила разработки — в [AGENTS.md](AGENTS.md).

## Структура

```
bot/
├── __main__.py      # точка входа: polling или webhook — по MODE из .env
├── config.py        # настройки из .env (pydantic-settings)
├── handlers/        # роутеры: один файл = один сценарий
├── dialogs/         # тексты сообщений и FSM-состояния
├── keyboards/       # клавиатуры, callback через CallbackData-фабрики
├── services/        # бизнес-логика без aiogram-импортов
├── db/              # модели, session factory, миграции Alembic
└── middlewares/     # db-сессия в хэндлеры
deploy/              # nginx-конфиг и systemd-юнит для прода
tests/               # зеркалит структуру bot/
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

## Проверки перед коммитом

```bash
uv run ruff check --fix .
uv run ruff format .
uv run mypy bot/ tests/
uv run pytest
```

## Деплой (webhook на mybots.vashfindir.ru)

Бот будет доступен по адресу `https://mybots.vashfindir.ru/vashfindir`
(путь настраивается через `WEBHOOK_PATH`).

1. DNS: A-запись `mybots.vashfindir.ru` → IP сервера.
2. SSL-сертификат (Telegram шлёт webhook только на HTTPS), например через
   certbot. Прописать пути к сертификату в `deploy/nginx-mybot.conf`.
3. Подключить `deploy/nginx-mybot.conf` в nginx (проксирует `/vashfindir`
   на `127.0.0.1:8081`) и перезагрузить nginx.
4. В `.env` на сервере:
   ```
   MODE=webhook
   WEBHOOK_SECRET=<случайная строка: openssl rand -hex 32>
   BOT_TOKEN=<токен>
   ```
5. Запуск как сервис: скопировать `deploy/vf-materials-bot.service` в
   `/etc/systemd/system/`, поправить пути, затем
   `systemctl enable --now vf-materials-bot`.

## Полезные команды

```bash
uv run alembic revision --autogenerate -m "..."   # новая миграция
uv run alembic upgrade head                       # применить миграции
uv run pytest                                     # тесты
```
