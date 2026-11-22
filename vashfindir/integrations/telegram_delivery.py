import asyncio
from pathlib import Path
from typing import Literal

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import FSInputFile
from pydantic import BaseModel

from vashfindir.domain.attribution.dto import MagnetContent


class DeliveryResult(BaseModel):
    status: Literal["sent", "blocked", "file_error", "telegram_error"]
    reason: str | None = None


class TelegramDelivery:
    def __init__(self, bot: Bot, root: str) -> None:
        self._bot = bot
        self._root = Path(root)

    def _resolve_document(self, value: str) -> str | FSInputFile:
        if not value.startswith("file:") and "/" not in value:
            return value
        base = self._root.resolve()
        path = (base / value.removeprefix("file:")).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            raise FileNotFoundError
        return FSInputFile(path)

    async def send_magnet(self, chat_id: int, magnet: MagnetContent) -> DeliveryResult:
        try:
            if magnet.content_type == "file":
                document = await asyncio.to_thread(self._resolve_document, magnet.file_ref or "")
                if magnet.message:
                    await self._bot.send_message(chat_id, magnet.message, parse_mode=None)
                await self._bot.send_document(chat_id, document, parse_mode=None)
            elif magnet.content_type == "link":
                if magnet.message:
                    await self._bot.send_message(chat_id, magnet.message, parse_mode=None)
                await self._bot.send_message(chat_id, magnet.url or "", parse_mode=None)
            else:
                await self._bot.send_message(chat_id, magnet.message, parse_mode=None)
        except TelegramForbiddenError as exc:
            if "bot was blocked" in str(exc).lower():
                return DeliveryResult(status="blocked")
            return DeliveryResult(status="telegram_error")
        except OSError:
            return DeliveryResult(status="file_error", reason="Локальный файл недоступен.")
        except TelegramAPIError:
            if magnet.content_type == "file":
                return DeliveryResult(
                    status="file_error", reason="Telegram отклонил отправку файла."
                )
            return DeliveryResult(status="telegram_error")
        return DeliveryResult(status="sent")

    async def bot_username(self) -> str | None:
        try:
            return (await self._bot.get_me()).username
        except TelegramAPIError:
            return None

    async def notify(self, chat_id: int, message: str) -> bool:
        try:
            await self._bot.send_message(chat_id, message, parse_mode=None)
        except TelegramAPIError:
            return False
        return True
