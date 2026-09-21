#!/usr/bin/env python3
"""Импорт своих разговоров вместо синтетики.

Код разбирает форматы, модель решает смысл. Скрипт читает файлы из
data/import/ и раскладывает их на разговоры и реплики. Кто из говорящих
менеджер, к какой сделке относится разговор и чем она закончилась — вопрос
смысла: агент смотрит на разбор, уточняет у участника недостающее и пишет
ответы в data/import/_mapping.json. Потом скрипт собирает из этого базу.

    python3 scripts/import_data.py scan                  # разобрать файлы, подготовить сопоставление
    python3 scripts/import_data.py build                 # собрать базу из разбора и сопоставления
    python3 scripts/import_data.py build --top-up 200    # догенерировать до 200 разговоров всего

Что понимает без помощи агента:
  - WhatsApp: .txt с телефона на Android, архив .zip с айфона, русский и английский
  - Telegram Desktop: result.json — один чат или весь архив, можно прямо в папке ChatExport_…
  - расшифровки звонков (.txt, .md, .docx): «Менеджер: …», «Спикер 1: …», «**Имя:** …»,
    «[00:01:23] Имя: …», «Имя (00:01:23): …», а также формат Teams и Word: строка «Имя   0:03»,
    под ней реплика
  - субтитры встреч Zoom, Meet, Teams (.vtt, .srt)
  - таблицы (.csv) из телефонии или Excel: «разговор, дата, говорящий, текст»
  - кодировки UTF-8 с BOM и без, UTF-16, cp1251

Заметки без реплик, аудио и pdf скрипт не читает: их агент приводит к виду
«Имя: реплика», а оригинал переносит в data/import/_done/.

Зависимостей нет: только стандартная библиотека.
"""

import argparse, csv, html, io, json, pathlib, re, shutil, subprocess, sys, tempfile, zipfile
from collections import Counter, defaultdict
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "import"
PARSED = SRC / "_parsed.json"
MAPPING = SRC / "_mapping.json"
DONE = SRC / "_done"
OWN = ROOT / "data" / "own"
CAB = ROOT / "cabinet"
OURS = {"_parsed.json", "_mapping.json", ".gitkeep", "README.md", ".DS_Store"}

MANAGER_HINT = r"менеджер|оператор|продаж|консультант|агент|\bроп\b|руководител|manager|sales|operator|agent"
CLIENT_HINT = r"клиент|покупател|абонент|заказчик|пациент|родител|гость|client|customer|caller"
GENERIC = re.compile(r"^(спикер|speaker|участник|говорящий|собеседник|абонент|клиент|менеджер|оператор|"
                     r"client|customer|manager|operator)\s*\d*$", re.I)
# Метки, которые в заметках выглядят как говорящие, но ими не являются
NOT_SPEAKER = {"итог", "итоги", "итого", "участники", "дата", "тема", "первое", "второе", "третье", "задачи",
               "договорились", "следующий шаг", "следующие шаги", "примечание", "по деньгам", "боль", "объём",
               "объем", "цель", "повестка", "решение", "вопросы", "вопрос", "ответ", "контакты", "адрес",
               "телефон", "email", "время", "место", "бюджет", "сроки", "срок", "важно", "итог встречи", "резюме",
               "summary", "agenda", "notes", "action items", "next steps", "note", "p.s", "ps", "upd"}
SERVICE = ("без медиафайлов", "медиафайл отсутствует", "media omitted", "сообщение удалено", "message was deleted",
           "you deleted this message", "вы удалили это сообщение", "защищены сквозным шифрованием",
           "end-to-end encrypted", "изображение отсутствует", "image omitted", "видео отсутствует", "video omitted",
           "аудиофайл отсутствует", "audio omitted", "стикер отсутствует", "sticker omitted", "gif omitted",
           "документ отсутствует", "document omitted", "пропущенный звонок", "пропущенный аудиозвонок",
           "missed voice call", "missed video call", "контакт изменён", "создал(а) группу", "created group")


class Skip(Exception):
    """Файл не разобран: причина человеческими словами."""


# ─────────────────────────── чтение форматов ───────────────────────────

def decode(raw):
    """Текст в любой из обычных кодировок: UTF-8 с BOM и без, UTF-16, cp1251."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1251", errors="replace")


def clean(s):
    """Невидимые символы из экспорта: метки направления, узкие и неразрывные пробелы, мягкий перенос."""
    return s.replace("‎", "").replace("‏", "").replace(" ", " ").replace("\xa0", " ").replace("­", "")


def parse_date(s):
    s = clean(s or "").strip()
    for fmt in ("%d.%m.%Y, %H:%M:%S", "%d.%m.%Y, %H:%M", "%d.%m.%y, %H:%M:%S", "%d.%m.%y, %H:%M",
                "%d/%m/%Y, %H:%M:%S", "%d/%m/%Y, %H:%M", "%d/%m/%y, %H:%M:%S", "%d/%m/%y, %H:%M",
                "%m/%d/%y, %I:%M:%S %p", "%m/%d/%y, %I:%M %p", "%m/%d/%Y, %I:%M:%S %p", "%m/%d/%Y, %I:%M %p",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def date_from_name(name):
    m = re.search(r"(20\d\d)[-_.](\d\d)[-_.](\d\d)", name) or re.search(r"(\d\d)[-_.](\d\d)[-_.](20\d\d)", name)
    if not m:
        return None
    a, b, c = m.groups()
    try:
        return datetime(int(a), int(b), int(c)) if len(a) == 4 else datetime(int(c), int(b), int(a))
    except ValueError:
        return None


MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7, "август": 8, "сентябр": 9,
          "октябр": 10, "ноябр": 11, "декабр": 12}


def date_in_text(text):
    """Дата из заголовка документа: «# Созвон с Нур Фарм, 2026-09-14», «22 сентября 2026 г.»."""
    head = "\n".join(text.splitlines()[:6])
    d = date_from_name(head)
    if d:
        return d
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(20\d\d)", head)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    m = re.search(r"(\d{1,2})\s+([а-яё]+)\s+(20\d\d)", head.lower())
    if m:
        mon = next((v for k, v in MONTHS.items() if m.group(2).startswith(k)), None)
        if mon:
            try:
                return datetime(int(m.group(3)), mon, int(m.group(1)))
            except ValueError:
                pass
    return None


