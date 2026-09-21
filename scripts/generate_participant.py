#!/usr/bin/env python3
"""Генератор базы коммуникаций под конкретную компанию участника.

Разделение труда: смысл делает модель, объём делает код.
Модель по ответам участника заполняет profile.json (пулы реплик под его
индустрию), этот скрипт собирает из них сотни диалогов за секунды —
без ожидания, без обрывов и без расхода лимитов.

    python3 scripts/generate_participant.py --validate active/profile.json
    python3 scripts/generate_participant.py active/profile.json --calls 260 --chats 90

Результат: data/own/dataset.json + пересборка cabinet/data.js
"""

import json, random, argparse, pathlib, re, sys
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent

REQUIRED = {
    "company": str, "what_we_sell": str, "type": str,
    "funnel": list, "managers": list, "segments": list,
    "questions": dict, "product_lines": list, "value_lines": list,
    "objections": list, "objection_answers": dict, "closings": dict,
    "clients": list, "sources": list,
}
MIN_LEN = {"funnel": 4, "managers": 3, "segments": 2, "product_lines": 3,
           "value_lines": 3, "objections": 4, "clients": 12, "sources": 2}
Q_KEYS = ["situation", "pain", "qualify", "deep"]
OA_KEYS = ["counter", "justify", "avoid", "discount"]
CL_KEYS = ["strong", "mid", "weak"]

FILLER_M = ["ну", "смотрите", "так", "слушайте", "в общем", "э-э", "то есть"]
FILLER_C = ["ну", "э-э", "как сказать", "в принципе", "честно говоря"]
ACK = ["Да, удобно.", "Да, слушаю.", "Угу.", "Да-да.", "Говорите.", "Слушаю вас.",
       "Секунду... да, всё, говорите.", "Да, но недолго, у меня встреча через пятнадцать минут."]
NOISE = ["Извините, секунду... да, я тут.", "Я сейчас за рулём, но говорите.",
         "Подождите, я выйду... так, всё, слышно.", "У меня тут шумно, говорите громче."]
SHORT_ACK = ["Понятно.", "Угу.", "Ясно.", "Хорошо.", "Ага.", "Интересно."]
PRICE_Q = ["А сколько это стоит?", "Порядок цен какой?", "Сколько мы за это заплатим?",
           "И во сколько нам это обойдётся?", "Цена какая?"]
CLI_YES = ["Хорошо, договорились.", "Да, давайте.", "Идёт.", "Согласен, так и сделаем.", "Да, ставьте."]
CLI_NO = ["Я подумаю и напишу.", "Надо посоветоваться.", "Хорошо, посмотрю.",
          "Понятно, мы вернёмся к этому позже.", "Ладно, спасибо."]
# Встречные вопросы клиента — нейтральные, чтобы звучать в любом бизнесе.
# Свои можно дать в профиле полем client_questions.
CLIENT_Q = ["А как это будет работать в нашем случае?", "Как быстро сможете начать?",
            "А если у нас всё по-другому устроено?", "Кто будет с нами работать с вашей стороны?",
            "А если что-то пойдёт не так, что тогда?", "Можно сначала попробовать на небольшом объёме?",
            "А что если не подойдёт?", "Какие у вас гарантии?"]


