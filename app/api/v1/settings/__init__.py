from fastapi import APIRouter
from app.api.v1.settings.custom_fields import router as custom_fields_router
from app.api.v1.settings.pipelines import router as pipelines_router
from app.api.v1.settings.handbooks import router as handbooks_router
from app.api.v1.settings.templates import router as templates_router
from app.api.v1.settings.branches import router as branches_router
from app.api.v1.settings.staff_roles import router as staff_roles_router
from app.api.v1.settings.presets import router as presets_router

settings_router = APIRouter()

settings_router.include_router(custom_fields_router)
settings_router.include_router(pipelines_router)
settings_router.include_router(handbooks_router)
settings_router.include_router(templates_router)
settings_router.include_router(branches_router)
settings_router.include_router(staff_roles_router)
settings_router.include_router(presets_router)

__all__ = ["settings_router"]