def service(text):
    t = text.lower()
    return any(x in t for x in SERVICE)


WA = [re.compile(r"^\[(\d{1,2}[./]\d{1,2}[./]\d{2,4}, \d{1,2}:\d{2}(?::\d{2})?(?: ?[AP]M)?)\] ([^:]{1,60}): (.*)$"),
      re.compile(r"^(\d{1,2}[./]\d{1,2}[./]\d{2,4}, \d{1,2}:\d{2}(?::\d{2})?(?: ?[AP]M)?) - ([^:]{1,60}): (.*)$")]
WA_SYS = re.compile(r"^\[?\d{1,2}[./]\d{1,2}[./]\d{2,4}, \d{1,2}:\d{2}")   # строка с датой, но без автора


def read_whatsapp(text):
    turns = []
    for line in text.splitlines():
        line = clean(line).rstrip()
        m = next((r.match(line) for r in WA if r.match(line)), None)
        if m:
            turns.append({"speaker": m.group(2).strip(), "text": m.group(3).strip(), "ts": parse_date(m.group(1))})
        elif WA_SYS.match(line):
            turns.append({"speaker": None, "text": "", "ts": None})      # системная строка обрывает реплику
        elif turns and turns[-1]["speaker"] and line.strip():
            turns[-1]["text"] += "\n" + line.strip()
    return [t for t in turns if t["speaker"] and t["text"].strip() and not service(t["text"])]


def tg_text(t):
    if isinstance(t, str):
        return t
    return "".join(x if isinstance(x, str) else x.get("text", "") for x in t or [])


def read_telegram(data, stem):
    chats = [data] if "messages" in data else (data.get("chats") or {}).get("list", [])
    out = []
    for i, ch in enumerate(chats, 1):
        turns = [{"speaker": m.get("from") or "—", "text": tg_text(m.get("text")), "ts": parse_date(m.get("date"))}
                 for m in ch.get("messages", []) if m.get("type") == "message" and tg_text(m.get("text")).strip()]
        turns = [t for t in turns if not service(t["text"])]
        if turns:
            out.append({"title": ch.get("name") or ("Избранное" if ch.get("type") == "saved_messages" else f"{stem} {i}"),
                        "tg_type": ch.get("type"), "turns": turns})
    return out


LABEL = re.compile(r"^\s*(?:\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s+)?"          # [00:01:23] перед именем
                   r"([^\s:#>*_\-][^:]{0,40}?)"                               # имя или роль
                   r"(?:\s*\((\d{1,2}:\d{2}(?::\d{2})?)\))?\s*:\s+(.+)$")     # (00:01:23) после имени
HEADER = re.compile(r"^\s*([^\d\s:][^:]{0,40}?)\s{2,}(\d{1,2}:\d{2}(?::\d{2})?)\s*$")   # «Имя   0:03» — Teams, Word


def unmark(line):
    """Markdown: «**Имя:** текст» → «Имя: текст»; заголовки и цитаты — без разметки."""
    line = re.sub(r"^\s*[*_]{1,2}([^*_:]{1,40}?)[*_]{0,2}\s*:\s*[*_]{0,2}\s*", r"\1: ", line)
    return re.sub(r"^\s*>\s?", "", line)


def speaker_ok(label, count):
    l = label.strip().lower().rstrip(".")
    if l in NOT_SPEAKER or len(label.split()) > 4 or l.startswith(("http", "www")):
        return False
    return count >= 2 or bool(GENERIC.match(l)) or bool(re.search(MANAGER_HINT + "|" + CLIENT_HINT, l))


def to_secs(ts):
    p = [int(x) for x in ts.split(":")]
    return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else p[0] * 60 + p[1]


def read_transcript(text):
    """Расшифровка. Два вида разметки: «Имя: реплика» в строке или «Имя   0:03»
    отдельной строкой и реплика под ней. Метка, которая встретилась один раз
    и не похожа на роль, — это текст («Итог: …»), а не говорящий."""
    lines = [unmark(clean(x)) for x in text.splitlines()]
    lines = [x for x in lines if x.strip() and not x.lstrip().startswith("#")]
    heads = [HEADER.match(x) for x in lines]
    if sum(1 for h in heads if h) >= 2:
        turns, secs = [], []
        for line, h in zip(lines, heads):
            if h:
                turns.append({"speaker": h.group(1).strip(), "text": "", "ts": None}); secs.append(to_secs(h.group(2)))
            elif turns:
                turns[-1]["text"] = (turns[-1]["text"] + " " + line.strip()).strip()
        return [t for t in turns if t["text"]], (max(secs) if secs else None)
    counts = Counter(m.group(2).strip() for m in (LABEL.match(x) for x in lines) if m)
    turns, secs = [], []
    for line in lines:
        m = LABEL.match(line)
        if m and speaker_ok(m.group(2), counts[m.group(2).strip()]):
            ts = m.group(1) or m.group(3)
            if ts:
                secs.append(to_secs(ts))
            turns.append({"speaker": m.group(2).strip(), "text": m.group(4).strip(), "ts": None})
        elif turns:
            turns[-1]["text"] += " " + line.strip()
    return turns, (max(secs) if secs else None)


CUE = re.compile(r"(\d{1,2}:)?(\d{2}):(\d{2})[.,]\d{3}\s*-->\s*(\d{1,2}:)?(\d{2}):(\d{2})[.,]\d{3}")


