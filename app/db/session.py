from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

settings = get_settings()

# Движок SQLAlchemy создается один раз на старте приложения.
engine = create_engine(settings.database_url, pool_pre_ping=True)

# Фабрика сессий используется в API-зависимостях и сервисах.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Сессия базы данных создается на время одного запроса и закрывается после обработки."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
