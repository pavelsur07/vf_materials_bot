from fastapi import APIRouter

from vashfindir.apps.admin.routes.attribution import (
    access,
    catalog,
    exports,
    links,
    reset,
    settings,
    touches,
)

router = APIRouter()
for section in (access, catalog, links, touches, exports, settings, reset):
    router.include_router(section.router, prefix=access.PREFIX)
