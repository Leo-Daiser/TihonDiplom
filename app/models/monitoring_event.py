from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MonitoringEvent(Base):
    """Событие мониторинга хранит исходный факт, из которого может быть создана задача-инцидент."""

    __tablename__ = "monitoring_events"
    __table_args__ = (UniqueConstraint("source_system", "external_event_id", name="uq_monitoring_event_source_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    source_system: Mapped[str] = mapped_column(String(100), default="zabbix", nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trigger_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="received", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    task = relationship("Task", back_populates="monitoring_events")
