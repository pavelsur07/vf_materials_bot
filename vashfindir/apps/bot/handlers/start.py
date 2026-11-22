from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.domain.attribution.dto import StartRequest
from vashfindir.domain.attribution.touches import finish_delivery
from vashfindir.modules.attribution.handlers import send_selected, show_catalogue
from vashfindir.modules.attribution.keyboards import catalog_button
from vashfindir.modules.attribution.use_cases import AttributionUseCase
from vashfindir.modules.onboarding.handlers import on_start as legacy_start
from vashfindir.modules.onboarding.use_cases import OnboardingUseCase

router = Router(name="start")


@router.message(CommandStart())
async def on_start(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    use_case: OnboardingUseCase,
    attribution: AttributionUseCase,
) -> None:
    user = message.from_user
    if user is None:
        return
    if not attribution.settings.attribution_enabled:
        await legacy_start(message, session, use_case)
        return

    touch = await attribution.register(
        session,
        StartRequest(
            tg_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            payload=command.args,
        ),
    )
    if touch.magnet is not None:
        await send_selected(message, user.id, touch.touch_id, touch.magnet, session, attribution)
    elif touch.code_status == "direct":
        catalogue = await attribution.catalogue(session)
        button = catalog_button(touch.touch_id) if catalogue.magnets else None
        await legacy_start(message, session, use_case, catalogue_button=button)
        await finish_delivery(session, user.id, touch.touch_id)
    else:
        await show_catalogue(message, user.id, touch, session, attribution)
