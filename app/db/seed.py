from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.integration_setting import IntegrationSetting
from app.models.role import Role
from app.models.task_priority import TaskPriority
from app.models.task_status import TaskStatus
from app.models.user import User


ROLES = [
    {"code": "admin", "name": "Администратор", "description": "Полный доступ к настройкам системы"},
    {"code": "manager", "name": "Руководитель", "description": "Создание и распределение задач"},
    {"code": "worker", "name": "Исполнитель", "description": "Работа с назначенными задачами"},
]

STATUSES = [
    {"code": "new", "name": "Новая", "sort_order": 10, "is_final": False},
    {"code": "in_progress", "name": "В работе", "sort_order": 20, "is_final": False},
    {"code": "done", "name": "Завершена", "sort_order": 30, "is_final": True},
    {"code": "cancelled", "name": "Отменена", "sort_order": 40, "is_final": True},
]

PRIORITIES = [
    {"code": "low", "name": "Низкий", "sort_order": 10},
    {"code": "medium", "name": "Средний", "sort_order": 20},
    {"code": "high", "name": "Высокий", "sort_order": 30},
    {"code": "critical", "name": "Критический", "sort_order": 40},
]

INTEGRATIONS = [
    {"system": "zabbix", "is_enabled": False, "config": {"description": "Обработка webhook-событий мониторинга"}},
    {"system": "rocketchat", "is_enabled": False, "config": {"description": "Отправка уведомлений"}},
    {"system": "passbolt", "is_enabled": False, "config": {"description": "Ссылки на секреты без хранения секретов в системе"}},
    {"system": "minio", "is_enabled": False, "config": {"description": "Хранение файловых вложений"}},
]


def get_or_create(db: Session, model, lookup: dict, values: dict | None = None):
    """Запись создается только при отсутствии, чтобы seed можно было запускать повторно."""
    instance = db.query(model).filter_by(**lookup).first()
    if instance:
        return instance

    instance = model(**lookup, **(values or {}))
    db.add(instance)
    db.flush()
    return instance


def seed_roles(db: Session) -> None:
    for item in ROLES:
        get_or_create(db, Role, {"code": item["code"]}, {"name": item["name"], "description": item["description"], "is_system": True})


def seed_statuses(db: Session) -> None:
    for item in STATUSES:
        get_or_create(
            db,
            TaskStatus,
            {"code": item["code"]},
            {"name": item["name"], "sort_order": item["sort_order"], "is_final": item["is_final"], "is_system": True},
        )


def seed_priorities(db: Session) -> None:
    for item in PRIORITIES:
        get_or_create(
            db,
            TaskPriority,
            {"code": item["code"]},
            {"name": item["name"], "sort_order": item["sort_order"], "is_system": True},
        )


def seed_integrations(db: Session) -> None:
    for item in INTEGRATIONS:
        get_or_create(
            db,
            IntegrationSetting,
            {"system": item["system"]},
            {"is_enabled": item["is_enabled"], "config": item["config"]},
        )


def seed_users(db: Session) -> None:
    admin_role = db.query(Role).filter_by(code="admin").one()
    manager_role = db.query(Role).filter_by(code="manager").one()
    worker_role = db.query(Role).filter_by(code="worker").one()

    # Пароли будут нормально хешироваться на этапе авторизации. Сейчас фиксируется только стартовая структура данных.
    get_or_create(
        db,
        User,
        {"email": "admin@example.com"},
        {"full_name": "Администратор системы", "hashed_password": "temporary-admin-password-hash", "role_id": admin_role.id, "is_active": True},
    )
    get_or_create(
        db,
        User,
        {"email": "manager@example.com"},
        {"full_name": "Руководитель ИТ-подразделения", "hashed_password": "temporary-manager-password-hash", "role_id": manager_role.id, "is_active": True},
    )
    get_or_create(
        db,
        User,
        {"email": "worker@example.com"},
        {"full_name": "Исполнитель ИТ-подразделения", "hashed_password": "temporary-worker-password-hash", "role_id": worker_role.id, "is_active": True},
    )


def run_seed() -> None:
    db = SessionLocal()
    try:
        seed_roles(db)
        seed_statuses(db)
        seed_priorities(db)
        seed_integrations(db)
        seed_users(db)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
    print("Начальные данные добавлены")
