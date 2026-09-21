from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.dialogs.start import SECTION_STUB, WELCOME
from bot.keyboards.main import MenuCb, main_menu_kb
from bot.services.users import get_or_create_user

router = Router(name="start")


@router.message(CommandStart())
async def on_start(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    await get_or_create_user(
        session,
        tg_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    await message.answer(WELCOME, reply_markup=main_menu_kb())


@router.callback_query(MenuCb.filter())
async def on_menu_section(callback: CallbackQuery, callback_data: MenuCb) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(SECTION_STUB.format(section=callback_data.section))
