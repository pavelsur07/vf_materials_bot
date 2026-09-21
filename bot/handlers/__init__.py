from aiogram import Router

from bot.handlers import errors, start


def get_routers() -> list[Router]:
    return [start.router, errors.router]
