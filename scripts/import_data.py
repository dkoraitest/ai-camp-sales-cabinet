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

import argparse, csv, html, io, itertools, json, pathlib, re, shutil, subprocess, sys, tempfile, zipfile
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
# Служебная запись мессенджера — это сообщение целиком, а не слово внутри живого:
# «вижу пропущенный звонок от вас» — сообщение клиента, «Пропущенный звонок» — нет.
SERVICE_RX = re.compile(
    r"^\W*<?\s*(без медиафайлов|медиафайл отсутствует|media omitted|изображение отсутствует|image omitted|"
    r"видео отсутствует|video omitted|аудиофайл отсутствует|audio omitted|стикер отсутствует|sticker omitted|"
    r"gif omitted|gif отсутствует|документ отсутствует|document omitted|контакт отсутствует|contact card omitted|"
    r"(данное |это )?сообщение удалено|this message was deleted|you deleted this message|вы удалили это сообщение|"
    r"пропущенный (аудио|видео)?звонок|missed (voice|video) call|null)\s*>?\W*$", re.I)
NOTICE = ("сообщения и звонки защищены сквозным шифрованием", "messages and calls are end-to-end encrypted")
# Реплика живого разговора: вопрос, обращение, «я/мы/вы», приветствие, «да/нет».
# В заметках строки безличные: «Статус: ждёт расчёт».
TALK = re.compile(r"\?|(?<![\w])(я|мы|вы|вас|вам|нам|нас|мне|меня|ты|тебя|у нас|у вас|здравствуй\w*|добр\w+ (день|утро|вечер)|"
                  r"привет|спасибо|алло|да|нет|хорошо|давайте|понял\w*|i|we|you|hello|hi|thanks|yes|no|ok)(?![\w])", re.I)
MEDIA = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".mp4", ".mov", ".webm", ".tgs", ".svg"}
AUDIO = {".ogg", ".opus", ".oga", ".m4a", ".mp3", ".wav", ".aac", ".amr"}


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
    t = clean(text).strip()
    return bool(SERVICE_RX.match(t)) or t.lower().lstrip("\u200e ").startswith(NOTICE)


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
                        "tg_type": ch.get("type"), "chat_id": ch.get("id"), "turns": turns})
    return out


LABEL = re.compile(r"^\s*(?:\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s+)?"          # [00:01:23] перед именем
                   r"([^\s:#>*_\-][^:]{0,40}?)"                               # имя или роль
                   r"(?:\s*\((\d{1,2}:\d{2}(?::\d{2})?)\))?\s*:\s+(.+)$")     # (00:01:23) после имени
HEADER = re.compile(r"^\s*([^\d\s:][^:\t]{0,40}?)(?:\s{2,}|\t+)(\d{1,2}:\d{2}(?::\d{2})?)\s*$")   # «Имя   0:03» — Teams, Word


def unmark(line):
    """Markdown: «**Имя:** текст» → «Имя: текст»; заголовки и цитаты — без разметки."""
    line = re.sub(r"^\s*[*_]{1,2}([^*_:]{1,40}?)[*_]{0,2}\s*:\s*[*_]{0,2}\s*", r"\1: ", line)
    return re.sub(r"^\s*>\s?", "", line)


def label_shape(label):
    """Похоже ли на имя или роль: до четырёх слов, без ссылок и цифр (кроме «Спикер 1»)."""
    l = label.strip()
    return (0 < len(l) <= 40 and len(l.split()) <= 4 and l[0].isalpha() and not l.lower().startswith(("http", "www"))
            and (not re.search(r"\d", l) or bool(GENERIC.match(l.lower()))))


def full_name(label):
    """«Нурлан Серикович», «Мадина Ахметова»: два-три слова с заглавной — так подписаны
    люди. Пометки пишутся одним словом или со строчной: «Итог», «Следующий шаг»."""
    w = label.split()
    return 2 <= len(w) <= 3 and all(x[0].isupper() and x.replace("-", "").isalpha() for x in w)


def to_secs(ts):
    p = [int(x) for x in ts.split(":")]
    return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else p[0] * 60 + p[1]


