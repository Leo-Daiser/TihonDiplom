from sqlalchemy.orm import Session

from app.core.security import hash_password
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

DEMO_USERS = [
    {"email": "admin@example.com", "full_name": "Администратор системы", "password": "admin12345", "role": "admin"},
    {"email": "manager@example.com", "full_name": "Руководитель ИТ-подразделения", "password": "manager12345", "role": "manager"},
    {"email": "worker@example.com", "full_name": "Исполнитель ИТ-подразделения", "password": "worker12345", "role": "worker"},
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
    roles_by_code = {role.code: role for role in db.query(Role).all()}

    for item in DEMO_USERS:
        role = roles_by_code[item["role"]]
        user = get_or_create(
            db,
            User,
            {"email": item["email"]},
            {
                "full_name": item["full_name"],
                "hashed_password": hash_password(item["password"]),
                "role_id": role.id,
                "is_active": True,
            },
        )

        # Для демонстрационной базы пароль обновляется повторным запуском seed, чтобы не зависеть от старых временных хешей.
        user.full_name = item["full_name"]
        user.role_id = role.id
        user.is_active = True
        user.hashed_password = hash_password(item["password"])


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
