from app.models import AuditLog, Task, TaskComment, TaskStatus
from tests.conftest import auth_header_for, create_task


def test_admin_can_create_task_through_api(client, db_session):
    headers = auth_header_for(db_session, "admin@example.com")
    worker = db_session.query(Task).first()
    assignee = db_session.query(Task).first()
    worker_id = db_session.execute("SELECT id FROM users WHERE email = 'worker@example.com'").scalar_one()

    response = client.post(
        "/api/v1/tasks",
        headers=headers,
        json={
            "title": "API task",
            "description": "Created from API test",
            "assignee_id": worker_id,
            "status_code": "new",
            "priority_code": "medium",
        },
    )

    assert response.status_code == 201
    assert response.json()["title"] == "API task"
    assert db_session.query(Task).filter(Task.title == "API task").count() == 1
    assert db_session.query(AuditLog).filter(AuditLog.action == "create_task").count() == 1


def test_worker_cannot_create_task_through_api(client, db_session):
    headers = auth_header_for(db_session, "worker@example.com")

    response = client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"title": "Forbidden", "status_code": "new", "priority_code": "medium"},
    )

    assert response.status_code == 403


def test_worker_can_change_own_task_status(client, db_session):
    task = create_task(db_session, title="Own task", assignee_email="worker@example.com")
    headers = auth_header_for(db_session, "worker@example.com")

    response = client.patch(f"/api/v1/tasks/{task.id}/status?status_code=in_progress", headers=headers)

    assert response.status_code == 200
    db_session.expire_all()
    updated = db_session.get(Task, task.id)
    status_obj = db_session.get(TaskStatus, updated.status_id)
    assert status_obj.code == "in_progress"
    assert db_session.query(AuditLog).filter(AuditLog.action == "update_task_status").count() == 1


def test_worker_cannot_read_foreign_task_through_api(client, db_session):
    task = create_task(db_session, title="Foreign task", assignee_email="other.worker@example.com")
    headers = auth_header_for(db_session, "worker@example.com")

    response = client.get(f"/api/v1/tasks/{task.id}", headers=headers)

    assert response.status_code == 403


def test_add_comment_creates_comment_and_audit_log(client, db_session):
    task = create_task(db_session, title="Commented task", assignee_email="worker@example.com")
    headers = auth_header_for(db_session, "worker@example.com")

    response = client.post(f"/api/v1/tasks/{task.id}/comments", headers=headers, json={"text": "API comment"})

    assert response.status_code == 201
    assert db_session.query(TaskComment).filter(TaskComment.text == "API comment").count() == 1
    assert db_session.query(AuditLog).filter(AuditLog.action == "create_task_comment").count() == 1
