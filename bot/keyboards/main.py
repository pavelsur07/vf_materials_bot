from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class MenuCb(CallbackData, prefix="menu"):
    section: str


SECTIONS: dict[str, str] = {
    "materials": "Материалы",
    "consultation": "Консультация",
    "about": "О боте",
}


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for section, title in SECTIONS.items():
        builder.button(text=title, callback_data=MenuCb(section=section))
    builder.adjust(1)
    return builder.as_markup()
