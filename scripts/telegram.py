#!/usr/bin/env python3
"""Доставка обратной связи менеджеру в Telegram.

Кабинет показывает руководителю, что происходит. Но менеджер кабинет не
открывает — он живёт в мессенджере. Поэтому разбор и тренировка уходят туда,
где человек их прочитает, через пару минут после разговора.

На воркшопе используется общий бот: заводить своего не нужно, токен даёт
спикер. Дома вы заведёте свой за пять минут — docs/telegram.md.

    python3 scripts/telegram.py init                 # узнать бота и показать ссылки в кабинете
    python3 scripts/telegram.py link --auto          # привязать всех, кто прошёл по своей ссылке
    python3 scripts/telegram.py who                  # кто написал боту
    python3 scripts/telegram.py link m1 --user @ivan # привязать вручную
    python3 scripts/telegram.py send m1              # отправить разбор и тренировку
    python3 scripts/telegram.py send all --dry       # показать, что уйдёт, и не отправлять

Менеджер не вводит ничего: он открывает ссылку вида t.me/<бот>?start=m2 из
своей карточки в кабинете и жмёт «Старт». Телеграм передаёт боту id менеджера,
и `link --auto` расставляет привязки сам.

Зависимостей нет: только стандартная библиотека.
"""

import argparse, json, pathlib, re, sys, urllib.request, urllib.error, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
LINKS = ROOT / "active" / "telegram.json"
STATE = ROOT / "cabinet" / "telegram.js"
API = "https://api.telegram.org/bot{}/{}"


def token() -> str:
    """Токен живёт только в .env и никогда не попадает ни в репозиторий, ни в вывод."""
    env = ROOT / ".env"
    if not env.exists():
        sys.exit("Нет файла .env. Скопируйте .env.example в .env и вставьте токен бота.\n"
                 "На воркшопе токен даёт спикер, заводить своего бота не нужно.")
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            t = line.split("=", 1)[1].strip().strip('"\'')
            if t and not t.startswith("сюда"):
                return t
    sys.exit("В .env нет TELEGRAM_BOT_TOKEN. Вставьте токен и запустите снова.")