def read_transcript(text):
    """Расшифровка. Два вида разметки: «Имя: реплика» в строке или «Имя   0:03»
    отдельной строкой и реплика под ней.

    Заметки тоже бывают вида «Слово: текст», поэтому диалог узнаётся по устройству,
    а не по словарю: метки стоят у большинства строк, говорящие чередуются, в репликах
    есть вопросы, обращения, «я/мы/вы». Участник с одной репликой — тоже говорящий,
    если его строка звучит как реплика или подписана именем и фамилией."""
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
    marks = [(LABEL.match(x), x) for x in lines]
    labeled = [m for m, _ in marks if m and label_shape(m.group(2))]
    if not labeled:
        return [], None
    seq = [m.group(2).strip() for m in labeled]
    counts = Counter(seq)
    alternation = sum(1 for a, b in zip(seq, seq[1:]) if a != b) / max(1, len(seq) - 1)
    talk = sum(1 for m in labeled if TALK.search(m.group(4))) / len(labeled)
    if len(counts) < 2 or len(labeled) / len(lines) < 0.5 or alternation < 0.3 or talk < 0.3:
        return [], None                                    # заметки, а не разговор
    turns, secs = [], []
    for m, line in marks:
        ok = m and label_shape(m.group(2)) and (counts[m.group(2).strip()] >= 2 or TALK.search(m.group(4))
                                                  or GENERIC.match(m.group(2).strip().lower()) or full_name(m.group(2)))
        if ok:
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
    # табуляция и перенос живут вне <w:t>: превращаем их в текст, иначе «Именно.Плюс»
    xml = re.sub(r"<w:tab/>", "<w:t>\t</w:t>", xml)
    xml = re.sub(r"<w:br[^>]*/>", "<w:t>\n</w:t>", xml)
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
    """Файлы для разбора и что пропущено молча. В папке экспорта Telegram
    (ChatExport_…, DataExport_…) нужен только result.json, остальное — фото и видео."""
    out, media, audio = [], 0, []
    for p in sorted(SRC.rglob("*")):
        rel = p.relative_to(SRC).as_posix()
        if not p.is_file() or rel in OURS or rel.startswith("_done/") or any(x.startswith(".") for x in rel.split("/")):
            continue
        in_export = "/" in rel and ((p.parent / "result.json").exists() or re.match(r"(Chat|Data)Export", rel))
        if in_export and p.name != "result.json":
            media += 1; continue
        if p.suffix.lower() in MEDIA:
            media += 1; continue
        if p.suffix.lower() in AUDIO:
            audio.append(rel); continue
        out.append((p, rel))
    return out, media, audio


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


def strong_managers(convs):
    """Менеджер ведёт разных клиентов: он есть хотя бы в двух разговорах с
    непересекающимися собеседниками. Но клиент, у которого сделку передали от
    одного менеджера другому, тоже говорит с двумя людьми. Поэтому если два
    кандидата говорят между собой, менеджер — тот, у кого собеседников больше."""
    seen, people = defaultdict(list), defaultdict(set)
    for c in convs:
        for sp in c["speakers"]:
            seen[sp].append(frozenset(c["speakers"]) - {sp})
            people[sp] |= set(c["speakers"]) - {sp}
    cand = set()
    for sp, others in seen.items():
        if GENERIC.match(sp.lower()) or re.search(CLIENT_HINT, sp.lower()) or sp == "—":
            continue
        if any(not (a & b) for i, a in enumerate(others) for b in others[i + 1:]):
            cand.add(sp)
    for a in list(cand):
        for b in list(cand):
            if a != b and b in people[a] and a in cand and b in cand and len(people[a]) != len(people[b]):
                cand.discard(a if len(people[a]) < len(people[b]) else b)
    return sorted(cand)


SELLER_SAYS = ("отправил", "отправляю", "пришлю", "вышлю", "подготовлю", "подготовил", "посчитаю", "рассчитаю",
               "предлагаю", "предлагаем", "могу предложить", "у нас есть", "мы можем", "мы делаем", "наша компания",
               "наш склад", "наш менеджер", "отгрузим", "привезём", "sending", "we can", "our offer", "i will send",
               "i'll send", "we offer")
CLIENT_SAYS = ("жду", "пришлите", "скиньте", "сколько стоит", "сколько будет стоить", "дорого", "дешевле", "у других",
               "нам нужн", "нам надо", "what about", "how much", "send me", "too expensive", "we need")


