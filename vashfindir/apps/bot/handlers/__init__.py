from aiogram import Router

from vashfindir.apps.bot.handlers import errors, start
from vashfindir.modules import onboarding
from vashfindir.modules.attribution import handlers as attribution


def get_routers() -> list[Router]:
    return [start.router, attribution.router, onboarding.router, errors.router]
