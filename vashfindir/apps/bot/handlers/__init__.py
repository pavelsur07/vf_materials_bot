from aiogram import Router

from vashfindir.apps.bot.handlers import errors
from vashfindir.modules import onboarding


def get_routers() -> list[Router]:
    return [onboarding.router, errors.router]
