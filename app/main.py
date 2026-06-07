from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
)

# Подключены базовые маршруты: проверка запуска и первичная авторизация.
app.include_router(health_router)
app.include_router(auth_router)
