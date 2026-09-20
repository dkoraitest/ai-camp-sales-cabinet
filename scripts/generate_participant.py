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

import json, random, argparse, pathlib, sys
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
        errs.append("«type» должен быть \"long\" (длинный цикл) или \"flow\" (поток заявок)")
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


def build_call(P, mgr, stage, seg, lead, idx, dt):
    st = mgr["style"]; t = []; said = set()
    add = lambda w, x: t.append({"who": w, "text": x})
    def pick(pool):
        fresh = [x for x in pool if x not in said] or list(pool)
        x = random.choice(fresh); said.add(x); return x

    weak = random.random() > st.get("asks_first", .5) + .3
    greet = (P["greetings"]["weak"] if weak and P.get("greetings", {}).get("weak") else P["greetings"]["normal"])
    add("manager", random.choice(greet).format(
        name=lead["contact"].split()[0], mgr=mgr["name"].split()[0], company=P["company"]))
    add("client", random.choice(NOISE if random.random() < .18 else ACK))

    asks = random.random() < st.get("asks_first", .5)
    if asks:
        deep = st.get("asks_first", .5) > .5
        for q in random.sample(P["questions"]["situation"], k=min(2 if deep else 1, len(P["questions"]["situation"]))):
            add("manager", say("manager", q, st.get("filler", .2)))
            add("client", say("client", pick(seg["situation"]), .3))
        for q in random.sample(P["questions"]["pain"], k=min(2 if deep else 1, len(P["questions"]["pain"]))):
            add("manager", say("manager", q, st.get("filler", .2)))
            add("client", say("client", pick(seg["pain"]), .3))
        if random.random() < st.get("qualify", .4) and P["questions"].get("qualify"):
            add("manager", say("manager", random.choice(P["questions"]["qualify"]), st.get("filler", .2)))
            add("client", say("client", random.choice(P.get("qualify_answers", ["Решаю я.", "Согласовываю с руководителем."])), .25))
        if random.random() < st.get("to_depth", .3) and P["questions"].get("deep"):
            add("manager", random.choice(P["questions"]["deep"]))
            add("client", say("client", pick(seg["cost"]), .35))
    else:
        add("manager", say("manager", pick(P["product_lines"]), st.get("filler", .2)))
        add("client", random.choice(SHORT_ACK))
        add("manager", pick(P["product_lines"]))
        add("client", random.choice(SHORT_ACK))

    if random.random() < st.get("value_first", .4) and P.get("value_lines"):
        add("manager", pick(P["value_lines"]))
        add("client", random.choice(["Это как раз то, что нам нужно.", "Интересно.", "Хорошо."]))

    if random.random() < .75:
        add("client", random.choice(PRICE_Q))
        add("manager", random.choice(P.get("price_lines", ["Зависит от объёма, посчитаю и пришлю."])))
        if random.random() < .7:
            add("client", random.choice(P["objections"]))
            style = st.get("objection_style", "justify")
            pool = P["objection_answers"].get(style) or next(iter(P["objection_answers"].values()))
            add("manager", random.choice(pool))

    closed = random.random() < st.get("next_step", .5)
    if closed:
        pool = P["closings"]["strong"] if st.get("asks_first", .5) > .5 else P["closings"]["mid"]
        add("manager", random.choice(pool).format(
            day=random.choice(["во вторник", "в среду", "в четверг", "в понедельник", "в пятницу"]),
            time=random.choice(["в одиннадцать", "в пятнадцать часов", "в десять", "после обеда"])))
        add("client", random.choice(CLI_YES))
    else:
        add("manager", random.choice(P["closings"]["weak"]))
        add("client", random.choice(CLI_NO))

    depth = any(q in " ".join(x["text"] for x in t) for q in P["questions"].get("deep", ["\0"]))
    outcome = (("потребность раскрыта до последствий" if depth else
                "ситуация выяснена, до сути не дошли") if asks else "презентация без выявления")
    outcome += ", следующий шаг с датой" if closed else ", next step не зафиксирован"
    return {"id": f"c{idx:03d}", "date": dt.isoformat(timespec="minutes"),
            "manager_id": mgr["id"], "lead_id": lead["id"], "stage": stage,
            "direction": random.choice(["outbound", "outbound", "inbound"]),
            "duration_min": max(3, int(len(t) * random.uniform(1.1, 2.0))),
            "outcome": outcome, "transcript": t}


CHAT_KINDS = {
 "lead": [("manager", "{n}, отправил материалы, как договаривались."),
          ("client", "Получил, спасибо. Посмотрю."),
          ("client", "Слушайте, а вопрос: {q}"),
          ("manager", "Хороший вопрос. {a} Пришлю расчёт отдельно, чтобы цифра была заранее."),
          ("client", "Это снимет вопрос."),
          ("manager", "{n}, как продвигается? Хочу понимать, к чему готовиться на созвоне."),
          ("client", "Честно — упирается в сроки."),
          ("manager", "Решаемо: подготовку делаем сейчас, запуск позже. Так выигрываем две недели."),
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
    q = random.choice(P["objections"])
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
    ap.add_argument("--calls", type=int, default=260)
    ap.add_argument("--chats", type=int, default=90)
    ap.add_argument("--leads", type=int, default=180)
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
    start = datetime.now() - timedelta(days=90)
    stages = [s["id"] for s in P["funnel"]]
    weights = [18, 22, 16, 14, 10, 10, 10][:len(stages)] or [1] * len(stages)

    leads = []
    for i in range(a.leads):
        resp = random.choices([6, 9, 12, 15, 20, 30, 45, 60, 90, 150, 240],
                              weights=[8, 10, 12, 12, 10, 9, 8, 7, 6, 5, 4])[0]
        leads.append({"id": f"l{i+1:03d}", "company": P["clients"][i % len(P["clients"])],
          "contact": random.choice(P.get("contact_names", ["Клиент Клиентов"])),
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
    for i in range(a.calls):
        lead = random.choice(leads)
        mgr = random.choice(mgrs)
        seg = next((s for s in P["segments"] if s["name"] == lead["industry"]), P["segments"][0])
        dt = start + timedelta(days=random.randint(0, 88), hours=random.randint(0, 9),
                               minutes=random.choice([0, 5, 10, 15, 20, 30, 40, 45]))
        calls.append(build_call(P, mgr, random.choice(stages), seg, lead, i + 1, dt))
    chat_n = 0 if a.no_chats else a.chats
    for i in range(chat_n):
        lead = random.choice(leads); mgr = random.choice(mgrs)
        style = mgr["style"].get("objection_style", "justify")
        kind = {"counter": "lead", "justify": "fade", "avoid": "pricelist", "discount": "haggle"}.get(style, "fade")
        if random.random() < .35: kind = random.choice(list(CHAT_KINDS))
        dt = start + timedelta(days=random.randint(0, 85), hours=random.randint(0, 8))
        chats.append(build_chat(P, mgr, lead, i + 1, dt, kind))

    calls.sort(key=lambda c: c["date"]); chats.sort(key=lambda c: c["date_start"])
    out = {"profile": {"id": "own", "title": P["company"], "company": P["company"],
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
