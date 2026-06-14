import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_DEBUG", "false")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://tihon_test:tihon_test@localhost:55432/tihon_diplom_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")
os.environ.setdefault("ZABBIX_WEBHOOK_TOKEN", "test-zabbix-token")
os.environ.setdefault("ROCKETCHAT_ENABLED", "false")
os.environ.setdefault("ROCKETCHAT_WEBHOOK_URL", "")
os.environ.setdefault("MINIO_ENDPOINT", "minio:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "local-access-key")
os.environ.setdefault("MINIO_SECRET_KEY", "local-secret-key")
os.environ.setdefault("MINIO_BUCKET", "task-attachments-test")
os.environ.setdefault("MINIO_SECURE", "false")

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Attachment, Role, Task, TaskComment, TaskPriority, TaskStatus, User  # noqa: E402,F401

PASSWORD = "password123"


def seed_reference_data() -> None:
    db = SessionLocal()
    try:
        roles = [
            Role(code="admin", name="Администратор", description="Полный доступ"),
            Role(code="manager", name="Руководитель", description="Управление задачами"),
            Role(code="worker", name="Исполнитель", description="Работа со своими задачами"),
        ]
        statuses = [
            TaskStatus(code="new", name="Новая", sort_order=10),
            TaskStatus(code="in_progress", name="В работе", sort_order=20),
            TaskStatus(code="done", name="Завершена", sort_order=30, is_final=True),
        ]
        priorities = [
            TaskPriority(code="low", name="Низкий", sort_order=10),
            TaskPriority(code="medium", name="Средний", sort_order=20),
            TaskPriority(code="high", name="Высокий", sort_order=30),
            TaskPriority(code="critical", name="Критический", sort_order=40),
        ]
        db.add_all(roles + statuses + priorities)
        db.flush()
        role_by_code = {role.code: role for role in roles}
        db.add_all(
            [
                User(email="admin@example.com", full_name="Admin User", hashed_password=hash_password(PASSWORD), role_id=role_by_code["admin"].id),
                User(email="manager@example.com", full_name="Manager User", hashed_password=hash_password(PASSWORD), role_id=role_by_code["manager"].id),
                User(email="worker@example.com", full_name="Worker User", hashed_password=hash_password(PASSWORD), role_id=role_by_code["worker"].id),
                User(email="other.worker@example.com", full_name="Other Worker", hashed_password=hash_password(PASSWORD), role_id=role_by_code["worker"].id),
            ]
        )
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def reset_database() -> Iterator[None]:
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        seed_reference_data()
    except OperationalError as exc:
        pytest.skip(f"test PostgreSQL database is not available: {exc}")
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(reset_database):
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(reset_database) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def login_as(client: TestClient, email: str, password: str = PASSWORD) -> None:
    response = client.post("/login", data={"email": email, "password": password}, follow_redirects=False)
    assert response.status_code == 303


def auth_header_for(db_session, email: str) -> dict[str, str]:
    user = db_session.query(User).filter(User.email == email).one()
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


def create_task(db_session, *, title: str = "Test task", assignee_email: str = "worker@example.com") -> Task:
    creator = db_session.query(User).filter(User.email == "admin@example.com").one()
    assignee = db_session.query(User).filter(User.email == assignee_email).one()
    status = db_session.query(TaskStatus).filter(TaskStatus.code == "new").one()
    priority = db_session.query(TaskPriority).filter(TaskPriority.code == "medium").one()
    task = Task(
        title=title,
        description="Task description",
        creator_id=creator.id,
        assignee_id=assignee.id,
        status_id=status.id,
        priority_id=priority.id,
        source_type="manual",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def add_comment(db_session, *, task: Task, author_email: str = "worker@example.com", text: str = "Test comment") -> TaskComment:
    author = db_session.query(User).filter(User.email == author_email).one()
    comment = TaskComment(task_id=task.id, author_id=author.id, text=text)
    db_session.add(comment)
    db_session.commit()
    db_session.refresh(comment)
    return comment


def add_attachment(db_session, *, task: Task, uploaded_by_email: str = "worker@example.com") -> Attachment:
    uploader = db_session.query(User).filter(User.email == uploaded_by_email).one()
    attachment = Attachment(
        task_id=task.id,
        uploaded_by_id=uploader.id,
        file_name="evidence.txt",
        object_key=f"test/{task.id}/evidence.txt",
        content_type="text/plain",
        size_bytes=12,
    )
    db_session.add(attachment)
    db_session.commit()
    db_session.refresh(attachment)
    return attachment
