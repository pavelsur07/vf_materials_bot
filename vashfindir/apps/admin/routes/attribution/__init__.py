from fastapi import APIRouter

from vashfindir.apps.admin.routes.attribution import access, catalog, links, settings, touches

router = APIRouter()
for section in (access, catalog, links, touches, settings):
    router.include_router(section.router, prefix=access.PREFIX)
