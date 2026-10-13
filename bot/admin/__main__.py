import logging

import uvicorn

from bot.admin.app import create_admin_app
from bot.core.config import get_settings
from bot.core.glitchtip import init_glitchtip
from bot.db.session import create_session_factory


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    init_glitchtip(settings)
    if not settings.admin_secret_key or not settings.admin_password_hash:
        raise SystemExit(
            "ADMIN_SECRET_KEY и ADMIN_PASSWORD_HASH должны быть заданы в .env. "
            "Хэш пароля: uv run python -m bot.admin.hashpw"
        )
    app = create_admin_app(settings, create_session_factory())
    uvicorn.run(app, host=settings.admin_host, port=settings.admin_port)


if __name__ == "__main__":
    main()
