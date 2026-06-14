from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.attachments import router as attachments_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.dictionaries import router as dictionaries_router
from app.api.health import router as health_router
from app.api.integrations import router as integrations_router
from app.api.notifications import router as notifications_router
from app.api.tasks import router as tasks_router
from app.api.users import router as users_router
from app.core.config import get_settings
from app.web.admin_user_pages import router as admin_user_pages_router
from app.web.integration_pages import router as integration_pages_router
from app.web.pages import router as pages_router
from app.web.task_pages import router as task_pages_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
)

# Статика подключена отдельно, чтобы шаблоны не зависели от внешних CDN.
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Более специализированные web-роуты подключаются раньше общего pages_router.
app.include_router(task_pages_router)
app.include_router(admin_user_pages_router)
app.include_router(pages_router)
app.include_router(integration_pages_router)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(tasks_router)
app.include_router(attachments_router)
app.include_router(users_router)
app.include_router(dictionaries_router)
app.include_router(audit_router)
app.include_router(integrations_router)
app.include_router(notifications_router)
