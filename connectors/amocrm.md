# amoCRM → кабинет

Доступ: интеграция в amoCRM (Настройки → Интеграции → Создать интеграцию), долгосрочный токен в `.env` как `AMOCRM_TOKEN`, домен как `AMOCRM_DOMAIN`.

| Кабинет | amoCRM API v4 | Заметка |
|---|---|---|
| `leads[].id` | `GET /api/v4/leads` → `id` | |
| `leads[].stage` | `status_id` | сопоставить со своими этапами: `GET /api/v4/leads/pipelines` |
| `leads[].owner` | `responsible_user_id` | |
| `leads[].value_kzt` | `price` | |
| `leads[].created` | `created_at` | unix time → ISO-дата |
| `leads[].next_step` | ближайшая открытая задача: `GET /api/v4/tasks?filter[entity_id]=…` → `complete_till` | |
| `leads[].source` | кастомное поле или `_embedded.source` | зависит от настройки |
| `leads[].company`, `contact` | `?with=contacts,companies` | |
| `managers[]` | `GET /api/v4/users` | |
| `calls[]` | `GET /api/v4/leads/{id}/notes` с `note_type=call_in/call_out` → ссылка на запись | запись → транскрибация → `transcript` |

Запись обратно: `PATCH /api/v4/leads/{id}` (этап, поля), `POST /api/v4/tasks` (задачи), `POST /api/v4/leads/{id}/notes` (саммари разговора).