def guess_roles(c, managers, words, people=None, notes=None):
    """Роль каждого говорящего в этом разговоре: id менеджера или client.
    Метка одна на файл, а не на весь корпус: «Спикер 1» во входящем звонке —
    менеджер, в исходящем — клиент.
    people — полные имена из всех записей по первому слову: по ним видно, чьё это
    имя без фамилии. В notes попадают роли, угаданные по одному имени."""
    by_name = {v: k for k, v in managers.items()}
    by_norm = {norm(v): k for k, v in managers.items()}
    for sp in c["speakers"]:
        if sp not in by_name and norm(sp) in by_norm:
            mid = by_norm[norm(sp)]
            by_name[sp] = mid
            if re.search(r"[а-яё]", sp.lower()) and not re.search(r"[а-яё]", managers[mid].lower()):
                managers[mid] = sp                     # показываем так, как имя пишут в компании
    for sp in c["speakers"]:
        # «Марат» без фамилии — менеджер Марат Садыков, если других Маратов в записях нет.
        # «Асель» при менеджере Асель Ким и клиентке Асель Нурлановой — не угадываем.
        if people is None or sp in by_name or len(norm(sp).split()) != 1 or GENERIC.match(sp.lower()):
            continue
        hit = [k for k, v in managers.items() if norm(v).split()[:1] == [norm(sp)]]
        if len(hit) == 1 and not people.get(norm(sp), set()) - {norm(managers[hit[0]])}:
            by_name[sp] = hit[0]
            if notes is not None:
                notes.append(f"«{sp}» → {hit[0]} {managers[hit[0]]}")
    text_of, first_of = defaultdict(str), defaultdict(list)
    for t in c["turns"]:
        text_of[t["speaker"]] += " " + t["text"].lower()
        if len(first_of[t["speaker"]]) < 2:
            first_of[t["speaker"]].append(t["text"].lower())
    roles, seller = {}, []
    for sp in c["speakers"]:
        low = sp.lower()
        if sp in by_name:
            roles[sp] = by_name[sp]
        elif re.search(CLIENT_HINT, low):
            roles[sp] = "client"
        elif re.search(MANAGER_HINT, low) or (words and any(w in " ".join(first_of[sp]) for w in words)):
            seller.append(sp)                  # своя компания — в первых репликах, так представляются
    if not any(r != "client" for r in roles.values()) and not seller and len(c["speakers"]) == 2:
        # Кто продавец, если компанию не назвали: по тому, что человек делает в разговоре.
        # Вопросы — признак продавца только в звонке: в переписке спрашивает чаще клиент.
        score = Counter()
        for t in c["turns"]:
            low = t["text"].lower()
            score[t["speaker"]] += 2 * sum(w in low for w in SELLER_SAYS) - 2 * sum(w in low for w in CLIENT_SAYS)
            if c["kind"] == "call":
                score[t["speaker"]] += low.count("?")
        free = sorted((sp for sp in c["speakers"] if sp not in roles), key=lambda sp: -score[sp])
        if len(free) == 2 and score[free[0]] > 0 and score[free[0]] > score[free[1]]:
            seller.append(free[0])
        # признаки не различают стороны — роли не выдумываем: build попросит указать менеджера
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


APPS = {"whatsapp", "telegram", "teams", "zoom", "meet", "skype", "viber", "chatexport", "dataexport", "result",
        "export", "wa", "ios", "android"}
DOC = {"чат", "звонок", "встреча", "созвон", "запись", "транскрипт", "расшифровка", "заметки", "итоги", "переписка",
       "протокол", "call", "meeting", "chat", "notes", "transcript", "recording"}


def title_lead(title, seller=()):
    """Имя сделки из имени файла: «2026-09-25_звонок_Нур_Фарм_передача» → «Нур Фарм».
    Названия компаний пишутся с заглавной, описания — со строчной, поэтому берутся
    только слова с заглавной; своя компания, программы, тип документа и роли
    («Мега_с_РОП», «Клиент») — нет."""
    t = re.sub(r"(20\d\d[-_.]\d\d[-_.]\d\d|\d\d[-_.]\d\d[-_.]20\d\d)", " ", title or "")
    words = [w for w in re.split(r"[\s_\-.·×()]+", t) if w]
    keep = [w for w in words if w[0].isupper() and not w.isdigit() and w.lower() not in APPS | DOC
            and w.lower() not in seller and not re.match(r"^(call|chat)\d*$", w.lower())
            and not re.search(MANAGER_HINT + "|" + CLIENT_HINT, w.lower())]
    return " ".join(keep) if keep and any(len(w) > 2 for w in keep) else None


