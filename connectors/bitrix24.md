# Битрикс24 → кабинет

Доступ: входящий вебхук (Разработчикам → Другое → Входящий вебхук) с правами `crm`, `user`, `task`. URL вебхука в `.env` как `BITRIX_WEBHOOK`.

| Кабинет | Битрикс24 REST | Заметка |
|---|---|---|
| `leads[].id` | `crm.deal.list` → `ID` | для потока заявок — `crm.lead.list` |
| `leads[].stage` | `STAGE_ID` | этапы воронки: `crm.dealcategory.stage.list` |
| `leads[].owner` | `ASSIGNED_BY_ID` | |
| `leads[].value_kzt` | `OPPORTUNITY` | |
| `leads[].created` | `DATE_CREATE` | |
| `leads[].next_step` | ближайшее дело: `crm.activity.list` по `OWNER_ID` → `DEADLINE` | |
| `leads[].source` | `SOURCE_ID` | справочник: `crm.status.list` |
| `leads[].company`, `contact` | `COMPANY_ID`, `CONTACT_ID` → `crm.company.get`, `crm.contact.get` | |
| `managers[]` | `user.get` | |
| `calls[]` | `crm.activity.list` с `TYPE_ID=2` (звонок) → запись в `voximplant.statistic.get` | запись → транскрибация → `transcript` |

Запись обратно: `crm.deal.update` (этап, поля), `tasks.task.add` (задачи), `crm.timeline.comment.add` (саммари разговора).
