from aiogram import Router

from bot.handlers import errors
from bot.modules import onboarding


def get_routers() -> list[Router]:
    return [onboarding.router, errors.router]