def merge_leads(conv_map, convs, only):
    """Предложение, а не решение: агент сверяет каждую сделку по preview.
    Склеивается только то, за что говорят люди в разговорах:
    · имя человека перед названием компании — «Ерлан Мега Склад» → «Мега Склад»,
      если Ерлан — клиент в этих разговорах: так контакт записан в телефоне;
    · одно слово, с которого начинается ровно одно полное название — «Каспий» →
      «Каспий Трейд», если в обоих звучит один и тот же клиент.
    По одним названиям сокращение не отличить от другой компании: «Береке» и
    «Береке Шымкент» без общего клиента не склеиваются, а возвращаются подсказкой."""
    by_key = {c["key"]: c for c in convs}
    hints = {}
    for _ in range(5):
        live = [(k, m) for k, m in conv_map.items() if not m["exclude"]]
        cnt = Counter(m["lead"] for _, m in live)
        firsts, fulls, said = defaultdict(set), defaultdict(set), defaultdict(str)
        for k, m in live:
            clients = [sp for sp, r in m["speakers"].items() if r == "client" and not GENERIC.match(sp.lower())]
            for sp in clients:
                w = sp.split()
                if w and not w[0].isupper() and len(norm(w[0])) >= 3:     # «ТОО Мега» — не имя
                    firsts[m["lead"]].add(norm(w[0]))
                    if len(w) >= 2:
                        fulls[m["lead"]].add(norm(sp))
            said[m["lead"]] += " " + " ".join(clients) + " " + " ".join(
                t["text"] for t in (by_key.get(k) or {}).get("turns", []))
        ren, hints = {}, {}
        for a in cnt:
            longer = [b for b in cnt if b != a and len(norm(a)) < len(norm(b)) and contains(a, b)]
            starts = [b for b in longer if norm(b).startswith(norm(a))]
            for b in longer:
                if a in ren or b in ren:
                    continue
                extra = norm(b)[:len(norm(b)) - len(norm(a))].split() if norm(b).endswith(norm(a)) else []
                if extra:
                    if len(extra) <= 2 and extra[0] in firsts[b]:
                        ren[b] = a
                    else:
                        hints.setdefault(b, []).append(a)
                elif b in starts:
                    shared = fulls[a] & fulls[b] or any(contains(f, said[a]) for f in firsts[b])
                    if len(norm(a).split()) == 1 and len(starts) == 1 and shared:
                        ren[a] = b
                    else:                               # «Мега Склад» и «Мега Склад Астана» — филиал?
                        hints.setdefault(a, []).append(b)
        changed = False
        for k in only:
            m = conv_map[k]
            if m["lead"] in ren:
                m["lead_why"] = f"склеено: «{m['lead']}» → «{ren[m['lead']]}»"
                m["lead"] = ren[m["lead"]]; changed = True
        if not changed:
            break
    return hints


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
        hit = [n for n in hit if not any(n != o and contains(n, o) for o in hit)]   # «Мега» внутри «Мега Склад»
        if len(hit) == 1:
            m["lead"], m["lead_why"] = hit[0], f"в разговоре упоминается «{hit[0]}»"


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
        if not any(person in m["speakers"] and m["speakers"][person] == "client" for m in own):
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
                m["lead"], m["lead_why"] = to, f"клиент «{person}» представлялся от «{to}» в другом разговоре"


def work_chats(conv_map, only):
    """Рабочий чат бывает и без слов про деньги и сроки: «Удобно созвониться
    завтра в 11?». Он рабочий, если в его названии звучит сделка из других
    разговоров или в нём пишет клиент, который в других разговорах говорит от
    сделки. Имя без фамилии не считается: друг «Руслан» — не клиент «Руслан Ибраев»."""
    live = [m for m in conv_map.values() if not m["exclude"]]
    person = {m["lead"] for m in live for sp, r in m["speakers"].items()
              if r == "client" and norm(m["lead"]) in (norm(sp), (norm(sp).split() or [""])[0])}
    companies = sorted({m["lead"] for m in live} - person, key=lambda x: -len(norm(x)))
    client_of = defaultdict(set)
    for m in live:
        for sp, r in m["speakers"].items():
            if r == "client" and len(norm(sp).split()) >= 2:
                client_of[norm(sp)].add(m["lead"])
    back = []
    for k in only:
        m = conv_map[k]
        if not m["exclude"] or all(r == "client" for r in m["speakers"].values()):
            continue
        hit = [l for l in companies if contains(l, m["title"])]
        if hit:
            why = f"в названии чата — сделка «{hit[0]}»"
        else:
            hit = sorted(set().union(*(client_of.get(norm(sp), set()) for sp, r in m["speakers"].items()
                                       if r == "client")))
            if len(hit) != 1:
                continue
            why = f"пишет клиент сделки «{hit[0]}»"
        m["exclude"], m["lead"], m["lead_why"] = False, hit[0], why
        back.append(k)
    return back


