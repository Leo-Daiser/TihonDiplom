from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Простейшая проверка, что приложение запущено и отвечает на HTTP-запросы."""
    return {"status": "ok"}
