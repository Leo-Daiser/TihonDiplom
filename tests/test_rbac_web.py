from app.models import User
from tests.conftest import add_attachment, add_comment, create_task, login_as


def test_worker_does_not_see_new_task_action_on_dashboard(client):
    login_as(client, "worker@example.com")

    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/tasks/new"' not in response.text
    assert "Новая задача" not in response.text


def test_worker_does_not_see_new_task_action_on_tasks_page(client):
    login_as(client, "worker@example.com")

    response = client.get("/tasks")

    assert response.status_code == 200
    assert 'href="/tasks/new"' not in response.text
    assert "Новая задача" not in response.text


def test_admin_sees_new_task_action(client):
    login_as(client, "admin@example.com")

    dashboard = client.get("/")
    tasks = client.get("/tasks")

    assert dashboard.status_code == 200
    assert tasks.status_code == 200
    assert 'href="/tasks/new"' in dashboard.text
    assert 'href="/tasks/new"' in tasks.text


def test_worker_cannot_open_new_task_page(client):
    login_as(client, "worker@example.com")

    response = client.get("/tasks/new")

    assert response.status_code == 403


def test_admin_users_page_requires_admin_role(client):
    login_as(client, "manager@example.com")
    manager_response = client.get("/admin/users")

    client.cookies.clear()
    login_as(client, "worker@example.com")
    worker_response = client.get("/admin/users")

    client.cookies.clear()
    login_as(client, "admin@example.com")
    admin_response = client.get("/admin/users")

    assert manager_response.status_code == 403
    assert worker_response.status_code == 403
    assert admin_response.status_code == 200
    assert "Пользователи" in admin_response.text


def test_worker_cannot_open_foreign_task(client, db_session):
    task = create_task(db_session, title="Foreign task", assignee_email="other.worker@example.com")
    login_as(client, "worker@example.com")

    response = client.get(f"/tasks/{task.id}")

    assert response.status_code == 403


def test_worker_cannot_download_foreign_task_attachment(client, db_session):
    task = create_task(db_session, title="Foreign task", assignee_email="other.worker@example.com")
    attachment = add_attachment(db_session, task=task, uploaded_by_email="other.worker@example.com")
    login_as(client, "worker@example.com")

    response = client.get(f"/api/v1/attachments/{attachment.id}/open")

    assert response.status_code == 403


def test_comment_author_name_is_rendered(client, db_session):
    task = create_task(db_session, title="Task with comments", assignee_email="worker@example.com")
    add_comment(db_session, task=task, author_email="worker@example.com", text="Visible comment")
    login_as(client, "worker@example.com")

    response = client.get(f"/tasks/{task.id}")

    assert response.status_code == 200
    assert "Worker User" in response.text
    assert "Visible comment" in response.text
    assert "Пользователь #" not in response.text


def test_inactive_user_cannot_log_in(client, db_session):
    user = db_session.query(User).filter(User.email == "worker@example.com").one()
    user.is_active = False
    db_session.commit()

    response = client.post("/login", data={"email": "worker@example.com", "password": "password123"}, follow_redirects=False)

    assert response.status_code == 400