def cmd_scan(_):
    found, media, audio = files()
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
            # два чата «Руслан» в одном архиве — разные разговоры: ключ по id чата из экспорта
            c["key"] = rel if len(got) == 1 else f"{rel}#{c.get('chat_id') or c['title'] or i + 1}"
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
    seen, dupes = {}, []
    for c in list(convs):
        fp = (c["kind"], len(c["turns"]), tuple((t["speaker"], t["text"][:80]) for t in c["turns"][:5]))
        if fp in seen:
            dupes.append((c["key"], seen[fp])); convs.remove(c)
        else:
            seen[fp] = c["key"]
    PARSED.write_text(json.dumps(convs, ensure_ascii=False, indent=1), encoding="utf-8")

    P = profile()
    words = company_words(P)
    old = json.loads(MAPPING.read_text(encoding="utf-8")) if MAPPING.exists() else {}
    managers = dict(old.get("managers") or {})              # id → имя, заполненное не теряется
    for sp in strong_managers(convs):
        if sp not in managers.values():
            managers[f"m{len(managers) + 1}"] = sp
    oldc = old.get("conversations") or {}
    # Первый проход только находит менеджеров: иначе разговор, разобранный раньше,
    # не узнал бы менеджера, который назван по имени лишь в файле ниже по списку.
    people = defaultdict(set)          # первое слово → полные имена: чьё это имя без фамилии
    for c in convs:
        for sp in c["speakers"]:
            if len(norm(sp).split()) >= 2 and not GENERIC.match(sp.lower()) and not re.search(MANAGER_HINT, sp.lower()):
                people[norm(sp).split()[0]].add(norm(sp))
    for c in convs:
        guess_roles(c, managers, words, people)
    conv_map, by_first = {}, {}
    for c in convs:
        prev = oldc.get(c["key"], {})
        notes = []
        roles = guess_roles(c, managers, words, people, notes)
        roles.update({k: v for k, v in (prev.get("speakers") or {}).items() if k in c["speakers"]})
        if notes and not prev.get("speakers"):
            by_first[c["key"]] = notes
        client = [sp for sp, r in roles.items() if r == "client" and not GENERIC.match(sp.lower()) and sp != "—"]
        # сделка: из имени файла или чата, иначе названный клиент, иначе как есть
        named = title_lead(c["title"], words)
        # в названии одно слово («Мега»), а клиент подписан полнее («Ерлан Мега Склад») — берём «Мега Склад»
        fuller = set()
        for sp in client if named and len(named.split()) == 1 else ():
            w = sp.split()
            i = next((j for j, x in enumerate(w) if norm(x) == norm(named)), None)
            tail = [] if i is None else list(itertools.takewhile(lambda x: x[0].isupper(), w[i:]))
            if len(tail) > 1:
                fuller.add(" ".join(tail))
        part = named if len(fuller) == 1 else None
        if part:
            named = fuller.pop()
        person = named and any(norm(named) == norm(sp) or norm(named) == norm(sp.split()[0]) for sp in client)
        lead = prev.get("lead") or named or (client[0] if len(client) == 1 else c["title"])
        why = "проверено раньше" if prev.get("lead") else ("имя человека — ищу компанию" if person else
              f"в названии «{part}», клиент подписан полнее" if part else
              "из названия файла или чата" if named else "клиент в разговоре" if len(client) == 1 else
              "не нашёл — укажите сделку")
        personal = c.get("tg_type") in ("saved_messages", "public_channel", "private_channel") or \
                   (c["format"] == "telegram" and not business(c, words, P))
        weak = not prev.get("lead") and (not named or person)
        conv_map[c["key"]] = {
            "title": c["title"], "date": prev.get("date") or c["date"], "kind": c["kind"],
            "preview": " / ".join(f"{t['speaker']}: {t['text'][:60]}" for t in c["turns"][:2]),
            "speakers": roles, "lead": lead, "lead_why": why, "stage": prev.get("stage"),
            "outcome": prev.get("outcome") or "",
            "exclude": prev.get("exclude", True if personal else False), "_weak": weak}
    auto = {k for k in conv_map if not (oldc.get(k) or {}).get("lead")}   # заполненное раньше не трогаем
    merge_leads(conv_map, convs, auto)
    mention_leads(conv_map, [c for c in convs if c["key"] in auto])
    hints = merge_leads(conv_map, convs, auto)
    person_to_company(conv_map, convs, auto)
    tg = [c["key"] for c in convs if c["format"] == "telegram"]
    back = work_chats(conv_map, [k for k in tg if "exclude" not in oldc.get(k, {}) and
                                 next(c for c in convs if c["key"] == k).get("tg_type") not in
                                 ("saved_messages", "public_channel", "private_channel")])
    for m in conv_map.values():
        m.pop("_weak", None)
    leads = dict(old.get("leads") or {})
    for m in conv_map.values():
        if not m["exclude"]:
            leads.setdefault(m["lead"], {"result": None, "value_kzt": None, "owner": None})
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
            "leads — итог сделки: result won/lost/null и value_kzt; owner — id ответственного, "
            "если он не тот, кто говорил с клиентом последним."),
        "_этапы": {s["id"]: s["label"] for s in (P or {}).get("funnel", [])},
        "managers": managers, "conversations": conv_map, "leads": leads}
    MAPPING.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Разобрано {len(convs)} разговоров из {len(found) - len(skipped)} файлов:")
    for fmt, n in Counter(c["format"] for c in convs).most_common():
        print(f"  {fmt:<11} {n}")
    if dupes:
        print(f"\nПовторы — одна и та же переписка дважды, взята одна ({len(dupes)}):")
        for a, b in dupes:
            print(f"  {a} = {b}")
    if media or audio:
        print(f"\nПропущены: медиафайлов {media}" + (f", аудио {len(audio)} — их нужно расшифровать в сервисе "
              f"транскрибации и положить текст" if audio else ""))
    if skipped:
        print(f"\nНе разобраны ({len(skipped)}). Заметки и итоги — не разговор: в диалог их не превращают, переносят "
              f"в data/import/_done/. Расшифровку без меток размечают «Имя: реплика» в .txt, только если ясно, кто говорит:")
        for rel, why in skipped:
            print(f"  {rel}: {why}")
    print(f"\nМенеджеры: {', '.join(f'{k} {v}' for k, v in managers.items()) or 'не нашёл'}")
    unsure = [k for k, m in conv_map.items() if "m?" in m["speakers"].values()]
    if unsure:
        print(f"Не ясно, какой менеджер говорит ({len(unsure)}): " + "; ".join(unsure[:6]) + (" …" if len(unsure) > 6 else ""))
    nobody = [k for k, m in conv_map.items() if not m["exclude"] and all(r == "client" for r in m["speakers"].values())]
    if nobody:
        print(f"Не нашёл менеджера ({len(nobody)}) — в speakers поставьте id тому, кто продаёт: " + "; ".join(nobody[:6])
              + (" …" if len(nobody) > 6 else ""))
    if by_first:
        print("Менеджер узнан по имени без фамилии — проверьте:")
        for k, n in list(by_first.items())[:6]:
            print(f"  {k}: {', '.join(n)}")
    nodate = [c["key"] for c in convs if not c["dated"]]
    if nodate:
        print(f"Без даты — стоит дата файла, поправьте поле date ({len(nodate)}): " + "; ".join(nodate[:5]))
    if tg:
        print("Чаты из Telegram — проверьте, что личные исключены (exclude: true):")
        for k in tg:
            m = conv_map[k]
            print(f"  {'✗ исключён' if m['exclude'] else '· в базе  '}  {m['title']}"
                  + (f" — {m['lead_why']}" if k in back else ""))
    if not P:
        print("\nНет active/profile.json — до build пройдите окна шага 0: нужны воронка и название компании.")
    print("\nСделки — это предложение, сверьте каждую по preview:")
    for lead in sorted({m["lead"] for m in conv_map.values() if not m["exclude"]}):
        ks = [k for k, m in conv_map.items() if m["lead"] == lead and not m["exclude"]]
        whys = sorted({conv_map[k].get("lead_why", "") for k in ks} - {""})
        print(f"  {lead} — разговоров {len(ks)}" + (f" ({'; '.join(whys)})" if whys else ""))
    live = {m["lead"] for m in conv_map.values() if not m["exclude"]}
    handed = []
    for lead in sorted(live):
        seq = [next((r for r in m["speakers"].values() if r != "client"), None)
               for m in sorted((m for m in conv_map.values() if m["lead"] == lead and not m["exclude"]),
                               key=lambda m: m["date"])]
        seq = [managers.get(x, x) for x in dict.fromkeys(x for x in seq if x and x != "m?")]
        if len(seq) > 1:
            handed.append(f"  {lead}: {' → '.join(seq)}")
    if handed:
        print("Сделку вели разные менеджеры — ответственным станет тот, кто говорил последним. "
              "Если это не так, впишите его id в owner в leads:")
        print("\n".join(handed))
    hints = {a: [b for b in bs if b in live] for a, bs in hints.items() if a in live}
    if any(hints.values()):
        print("Похожие названия без общего клиента — одна компания или разные, решите по preview:")
        for a, bs in hints.items():
            if bs:
                print(f"  «{a}» — {' или '.join(f'«{b}»' for b in bs)}?")
    print("\nПроверьте data/import/_mapping.json, потом: python3 scripts/import_data.py build")


