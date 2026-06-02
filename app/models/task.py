from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Task(Base):
    """Задача является центральной сущностью: через нее связываются исполнитель, комментарии, инциденты и аудит."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status_id: Mapped[int] = mapped_column(ForeignKey("task_statuses.id"), nullable=False)
    priority_id: Mapped[int] = mapped_column(ForeignKey("task_priorities.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    creator = relationship("User", foreign_keys=[creator_id], back_populates="created_tasks")
    assignee = relationship("User", foreign_keys=[assignee_id], back_populates="assigned_tasks")
    status = relationship("TaskStatus", back_populates="tasks")
    priority = relationship("TaskPriority", back_populates="tasks")
    comments = relationship("TaskComment", back_populates="task", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="task", cascade="all, delete-orphan")
    monitoring_events = relationship("MonitoringEvent", back_populates="task")
    external_links = relationship("ExternalLink", back_populates="task", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="task")
