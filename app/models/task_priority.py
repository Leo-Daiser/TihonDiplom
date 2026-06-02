from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TaskPriority(Base):
    """Приоритет вынесен в справочник, чтобы правила обработки инцидентов можно было менять отдельно."""

    __tablename__ = "task_priorities"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    tasks = relationship("Task", back_populates="priority")
