# Интеграции внешних систем

## Zabbix

Система принимает события мониторинга через production endpoint:

```http
POST /api/v1/integrations/zabbix/webhook
Authorization: Bearer <ZABBIX_WEBHOOK_TOKEN>
Content-Type: application/json
```

Zabbix webhook media type позволяет формировать параметры и выполнять JavaScript-сценарий отправки HTTP-запроса во внешнюю систему. Поэтому endpoint принимает гибкий JSON-контракт и не зависит от строго фиксированного набора полей.

Минимально полезные поля:

```json
{
  "event_id": "{EVENT.ID}",
  "host": "{HOST.NAME}",
  "trigger": "{TRIGGER.NAME}",
  "severity": "{TRIGGER.SEVERITY}",
  "subject": "{ALERT.SUBJECT}",
  "message": "{ALERT.MESSAGE}"
}
```

Поддерживаются альтернативные имена ключей:

| Нормализованное поле | Допустимые варианты |
|---|---|
| event_id | event_id, eventid, event.id, eventId, EVENT.ID |
| host | host, host_name, hostname, host.name, HOST.NAME |
| trigger | trigger, trigger_name, trigger.description, TRIGGER.NAME, ALERT.SUBJECT |
| severity | severity, event_severity, trigger_severity, event.severity, TRIGGER.SEVERITY |
| subject | subject, alert_subject, ALERT.SUBJECT |
| message | message, alert_message, ALERT.MESSAGE |
| timestamp | timestamp, event_time, event.clock, EVENT.TIME |

Лишние поля не ломают обработку. Полный исходный payload сохраняется в `monitoring_events.payload`.

Если `event_id` не передан, система формирует стабильный служебный идентификатор по основным полям события. Это защищает webhook от падения при нестандартной настройке Zabbix и сохраняет возможность дедупликации.

Пример JavaScript-сценария для Zabbix media type:

```javascript
var params = JSON.parse(value);

var req = new HttpRequest();
req.addHeader('Content-Type: application/json');
req.addHeader('Authorization: Bearer ' + params.token);

var payload = {
    event_id: params.event_id,
    host: params.host,
    trigger: params.trigger,
    severity: params.severity,
    subject: params.subject,
    message: params.message
};

var response = req.post(params.url, JSON.stringify(payload));

if (req.getStatus() < 200 || req.getStatus() >= 300) {
    throw 'IT Workflow webhook failed with status ' + req.getStatus() + ': ' + response;
}

return response;
```

Параметры media type в Zabbix:

```text
url      = http://<server>:8000/api/v1/integrations/zabbix/webhook
token    = <ZABBIX_WEBHOOK_TOKEN>
event_id = {EVENT.ID}
host     = {HOST.NAME}
trigger  = {TRIGGER.NAME}
severity = {TRIGGER.SEVERITY}
subject  = {ALERT.SUBJECT}
message  = {ALERT.MESSAGE}
```

## Rocket.Chat

Система отправляет уведомления в Rocket.Chat через Incoming Webhook. Внешняя отправка не вызывается из UI вручную: уведомления формируются автоматически при системных событиях, например при создании задачи-инцидента из Zabbix.

Настройки окружения:

```env
ROCKETCHAT_ENABLED=true
ROCKETCHAT_WEBHOOK_URL=https://<rocket-chat-host>/hooks/<webhook-id>/<token>
```

Если `ROCKETCHAT_ENABLED=false`, запись о попытке уведомления сохраняется со статусом `skipped`. Если URL не задан или Rocket.Chat вернул ошибку, статус будет `failed`.

Формат отправляемого payload:

```json
{
  "alias": "IT Workflow",
  "emoji": ":warning:",
  "text": "Новый инцидент Zabbix: задача #15",
  "attachments": [
    {
      "color": "#e36209",
      "title": "Инцидент мониторинга — server-01 — CPU load is too high",
      "text": "Событие Zabbix: CPU load is too high",
      "fields": [
        {"title": "ID задачи", "value": "15", "short": true},
        {"title": "Приоритет", "value": "Высокий", "short": true},
        {"title": "Статус", "value": "Новая", "short": true},
        {"title": "Исполнитель", "value": "Иван Петров", "short": true},
        {"title": "Источник", "value": "zabbix", "short": true}
      ]
    }
  ]
}
```

Журнал внешних уведомлений доступен в интерфейсе:

```text
/notifications
```

В журнале фиксируются канал, статус, связанная задача, дата создания и ответ внешней системы.