def validate(profile):
    errs, warns = [], []
    for key, typ in REQUIRED.items():
        if key not in profile:
            errs.append(f"нет обязательного поля «{key}»"); continue
        if not isinstance(profile[key], typ):
            errs.append(f"поле «{key}» должно быть {typ.__name__}")
    for key, n in MIN_LEN.items():
        if isinstance(profile.get(key), list) and len(profile[key]) < n:
            warns.append(f"«{key}»: {len(profile.get(key, []))} элементов, желательно хотя бы {n}")
    if profile.get("type") not in ("long", "flow"):
        errs.append("«type» — это длина цикла: \"long\" (сделка идёт неделями) или \"flow\" (поток заявок, решение за дни)")
    if profile.get("audience") not in ("b2b", "b2c"):
        warns.append("нет «audience»: кому продаём — \"b2b\" (компаниям) или \"b2c\" (людям). "
                     "Это не то же самое, что длина цикла: опт с коротким циклом — это b2b и flow")
    for k in Q_KEYS:
        if k not in profile.get("questions", {}):
            errs.append(f"в «questions» нет группы «{k}»")
    for k in OA_KEYS:
        if k not in profile.get("objection_answers", {}):
            warns.append(f"в «objection_answers» нет стиля «{k}» — будет использован соседний")
    for k in CL_KEYS:
        if k not in profile.get("closings", {}):
            errs.append(f"в «closings» нет группы «{k}»")
    for i, m in enumerate(profile.get("managers", [])):
        for f in ("id", "name", "style"):
            if f not in m: errs.append(f"менеджер #{i+1}: нет поля «{f}»")
    for i, s in enumerate(profile.get("segments", [])):
        for f in ("name", "situation", "pain", "cost"):
            if f not in s: errs.append(f"сегмент #{i+1} ({s.get('name','?')}): нет поля «{f}»")
    return errs, warns


def say(who, text, p):
    if random.random() >= p: return text
    f = random.choice(FILLER_M if who == "manager" else FILLER_C) + ", "
    return f + (text[0].lower() + text[1:] if text[:1].isupper() else text)


# сколько «кругов» вопрос-ответ на этапе: на демо и переговорах разговор длиннее
STAGE_DEPTH = {0: 1, 1: 3, 2: 4, 3: 3, 4: 3, 5: 2, 6: 1}

CITIES = ["Астана", "Алматы", "Шымкент", "Караганда", "Актобе", "Атырау"]

def unique_names(base, n, suffixes=CITIES):
    """Имена клиентов не должны повторяться.

    Профиль компании даёт десяток названий, а сделок нужны сотни. Если просто
    крутить список по кругу, в таблице коммуникаций одна и та же «Мега Склад»
    встретится четырнадцать раз — и человек прочитает это как одну сделку.
    Недостающие названия — те же компании с городом или формой: «Мега Склад
    Астана», «Мега Склад Групп». Слова из разных названий не склеиваем: так
    выходило «Добрый Облако»."""
    out = list(dict.fromkeys(base))
    seen = set(out)
    forms = list(suffixes) + ["Групп", "Трейд", "Плюс", "Сервис", "KZ"]
    for extra in forms:
        for c in list(dict.fromkeys(base)):
            if len(out) >= n:
                return out[:n]
            name = f"{c} {extra}"
            if name not in seen:
                seen.add(name); out.append(name)
    i = 2
    while len(out) < n:
        out += [f"{c} {i}" for c in base]
        i += 1
    return out[:n]


def people_pool(base):
    """Имена собеседников — перекрёстное произведение имён и фамилий из профиля.

    Повторяющееся имя у разных компаний не мешает: сделку различает компания.
    А вот «Руслан Ибраев 3» в карточке сразу выдаёт генератор."""
    fem = lambda w: w.endswith(("ова", "ева", "ина", "ская", "кызы"))
    male = lambda w: w.endswith(("ов", "ев", "ин", "ский", "улы"))
    groups, pool = {}, []
    for name in base:                      # имена и фамилии не смешиваются по роду
        f, l = name.split()[0], name.split()[-1]
        if not (fem(l) or male(l)):        # Ким, Ли, Пак: род по фамилии не понять — берём как есть
            pool.append(name); continue
        g = groups.setdefault(fem(l), ([], []))
        g[0].append(f); g[1].append(l)
    for firsts, lasts in groups.values():
        firsts, lasts = list(dict.fromkeys(firsts)), list(dict.fromkeys(lasts))
        pool += [f"{f} {l}" for l in lasts for f in firsts]
    random.shuffle(pool)
    return pool or list(base)


