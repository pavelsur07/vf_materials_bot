# AGENTS.md — «Ваш Финдир»

Платформа «Ваш Финдир» — набор сервисов для бизнеса на Python: Telegram-бот,
публичное API для интеграций, веб-админка и фоновый воркер. Сервисы живут в
одном репозитории и развёртке: общий конфиг `.env`, общая SQLite (WAL) и единый
автодеплой. Telegram-бот — один из каналов доставки и один из процессов
платформы, а не монолит, вокруг которого всё строится.

Этот файл — обязательные правила для человека и ИИ-агента. Он короче ума:
когда правило мешает, сначала обнови этот файл, потом код — а не наоборот.

## Стек (зафиксирован, не менять без обновления этого файла)

- Python 3.12+, asyncio
- aiogram 3.x (Router, F-фильтры, FSM для диалогов)
- SQLite через SQLAlchemy 2.x (async) + Alembic для миграций (одна БД на все
  процессы, WAL + busy_timeout включаются в `vashfindir/db/session.py`)
- uv — управление зависимостями и окружением (никакого pip/poetry)
- ruff — линтер и форматтер, mypy — строгая типизация
- pytest + pytest-asyncio — тесты
- Pillow (PIL) — чтение, валидация и нормализация PNG-изображений
- sentry-sdk — отправка ошибок в GlitchTip/Sentry
- FastAPI + uvicorn + Jinja2 — веб-сервисы (`vashfindir/apps/admin/`,
  `vashfindir/apps/api/`, отдельные процессы)
- bcrypt + itsdangerous — авторизация в админке (хэш пароля, подписанная сессия)

## Структура проекта

```
vf_materials_bot/             # имя репозитория — историческое, пакет платформы
│                             # называется vashfindir; переименование репо —
│                             # отдельная фаза (каталог на сервере /opt/...)
├── pyproject.toml            # зависимости, конфиг ruff/mypy/pytest
├── .env.example              # шаблон переменных (BOT_TOKEN=...); .env — в .gitignore
├── vashfindir/               # корневой пакет платформы
│   ├── core/                 # конфиг и исключения
│   │   ├── config.py         # pydantic-settings, единственный источник конфига
│   │   └── exceptions.py     # кастомные исключения проекта
│   ├── db/                   # SQLAlchemy + Alembic
│   │   ├── models.py
│   │   ├── session.py
│   │   └── migrations/
│   ├── domain/               # кросс-модульная бизнес-логика (чистые функции/классы)
│   ├── agents/               # ИИ-агенты: интерфейс, регистр, оркестратор
│   ├── knowledge/            # база знаний (RAG): хранилище, ретривер, загрузчики
│   ├── integrations/         # адаптеры для внешних API (Telegram, MOEX, ЦБ и др.)
│   ├── modules/              # бизнес-модули (mini-apps): onboarding, leads, ...
│   │   └── onboarding/       # пример: старт и проверка подписки
│   │       ├── handlers.py
│   │       ├── use_cases.py
│   │       ├── dto.py
│   │       ├── keyboards.py
│   │       └── dialogs.py
│   └── apps/                 # процессы (deployable units) — «сервисы»
│       ├── bot/              # Telegram-бот: __main__.py (polling/webhook),
│       │                     # handlers/ (сборщик роутеров + error handlers),
│       │                     # middlewares/ (db-сессия, DI)
│       ├── admin/            # веб-админ-панель (FastAPI): отдельный процесс,
│       │                     # роуты — тонкие адаптеры, логика — в domain/
│       │   ├── app.py        # фабрика FastAPI-приложения
│       │   ├── auth.py       # авторизация, CSRF, AuthMiddleware
│       │   └── routes/       # страницы (login, dashboard)
│       ├── api/              # публичное API для бизнес-интеграций (FastAPI):
│       │                     # отдельный процесс, токен-аутентификация, без сессий
│       │   ├── app.py        # фабрика FastAPI-приложения
│       │   ├── auth.py       # проверка токена (x-api-token / legacy x-lead-token)
│       │   └── routes/       # машинные endpoint'ы (/api/leads)
│       └── worker/           # фоновый воркер: забирает задачи из очереди jobs
│           ├── __main__.py   # цикл поллинга очереди, остановка по SIGTERM
│           └── handlers.py   # реестр обработчиков задач
├── data/                     # локальная SQLite (в git не коммитится)
├── tests/                    # зеркалит структуру vashfindir/
└── deploy/                   # systemd-юниты, nginx-конфиг, скрипты деплоя
```

