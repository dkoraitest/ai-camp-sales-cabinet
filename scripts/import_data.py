#!/usr/bin/env python3
"""Импорт своих разговоров вместо синтетики.

Код разбирает форматы, модель решает смысл. Скрипт читает файлы из
data/import/ и раскладывает их на разговоры и реплики. Кто из говорящих
менеджер и к какой сделке относится разговор — вопрос смысла: агент
смотрит на разбор, уточняет у участника недостающее и записывает ответы в
data/import/_mapping.json. Потом скрипт собирает из этого базу кабинета.

    python3 scripts/import_data.py scan                  # разобрать файлы, подготовить сопоставление
    python3 scripts/import_data.py build                 # собрать базу из разбора и сопоставления
    python3 scripts/import_data.py build --top-up 200    # и догенерировать до рабочего объёма

Что понимает без помощи агента:
  - экспорт чата WhatsApp (.txt) — айфон и андроид
  - экспорт Telegram Desktop (result.json) — один чат или весь архив
  - расшифровки с метками говорящих (.txt, .md): «Менеджер: …», «Спикер 1: …»,
    «[00:01:23] Айгуль: …», «Айгуль (00:01:23): …»
  - субтитры встреч Zoom, Meet, Teams (.vtt, .srt)
  - документы Word (.docx) с такой же расшифровкой внутри
  - таблицы (.csv) с колонками «разговор, дата, говорящий, текст» — по-русски или по-английски

Остальное скрипт помечает как нераспознанное, и агент разбирает такие
файлы вручную, приводя к тому же виду.

Зависимостей нет: только стандартная библиотека.
"""

import argparse, csv, json, pathlib, re, subprocess, sys, tempfile, zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "import"
PARSED = SRC / "_parsed.json"
MAPPING = SRC / "_mapping.json"
OWN = ROOT / "data" / "own"

MANAGER_HINT = r"менеджер|оператор|продаж|консультант|агент|manager|sales|operator|agent"
CLIENT_HINT = r"клиент|покупател|абонент|заказчик|пациент|родител|гость|client|customer|caller"


# ─────────────────────────── чтение форматов ───────────────────────────