EVENTS = {
 "news": ["{c} открывает новую точку в {city}", "{c} объявила о расширении ассортимента",
          "{c} вышла на Kaspi и Wildberries", "{c} получила кредитную линию на развитие",
          "В {c} сменился коммерческий директор", "{c} подписала контракт с крупной сетью",
          "{c} переезжает на новый склад"],
 "vacancy": ["Ищут руководителя отдела закупок", "Открыто пять вакансий менеджеров по продажам",
             "Ищут операционного директора", "Набирают персонал на новую точку",
             "Ищут финансового контролёра"],
 "tender": ["Объявлен тендер: {what}, заявки до {due}"],
}
EVENT_SRC = {"news": "новости", "vacancy": "hh.kz", "tender": "goszakup.gov.kz"}
CITIES_IN = ["Астане", "Алматы", "Шымкенте", "Караганде", "Актобе", "Атырау"]


def make_events(company, what, now, rnd=random):
    """Один-три датированных события по компании: из них инфо-помощник
    строит повод касания. Всё синтетическое: в реальной работе это
    коннектор к новостям, hh.kz и госзакупкам."""
    out = []
    for kind in rnd.sample(list(EVENTS), rnd.choice([1, 2, 2, 3])):
        d = now - timedelta(days=rnd.randint(2, 70))
        title = rnd.choice(EVENTS[kind]).format(
            c=company, city=rnd.choice(CITIES_IN), what=re.split(r",| для | под ", what or "")[0].strip()[:70],
            due=(now + timedelta(days=rnd.randint(7, 25))).strftime("%d.%m"))
        out.append({"date": d.date().isoformat(), "type": kind, "title": title, "source": EVENT_SRC[kind]})
    return sorted(out, key=lambda e: e["date"])


def workhour(dt):
    """Ставит разговор в рабочее время буднего дня.

    Раньше дата следующего касания двигалась на «плюс несколько дней и
    плюс-минус несколько часов», и через три шага звонок оказывался в 03:40
    в воскресенье. В зале это первое, что замечает человек из продаж."""
    while dt.weekday() > 4:
        dt += timedelta(days=1)
    return dt.replace(hour=random.randint(9, 17),
                      minute=random.choice([0, 5, 10, 15, 20, 25, 30, 40, 45, 50]))


# Вопросы и ответы квалификации раскладываются по смыслу, чтобы на «бюджет
# закладывали?» клиент не отвечал «решаю я».
QA_KIND = [("authority", r"кто|реша|решени|утвержда|согласов|подпис|партн|супруг|муж|жена|собственник|директор"),
           ("budget", r"бюджет|сумм|стоим|цен|деньг|оплат|рассрочк|закладыва|миллион|тысяч|тенге|₸"),
           ("timing", r"срок|когда|квартал|месяц|недел|сезон|к нов|до конца|к какому")]


def qa_kind(text):
    t = text.lower()
    return next((k for k, rx in QA_KIND if re.search(rx, t)), "need")


def persona(P, seg, rnd=random):
    """Один клиент — одна история во всех разговорах сделки.

    Без этого в пяти звонках одной сделки клиент то держит сеть заправок, то
    магазин вдвоём, а на шаге 3 досье и сообщение строятся на противоречиях."""
    answers = {}
    for a in P.get("qualify_answers", []):
        answers.setdefault(qa_kind(a), []).append(a)
    return {
        "situation": rnd.sample(seg["situation"], k=min(2, len(seg["situation"]))),
        "pain": rnd.sample(seg["pain"], k=min(2, len(seg["pain"]))),
        "cost": [rnd.choice(seg["cost"])],
        "qa": {k: rnd.choice(v) for k, v in answers.items()},
        "qa_any": rnd.choice(P.get("qualify_answers") or ["Решаю я."]),
        "objections": rnd.sample(P["objections"], k=min(2, len(P["objections"]))),
    }


def fix_prep(text):
    """«в четверг в в пятнадцать часов» — плейсхолдер уже с предлогом."""
    return re.sub(r"\bв (в|во|после)\b", r"\1", text)