Внутри `vashfindir/` — две зоны, не смешиваем их в голове:

1. **Библиотека платформы**: слои `core`, `db`, `domain`, `agents`,
   `knowledge`, `integrations` + бизнес-модули `modules/<name>/`. Никакого
   aiogram/fastapi в этой зоне — её можно тестировать без Telegram и веб-сервера.
2. **Процессы**: `apps/<name>/` — тонкие оболочки, которые запускаются
   systemd и используют библиотеку. Бот — один из четырёх процессов
   (bot, admin, api, worker), см. раздел «Сервисы (процессы)».

Новый код кладётся строго по слою. Если непонятно куда — значит, это `domain/`,
а импорты aiogram в нём — признак ошибки проектирования.

## Сервисы (процессы)

Сервис = `python -m vashfindir.apps.<name>` = systemd-юнит `vf-materials-<name>`.
Все сервисы читают один `.env`, ходят в одну SQLite и используют общие слои
(`core`, `db`, `domain`, `integrations`, `agents`, `knowledge`). Схема БД единая,
владелец — Alembic: миграцию генерируем локально и коммитим, применяет
`deploy/deploy.sh` один раз до перезапуска сервисов.

| Сервис | Модуль                   | Порт | Включается в деплое              |
|--------|--------------------------|------|----------------------------------|
| bot    | `vashfindir.apps.bot`    | 8081 | всегда                           |
| admin  | `vashfindir.apps.admin`  | 8082 | `ADMIN_SECRET_KEY` в .env        |
| api    | `vashfindir.apps.api`    | 8083 | `API_TOKEN` или `LEAD_API_TOKEN` |
| worker | `vashfindir.apps.worker` | —    | `WORKER_ENABLED=true`            |

Nginx снаружи (`deploy/nginx-mybot.conf`): `/vashfindir` → bot, `/admin/` →
admin, `/api/` → api. Очередь фоновых задач — таблица `jobs` в общей БД:
кладут через `vashfindir/domain/jobs.py`, выполняет worker по реестру из
`vashfindir/apps/worker/handlers.py`. Точка роста: при втором хосте или росте
нагрузки — Postgres вместо SQLite и брокер очередей вместо таблицы `jobs`.

## Архитектурные правила (не превращаемся в кашу)

1. **Слои только вниз**:
   ```
   handlers → use_cases → domain → agents/knowledge/integrations → db/external API
   ```
   Обратных и поперечных импортов нет. `domain`, `db`, `agents`, `knowledge`,
   `integrations` не импортируют aiogram и fastapi — их можно тестировать
   без Telegram и без веб-сервера.

2. **Хэндлер — тонкий**: принять update, вызвать use case, ответить. Никакой
   логики, SQL и f-строк с бизнес-правилами в хэндлерах.

3. **Use case — сценарий**: один пользовательский сценарий = один use case.
   Он координирует domain-функции, агентов и интеграции, но не знает про aiogram.

4. **Модуль — mini-app**: `vashfindir/modules/<name>/` содержит handlers,
   use_cases, dto, keyboards, dialogs, states. Модуль регистрирует свой router
   в `vashfindir/apps/bot/handlers/__init__.py`.

5. **Тексты сообщений — отдельно от логики**: в `dialogs.py` модуля. В коде
   хэндлеров и use cases нет длинных литералов.

6. **Клавиатуры — только внутри модуля** (`keyboards.py`), собираются функциями-фабриками,
   callback_data — через `CallbackData`-фабрики aiogram, а не сырые строки.

7. **FSM-состояния — через `StatesGroup`**, по одной группе на диалог, рядом
   со сценарием. Никаких магических строк состояний.

8. **Конфиг — только через `vashfindir/core/config.py`**. Запрещены `os.environ`
   вне него и захардкоженные токены/ID. Секреты — в `.env` (в git не коммитим,
   шаблон — `.env.example`).

9. **БД — только через миграции Alembic**. Руками схему не правим; изменил
   модель — сгенерируй миграцию. Схема одна на все сервисы, применяет её
   `deploy/deploy.sh` до перезапуска. Сессия пробрасывается через middleware/
   фабрику, не создаётся в хэндлерах.

10. **Внешние API — только через адаптеры в `integrations/`**. Адаптер изолирует
    детали HTTP/Telegram от бизнес-логики. В use cases используем адаптер, а не
    `Bot` или `ClientSession` напрямую.