def read_text(path):
    """Текст файла в любой из обычных кодировок: UTF-8 с BOM и без,
    UTF-16 (экспорт на Windows), cp1251 (старые выгрузки телефонии)."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1251", errors="replace")


def parse_date(s):
    """Дата из разных записей: 21.09.2026, 21/09/26, 2026-09-21 — с временем или без."""
    s = s.strip().replace(" ", " ").replace("‎", "")
    for fmt in ("%d.%m.%Y, %H:%M:%S", "%d.%m.%Y, %H:%M", "%d.%m.%y, %H:%M:%S", "%d.%m.%y, %H:%M",
                "%d/%m/%Y, %H:%M:%S", "%d/%m/%Y, %H:%M", "%d/%m/%y, %H:%M:%S", "%d/%m/%y, %H:%M",
                "%m/%d/%y, %I:%M %p", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y-%m-%d", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def date_from_name(path):
    m = re.search(r"(20\d\d)[-_.](\d\d)[-_.](\d\d)", path.name) or \
        re.search(r"(\d\d)[-_.](\d\d)[-_.](20\d\d)", path.name)
    if not m:
        return None
    a, b, c = m.groups()
    try:
        return datetime(int(a), int(b), int(c)) if len(a) == 4 else datetime(int(c), int(b), int(a))
    except ValueError:
        return None


WA = [re.compile(r"^\[(\d{1,2}[./]\d{1,2}[./]\d{2,4}, \d{1,2}:\d{2}(?::\d{2})?)\] ([^:]{1,60}): (.*)$"),
      re.compile(r"^(\d{1,2}[./]\d{1,2}[./]\d{2,4}, \d{1,2}:\d{2}(?::\d{2})?(?: [AP]M)?) - ([^:]{1,60}): (.*)$")]


def read_whatsapp(text):
    turns = []
    for line in text.splitlines():
        # невидимые метки направления и узкие пробелы перед AM/PM из экспорта WhatsApp
        line = line.replace("\u200e", "").replace("\u202f", " ").replace("\xa0", " ").rstrip()
        m = next((r.match(line) for r in WA if r.match(line)), None)
        if m:
            turns.append({"speaker": m.group(2).strip(), "text": m.group(3).strip(),
                          "ts": parse_date(m.group(1))})
        elif turns and line.strip():
            turns[-1]["text"] += "\n" + line.strip()          # продолжение многострочного сообщения
    skip = ("<медиафайл", "<media omitted", "сообщение удалено", "this message was deleted")
    return [t for t in turns if not t["text"].lower().startswith(skip)]


def tg_text(t):
    if isinstance(t, str):
        return t
    return "".join(x if isinstance(x, str) else x.get("text", "") for x in t or [])


def read_telegram(data, path):
    chats = [data] if "messages" in data else (data.get("chats") or {}).get("list", [])
    out = []
    for ch in chats:
        turns = [{"speaker": m.get("from") or "—", "text": tg_text(m.get("text")),
                  "ts": parse_date((m.get("date") or "").replace("T", " "))}
                 for m in ch.get("messages", []) if m.get("type") == "message" and tg_text(m.get("text")).strip()]
        if turns:
            out.append({"title": ch.get("name") or path.stem, "turns": turns})
    return out


LABEL = re.compile(r"^\s*(?:\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s+)?"          # [00:01:23] перед именем
                   r"([^\s:][^:]{0,38}?)"                                    # имя или роль
                   r"(?:\s*\((\d{1,2}:\d{2}(?::\d{2})?)\))?\s*:\s+(.+)$")    # (00:01:23) после имени


def read_transcript(text):
    """Расшифровка с метками говорящих. Строка без метки — продолжение реплики."""
    turns, secs = [], []
    for line in text.splitlines():
        if not line.strip():
            continue
        m = LABEL.match(line)
        if m and len(m.group(2).split()) <= 4 and not m.group(2).lower().startswith(("http", "www")):
            ts = m.group(1) or m.group(3)
            if ts:
                parts = [int(x) for x in ts.split(":")]
                secs.append(parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1])
            turns.append({"speaker": m.group(2).strip(), "text": m.group(4).strip(), "ts": None})
        elif turns:
            turns[-1]["text"] += " " + line.strip()
    return turns, (max(secs) if secs else None)


CUE = re.compile(r"(\d{1,2}:)?(\d{2}):(\d{2})[.,]\d{3}\s*-->\s*(\d{1,2}:)?(\d{2}):(\d{2})[.,]\d{3}")


def read_subtitles(text):
    """Субтитры встреч: говорящий в <v Имя> или в начале строки «Имя: …»."""
    turns, end = [], 0
    for block in re.split(r"\n\s*\n", text.replace("\r", "")):
        lines = [x for x in block.strip().splitlines() if x.strip()]
        cue = next((CUE.search(x) for x in lines if CUE.search(x)), None)
        if not cue:
            continue
        h = int((cue.group(4) or "0:")[:-1] or 0)
        end = max(end, h * 3600 + int(cue.group(5)) * 60 + int(cue.group(6)))
        body = " ".join(x for x in lines if not CUE.search(x) and not x.strip().isdigit() and x.strip() != "WEBVTT")
        v = re.match(r"<v\s+([^>]+)>(.*?)(?:</v>)?$", body)
        who, said = (v.group(1), v.group(2)) if v else (body.split(":", 1) if ":" in body[:40] else ("—", body))
        said = re.sub(r"<[^>]+>", "", said).strip()
        if not said:
            continue
        if turns and turns[-1]["speaker"] == who.strip():
            turns[-1]["text"] += " " + said                    # соседние субтитры одного человека — одна реплика
        else:
            turns.append({"speaker": who.strip(), "text": said, "ts": None})
    return turns, end or None


def read_docx(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    paras = re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S)
    return "\n".join("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)) for p in paras)


COLS = {"conv": ("conversation", "conversation_id", "call_id", "chat_id", "разговор", "звонок", "id разговора", "диалог"),
        "date": ("date", "datetime", "time", "дата", "время"),
        "speaker": ("speaker", "role", "author", "from", "говорящий", "роль", "автор", "кто"),
        "text": ("text", "message", "phrase", "текст", "сообщение", "реплика")}


def read_csv(path):
    raw = read_text(path)
    dialect = csv.Sniffer().sniff(raw[:2000], delimiters=",;\t") if raw.strip() else csv.excel
    rows = list(csv.DictReader(raw.splitlines(), dialect=dialect))
    if not rows:
        return None
    col = {}
    for key, names in COLS.items():
        col[key] = next((h for h in rows[0] if h and h.strip().lower() in names), None)
    if not col["speaker"] or not col["text"]:
        return None
    groups = defaultdict(list)
    for r in rows:
        groups[(r.get(col["conv"]) or path.stem).strip()].append(r)
    out = []
    for cid, rs in groups.items():
        turns = [{"speaker": (r.get(col["speaker"]) or "—").strip(), "text": (r.get(col["text"]) or "").strip(),
                  "ts": parse_date(r.get(col["date"]) or "") if col["date"] else None} for r in rs]
        out.append({"title": cid, "turns": [t for t in turns if t["text"]]})
    return out


def scan_file(path):
    """Файл → список разговоров. Пустой список — формат не распознан."""
    suf = path.suffix.lower()
    base = {"file": path.name, "date": date_from_name(path)}
    try:
        if suf == ".json":
            return [dict(base, format="telegram", kind="chat", channel="telegram", title=c["title"], turns=c["turns"])
                    for c in read_telegram(json.loads(read_text(path)), path)]
        if suf == ".csv":
            return [dict(base, format="csv", kind="call", channel=None, title=c["title"], turns=c["turns"])
                    for c in (read_csv(path) or [])]
        if suf in (".vtt", ".srt"):
            turns, sec = read_subtitles(read_text(path))
            return [dict(base, format=suf[1:], kind="call", channel=None, title=path.stem, turns=turns,
                         duration_min=round(sec / 60) if sec else None)] if turns else []
        text = read_docx(path) if suf == ".docx" else read_text(path) if suf in (".txt", ".md", "") else None
        if text is None:
            return []
        wa = read_whatsapp(text)
        if len(wa) >= 2:
            return [dict(base, format="whatsapp", kind="chat", channel="whatsapp", title=path.stem, turns=wa)]
        turns, sec = read_transcript(text)
        if len(turns) >= 2:
            return [dict(base, format="docx" if suf == ".docx" else "transcript", kind="call", channel=None,
                         title=path.stem, turns=turns, duration_min=round(sec / 60) if sec else None)]
    except Exception as e:
        print(f"  ⚠ {path.name}: не прочитался ({e.__class__.__name__}: {e})")
    return []


# ─────────────────────────── scan ───────────────────────────

def cmd_scan(_):
    files = sorted(p for p in SRC.glob("*") if p.is_file() and not p.name.startswith(("_", ".")) and p.name != "README.md")
    if not files:
        sys.exit("В data/import/ нет файлов. Сложите туда расшифровки, экспорт чатов или субтитры встреч — docs/import.md")
    convs, unknown = [], []
    for f in files:
        got = scan_file(f)
        (convs.extend(got) if got else unknown.append(f.name))
    for i, c in enumerate(convs, 1):
        c["id"] = f"imp{i:03d}"
        ts = [t["ts"] for t in c["turns"] if t.get("ts")]
        start = min(ts) if ts else c.get("date") or datetime.fromtimestamp((SRC / c["file"]).stat().st_mtime)
        c["date"] = start.isoformat(timespec="minutes")
        c["date_end"] = (max(ts) if ts else start).isoformat(timespec="minutes")
        for t in c["turns"]:
            t["ts"] = t["ts"].isoformat(timespec="minutes") if t.get("ts") else None
        c["speakers"] = dict(Counter(t["speaker"] for t in c["turns"]))
    PARSED.write_text(json.dumps(convs, ensure_ascii=False, indent=1), encoding="utf-8")

    # Одно и то же лицо в разных файлах: «Тимур» и «Тимур Абдиров».
    full = {sp for c in convs for sp in c["speakers"] if len(sp.split()) > 1}
    canon = {}
    for c in convs:
        for sp in c["speakers"]:
            canon[sp] = next((f for f in full if f.split()[0] == sp and " " not in sp), sp)
    for c in convs:
        for t in c["turns"]:
            t["speaker"] = canon.get(t["speaker"], t["speaker"])
        c["speakers"] = dict(Counter(t["speaker"] for t in c["turns"]))
    PARSED.write_text(json.dumps(convs, ensure_ascii=False, indent=1), encoding="utf-8")

    # Догадка, кто менеджер: подсказка в метке; человек, который говорит с
    # разными собеседниками — менеджер ведёт многих клиентов, а клиент сделки
    # и в звонке, и в переписке говорит с одним и тем же; в разговоре, где
    # менеджер так и не найден, — тот, кто задаёт больше вопросов.
    generic = lambda sp: bool(re.match(r"(спикер|speaker|участник|говорящий)\s*\d", sp.lower()))
    peers = defaultdict(set)
    for c in convs:
        for sp in c["speakers"]:
            peers[sp] |= set(c["speakers"]) - {sp}
    managers = {}
    def mark(sp):
        if sp not in managers:
            managers[sp] = f"m{len(managers) + 1}"
    for sp in peers:
        if re.search(MANAGER_HINT, sp.lower()) or (len(peers[sp]) >= 2 and not re.search(CLIENT_HINT, sp.lower())
                                                    and not generic(sp)):
            mark(sp)
    for c in convs:
        if any(sp in managers for sp in c["speakers"]):
            continue
        q = Counter()
        for i, t in enumerate(c["turns"]):
            q[t["speaker"]] += t["text"].count("?") * 2 + (1 if i == 0 else 0)
        cand = [sp for sp, _ in q.most_common() if not re.search(CLIENT_HINT, sp.lower())]
        if cand:
            mark(cand[0])
    old = json.loads(MAPPING.read_text(encoding="utf-8")) if MAPPING.exists() else {}
    mapping = {
        "_как_заполнять": "managers: говорящий → id менеджера (m1, m2…); остальные — клиенты. "
                          "manager_names: id → имя, как его показывать. conversations: у каждого разговора "
                          "lead — компания или клиент (одинаковое имя склеит разговоры в одну сделку), "
                          "stage — id этапа из вашей воронки или null (по порядку), outcome — итог одной строкой, "
                          "value_kzt — сумма сделки, won/lost — если сделка закрыта.",
        "managers": old.get("managers") or managers,
        "manager_names": old.get("manager_names") or {v: re.sub(r"\s*\(.*?\)", "", k) for k, v in managers.items()},
        "conversations": {},
    }
    for c in convs:
        prev = (old.get("conversations") or {}).get(c["id"], {})
        others = [sp for sp in c["speakers"] if sp not in mapping["managers"]]
        named = [sp for sp in others if not re.search(CLIENT_HINT, sp.lower()) and not generic(sp)]
        guess = c["title"] if c["format"] == "telegram" or not named else named[0]
        mapping["conversations"][c["id"]] = {"file": c["file"], "lead": prev.get("lead", guess),
                                             "stage": prev.get("stage"), "outcome": prev.get("outcome"),
                                             "value_kzt": prev.get("value_kzt"), "result": prev.get("result")}
    MAPPING.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Разобрано {len(convs)} разговоров из {len(files) - len(unknown)} файлов:")
    for fmt, n in Counter(c["format"] for c in convs).most_common():
        print(f"  {fmt:<11} {n}")
    if unknown:
        print(f"Не распознаны ({len(unknown)}): {', '.join(unknown[:8])}{' …' if len(unknown) > 8 else ''}")
        print("  Их агент разбирает вручную: приводит к виду «Имя: реплика» и кладёт рядом как .txt")
    print(f"\nГоворящие, похожие на менеджеров: {', '.join(mapping['managers']) or 'не угадал'}")
    nameless = [sp for sp in mapping["managers"] if re.search(MANAGER_HINT, sp.lower()) or generic(sp)]
    if nameless:
        print(f"Метки без имени ({', '.join(nameless)}) — спросите, кто это, и впишите имя в manager_names")
    print("Проверьте data/import/_mapping.json: кто менеджер, к какой сделке относится разговор,")
    print("этап и итог, если известны. Потом: python3 scripts/import_data.py build")


# ─────────────────────────── build ───────────────────────────

def load_profile():
    p = ROOT / "active" / "profile.json"
    if not p.exists():
        sys.exit("Нет active/profile.json. Шаг 0 собирает профиль и воронку — пройдите окна шага 0,\n"
                 "а генерацию пропустите: база будет из ваших записей.")
    return json.loads(p.read_text(encoding="utf-8"))


def cmd_build(a):
    if not PARSED.exists() or not MAPPING.exists():
        sys.exit("Сначала разбор: python3 scripts/import_data.py scan")
    P = load_profile()
    convs = json.loads(PARSED.read_text(encoding="utf-8"))
    mp = json.loads(MAPPING.read_text(encoding="utf-8"))
    stages = [s["id"] for s in P["funnel"]]
    working = stages[:-2] if len(stages) > 2 else stages
    b2c = P.get("audience", "b2c" if P.get("type") == "flow" else "b2b") == "b2c"
    mgr_of = mp.get("managers") or {}
    names = mp.get("manager_names") or {}
    if not mgr_of:
        sys.exit("В _mapping.json не указано, кто менеджер. Без этого разговоры не разложить на менеджера и клиента.")

    by_lead = defaultdict(list)
    for c in convs:
        m = (mp.get("conversations") or {}).get(c["id"], {})
        by_lead[(m.get("lead") or c["title"]).strip()].append((c, m))

    calls, chats, leads = [], [], []
    for li, (lead_name, items) in enumerate(sorted(by_lead.items()), 1):
        items.sort(key=lambda x: x[0]["date"])
        lid = f"l{li:03d}"
        owner = None
        for n, (c, m) in enumerate(items):
            stage = m.get("stage") if m.get("stage") in stages else working[min(n, len(working) - 1)]
            mid = next((mgr_of[t["speaker"]] for t in c["turns"] if t["speaker"] in mgr_of), None) or "m1"
            owner = owner or mid
            turns = [{"who": "manager" if t["speaker"] in mgr_of else "client", "text": t["text"],
                      **({"ts": t["ts"]} if c["kind"] == "chat" and t.get("ts") else {})} for t in c["turns"]]
            if c["kind"] == "chat":
                chats.append({"id": f"ch{len(chats) + 1:03d}", "channel": c.get("channel") or "переписка",
                              "manager_id": mid, "lead_id": lid, "stage": stage, "imported": True,
                              "date_start": c["date"], "date_end": c["date_end"], "messages_count": len(turns),
                              "outcome": m.get("outcome") or "", "messages": turns})
            else:
                calls.append({"id": f"c{len(calls) + 1:03d}", "date": c["date"], "manager_id": mid, "lead_id": lid,
                              "stage": stage, "direction": "inbound" if "вход" in (c["file"] or "").lower() else "outbound",
                              "duration_min": c.get("duration_min") or max(2, round(len(turns) * 0.6)),
                              "turns": len(turns), "outcome": m.get("outcome") or "", "imported": True,
                              "transcript": turns})
        last = items[-1][1]
        result = (last.get("result") or "").lower()
        stage = stages[-2] if result in ("won", "выиграна") else stages[-1] if result in ("lost", "проиграна") else \
            (last.get("stage") if last.get("stage") in stages else working[min(len(items) - 1, len(working) - 1)])
        lead = {"id": lid, "company": lead_name, "contact": lead_name if b2c else "", "source": "импорт",
                "created": items[0][0]["date"][:10], "stage": stage,
                "value_kzt": next((m.get("value_kzt") for _, m in items if m.get("value_kzt")), 0),
                "next_step": None, "owner": owner, "manager_id": owner}
        leads.append(lead)

    ids = sorted(set(mgr_of.values()))
    managers = [{"id": i, "name": names.get(i) or next(k for k, v in mgr_of.items() if v == i), "role": "Менеджер"} for i in ids]
    out = {"profile": {"id": "own", "title": P["company"], "company": P["company"], "what_we_sell": P.get("what_we_sell", ""),
                       "type": "b2c" if b2c else "b2b", "crm": P.get("crm", "none"), "synthetic": False, "imported": True,
                       "stages": stages, "stage_labels": {s["id"]: s["label"] for s in P["funnel"]}, "funnel": P["funnel"]},
           "managers": managers, "calls": calls, "chats": chats, "leads": leads}
    OWN.mkdir(parents=True, exist_ok=True)
    (OWN / "imported.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    if a.top_up:
        out = top_up(out, P, a.top_up)
    (OWN / "dataset.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    real = sum(1 for x in out["calls"] + out["chats"] if x.get("imported"))
    synth = len(out["calls"]) + len(out["chats"]) - real
    print(f"✓ База собрана: {real} ваших разговоров" + (f" и {synth} синтетических" if synth else "") +
          f", {len(out['leads'])} сделок, {len(out['managers'])} менеджеров → data/own/dataset.json")
    if real < 20:
        print(f"  Разговоров мало для закономерностей. Догенерировать до рабочего объёма: "
              f"python3 scripts/import_data.py build --top-up 200")
    print("  Дальше: в cabinet/config.js profile: \"own\", затем python3 scripts/build_data.py и шаг 1")


def top_up(base, P, n):
    """Догенерация до рабочего объёма. Синтетика идёт к вашим же менеджерам
    и помечается: в кабинете свои разговоры не перепутать с иллюстрацией."""
    with tempfile.TemporaryDirectory() as tmp:
        dst = pathlib.Path(tmp) / "synthetic.json"
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_participant.py"),
                            str(ROOT / "active" / "profile.json"), "--calls", str(n), "--out", str(dst)],
                           capture_output=True, text=True)
        if r.returncode:
            sys.exit("Догенерация не получилась:\n" + r.stdout + r.stderr)
        syn = json.loads(dst.read_text(encoding="utf-8"))
    real_ids = [m["id"] for m in base["managers"]]
    remap = {m["id"]: real_ids[i % len(real_ids)] for i, m in enumerate(syn["managers"])}
    for l in syn["leads"]:
        l["id"] = "s" + l["id"]
        l["owner"] = l["manager_id"] = remap.get(l.get("owner") or l.get("manager_id"), real_ids[0])
        l["synthetic"] = True
    for kind, prefix in (("calls", "sc"), ("chats", "sch")):
        for x in syn[kind]:
            x["id"] = prefix + re.sub(r"^\D+", "", x["id"])
            x["lead_id"] = "s" + x["lead_id"]
            x["manager_id"] = remap.get(x["manager_id"], real_ids[0])
            x["synthetic"] = True
    base = dict(base)
    base["calls"] = sorted(base["calls"] + syn["calls"], key=lambda c: c["date"])
    base["chats"] = sorted(base["chats"] + syn["chats"], key=lambda c: c["date_start"])
    base["leads"] = base["leads"] + syn["leads"]
    base["profile"] = dict(base["profile"], topped_up=len(syn["calls"]) + len(syn["chats"]))
    return base


def main():
    ap = argparse.ArgumentParser(description="Импорт своих разговоров: data/import/ → data/own/dataset.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan", help="разобрать файлы и подготовить сопоставление").set_defaults(fn=cmd_scan)
    p = sub.add_parser("build", help="собрать базу"); p.set_defaults(fn=cmd_build)
    p.add_argument("--top-up", type=int, default=0, help="догенерировать столько синтетических звонков")
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