def build_call(P, mgr, stage, seg, lead, idx, dt, stage_idx=1):
    st = mgr["style"]; t = []; said = set()
    who = lead.get("_persona") or persona(P, seg)
    add = lambda w, x: t.append({"who": w, "text": x})
    def pick(pool):
        fresh = [x for x in pool if x not in said] or list(pool)
        x = random.choice(fresh); said.add(x); return x

    objection_closed_talk = False
    weak = random.random() > st.get("asks_first", .5) + .3
    greet = (P["greetings"]["weak"] if weak and P.get("greetings", {}).get("weak") else P["greetings"]["normal"])
    add("manager", random.choice(greet).format(
        name=lead["contact"].split()[0], mgr=mgr["name"].split()[0], company=P["company"]))
    add("client", random.choice(NOISE if random.random() < .18 else ACK))

    rounds = STAGE_DEPTH.get(stage_idx, 2)
    asks = random.random() < st.get("asks_first", .5)
    if asks:
        deep = st.get("asks_first", .5) > .5
        k_sit = min(len(P["questions"]["situation"]), (2 if deep else 1) + rounds - 1)
        for q in random.sample(P["questions"]["situation"], k=k_sit):
            add("manager", say("manager", q, st.get("filler", .2)))
            add("client", say("client", pick(who["situation"]), .3))
        k_pain = min(len(P["questions"]["pain"]), (2 if deep else 1) + rounds - 1)
        for q in random.sample(P["questions"]["pain"], k=k_pain):
            add("manager", say("manager", q, st.get("filler", .2)))
            add("client", say("client", pick(who["pain"]), .3))
        if random.random() < st.get("qualify", .4) and P["questions"].get("qualify"):
            # сильный менеджер закрывает квалификацию несколькими вопросами, слабый одним
            k = 3 if st.get("qualify", .4) > .6 else 2 if st.get("qualify", .4) > .3 else 1
            for q in random.sample(P["questions"]["qualify"], k=min(k, len(P["questions"]["qualify"]))):
                add("manager", say("manager", q, st.get("filler", .2)))
                add("client", say("client", who["qa"].get(qa_kind(q), who["qa_any"]), .25))
        if random.random() < st.get("to_depth", .3) and P["questions"].get("deep"):
            add("manager", random.choice(P["questions"]["deep"]))
            add("client", say("client", pick(who["cost"]), .35))
    else:
        for _ in range(max(2, rounds)):
            add("manager", say("manager", pick(seg.get("product_lines") or P["product_lines"]), st.get("filler", .2)))
            add("client", random.choice(SHORT_ACK))

    if random.random() < st.get("value_first", .4) and P.get("value_lines"):
        add("manager", pick(seg.get("value_lines") or P["value_lines"]))
        add("client", random.choice(["Это как раз то, что нам нужно.", "Интересно.", "Хорошо."]))

    # на демо и обсуждении предложения клиент задаёт встречные вопросы
    if stage_idx in (2, 3, 4):
        for _ in range(random.randint(1, 3)):
            add("client", random.choice(P.get("client_questions") or CLIENT_Q))
            add("manager", pick((seg.get("value_lines") or P["value_lines"]) + (seg.get("product_lines") or P["product_lines"])))

    if random.random() < .75:
        add("client", random.choice(PRICE_Q))
        add("manager", random.choice(P.get("price_lines", ["Зависит от объёма, посчитаю и пришлю."])))
        if random.random() < .7:
            add("client", random.choice(who["objections"]))
            style = st.get("objection_style", "justify")
            pool = P["objection_answers"].get(style) or next(iter(P["objection_answers"].values()))
            add("manager", random.choice(pool))
            objection_closed_talk = (style == "avoid")

    closed = random.random() < st.get("next_step", .5)
    if objection_closed_talk:
        # менеджер уже свернул разговор («перезвоню позже») — второго финала не будет
        closed = False
        t.append({"who": "client", "text": random.choice(CLI_NO)})
        return finish(P, t, lead, mgr, stage, idx, dt, asks, False)
    if closed:
        pool = P["closings"]["strong"] if st.get("asks_first", .5) > .5 else P["closings"]["mid"]
        add("manager", fix_prep(random.choice(pool).format(
            day=random.choice(["во вторник", "в среду", "в четверг", "в понедельник", "в пятницу"]),
            time=random.choice(["в одиннадцать", "в пятнадцать часов", "в десять", "после обеда"]))))
        add("client", random.choice(CLI_YES))
    else:
        add("manager", random.choice(P["closings"]["weak"]))
        add("client", random.choice(CLI_NO))

    return finish(P, t, lead, mgr, stage, idx, dt, asks, closed)


