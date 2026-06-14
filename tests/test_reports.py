from tests.conftest import create_task, login_as


def test_tasks_csv_requires_manager_or_admin(client, db_session):
    create_task(db_session, title="Report task", assignee_email="worker@example.com")

    login_as(client, "worker@example.com")
    worker_response = client.get("/reports/tasks.csv")

    client.cookies.clear()
    login_as(client, "manager@example.com")
    manager_response = client.get("/reports/tasks.csv")

    client.cookies.clear()
    login_as(client, "admin@example.com")
    admin_response = client.get("/reports/tasks.csv")

    assert worker_response.status_code == 403
    assert manager_response.status_code == 200
    assert admin_response.status_code == 200
    assert "text/csv" in admin_response.headers["content-type"]
    assert "Report task" in admin_response.text


def test_incidents_csv_requires_manager_or_admin(client):
    login_as(client, "worker@example.com")
    worker_response = client.get("/reports/incidents.csv")

    client.cookies.clear()
    login_as(client, "manager@example.com")
    manager_response = client.get("/reports/incidents.csv")

    assert worker_response.status_code == 403
    assert manager_response.status_code == 200
    assert "text/csv" in manager_response.headers["content-type"]
    assert "external_event_id" in manager_response.text