# ─────────────────────────── build ───────────────────────────

def ensure_config(P, backup_dir):
    """Кабинет после импорта — про компанию участника. Если до этого включали демо,
    в cabinet/config.js лежит эталон демо-компании: восстанавливаем конфиг участника
    из active/before-demo/, а если его нет — собираем из профиля."""
    cfg = CAB / "config.js"
    company_of = lambda t: (re.search(r'company:\s*"([^"]*)"', t) or [None, None])[1]
    own_profile = lambda t: re.sub(r'profile:\s*"\w+"', 'profile: "own"', t, count=1)
    CAB.mkdir(exist_ok=True)
    if cfg.exists():
        text = cfg.read_text(encoding="utf-8")
        if company_of(text) == P["company"]:
            cfg.write_text(own_profile(text), encoding="utf-8")
            return None
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cfg, backup_dir / "config.js")
    for old in sorted((ROOT / "active" / "before-demo").glob("*/config.js"), reverse=True):
        text = old.read_text(encoding="utf-8")
        if company_of(text) == P["company"]:
            cfg.write_text(own_profile(text), encoding="utf-8")
            return f"конфиг «{P['company']}» восстановлен из {old.parent.relative_to(ROOT)}"
    tpl = (ROOT / "blocks" / "config.template.js").read_text(encoding="utf-8")
    funnel = [{k: v for k, v in s.items() if k in ("id", "label", "goal", "exit")} for s in P["funnel"]]
    focus = P.get("focus_stage") if P.get("focus_stage") in [s["id"] for s in P["funnel"]] else \
        (P["funnel"][1]["id"] if len(P["funnel"]) > 1 else P["funnel"][0]["id"])
    text = own_profile(tpl)
    text = re.sub(r'company:\s*"[^"]*"', "company: " + json.dumps(P["company"], ensure_ascii=False), text, count=1)
    text = re.sub(r'what_we_sell:\s*"[^"]*"', "what_we_sell: " + json.dumps(P.get("what_we_sell", ""), ensure_ascii=False), text, count=1)
    text = re.sub(r'focus_stage:\s*"[^"]*"', "focus_stage: " + json.dumps(focus), text, count=1)
    text = text.replace("funnel: [],", "funnel: " + json.dumps(funnel, ensure_ascii=False) + ",", 1)
    cfg.write_text(text, encoding="utf-8")
    return f"конфиг собран из профиля «{P['company']}»: матрица по умолчанию, вопросы к данным — на шаге 1"