def finish(P, t, lead, mgr, stage, idx, dt, asks, closed):
    """Собирает контакт и считает длительность из объёма разговора.

    Реплика в живом разговоре — это 15–25 секунд с паузами и уточнениями.
    Раньше длительность бралась с потолка, и 10 реплик превращались в 22 минуты."""
    depth = any(q in " ".join(x["text"] for x in t) for q in P["questions"].get("deep", ["\0"]))
    outcome = (("потребность раскрыта до последствий" if depth else
                "ситуация выяснена, до сути не дошли") if asks else "презентация без выявления")
    outcome += ", следующий шаг с датой" if closed else ", next step не зафиксирован"
    minutes = max(2, round(len(t) * random.uniform(0.45, 0.75)))
    return {"id": f"c{idx:03d}", "date": dt.isoformat(timespec="minutes"),
            "manager_id": mgr["id"], "lead_id": lead["id"], "stage": stage,
            # доля входящих — из профиля: клиника живёт на входящих, холодный B2B на исходящих
            "direction": "inbound" if random.random() < P.get("inbound_share", 1 / 3) else "outbound",
            "duration_min": minutes, "turns": len(t),
            "outcome": outcome, "transcript": t}


CHAT_KINDS = {
 "lead": [("manager", "{n}, отправил материалы, как договаривались."),
          ("client", "Получил, спасибо. Посмотрю."),
          ("client", "Слушайте, а вопрос: {q}"),
          ("manager", "Хороший вопрос. {a} Пришлю расчёт отдельно, чтобы цифра была заранее."),
          ("client", "Это снимет вопрос."),
          ("manager", "{n}, как продвигается? Хочу понимать, к чему готовиться на созвоне."),
          ("client", "Честно — упирается в сроки."),
          ("manager", "Решаемо: начнём с небольшого объёма, остальное по результату."),
          ("client", "Вот это подойдёт, передам.")],
 "fade": [("manager", "{n}, добрый день! Отправил презентацию, посмотрите пожалуйста."),
          ("client", "Спасибо, посмотрю."),
          ("manager", "{n}, добрый день! Удалось посмотреть?"),
          ("client", "Пока нет."),
          ("manager", "Доброе утро! Напоминаю о себе."),
          ("client", "Да, помню."),
          ("manager", "{n}, есть новости по нашему вопросу?"),
          ("client", "Давайте позже вернёмся.")],
 "haggle": [("client", "Что там по цене?"),
            ("manager", "Руководитель согласовал скидку."),
            ("client", "А если возьмём больше объём?"),
            ("manager", "Тогда могу ещё немного подвинуться."),
            ("client", "Мы ещё думаем, у других условия мягче."),
            ("manager", "У нас тоже можно обсудить рассрочку."),
            ("client", "Пришлите итоговое предложение.")],
 "pricelist": [("manager", "{n}, добрый день! Отправляю прайс, как договаривались."),
               ("client", "Спасибо."),
               ("manager", "Если будут вопросы — пишите."),
               ("client", "Хорошо.")],
}

