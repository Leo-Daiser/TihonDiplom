from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IntegrationSetting(Base):
    """Настройки интеграций хранятся отдельно, секреты в явном виде в эту таблицу не закладываются."""

    __tablename__ = "integration_settings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    system: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