def reset_telegram(backup_dir):
    """После импорта m1, m2… — другие люди. Привязки Telegram по старым id отправили
    бы разбор не тому человеку: откладываем их и просим привязать заново."""
    moved = []
    for f in (ROOT / "active" / "telegram.json", ROOT / "active" / "telegram_seen.json"):
        if f.exists():
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), str(backup_dir / f.name)); moved.append(f.name)
    js = CAB / "telegram.js"
    if js.exists():
        m = re.search(r'"bot":\s*("[^"]*"|null)', js.read_text(encoding="utf-8"))
        bot = json.loads(m.group(1)) if m else None
        js.write_text("// Сгенерировано scripts/telegram.py — руками не править.\n"
                      f"window.CABINET_TELEGRAM = {json.dumps({'bot': bot, 'links': {}}, ensure_ascii=False)};\n",
                      encoding="utf-8")
        moved.append("telegram.js: привязки")
    return moved


def stale_outputs(dst):
    """Разборы шагов 1-4 относятся к прежней базе: id совпадают, а люди и сделки — другие."""
    names = ["scores.js", "aggregates.js", "coach.js", "enrich.js", "deep.js", "index.html", ".blocks.json", ".demo.json"]
    have = [n for n in names if (CAB / n).exists()]
    if have:
        dst.mkdir(parents=True, exist_ok=True)
        for n in have:
            shutil.move(str(CAB / n), str(dst / n))
    return have


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
        if (v or {}).get("owner") and v["owner"] not in managers:
            problems.append(f"сделка «{lead}»: owner {v['owner']} нет в managers")
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
        lid, owners = f"l{li:03d}", []
        for n, (c, m) in enumerate(items):
            roles = m["speakers"]
            stage = m.get("stage") or working[min(n, len(working) - 1)]
            mid = next((roles[t["speaker"]] for t in c["turns"] if roles.get(t["speaker"], "client") != "client"), None)
            owners.append(mid)
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
        # ответственный — кто ведёт сделку сейчас: после передачи это новый менеджер
        owner = info.get("owner") or next((x for x in reversed(owners) if x), None)
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
    dst = ROOT / "active" / "before-import" / datetime.now().strftime("%Y%m%d-%H%M%S")
    moved = stale_outputs(dst)
    cfg_note = ensure_config(P, dst)
    tg = reset_telegram(dst)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_data.py")], capture_output=True, text=True)

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
        print(f"  Разборы прежней базы перенесены в {dst.relative_to(ROOT)}: пройдите шаги 1-4 заново.")
    if cfg_note:
        print(f"  {cfg_note}.")
    if tg:
        print("  Telegram: привязки сброшены — после импорта менеджеры в базе другие. Разошлите ссылки из карточек "
              "заново и выполните python3 scripts/telegram.py link --auto")
    unknown = sorted(set((mp.get("leads") or {})) - {l["company"] for l in leads})
    if unknown:
        print(f"  В leads есть сделки, которых больше нет: {', '.join(unknown)} — перенесите result и value_kzt на новое имя.")
    print("  Данные кабинета пересобраны (cabinet/data.js). Дальше: шаг 1")