def build_chat(P, mgr, lead, idx, dt, kind):
    n = lead["contact"].split()[0]
    q = random.choice((lead.get("_persona") or {}).get("objections") or P["objections"])
    a = random.choice(next(iter(P["objection_answers"].values())))
    msgs, cur = [], dt
    for who, text in CHAT_KINDS[kind]:
        cur += timedelta(minutes=random.randint(20, 900))
        msgs.append({"who": who, "ts": cur.isoformat(timespec="minutes"),
                     "text": text.format(n=n, q=q.lower(), a=a)})
    outcome = {"lead": "скрытое возражение снято в переписке, решение ускорено",
               "fade": "серия напоминаний без нового аргумента, переписка затухла",
               "haggle": "торг ушёл в мессенджер, ценность не вернулась",
               "pricelist": "прайс без контекста, диалог закончился"}[kind]
    return {"id": f"ch{idx:03d}", "channel": random.choice(["whatsapp", "whatsapp", "telegram"]),
            "manager_id": mgr["id"], "lead_id": lead["id"],
            "stage": random.choice([s["id"] for s in P["funnel"][1:-2]] or [P["funnel"][1]["id"]]),
            "date_start": dt.isoformat(timespec="minutes"), "date_end": msgs[-1]["ts"],
            "messages_count": len(msgs), "outcome": outcome, "messages": msgs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile", nargs="?", default="active/profile.json")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--calls", type=int, default=None,
                    help="по умолчанию 60 на менеджера, но не меньше 260")
    ap.add_argument("--chats", type=int, default=90)
    ap.add_argument("--leads", type=int, default=None,
                    help="по умолчанию столько, сколько проведут выбранные звонки, плюс новые заявки")
    ap.add_argument("--no-chats", action="store_true", help="у участника нет переписки как канала")
    a = ap.parse_args()

    path = pathlib.Path(a.profile)
    if not path.exists():
        sys.exit(f"Нет файла {path}. Профиль компании готовит шаг 0.")
    P = json.loads(path.read_text(encoding="utf-8"))

    errs, warns = validate(P)
    for w in warns: print(f"  ⚠ {w}")
    if errs:
        print("\nПрофиль не готов к генерации:")
        for e in errs: print(f"  ✗ {e}")
        print("\nИсправьте профиль и запустите снова. Если времени нет — можно продолжить\n"
              "на демо-базе: верните в cabinet/config.js profile: \"b2b\" и идите дальше.")
        sys.exit(1)
    if a.validate:
        print(f"✓ Профиль «{P['company']}» валиден: "
              f"{len(P['funnel'])} этапов, {len(P['managers'])} менеджеров, {len(P['segments'])} сегментов")
        return

    random.seed(2609)
    flow = P["type"] == "flow"
    # кому продаём — отдельный вопрос от длины цикла; старые профили без него
    # считаем по циклу, как раньше
    b2c = P.get("audience", "b2c" if flow else "b2b") == "b2c"
    now = datetime.now().replace(second=0, microsecond=0)
    start = now - timedelta(days=90)
    stages = [s["id"] for s in P["funnel"]]
    weights = [18, 22, 16, 14, 10, 10, 10][:len(stages)] or [1] * len(stages)

    # Сделка проходит в среднем три-четыре этапа, и на каждом остаётся разговор.
    # Поэтому сделок столько, сколько проведут звонки, плюс немного новых заявок.
    # Иначе половина базы — сделки без единого разговора, и они раздувают деньги
    # на этапах и процент побед.
    if a.calls is None:
        a.calls = max(260, 60 * len(P["managers"]))
    if a.leads is None:
        a.leads = round(a.calls / 3.3 * 1.15)
    b2c_aud = P.get("audience", "b2c" if P["type"] == "flow" else "b2b") == "b2c"
    if b2c_aud:
        # клиенты — люди: имя и фамилия не должны склеиваться из разных людей
        pool = people_pool(list(P["clients"]) + list(P.get("contact_names", [])))
        names = [pool[i % len(pool)] for i in range(a.leads)]
    else:
        names = unique_names(P["clients"], a.leads)
    people = people_pool(P.get("contact_names", ["Клиент Клиентов"]))
    leads = []
    for i in range(a.leads):
        resp = random.choices([6, 9, 12, 15, 20, 30, 45, 60, 90, 150, 240],
                              weights=[8, 10, 12, 12, 10, 9, 8, 7, 6, 5, 4])[0]
        leads.append({"id": f"l{i+1:03d}", "company": names[i],
          "contact": names[i] if b2c_aud else people[i % len(people)],
          "position": random.choice(P.get("positions", ["Руководитель"])),
          "industry": random.choice(P["segments"])["name"],
          "size": random.randint(20, 400),
          "source": random.choice(P["sources"]),
          "created": (start + timedelta(days=random.randint(0, 85))).date().isoformat(),
          "stage": random.choices(stages, weights=weights[:len(stages)])[0],
          "value_kzt": random.randrange(*P.get("deal_range", [500000, 15000000]), 50000),
          "next_step": None, "responded_in_min": resp})

    mgrs = P["managers"]
    calls, chats = [], []
    cid = chid = 0
    chat_budget = 0 if a.no_chats else a.chats
    n_stages = len(stages)
    terminal = {stages[-1], stages[-2]} if n_stages >= 2 else set()

    # Контакты генерируются не вразнобой, а историями по сделкам: лид проходит
    # этапы по очереди, и на каждом пройденном остаётся след. Так в базе
    # оказываются все этапы воронки, а не только первый, и у каждой сделки
    # видно, как она двигалась.
    # сделки раздаются по кругу: при большом отделе случайный выбор оставляет
    # часть людей с тремя контактами, и оценка по ним ничего не значит
    queue = []
    for lead in leads:
        if not queue:
            queue = mgrs[:]; random.shuffle(queue)
        mgr = queue.pop()                             # сделку ведёт один человек
        lead["owner"] = mgr["id"]                     # поле CRM «ответственный»
        lead["manager_id"] = mgr["id"]

        # Сделка без разговоров бывает только в самом начале: это новая заявка,
        # до которой ещё не дошли. Выигранная сделка без единого разговора —
        # фантом, она раздувает деньги на этапах и процент побед.
        if cid >= a.calls:
            lead["stage"] = stages[0]
            lead["created"] = (now - timedelta(days=random.randint(0, 3 if flow else 6))).date().isoformat()
            lead["next_step"] = None
            continue

        # Докуда дошла сделка — следствие того, как с ней работали.
        # Без этой связи аналитика показала бы, что качество разговоров
        # не влияет на исход, и все выводы кабинета были бы неправдой.
        st_ = mgr["style"]
        skill = (st_.get("asks_first", .5) + st_.get("to_depth", .3) + st_.get("next_step", .5)) / 3
        w = []
        for i in range(n_stages):
            if i < n_stages - 2:                      # рабочие этапы
                w.append(max(.05, 1.0 - skill * (i / max(1, n_stages - 2)) * 0.9))
            elif i == n_stages - 2:                   # выиграна
                w.append(.15 + skill * 1.1)
            else:                                     # проиграна
                w.append(.55 - skill * .40)
        reached = random.choices(range(n_stages), weights=w)[0]
        # Проигранная сделка не проходит через «выиграна»: терминальный этап один.
        path = list(range(reached + 1))
        if stages[reached] in terminal:
            path = list(range(min(reached, n_stages - 2))) + [reached]
        # Разговоров не хватает на весь путь — сделка остаётся открытой там,
        # докуда дошла, а не получает исход без единого разговора о нём.
        left = a.calls - cid
        if len(path) > left:
            path = list(range(min(left, n_stages - 2)))
        reached = path[-1]
        lead["stage"] = stages[reached]
        seg = next((x for x in P["segments"] if x["name"] == lead["industry"]), P["segments"][0])
        lead["_persona"] = persona(P, seg)

        # Цепочка касаний строится назад от сегодня, чтобы последний разговор
        # не оказался в будущем: пауза между этапами известна заранее.
        # Открытая сделка живая — последний разговор был недавно; закрытая
        # могла закончиться и месяц назад.
        gaps = [random.randint(2, 12) for _ in path]
        tail = random.randint(1, 18) if stages[reached] not in terminal else random.randint(3, 45)
        dt = workhour(now - timedelta(days=sum(gaps[:-1]) + tail))
        # заявка пришла до первого разговора, а не после
        lead["created"] = (dt - timedelta(days=random.randint(0, 4))).date().isoformat()
        last, c0, h0 = None, len(calls), len(chats)
        for n, si in enumerate(path):
            cid += 1
            last = build_call(P, mgr, stages[si], seg, lead, cid, dt, stage_idx=si)
            calls.append(last)
            if n < len(path) - 1:
                dt = workhour(dt + timedelta(days=gaps[n]))

            # переписка возникает между звонками, чаще на средних этапах
            if chid < chat_budget and 0 < si < n_stages - 2 and random.random() < .45 and n < len(path) - 1:
                chid += 1
                style = mgr["style"].get("objection_style", "justify")
                kind = {"counter": "lead", "justify": "fade",
                        "avoid": "pricelist", "discount": "haggle"}.get(style, "fade")
                if random.random() < .3:
                    kind = random.choice(list(CHAT_KINDS))
                ch = build_chat(P, mgr, lead, chid, workhour(dt - timedelta(days=1)), kind)
                ch["stage"] = stages[si]
                chats.append(ch)

        # Перенос с выходных на понедельник мог вытолкнуть конец цепочки
        # в будущее. Сдвигаем всю сделку назад целыми неделями: дни недели
        # и порядок разговоров сохраняются.
        span = [c["date"] for c in calls[c0:]] + [c["date_end"] for c in chats[h0:]]
        over = (datetime.fromisoformat(max(span)) - now) if span else timedelta(0)
        if over > timedelta(0):
            back = timedelta(days=7 * (over.days // 7 + 1))
            sh = lambda x: (datetime.fromisoformat(x) - back).isoformat(timespec="minutes")
            for c in calls[c0:]:
                c["date"] = sh(c["date"])
            for c in chats[h0:]:
                c["date_start"], c["date_end"] = sh(c["date_start"]), sh(c["date_end"])
                for m in c["messages"]:
                    m["ts"] = sh(m["ts"])
            lead["created"] = (datetime.fromisoformat(lead["created"]) - back).date().isoformat()

        # Следующий шаг — тот, о котором договорились в последнем разговоре.
        # Если договорённости не было, его нет и в CRM: так и бывает в жизни.
        # Примерно каждый четвёртый уже просрочен — это и есть работа на сегодня.
        if stages[reached] not in terminal and last and "следующий шаг с датой" in last["outcome"]:
            after = datetime.fromisoformat(last["date"]) + timedelta(days=1)
            due = now + (timedelta(days=random.randint(1, 10)) if random.random() < .75
                         else -timedelta(days=random.randint(1, 6)))
            lead["next_step"] = max(after, due).date().isoformat()
        else:
            lead["next_step"] = None

    # Внешние события по компании — только в B2B: у сделки есть компания,
    # у заявки в потоке обычно нет.
    for lead in leads:
        lead.pop("_persona", None)
    if not b2c:
        for lead in leads:
            lead["events"] = make_events(lead["company"], P.get("what_we_sell", ""), now)

    calls.sort(key=lambda c: c["date"]); chats.sort(key=lambda c: c["date_start"])
    out = {"profile": {"id": "own", "title": P["company"], "company": P["company"],
                       "type": b2c and "b2c" or "b2b", "crm": P.get("crm", "none"),
                       "what_we_sell": P["what_we_sell"], "cycle": P.get("cycle", ""),
                       "deal_size": P.get("deal_size", ""), "synthetic": True,
                       "stages": stages,
                       "stage_labels": {s["id"]: s["label"] for s in P["funnel"]},
                       "funnel": P["funnel"]},
           "managers": [{"id": m["id"], "name": m["name"], "role": m.get("role", "Менеджер")} for m in mgrs],
           "calls": calls, "chats": chats, "leads": leads}
    d = ROOT / "data/own"; d.mkdir(parents=True, exist_ok=True)
    (d / "dataset.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ {P['company']}: {len(calls)} звонков, {len(chats)} переписок, {len(leads)} лидов → data/own/dataset.json")
    print("  Дальше: в cabinet/config.js поставьте profile: \"own\" и запустите python3 scripts/build_data.py")

if __name__ == "__main__":
    main()
