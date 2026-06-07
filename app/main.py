from fastapi import FastAPI

from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.dictionaries import router as dictionaries_router
from app.api.health import router as health_router
from app.api.integrations import router as integrations_router
from app.api.tasks import router as tasks_router
from app.api.users import router as users_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
)

# Подключены основные API-модули: авторизация, задачи, администрирование, аудит и интеграции.
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(tasks_router)
app.include_router(users_router)
app.include_router(dictionaries_router)
app.include_router(audit_router)
app.include_router(integrations_router)