# Собеседники синтетических сделок. Имена из профиля не годятся: там живые клиенты
# участника, и генератор склеил бы «Данияр Ибраев» из Данияра Абенова и Руслана Ибраева.
NEUTRAL = ((["Арман", "Ерболат", "Санжар", "Тимур", "Азамат", "Дамир", "Кайрат", "Андрей", "Сергей", "Павел"],
            ["Абдрахманов", "Жумагулов", "Касенов", "Нургалиев", "Оспанов", "Сарсенов", "Волков", "Лебедев", "Морозов"]),
           (["Айжан", "Гульмира", "Динара", "Камила", "Салтанат", "Алия", "Елена", "Ирина", "Наталья", "Светлана"],
            ["Абдрахманова", "Жумагулова", "Касенова", "Нургалиева", "Оспанова", "Сарсенова", "Волкова", "Лебедева",
             "Морозова"]))


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
    try:
        real_people = {norm(sp) for c in json.loads(PARSED.read_text(encoding="utf-8")) for sp in c["speakers"]}
    except Exception:
        real_people = set()
    P = json.loads((ROOT / "active" / "profile.json").read_text(encoding="utf-8"))
    # ни имени, ни фамилии живого человека из записей и профиля
    taken = {w for n in real_people | {norm(x) for x in P.get("contact_names", [])} |
             {norm(m.get("name", "")) for m in P.get("managers") or []} for w in n.split()}
    halves = [[f"{f} {l}" for f in firsts for l in lasts if norm(f) not in taken and norm(l) not in taken]
              for firsts, lasts in NEUTRAL]
    people = [n for h in halves for n in h] or ["Клиент Клиентов"]
    P["contact_names"] = people
    if P.get("audience", "b2c" if P.get("type") == "flow" else "b2b") == "b2c":
        P["clients"] = people                  # в B2C клиент — человек: тоже не из записей
    # в профиле — настоящая команда: «Айгуль Жумабаева · синтетика» рядом с живой Айгуль читалась бы как её оценки
    staff, seen = [], set()
    for n in [n for pair in itertools.zip_longest(*halves) for n in pair if n] or people:   # мужчина, женщина, …
        f, l = norm(n).split()
        if f not in seen and l[:5] not in seen:
            seen |= {f, l[:5]}; staff.append(n)
    for i, m in enumerate(P.get("managers") or []):
        m["name"] = staff[i % len(staff)]
    with tempfile.TemporaryDirectory() as tmp:
        dst, prof = pathlib.Path(tmp) / "synthetic.json", pathlib.Path(tmp) / "profile.json"
        prof.write_text(json.dumps(P, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_participant.py"),
                            str(prof), "--calls", str(calls), "--chats", str(chats),
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
        if l.get("contact") and norm(l["contact"]) in real_people:
            l["contact"] = f"Контакт {l['id']}"         # имя живого человека из ваших разговоров не повторяем
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
