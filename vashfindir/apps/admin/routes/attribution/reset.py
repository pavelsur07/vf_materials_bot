from fastapi import APIRouter, Request
from starlette.responses import RedirectResponse, Response

from vashfindir.apps.admin.auth import verify_csrf
from vashfindir.apps.admin.routes.attribution.access import PREFIX, Actor, Database, config, render
from vashfindir.domain.attribution.reset import ResetError, reset_test_user, test_accounts
from vashfindir.domain.attribution.settings import get_preferences

router = APIRouter()


async def _page(
    request: Request,
    session: Database,
    *,
    status_code: int = 200,
    error: str | None = None,
) -> Response:
    prefs = await get_preferences(session, config(request).attribution_bootstrap_admin_tg_ids)
    return render(
        request,
        "test_users",
        status_code=status_code,
        error=error,
        ids=prefs.test_ids,
        accounts=await test_accounts(session, prefs.test_ids),
        result=request.query_params.get("result"),
    )


@router.get("/test-users")
async def users_page(request: Request, session: Database, _: Actor) -> Response:
    return await _page(request, session)


@router.post("/test-users/{tg_id:int}/reset")
async def reset(request: Request, session: Database, actor: Actor, tg_id: int) -> Response:
    await verify_csrf(request)
    try:
        count = await reset_test_user(
            session,
            tg_id,
            config(request).attribution_bootstrap_admin_tg_ids,
            actor=actor,
        )
    except ResetError as exc:
        await session.rollback()
        return await _page(request, session, status_code=409, error=str(exc))
    await session.commit()
    return RedirectResponse(
        f"{PREFIX}/test-users?result={'absent' if count is None else 'reset'}",
        303,
    )