def read_subtitles(text):
    """Субтитры: говорящий в <v Имя> или «Имя: …». Идентификатор реплики
    (номер или GUID у Teams) стоит до строки времени и в текст не попадает."""
    turns, end = [], 0
    for block in re.split(r"\n\s*\n", clean(text).replace("\r", "")):
        lines = [x for x in block.strip().splitlines() if x.strip()]
        at = next((i for i, x in enumerate(lines) if CUE.search(x)), None)
        if at is None:
            continue
        cue = CUE.search(lines[at])
        h = int((cue.group(4) or "0:")[:-1] or 0)
        end = max(end, h * 3600 + int(cue.group(5)) * 60 + int(cue.group(6)))
        body = " ".join(lines[at + 1:])
        v = re.search(r"<v(?:\.[^\s>]+)?\s+([^>]+)>(.*?)(?:</v>|$)", body)
        if v:
            who, said = v.group(1), v.group(2)
        else:
            m = re.match(r"^([^:]{1,40}):\s+(.*)$", body)
            who, said = (m.group(1), m.group(2)) if m and len(m.group(1).split()) <= 4 else ("—", body)
        said = re.sub(r"<[^>]+>", "", said).strip()
        if not said:
            continue
        if turns and turns[-1]["speaker"] == who.strip():
            turns[-1]["text"] += " " + said
        else:
            turns.append({"speaker": who.strip(), "text": said, "ts": None})
    return turns, end or None


