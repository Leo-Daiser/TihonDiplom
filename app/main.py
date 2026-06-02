from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
)

# На первом этапе подключен только health endpoint. Бизнес-модули будут добавляться отдельно.
app.include_router(health_router)
