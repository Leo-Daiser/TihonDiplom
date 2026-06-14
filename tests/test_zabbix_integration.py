from app.models import MonitoringEvent, Notification, Task


ZABBIX_AUTH = {"Authorization": "Bearer test-zabbix-token"}


def test_zabbix_payload_with_extra_fields_creates_task_and_notification(client, db_session):
    response = client.post(
        "/api/v1/integrations/zabbix/webhook",
        headers=ZABBIX_AUTH,
        json={
            "EVENT.ID": "zbx-extra-001",
            "HOST.NAME": "server-01",
            "TRIGGER.NAME": "CPU load is too high",
            "TRIGGER.SEVERITY": "High",
            "ALERT.SUBJECT": "Problem: CPU load is too high",
            "ALERT.MESSAGE": "CPU load on server-01 exceeded threshold",
            "extra_field": "must be stored but ignored by business logic",
            "extra_object": {"nested": True},
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "created"
    assert db_session.query(Task).filter(Task.source_type == "zabbix").count() == 1
    event = db_session.query(MonitoringEvent).one()
    assert event.external_event_id == "zbx-extra-001"
    assert event.host == "server-01"
    assert event.trigger_name == "CPU load is too high"
    assert event.payload["extra_field"] == "must be stored but ignored by business logic"
    notification = db_session.query(Notification).one()
    assert notification.channel == "rocketchat"
    assert notification.status == "skipped"


def test_zabbix_duplicate_event_does_not_create_second_task(client, db_session):
    payload = {
        "event_id": "zbx-duplicate-001",
        "host": "server-02",
        "trigger": "Disk space is low",
        "severity": "warning",
    }

    first = client.post("/api/v1/integrations/zabbix/webhook", headers=ZABBIX_AUTH, json=payload)
    second = client.post("/api/v1/integrations/zabbix/webhook", headers=ZABBIX_AUTH, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "created"
    assert second.json()["status"] == "duplicate"
    assert second.json()["duplicate"] is True
    assert db_session.query(Task).filter(Task.source_type == "zabbix").count() == 1
    assert db_session.query(MonitoringEvent).count() == 1


def test_zabbix_webhook_requires_bearer_token(client):
    response = client.post(
        "/api/v1/integrations/zabbix/webhook",
        json={"event_id": "zbx-no-auth", "host": "server-03", "trigger": "No auth"},
    )

    assert response.status_code == 401


def test_zabbix_payload_without_event_id_generates_stable_event_id(client, db_session):
    payload = {
        "host": "server-04",
        "trigger": "Memory usage is high",
        "severity": "average",
        "message": "Memory usage exceeded threshold",
        "timestamp": "2026-06-14 12:00:00",
    }

    first = client.post("/api/v1/integrations/zabbix/webhook", headers=ZABBIX_AUTH, json=payload)
    second = client.post("/api/v1/integrations/zabbix/webhook", headers=ZABBIX_AUTH, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "created"
    assert second.json()["status"] == "duplicate"
    event = db_session.query(MonitoringEvent).one()
    assert event.external_event_id.startswith("generated-")