def read_docx(raw):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
    except (zipfile.BadZipFile, KeyError):
        raise Skip("файл .docx повреждён или это не документ Word — пересохраните его из Word")
    xml = re.sub(r"<w:tab/>", "\t", xml)
    xml = re.sub(r"<w:br[^>]*/>", "\n", xml)
    xml = re.sub(r"<w:softHyphen/>", "", xml)
    paras = re.findall(r"<w:p[ >].*?</w:p>|<w:p/>", xml, flags=re.S)
    return "\n".join(html.unescape("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))) for p in paras)


COLS = {"conv": ("conversation", "conversation_id", "call_id", "chat_id", "id", "разговор", "звонок", "id разговора",
                 "id звонка", "диалог", "номер звонка"),
        "date": ("date", "datetime", "time", "timestamp", "дата", "время", "дата и время"),
        "speaker": ("speaker", "role", "author", "from", "говорящий", "роль", "автор", "кто", "спикер"),
        "text": ("text", "message", "phrase", "текст", "сообщение", "реплика", "фраза")}


def read_csv(text, stem):
    first = text.splitlines()[0] if text.strip() else ""
    delim = max((";", ",", "\t"), key=first.count)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if len(rows) < 2:
        raise Skip("в таблице нет строк с репликами")
    head = [h.strip().lower() for h in rows[0]]
    col = {k: next((i for i, h in enumerate(head) if h in names), None) for k, names in COLS.items()}
    if col["speaker"] is None or col["text"] is None:
        raise Skip("в таблице не нашёл колонок «говорящий» и «текст». Нужны заголовки вроде "
                   "«Разговор;Дата;Говорящий;Текст»")
    groups = defaultdict(list)
    for r in rows[1:]:
        if len(r) <= max(v for v in col.values() if v is not None):
            continue
        cid = r[col["conv"]].strip() if col["conv"] is not None else stem
        groups[cid].append({"speaker": r[col["speaker"]].strip() or "—", "text": r[col["text"]].strip(),
                            "ts": parse_date(r[col["date"]]) if col["date"] is not None else None})
    return [{"title": cid, "turns": [t for t in ts if t["text"]]} for cid, ts in groups.items()]


def read_file(path, rel):
    """Файл → список разговоров. Skip — не разобран, с причиной."""
    suf = path.suffix.lower()
    raw = path.read_bytes()
    name = pathlib.Path(rel).name
    stem = path.stem if name != "result.json" else (path.parent.name if path.parent != SRC else "Telegram")
    if suf == ".zip":
        try:
            z = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile:
            raise Skip("архив повреждён или это не zip")
        txt = [n for n in z.namelist() if n.lower().endswith(".txt")]
        if not txt:
            raise Skip("в архиве нет текстового файла переписки")
        turns = read_whatsapp(decode(z.read(txt[0])))
        if len(turns) < 2:
            raise Skip("архив без переписки WhatsApp")
        title = re.sub(r"^(WhatsApp Chat - |Чат WhatsApp с |Чат WhatsApp - )", "", path.stem)
        return [{"format": "whatsapp", "kind": "chat", "channel": "whatsapp", "title": title, "turns": turns}]
    if suf == ".json":
        try:
            data = json.loads(decode(raw))
        except json.JSONDecodeError:
            raise Skip("JSON не читается — это точно экспорт Telegram (result.json)?")
        chats = read_telegram(data, stem)
        if not chats:
            raise Skip("в JSON нет сообщений Telegram")
        return [{"format": "telegram", "kind": "chat", "channel": "telegram", **c} for c in chats]
    if suf == ".csv":
        return [{"format": "csv", "kind": "call", "channel": None, **c} for c in read_csv(decode(raw), path.stem) if c["turns"]]
    if suf in (".vtt", ".srt"):
        turns, sec = read_subtitles(decode(raw))
        if len(turns) < 2:
            raise Skip("в субтитрах меньше двух реплик")
        return [{"format": suf[1:], "kind": "call", "channel": None, "title": path.stem, "turns": turns,
                 "duration_min": round(sec / 60) if sec else None}]
    if suf in (".txt", ".md", ".docx", ""):
        text = read_docx(raw) if suf == ".docx" else decode(raw)
        wa = read_whatsapp(text)
        if len(wa) >= 2:
            return [{"format": "whatsapp", "kind": "chat", "channel": "whatsapp",
                     "title": re.sub(r"^(WhatsApp Chat - |Чат WhatsApp с |Чат WhatsApp - )", "", path.stem), "turns": wa}]
        turns, sec = read_transcript(text)
        if len({t["speaker"] for t in turns}) >= 2:
            return [{"format": "docx" if suf == ".docx" else "transcript", "kind": "call", "channel": None,
                     "title": path.stem, "turns": turns, "duration_min": round(sec / 60) if sec else None,
                     "head_date": date_in_text(text)}]
        raise Skip("не нашёл реплик с именами говорящих — похоже на заметки или текст без разметки")
    raise Skip({".pdf": "pdf не читаю — скопируйте текст в .txt", ".mp3": "аудио не расшифровываю — нужна расшифровка",
                ".m4a": "аудио не расшифровываю — нужна расшифровка", ".ogg": "аудио не расшифровываю — нужна расшифровка",
                ".wav": "аудио не расшифровываю — нужна расшифровка", ".opus": "аудио не расшифровываю — нужна расшифровка",
                ".jpg": "картинку не читаю", ".png": "картинку не читаю", ".xlsx": "Excel сохраните как CSV (UTF-8)"
                }.get(suf, f"формат {suf or 'без расширения'} не знаю"))


def files():
    out = []
    for p in sorted(SRC.rglob("*")):
        rel = p.relative_to(SRC).as_posix()
        if not p.is_file() or rel in OURS or rel.startswith("_done/") or any(x.startswith(".") for x in rel.split("/")):
            continue
        if "/" in rel and p.suffix.lower() != ".json" and re.match(r"ChatExport", rel):
            continue                                            # фото и файлы из папки экспорта Telegram
        out.append((p, rel))
    return out


# ─────────────────────────── scan ───────────────────────────

def profile():
    p = ROOT / "active" / "profile.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def company_words(P):
    """Слова названия своей компании: реплики с ними — со стороны продавца."""
    if not P:
        return []
    names = [P.get("company", "")] + list(P.get("brand_words") or [])
    return sorted({w.lower() for n in names for w in re.findall(r"[\wёЁ]{3,}", n)
                   if w.lower() not in {"тоо", "ооо", "компания", "group", "групп", "kz", "llp"}})


LAT = [("shch", "щ"), ("zh", "ж"), ("kh", "х"), ("ch", "ч"), ("sh", "ш"), ("ya", "я"), ("yu", "ю"), ("ye", "е"),
       ("yo", "е"), ("ts", "ц"), ("a", "а"), ("b", "б"), ("v", "в"), ("g", "г"), ("d", "д"), ("e", "е"), ("z", "з"),
       ("i", "и"), ("y", "и"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("r", "р"),
       ("s", "с"), ("t", "т"), ("u", "у"), ("f", "ф"), ("h", "х"), ("c", "к"), ("q", "к"), ("w", "в"), ("x", "кс"),
       ("j", "дж")]


def norm(name):
    """Имя для сравнения: «Aigul Zhumabayeva» и «Айгуль Жумабаева» — одно и то же.
    Латиница переводится в кириллицу, мягкие знаки и й/ы/ё/я сводятся к одному виду."""
    t = (name or "").lower()
    for a, b in LAT:
        t = t.replace(a, b)
    for a, b in (("ь", ""), ("ъ", ""), ("й", "и"), ("ы", "и"), ("ё", "е"), ("э", "е"), ("я", "а"), ("ю", "у")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def contains(a, b):
    """Имя a целиком входит в имя b — с учётом письменности."""
    return bool(re.search(r"(?<![\w])" + re.escape(norm(a)) + r"(?![\w])", norm(b)))


def glue_names(convs):
    """«Асель» и «Асель Нурланова» — один человек, только если полное имя
    с таким началом одно. Два полных имени — не склеиваем: не угадать, кто из них."""
    full = sorted({sp for c in convs for sp in c["speakers"] if len(sp.split()) > 1})
    canon = {}
    for sp in sorted({sp for c in convs for sp in c["speakers"]}):
        if " " not in sp and not GENERIC.match(sp.lower()):
            cand = [f for f in full if f.split()[0].lower() == sp.lower()]
            if len(cand) == 1:
                canon[sp] = cand[0]
    for c in convs:
        for t in c["turns"]:
            t["speaker"] = canon.get(t["speaker"], t["speaker"])
        c["speakers"] = dict(Counter(t["speaker"] for t in c["turns"]))
    return canon


def strong_managers(convs):
    """Менеджер ведёт разных клиентов: он есть хотя бы в двух разговорах
    с непересекающимися собеседниками. Клиент сделки говорит в звонке и в
    переписке с одним и тем же менеджером, участник встречи — в одном разговоре."""
    seen = defaultdict(list)
    for c in convs:
        for sp in c["speakers"]:
            seen[sp].append(frozenset(c["speakers"]) - {sp})
    out = []
    for sp, others in seen.items():
        if GENERIC.match(sp.lower()) or re.search(CLIENT_HINT, sp.lower()) or sp == "—":
            continue
        if any(not (a & b) for i, a in enumerate(others) for b in others[i + 1:]):
            out.append(sp)
    return sorted(out)


def guess_roles(c, managers, words):
    """Роль каждого говорящего в этом разговоре: id менеджера или client.
    Метка одна на файл, а не на весь корпус: «Спикер 1» во входящем звонке —
    менеджер, в исходящем — клиент."""
    by_name = {v: k for k, v in managers.items()}
    by_norm = {norm(v): k for k, v in managers.items()}
    for sp in c["speakers"]:
        if sp not in by_name and norm(sp) in by_norm:
            by_name[sp] = by_norm[norm(sp)]
    text_of = defaultdict(str)
    for t in c["turns"]:
        text_of[t["speaker"]] += " " + t["text"].lower()
    roles, seller = {}, []
    for sp in c["speakers"]:
        low = sp.lower()
        if sp in by_name:
            roles[sp] = by_name[sp]
        elif re.search(CLIENT_HINT, low):
            roles[sp] = "client"
        elif re.search(MANAGER_HINT, low) or (words and any(w in text_of[sp] for w in words)):
            seller.append(sp)
    if not any(r != "client" for r in roles.values()) and not seller and len(c["speakers"]) == 2:
        q = Counter()
        for i, t in enumerate(c["turns"]):
            q[t["speaker"]] += t["text"].count("?") * 2 + (1 if i == 0 else 0)
        free = [sp for sp, _ in q.most_common() if sp not in roles]
        if free:
            seller.append(free[0])
    first_names = {v.split()[0].lower(): k for k, v in managers.items()}
    first_names.update({norm(v.split()[0]): k for k, v in managers.items()})
    for sp in seller:
        # «Нуржан РОП», «Менеджер Айгуль»: имя без слова-роли
        base = re.sub(MANAGER_HINT, "", sp, flags=re.I).strip(" -:()·,")
        if base and not GENERIC.match(sp.lower()) and sp != "—":
            known = by_name.get(sp) or next((k for k, v in managers.items()
                                             if base.lower() in (v.lower(), v.split()[0].lower())), None)
            mid = known or f"m{len(managers) + 1}"
            managers.setdefault(mid, sp); by_name.setdefault(sp, mid)
            roles[sp] = mid
            continue
        # «Спикер 2: …Это Айгуль, компания Qazaq Pack» — менеджер по имени в представлении.
        # Сначала первая реплика: дальше менеджер называет и клиента, «Асель, здравствуйте».
        own = [t["text"].lower() for t in c["turns"] if t["speaker"] == sp]
        find = lambda txt: [mid for fn, mid in first_names.items()
                            if re.search(r"(?<![\w])" + re.escape(fn) + r"(?![\w])", txt)]
        hit = find(own[0] if own else "")
        if len(hit) != 1:
            hit = find(" ".join(own)[:300])
        roles[sp] = hit[0] if len(hit) == 1 else ("m?" if len(managers) != 1 else next(iter(managers)))
    for sp in c["speakers"]:
        roles.setdefault(sp, "client")
    return roles


BIZ = ("заказ", "постав", "цен", "кп", "коммерческ", "счёт", "счет", "оплат", "договор", "₸", "тенге", "скидк",
       "расчёт", "расчет", "отгруз", "образц", "парти", "прайс", "объём", "объем", "срок", "доставк", "склад", "тонн")


def business(c, words, P):
    """Рабочий ли это чат: звучит своя компания, продукт или деньги и сроки.
    В полном архиве Telegram лежат «Мама» и «Избранное» — им в базе не место."""
    text = " ".join(t["text"].lower() for t in c["turns"])
    product = {w.lower()[:5] for w in re.findall(r"[\wёЁ]{5,}", (P or {}).get("what_we_sell", ""))}
    return any(w in text for w in words) or any(w in text for w in product) or any(w in text for w in BIZ)


TITLE_STOP = {"звонок", "звонки", "встреча", "созвон", "входящий", "исходящий", "чат", "whatsapp", "chat", "teams",
              "zoom", "meet", "транскрипт", "расшифровка", "запись", "заметки", "короткий", "телефония", "с", "со",
              "по", "после", "и", "call", "meeting", "transcript", "notes", "telegram", "result", "export",
              "chatexport", "роп", "итоги", "разговор", "переписка", "demo", "демо", "wa", "ios", "android",
              "en", "ru", "kz", "backup", "копия", "copy", "new", "новый", "final", "финал"}


def title_lead(title, seller=()):
    """«2026-09-15_звонок_Мега_Склад» → «Мега Склад»: имя сделки из имени файла.
    Слова своей компании выбрасываются: «Нур Фарм × Qazaq Pack» → «Нур Фарм»."""
    t = re.sub(r"(20\d\d[-_.]\d\d[-_.]\d\d|\d\d[-_.]\d\d[-_.]20\d\d)", " ", title or "")
    words = [w for w in re.split(r"[\s_\-.·×]+", t) if w and w.lower() not in TITLE_STOP and not w.isdigit()]
    words = [w for w in words if not re.match(r"^(call|chat)\d*$|^\d+h$", w.lower()) and w.lower() not in seller]
    return " ".join(words) if words and any(len(w) > 2 for w in words) else None


def merge_leads(conv_map, only):
    """Одна сделка под разными именами склеивается:
    «Ерлан Мега Склад» → «Мега Склад» (впереди имя человека),
    «Каспий» → «Каспий Трейд» (начало полного названия),
    «Erlan Mega Sklad» → «Мега Склад» (другая письменность).
    Опорой служат все сделки, переименовываются только разговоры из only —
    то, что уже проверено, не трогается."""
    for _ in range(5):
        cnt = Counter(m["lead"] for m in conv_map.values() if not m["exclude"])
        ren = {}
        for a in cnt:
            for b in cnt:
                if a == b or a in ren or b in ren or len(norm(a)) >= len(norm(b)) or not contains(a, b):
                    continue
                if norm(b).endswith(norm(a)):
                    ren[b] = a
                elif norm(b).startswith(norm(a)):
                    ren[a] = b
                else:
                    ren[a if cnt[b] >= cnt[a] else b] = b if cnt[b] >= cnt[a] else a
        changed = False
        for k in only:
            m = conv_map[k]
            if m["lead"] in ren:
                m["lead"] = ren[m["lead"]]; changed = True
        if not changed:
            return


def mention_leads(conv_map, convs):
    """Сделка без имени («call_101») берётся из текста, если в нём звучит ровно
    одна уже известная сделка: «Да, это Ерлан, Мега Склад»."""
    known = sorted({m["lead"] for m in conv_map.values() if not m["exclude"] and not m.get("_weak")},
                   key=lambda x: len(norm(x)), reverse=True)
    for c in convs:
        m = conv_map[c["key"]]
        if not m.get("_weak"):
            continue
        text = " ".join(t["text"] for t in c["turns"])
        hit = [n for n in known if contains(n, text)]
        if len(hit) == 1:
            m["lead"] = hit[0]


def person_to_company(conv_map, convs, only):
    """Сделка на имя человека («Асель Нурланова») — это компания, если у того же
    менеджера клиент этой компании представляется тем же именем: «Это Асель,
    закупщик Тенгри Фуд». Кандидат должен быть ровно один."""
    by_key = {c["key"]: c for c in convs}
    mgrs_of = lambda m: {r for r in m["speakers"].values() if r != "client"}
    for person in {m["lead"] for k, m in conv_map.items() if not m["exclude"]}:
        own = [m for k, m in conv_map.items() if m["lead"] == person and not m["exclude"] and k in only]
        if not own:
            continue
        if len(person.split()) < 2 or not any(person in m["speakers"] and m["speakers"][person] == "client" for m in own):
            continue
        mgrs = set().union(*(mgrs_of(m) for m in own))
        first = person.split()[0].lower()
        cand = set()
        for k, m in conv_map.items():
            if m["exclude"] or m["lead"] == person or not (mgrs_of(m) & mgrs):
                continue
            said = " ".join(t["text"].lower() for t in by_key.get(k, {"turns": []})["turns"]
                            if m["speakers"].get(t["speaker"]) == "client")
            if re.search(r"(?<![\w])" + re.escape(first) + r"(?![\w])", said):
                cand.add(m["lead"])
        if len(cand) == 1:
            to = cand.pop()
            for m in own:
                m["lead"] = to


def cmd_scan(_):
    found = files()
    if not found:
        sys.exit("В data/import/ нет файлов. Сложите туда расшифровки звонков, экспорт чатов или субтитры встреч — "
                 "что подойдёт, в docs/import.md")
    convs, skipped = [], []
    for path, rel in found:
        try:
            got = read_file(path, rel)
        except Skip as e:
            skipped.append((rel, str(e))); continue
        except Exception as e:
            skipped.append((rel, f"не прочитался: {e.__class__.__name__}")); continue
        base_date = date_from_name(rel)
        for i, c in enumerate(got):
            c["file"] = rel
            c["key"] = rel if len(got) == 1 else f"{rel}#{c['title'] or i + 1}"
            ts = [t["ts"] for t in c["turns"] if t.get("ts")]
            head = c.pop("head_date", None)
            start = min(ts) if ts else base_date or head or datetime.fromtimestamp(path.stat().st_mtime)
            c["date"] = start.isoformat(timespec="minutes")
            c["date_end"] = (max(ts) if ts else start).isoformat(timespec="minutes")
            c["dated"] = bool(ts or base_date or head)
            for t in c["turns"]:
                t["ts"] = t["ts"].isoformat(timespec="minutes") if t.get("ts") else None
            c["speakers"] = dict(Counter(t["speaker"] for t in c["turns"]))
            convs.append(c)
    glue_names(convs)
    PARSED.write_text(json.dumps(convs, ensure_ascii=False, indent=1), encoding="utf-8")

    P = profile()
    words = company_words(P)
    old = json.loads(MAPPING.read_text(encoding="utf-8")) if MAPPING.exists() else {}
    managers = dict(old.get("managers") or {})              # id → имя, заполненное не теряется
    for sp in strong_managers(convs):
        if sp not in managers.values():
            managers[f"m{len(managers) + 1}"] = sp
    oldc = old.get("conversations") or {}
    conv_map, telegram = {}, []
    for c in convs:
        prev = oldc.get(c["key"], {})
        roles = guess_roles(c, managers, words)
        roles.update({k: v for k, v in (prev.get("speakers") or {}).items() if k in c["speakers"]})
        client = [sp for sp, r in roles.items() if r == "client" and not GENERIC.match(sp.lower()) and sp != "—"]
        # сделка: из имени файла или чата, иначе названный клиент, иначе как есть
        named = title_lead(c["title"], words)
        lead = prev.get("lead") or named or (client[0] if len(client) == 1 else c["title"])
        personal = c.get("tg_type") in ("saved_messages", "public_channel", "private_channel") or \
                   (c["format"] == "telegram" and not business(c, words, P))
        weak = not prev.get("lead") and not named and len(client) != 1
        conv_map[c["key"]] = {
            "title": c["title"], "date": prev.get("date") or c["date"], "kind": c["kind"],
            "preview": " / ".join(f"{t['speaker']}: {t['text'][:60]}" for t in c["turns"][:2]),
            "speakers": roles, "lead": lead, "stage": prev.get("stage"), "outcome": prev.get("outcome") or "",
            "exclude": prev.get("exclude", True if personal else False), "_weak": weak}
        if c["format"] == "telegram":
            telegram.append((c["title"], conv_map[c["key"]]["exclude"]))
    auto = {k for k in conv_map if not (oldc.get(k) or {}).get("lead")}   # заполненное раньше не трогаем
    merge_leads(conv_map, auto)
    mention_leads(conv_map, [c for c in convs if c["key"] in auto])
    merge_leads(conv_map, auto)
    person_to_company(conv_map, convs, auto)
    for m in conv_map.values():
        m.pop("_weak", None)
    leads = dict(old.get("leads") or {})
    for m in conv_map.values():
        if not m["exclude"]:
            leads.setdefault(m["lead"], {"result": None, "value_kzt": None})
    stages = [s["id"] for s in (P or {}).get("funnel", [])]
    mapping = {
        "_как_заполнять": (
            "managers — id → имя. Один человек — один id: если его зовут в разных файлах по-разному, "
            "в speakers этих разговоров ставьте один и тот же id. "
            "conversations — ключ это файл (и чат внутри файла), при новых файлах он не сдвигается. "
            "speakers: кто в ЭТОМ разговоре менеджер (id) и кто client; m? — менеджер, но не ясно какой. "
            "lead — компания или клиент: одинаковое имя склеивает разговоры в одну сделку. "
            "stage — id этапа из _этапы или null (по порядку). date — поправьте, если в файле не было даты. "
            "exclude: true — разговор не про продажи (личный чат, Избранное). "
            "leads — итог сделки: result won/lost/null и value_kzt."),
        "_этапы": {s["id"]: s["label"] for s in (P or {}).get("funnel", [])},
        "managers": managers, "conversations": conv_map, "leads": leads}
    MAPPING.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Разобрано {len(convs)} разговоров из {len(found) - len(skipped)} файлов:")
    for fmt, n in Counter(c["format"] for c in convs).most_common():
        print(f"  {fmt:<11} {n}")
    if skipped:
        print(f"\nНе разобраны ({len(skipped)}) — агент приводит их к виду «Имя: реплика» в .txt, "
              f"а оригинал переносит в data/import/_done/:")
        for rel, why in skipped:
            print(f"  {rel}: {why}")
    print(f"\nМенеджеры: {', '.join(f'{k} {v}' for k, v in managers.items()) or 'не нашёл'}")
    unsure = [k for k, m in conv_map.items() if "m?" in m["speakers"].values()]
    if unsure:
        print(f"Не ясно, какой менеджер говорит ({len(unsure)}): " + "; ".join(unsure[:6]) + (" …" if len(unsure) > 6 else ""))
    nodate = [c["key"] for c in convs if not c["dated"]]
    if nodate:
        print(f"Без даты — стоит дата файла, поправьте поле date ({len(nodate)}): " + "; ".join(nodate[:5]))
    if telegram:
        print("Чаты из Telegram — проверьте, что личные исключены (exclude: true):")
        for t, ex in telegram:
            print(f"  {'✗ исключён' if ex else '· в базе  '}  {t}")
    if not P:
        print("\nНет active/profile.json — до build пройдите окна шага 0: нужны воронка и название компании.")
    print("\nПроверьте data/import/_mapping.json, потом: python3 scripts/import_data.py build")


# ─────────────────────────── build ───────────────────────────

def stale_outputs():
    """Разборы шагов 1-4 относятся к прежней базе: id совпадают, а люди и сделки — другие."""
    names = ["scores.js", "aggregates.js", "coach.js", "enrich.js", "deep.js", "index.html", ".blocks.json", ".demo.json"]
    have = [n for n in names if (CAB / n).exists()]
    if not have:
        return None
    dst = ROOT / "active" / "before-import" / datetime.now().strftime("%Y%m%d-%H%M%S")
    dst.mkdir(parents=True, exist_ok=True)
    for n in have:
        shutil.move(str(CAB / n), str(dst / n))
    return dst


def cmd_build(a):
    if not PARSED.exists() or not MAPPING.exists():
        sys.exit("Сначала разбор: python3 scripts/import_data.py scan")
    P = profile()
    if not P or not P.get("funnel"):
        sys.exit("Нет active/profile.json с воронкой. Пройдите окна шага 0, генерацию пропустите — база будет из записей.")
    convs = {c["key"]: c for c in json.loads(PARSED.read_text(encoding="utf-8"))}
    mp = json.loads(MAPPING.read_text(encoding="utf-8"))
    stages = [s["id"] for s in P["funnel"]]
    working = stages[:-2] if len(stages) > 2 else stages
    b2c = P.get("audience", "b2c" if P.get("type") == "flow" else "b2b") == "b2c"
    managers = mp.get("managers") or {}
    conv_map = mp.get("conversations") or {}

    problems = []
    for key, m in conv_map.items():
        if m.get("exclude") or key not in convs:
            continue
        ids = [r for r in (m.get("speakers") or {}).values() if r != "client"]
        if not ids:
            problems.append(f"{key}: не указан менеджер — в speakers у кого-то должен стоять id")
        elif "m?" in ids:
            problems.append(f"{key}: «m?» — впишите id менеджера из managers")
        elif any(r not in managers for r in ids):
            problems.append(f"{key}: id {', '.join(r for r in ids if r not in managers)} нет в managers")
        if m.get("stage") and m["stage"] not in stages:
            problems.append(f"{key}: этапа «{m['stage']}» нет в воронке. Есть: {', '.join(stages)}")
    for lead, v in (mp.get("leads") or {}).items():
        if (v or {}).get("result") not in (None, "", "won", "lost"):
            problems.append(f"сделка «{lead}»: result — won, lost или null")
    if problems:
        print("Сопоставление не готово, база не собрана:")
        for p in problems[:30]:
            print("  " + p)
        sys.exit(1)

    by_lead = defaultdict(list)
    for key, m in conv_map.items():
        if not m.get("exclude") and key in convs:
            by_lead[(m.get("lead") or convs[key]["title"]).strip()].append((convs[key], m))
    calls, chats, leads = [], [], []
    for li, (lead_name, items) in enumerate(sorted(by_lead.items()), 1):
        items.sort(key=lambda x: x[1].get("date") or x[0]["date"])
        lid, owners = f"l{li:03d}", Counter()
        for n, (c, m) in enumerate(items):
            roles = m["speakers"]
            stage = m.get("stage") or working[min(n, len(working) - 1)]
            mid = next((roles[t["speaker"]] for t in c["turns"] if roles.get(t["speaker"], "client") != "client"), None)
            owners[mid] += 1
            date = m.get("date") or c["date"]
            turns = [{"who": "manager" if roles.get(t["speaker"], "client") != "client" else "client", "text": t["text"],
                      **({"ts": t["ts"]} if c["kind"] == "chat" and t.get("ts") else {})} for t in c["turns"]]
            if c["kind"] == "chat":
                chats.append({"id": f"ch{len(chats) + 1:03d}", "channel": c.get("channel") or "переписка",
                              "manager_id": mid, "lead_id": lid, "stage": stage, "imported": True, "source_key": c["key"],
                              "date_start": date, "date_end": max(date, c["date_end"]), "messages_count": len(turns),
                              "outcome": m.get("outcome") or "", "messages": turns})
            else:
                calls.append({"id": f"c{len(calls) + 1:03d}", "date": date, "manager_id": mid, "lead_id": lid,
                              "stage": stage, "direction": "inbound" if re.search(r"входящ|inbound", c["file"].lower()) else "outbound",
                              "duration_min": c.get("duration_min") or max(2, round(len(turns) * 0.6)),
                              "turns": len(turns), "outcome": m.get("outcome") or "", "imported": True,
                              "source_key": c["key"], "transcript": turns})
        info = (mp.get("leads") or {}).get(lead_name) or {}
        res = info.get("result")
        last = items[-1][1].get("stage")
        stage = stages[-2] if res == "won" else stages[-1] if res == "lost" else last or working[min(len(items) - 1, len(working) - 1)]
        owner = owners.most_common(1)[0][0]
        leads.append({"id": lid, "company": lead_name, "contact": lead_name if b2c else "", "source": "импорт",
                      "created": min((m.get("date") or c["date"]) for c, m in items)[:10], "stage": stage,
                      "value_kzt": info.get("value_kzt") or 0, "next_step": None, "owner": owner, "manager_id": owner})

    out = {"profile": {"id": "own", "title": P["company"], "company": P["company"], "what_we_sell": P.get("what_we_sell", ""),
                       "type": "b2c" if b2c else "b2b", "crm": P.get("crm", "none"), "synthetic": False, "imported": True,
                       "stages": stages, "stage_labels": {s["id"]: s["label"] for s in P["funnel"]}, "funnel": P["funnel"]},
           "managers": [{"id": k, "name": v, "role": "Менеджер"} for k, v in managers.items()],
           "calls": sorted(calls, key=lambda c: c["date"]), "chats": sorted(chats, key=lambda c: c["date_start"]),
           "leads": leads}
    OWN.mkdir(parents=True, exist_ok=True)
    (OWN / "imported.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.top_up:
        out = top_up(out, a.top_up)
    (OWN / "dataset.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    moved = stale_outputs()

    real = sum(1 for x in out["calls"] + out["chats"] if x.get("imported"))
    synth = len(out["calls"]) + len(out["chats"]) - real
    excluded = sum(1 for m in conv_map.values() if m.get("exclude"))
    print(f"✓ База собрана: {real} ваших разговоров" + (f" и {synth} синтетических" if synth else "") +
          f", {len(out['leads'])} сделок, {sum(1 for m in out['managers'] if not m.get('synthetic'))} менеджеров"
          + (f", исключено {excluded}" if excluded else "") + " → data/own/dataset.json")
    if real < 20 and not synth:
        print("  Разговоров мало для закономерностей. Догенерировать до рабочего объёма: "
              "python3 scripts/import_data.py build --top-up 200")
    if moved:
        print(f"  Разборы прежней базы перенесены в {moved.relative_to(ROOT)}: пройдите шаги 1-4 заново.")
    print("  Дальше: в cabinet/config.js profile: \"own\", затем python3 scripts/build_data.py и шаг 1")


def top_up(base, target):
    """Догенерация до target разговоров всего. Синтетические менеджеры и
    сделки — отдельные и помечены: оценки ваших людей считаются только по их
    разговорам, а в кабинете синтетику не перепутать со своими данными."""
    real = len(base["calls"]) + len(base["chats"])
    need = target - real
    if need <= 0:
        print(f"  В базе уже {real} разговоров — догенерация до {target} не нужна.")
        return base
    calls, chats = max(1, round(need * 0.8)), max(0, need - max(1, round(need * 0.8)))
    with tempfile.TemporaryDirectory() as tmp:
        dst = pathlib.Path(tmp) / "synthetic.json"
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_participant.py"),
                            str(ROOT / "active" / "profile.json"), "--calls", str(calls), "--chats", str(chats),
                            "--out", str(dst)], capture_output=True, text=True)
        if r.returncode:
            last = [x for x in (r.stdout + r.stderr).strip().splitlines() if x.strip()][-1:]
            sys.exit("Догенерация не получилась — профиль компании неполный. Что сказал генератор:\n  " + "\n  ".join(last) +
                     "\nПроверьте профиль: python3 scripts/generate_participant.py --validate active/profile.json")
        syn = json.loads(dst.read_text(encoding="utf-8"))
    real_names = {l["company"].lower() for l in base["leads"]}
    ids = {}
    for m in syn["managers"]:
        ids[m["id"]] = "s" + m["id"]
        m.update(id="s" + m["id"], name=m["name"] + " · синтетика", synthetic=True)
    for l in syn["leads"]:
        l["id"] = "s" + l["id"]
        for f in ("owner", "manager_id"):
            if l.get(f): l[f] = ids.get(l[f], l[f])
        if l.get("company", "").lower() in real_names:
            l["company"] += " · синтетика"
        l["synthetic"] = True
    for kind, prefix in (("calls", "sc"), ("chats", "sch")):
        for x in syn[kind]:
            x.update(id=prefix + re.sub(r"^\D+", "", x["id"]), lead_id="s" + x["lead_id"],
                     manager_id=ids.get(x["manager_id"], x["manager_id"]), synthetic=True)
    base = dict(base)
    base["managers"] = base["managers"] + syn["managers"]
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
    p.add_argument("--top-up", type=int, default=0, help="догенерировать до стольких разговоров всего")
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