11. **Агенты — единый интерфейс**: `BaseAgent` / `AgentResult`. Регистрация через
    `AgentRegistry`, координация через `AgentOrchestrator`.

12. **База знаний — за абстракцией**: `KnowledgeStore`. Реализация может быть
    SQLite FTS, pgvector, Chroma и т.д. Агенты и use cases зависят от интерфейса,
    не от конкретной БД.

13. **Контракты между слоями — Pydantic DTO**. Не передаём словари и сырые
    `TelegramObject` вглубь архитектуры.

14. **DI — через явную сборку зависимостей в точках входа и middleware/Depends**.
    Зависимости создаём при старте и пробрасываем в `data` хэндлеров, не создаём
    внутри обработчиков. Общий service locator не используем.

15. **Логирование — `logging` (или loguru, если добавлен в зависимости),
    никаких `print`**. Логируем события, не токены и не персональные данные.

16. **Новый сервис — по образцу `vashfindir/apps/api/`**: пакет
    `vashfindir/apps/<name>/` с `__main__.py` (config → glitchtip → session
    factory → uvicorn/цикл), фабрика приложения, healthcheck для HTTP,
    systemd-юнит в `deploy/`, включение в `deploy.sh` по флагу в `.env`,
    строки в `.env.example`. Машинные endpoint'ы — только в
    `vashfindir/apps/api/`, не в админке.

## Стиль кода

- Типы обязательны: все публичные функции аннотированы, mypy проходит без ошибок.
- async везде, где I/O. Блокирующие вызовы (файлы, requests, тяжёлый CPU) —
  только через `asyncio.to_thread` / пул.
- Имена: хэндлеры `on_<событие>`, клавиатуры `<раздел>_kb()`, функции domain-слоя
  — глагол (`get_user`, `save_answer`), use cases — `<сценарий>_use_case` /
  `<Scenario>UseCase`. Русский язык — только в текстах для пользователя, в коде
  и комментариях — английский/русский по существу, но консистентно внутри модуля.
- Комментарии — только про «почему», не про «что». Закомментированный код не коммитим.
- Не добавляем зависимость, пока задачу нельзя решить стеком выше. Новая
  зависимость = запись в этом файле, если она меняет стек.

## Команды (используй их, не выдумывай свои)

```bash
uv sync                            # установить зависимости
uv run python -m vashfindir.apps.bot      # запустить бота (polling/webhook — по MODE из .env)
uv run python -m vashfindir.apps.admin    # запустить админку (нужен ADMIN_SECRET_KEY)
uv run python -m vashfindir.apps.api      # запустить API (нужен API_TOKEN/LEAD_API_TOKEN)
uv run python -m vashfindir.apps.worker   # запустить воркер (нужен WORKER_ENABLED=true)
uv run ruff check --fix .          # линт
uv run ruff format .               # форматирование
uv run mypy vashfindir/            # типы
uv run pytest                      # тесты
uv run alembic revision --autogenerate -m "..."   # миграция
uv run alembic upgrade head                       # применить миграции
```

Перед коммитом обязательны зелёные: `ruff check`, `ruff format --check`,
`mypy`, `pytest`. Не работает — чиним, а не обходим флагами.

## Тестирование

- Пишем тесты на `domain/`, `use_cases/`, `integrations/` и разбор callback_data —
  это ядро, которое ломается первым.
- Тесты на хэндлеры — через моки `Message`/`CallbackQuery`, без реального Telegram.
- Фикстуры БД — SQLite in-memory, через `pytest-asyncio`.
- Тест живёт в `tests/` и зеркалит путь модуля:
  - `vashfindir/domain/x.py` → `tests/domain/test_x.py`
  - `vashfindir/modules/y/use_cases.py` → `tests/modules/y/test_use_cases.py`
  - `vashfindir/apps/api/routes/z.py` → `tests/apps/api/test_z.py`

## Git

- Ветки: `feature/<краткое-имя>`, коммиты на русском или английском в
  повелительном наклонении, один коммит — одно осмысленное изменение.
- В `.gitignore`: `.env`, `*.db`, `__pycache__/`, `.venv/`, `.idea/`.
- Не коммитим: токены, реальные БД с пользователями, логи.

## Как развивать проект (рецепты)

**Добавить новый сценарий/модуль:**
1. `vashfindir/modules/<имя>/`:
   - `dialogs.py` — тексты и `StatesGroup`.
   - `keyboards.py` — клавиатуры.
   - `dto.py` — Pydantic-модели входа/выхода.
   - `use_cases.py` — сценарий.
   - `handlers.py` — роутеры.