def call(method, **params):
    url = API.format(token(), method)
    data = urllib.parse.urlencode(params).encode() if params else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        detail = json.loads(body).get("description", body) if body.startswith("{") else body
        sys.exit(f"Telegram отказал: {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"Не достучались до Telegram: {e.reason}")
    if not out.get("ok"):
        sys.exit(f"Telegram отказал: {out.get('description')}")
    return out["result"]


def chats():
    """Кто писал боту. Offset не подтверждаем: бот общий, чужие сообщения
    забирать из очереди нельзя — соседу по залу они тоже нужны."""
    seen, out = set(), []
    for u in call("getUpdates", timeout=0, limit=100):
        msg = u.get("message") or u.get("edited_message") or {}
        ch = msg.get("chat") or {}
        if not ch.get("id") or ch["id"] in seen:
            continue
        seen.add(ch["id"])
        name = " ".join(x for x in (ch.get("first_name"), ch.get("last_name")) if x)
        out.append({"id": ch["id"], "user": ("@" + ch["username"]) if ch.get("username") else "",
                    "name": name or "—"})
    return out


def links():
    if LINKS.exists():
        try: return json.loads(LINKS.read_text(encoding="utf-8"))
        except Exception: pass
    return {}


def coach():
    f = ROOT / "cabinet" / "coach.js"
    if not f.exists():
        sys.exit("Нет cabinet/coach.js — сначала пройдите шаг 2, тренер пишет этот файл.")
    t = f.read_text(encoding="utf-8")
    return json.loads(t[t.index("{"):t.rindex("}") + 1])


def mgr_name(mid):
    f, cfg = ROOT / "cabinet" / "data.js", ROOT / "cabinet" / "config.js"
    if not f.exists():
        return mid
    t = f.read_text(encoding="utf-8")
    d = json.loads(t[t.index("{"):t.rindex("}") + 1])
    order = list(d)
    if cfg.exists():                      # имена берём из того же профиля, что и кабинет
        m = re.search(r'profile:\s*[\'"](\w+)[\'"]', cfg.read_text(encoding="utf-8"))
        if m and m.group(1) in d:
            order = [m.group(1)] + [k for k in order if k != m.group(1)]
    for k in order:
        for m in d[k].get("managers", []):
            if m["id"] == mid:
                return m["name"]
    return mid


def texts(fb):
    """Что уходит человеку: разбор после контакта и задание на отработку."""
    out = [m["text"] for m in fb.get("telegram_messages", []) if m.get("text")]
    d = fb.get("drill")
    if d and not any(d.get("title", "\0") in t for t in out):
        out.append(f"Тренировка: {d['title']}\n\n{d['task']}\n\n"
                   f"Формат ответа: {d.get('reply_format', 'текст')}.")
    return out


def publish(bot=None):
    """Кабинет — статический файл, он не ходит в сеть. Поэтому состояние
    привязок кладём рядом обычным <script>. Токена и id чатов здесь нет:
    только имя бота и кто уже подключён."""
    data = links()
    if bot is None:
        bot = json.loads(STATE.read_text(encoding="utf-8").split("=", 1)[1].rsplit(";", 1)[0])["bot"] \
              if STATE.exists() else None
    payload = {"bot": bot, "links": {k: True for k in data}}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text("// Сгенерировано scripts/telegram.py — руками не править.\n"
                     "// Токена и id чатов здесь нет: только имя бота и кто подключён.\n"
                     f"window.CABINET_TELEGRAM = {json.dumps(payload, ensure_ascii=False)};\n",
                     encoding="utf-8")
    return bot


def cmd_init(_):
    me = call("getMe")
    bot = me.get("username")
    publish(bot)
    print(f"Бот @{bot} на связи. Кабинет теперь показывает ссылку подключения в карточке каждого менеджера.")
    print("Менеджер открывает свою ссылку, жмёт «Старт», дальше: python3 scripts/telegram.py link --auto")


def cmd_auto(a):
    """Привязка по deep-link: в /start прилетает id менеджера, гадать не нужно."""
    found = {}
    for u in call("getUpdates", timeout=0, limit=100):
        msg = u.get("message") or {}
        text = (msg.get("text") or "").strip()
        ch = msg.get("chat") or {}
        if text.startswith("/start ") and ch.get("id"):
            found[text.split(None, 1)[1].strip()] = ch
    if not found:
        sys.exit("Никто ещё не прошёл по своей ссылке.\n"
                 "Ссылка есть в карточке менеджера в кабинете, и её же печатает python3 scripts/telegram.py init")
    data = links()
    for mid, ch in found.items():
        data[mid] = ch["id"]
        name = mgr_name(mid)
        call("sendMessage", chat_id=ch["id"],
             text=f"Готово. Сюда будет приходить обратная связь по разговорам: {name}.")
        print(f"✓ {mid} ({name}) → {('@' + ch['username']) if ch.get('username') else ch.get('first_name', '')}")
    LINKS.parent.mkdir(parents=True, exist_ok=True)
    LINKS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    publish()


def cmd_who(_):
    rows = chats()
    if not rows:
        print("Боту пока никто не писал.\n"
              "Откройте бота в Telegram, нажмите «Старт» и запустите команду снова.")
        return
    print("Кто написал боту:")
    for r in rows:
        print(f"  {r['id']:>12}  {r['user'] or '—':<20} {r['name']}")
    print("\nПривязать: python3 scripts/telegram.py link <manager_id> --user @handle")


def cmd_link(a):
    if a.auto:
        return cmd_auto(a)
    if not a.manager:
        sys.exit("Нужен id менеджера или флаг --auto.")
    rows = chats()
    if not rows:
        sys.exit("Боту никто не писал. Откройте бота, нажмите «Старт» и повторите.")
    if a.user:
        want = a.user if a.user.startswith("@") else "@" + a.user
        row = next((r for r in rows if r["user"].lower() == want.lower()), None)
        if not row:
            sys.exit(f"Среди написавших боту нет {want}. Проверьте: python3 scripts/telegram.py who")
    else:
        row = rows[-1]
        print(f"Беру последнего написавшего: {row['user'] or row['name']}")
    data = links(); data[a.manager] = row["id"]
    LINKS.parent.mkdir(parents=True, exist_ok=True)
    LINKS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    name = mgr_name(a.manager)
    call("sendMessage", chat_id=row["id"],
         text=f"Готово. Сюда будет приходить обратная связь по разговорам: {name}.")
    publish()
    print(f"✓ {a.manager} ({name}) → {row['user'] or row['name']}. Подтверждение отправлено.")


def cmd_send(a):
    data, ids = coach(), links()
    who = [m for m in data.get("managers", []) if a.manager == "all" or m["id"] == a.manager]
    if not who:
        sys.exit(f"В cabinet/coach.js нет разбора для {a.manager}.")
    for fb in who:
        msgs = texts(fb)
        name = mgr_name(fb["id"])
        chat = ids.get(fb["id"])
        if a.dry or not chat:
            mark = "черновик" if a.dry else "чат не привязан"
            print(f"\n── {name} ({fb['id']}) · {mark} · сообщений: {len(msgs)}")
            for t in msgs: print("   " + t.replace("\n", "\n   "))
            if not chat and not a.dry:
                print(f"   Привязать: python3 scripts/telegram.py link {fb['id']} --user @handle")
            continue
        for t in msgs:
            call("sendMessage", chat_id=chat, text=t)
        print(f"✓ {name}: отправлено {len(msgs)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="узнать бота и показать ссылки в кабинете").set_defaults(fn=cmd_init)
    sub.add_parser("who", help="кто написал боту").set_defaults(fn=cmd_who)
    p = sub.add_parser("link", help="привязать чат к менеджеру"); p.set_defaults(fn=cmd_link)
    p.add_argument("manager", nargs="?", help="id менеджера; не нужен с --auto")
    p.add_argument("--auto", action="store_true", help="привязать всех, кто прошёл по своей ссылке")
    p.add_argument("--user", help="@handle получателя")
    p = sub.add_parser("send", help="отправить разбор"); p.set_defaults(fn=cmd_send)
    p.add_argument("manager", help="id менеджера или all")
    p.add_argument("--dry", action="store_true", help="показать тексты, не отправляя")
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