2. Зарегистрировать router в `vashfindir/apps/bot/handlers/__init__.py`.
3. Если нужны данные — модель в `vashfindir/db/models.py` + миграция Alembic.
4. Если нужен внешний API — адаптер в `vashfindir/integrations/` + тест.
5. Тесты в `tests/modules/<имя>/`.

**Добавить новый сервис:**
1. Пакет `vashfindir/apps/<имя>/`: `__main__.py` (точка входа: config → glitchtip →
   session factory → uvicorn/цикл), фабрика приложения, `GET /healthz` если это HTTP.
2. Поля конфига в `vashfindir/core/config.py` + строки в `.env.example`.
3. `deploy/vf-materials-<имя>.service` + флаг включения в `deploy/deploy.sh`
   (рестарт по флагу в .env). Деплой сам ставит юнит, enable и sudoers.
4. Nginx-локация в `deploy/nginx-mybot.conf`, если сервис смотрит наружу —
   деплой сам применит конфиг (nginx -t + reload).
5. Тесты в `tests/apps/<имя>/`.

**Добавить ИИ-агента:**
1. Класс агента в `vashfindir/agents/concrete/<имя>.py`, наследник `BaseAgent`.
2. Зарегистрировать в `vashfindir/agents/registry.py`.
3. Вызвать из use case через `AgentOrchestrator` или напрямую.
4. Тест в `tests/agents/test_<имя>.py`.

**Добавить интеграцию с внешним сервисом:**
1. Адаптер в `vashfindir/integrations/<имя>.py` с единым интерфейсом.
2. Использовать в use case через DI, не создавать внутри хэндлера.
3. Тест в `tests/integrations/test_<имя>.py` с моком HTTP/Telegram.

**Добавить поле в БД:** изменить модель → `alembic revision --autogenerate` →
проверить сгенерированную миграцию глазами → `alembic upgrade head`.

**Новый секрет/настройка:** поле в `vashfindir/core/config.py` + строка в
`.env.example` (без значения). Никогда — реальное значение в репозиторий.

## Деплой и обновление (правила, не догадки)

1. **Код и инфраструктура деплоятся автоматически** при пуше в `master` через
   GitHub Actions и `deploy/deploy.sh` (исполняется от root). Деплой сам
   синхронизирует с репозиторием systemd-юниты (`deploy/*.service`), sudoers
   и nginx-конфиг (`deploy/nginx-mybot.conf`). Руками на сервере правим
   только `.env` (через `deploy/update-env.sh`); юниты/sudoers/nginx — только
   через репозиторий, иначе деплой перезапишет правки.
2. **`.env` не в репозитории** и не обновляется автодеплоем. Для обновления
   `.env` на сервере используем `deploy/update-env.sh`.
3. **Секреты не храним в GitHub Secrets** приложения. В GitHub Secrets только
   SSH-ключ для подключения к серверу. `BOT_TOKEN`, `WEBHOOK_SECRET` и прочее
   живут в `.env` на сервере.
4. **Перед продакшен-пушем** проверки должны быть зелёными: `ruff check`,
   `ruff format --check`, `mypy`, `pytest`.
5. **Миграции применяются автоматически** в `deploy/deploy.sh` — один раз, до
   перезапуска всех сервисов. Меняешь модель — генерируешь миграцию локально
   и коммитишь её. Автодеплой поднимает сервисы по флагам в `.env` сервера
   (`ADMIN_SECRET_KEY`, `API_TOKEN`/`LEAD_API_TOKEN`, `WORKER_ENABLED`).
   Новый сервис = юнит в `deploy/` + флаг в `deploy.sh` + (при публичном
   пути) локация в `deploy/nginx-mybot.conf` — ручных шагов на сервере нет.
   `deploy/setup-server.sh` — только первичная настройка чистого сервера.

## Антипаттерны (запрещено)

- Хэндлеры-простыни со всей логикой внутри.
- Один `handlers.py` на весь бот.
- SQL в хэндлерах; создание engine/session в хэндлерах.
- `callback_data="btn_1"` строками без фабрик; parse callback через `split`.
- Глобальные переменные для состояния пользователя (только FSM/БД).
- `except Exception: pass`, отключённые проверки ruff/mypy без причины в коде.
- Бот, который падает от одного плохого update: каждый роутер отвечает за
  свои ошибки, общий error handler обязателен.
- Прямое использование `Bot`, `ClientSession`, векторной БД внутри use cases
  или domain — только через адаптеры/абстракции.
