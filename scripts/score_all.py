#!/usr/bin/env python3
"""Разметка всей базы и четыре разреза аналитики.

Прогонять сотни разговоров через модель поштучно нельзя: это десятки тысяч
токенов, минуты ожидания и обрывы на середине. Поэтому формальные признаки
считает код — по всей базе и за секунды, — а модель приходит туда, где нужен
смысл: пишет инсайты поверх агрегатов и разбирает показательные разговоры.

Четыре разреза, каждый на своём месте:
  1. Качество коммуникаций — на одном этапе воронки (сравнивать можно только сопоставимое)
  2. Инсайты — по всей воронке (иначе не видно, где теряются деньги)
  3. BANT — на этапе квалификации (там, где он должен происходить)
  4. SPSV — по всей воронке (части модели клиента всплывают на разных этапах)

    python3 scripts/score_all.py                 # профиль из cabinet/config.js
    python3 scripts/score_all.py --profile b2b
"""

import json, re, pathlib, argparse, statistics as st
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent

NAMES = {
 "structure": "Соблюдение структуры разговора", "discovery": "Глубина выявления",
 "qualification": "Качество квалификации", "objections": "Работа с ценой и возражениями",
 "deal_control": "Управление сделкой", "expertise": "Экспертность", "balance": "Баланс диалога"}

M = {
 "depth":   ["что для компании стоит", "перевести это в деньги", "сколько стоит один",
             "во сколько обходится", "сколько вы теряете", "что важнее", "что вы хотите получить",
             "почему решили именно", "чем увлекается"],
 "qual":    ["кто ещё участвует", "бюджет", "кто у вас отвечает", "что должно произойти",
             "кто принимает решение", "с кем ещё будете", "какую сумму", "к какому сроку",
             "когда планируете", "кто утверждает"],
 "disc":    ["расскажите", "сколько у вас", "как сейчас", "что не устраивает", "где чаще всего",
             "что из этого болит", "как устроен", "кто занимается", "что уже пробовали"],
 "close":   ["ставлю в календарь", "созваниваемся", "созвонимся", "ставим", "подходит?",
             "записываю", "предлагаю пилот", "фиксируем решение", "пришлю расчёт", "соберу расчёт",
             "короткую встречу", "обсудим", "подготовлю", "присылаю", "во вторник", "в среду",
             "в четверг", "в пятницу", "в понедельник"],
 "weak":    ["алло", "беспокоит", "вы заявку оставляли", "актуально ещё", "интересовались"],
 "discount":["скидку", "процентов, если решите", "спрошу у руководителя", "специальные условия",
             "могу подвинуться", "сделаю дешевле"],
 "counter": ["с чем сравниваете", "какую сумму", "что должно измениться", "давайте разделим",
             "что входит в их", "какая сумма в месяц", "давайте посмотрим", "честно скажу"],
 "value":   ["не даёт закрыть", "второй скан", "маршруту сборки", "запись остаётся",
             "защищает свой проект", "результат он увидит", "до шести человек", "за неделю, а не"],
}
# Маркеры — по ключевым кускам, а не по целым фразам: формулировка
# у каждого участника своя, а «бюджет» и «кто решает» звучат одинаково.
BANT = {
 "budget":    ["бюджет", "какую сумму", "закладывал", "порядок инвестиц", "цена вопроса",
               "сколько готовы", "какие деньги", "во сколько оценивае"],
 "authority": ["кто принимает", "кто ещё участв", "кто утвержда", "с кем ещё", "кто отвечает",
               "решение принимаете", "кто решает", "согласовыва", "кто ещё влияет"],
 "need":      ["не устраивает", "что болит", "какая задача", "зачем вам", "что хотите получить",
               "что уже пробовали", "где ломается", "что мешает", "какую проблему"],
 "timing":    ["к какому сроку", "когда планируете", "срок", "когда нужно", "к какой дате",
               "когда хотите", "как скоро", "в какие сроки"],
}
# Вторая линия: регулярки с пропуском слов. «Кто у вас принимает решение»
# и «кто принимает решение» — один и тот же вопрос, подстрока ловит только второй.
BANT_RX = {
 "budget":    r"бюджет|закладыва|как(ую|ой) сумм|цена вопроса|сколько готовы|инвестиц|во сколько оценива|какие деньги|оплат|предоплат|отсрочк|рассрочк|по деньгам|сколько (планиру|рассчитыва)",
 "authority": r"кто(\s+\S+){0,3}\s+(принима|реша|утвержда|согласов|подписыва|участву|влияет|отвечает|будет решать)|с кем(\s+\S+){0,2}\s+(совет|реша|обсужд)|реша[её]те(\s+\S+){0,2}\s+сам|советова|решение принима|лпр|с супруг|с мужем|с женой",
 "need":      r"не устраива|что(\s+\S+){0,2}\s+(меша|беспоко|болит|волну|тревож)|как(ая|ую) (задач|проблем)|зачем вам|что хотите получить|что уже пробовали|где ломается|что должно (измениться|произойти)|с чем пришли|что привело",
 "timing":    r"к какому (сроку|числу|дате|сезону)|когда(\s+\S+){0,3}\s+(нач|законч|хоте|удобн|планиру|нужн|должн|старт|запуск)|срок|как скоро|к (началу|концу) (сезона|месяца|квартала)",
}


def load_profile_markers(prof):
    """Маркеры из профиля участника.

    Демо-маркеры написаны под DataFlow: «второй скан», «маршруту сборки».
    У другого бизнеса они не сработают никогда, и экспертность с работой
    с возражениями окажутся занижены у всех. Поэтому, если есть профиль
    шага 0, берём его же формулировки: генератор вставляет их в разговоры
    дословно, а участник узнаёт в них свои вопросы."""
    path = ROOT / "active" / "profile.json"
    if prof != "own" or not path.exists():
        return 0
    P = json.loads(path.read_text(encoding="utf-8"))
    head = lambda t: " ".join(re.sub(r"[^\w\s-]", " ", t.lower()).split()[:4])
    added = 0
    def add(key, lines, target=M):
        nonlocal added
        for t in lines or []:
            h = head(t)
            if len(h) >= 8 and h not in target[key]:
                target[key].append(h); added += 1
    q = P.get("questions", {})
    add("disc", q.get("situation")); add("disc", q.get("pain"))
    add("depth", q.get("deep")); add("qual", q.get("qualify"))
    oa = P.get("objection_answers", {})
    add("counter", oa.get("counter")); add("discount", oa.get("discount"))
    add("value", P.get("value_lines")); add("close", P.get("closings"))
    # вопросы квалификации раскладываем по BANT по смыслу самого вопроса
    for t in q.get("qualify", []) or []:
        for k, rx in BANT_RX.items():
            if re.search(rx, t.lower()):
                add(k, [t], BANT)
    return added


OBJ_WORDS = ["дорог", "дешевле", "подумать", "не закладывали", "рано", "бросит",
             "расписание", "посоветоваться", "не время", "уже есть", "сезон"]


def turns_of(c):
    return c.get("transcript") or c.get("messages") or []


def mark(c):
    """Формальные признаки одного контакта. Считается кодом — быстро и одинаково для всех."""
    t = turns_of(c)
    mgr = [x["text"].lower() for x in t if x["who"] == "manager"]
    cli = [x["text"].lower() for x in t if x["who"] == "client"]
    text, ctext = " ".join(mgr), " ".join(cli)
    has = lambda k: any(m in text for m in M[k])
    n_q = sum(x.count("?") for x in mgr)

    # сколько вопросов задано до первого упоминания продукта
    first_product = next((i for i, x in enumerate(mgr)
                          if any(w in x for w in ["у нас", "мы делаем", "наша система", "есть модуль",
                                                  "предлагаем", "наш продукт", "стоит"])), len(mgr))
    q_before_pitch = sum(x.count("?") for x in mgr[:first_product])

    structure = min(10, 1 + (4 if not has("weak") else 0) + (3 if has("close") else 0) + (2 if n_q else 0))
    discovery = min(10, (3 if has("disc") else 0) + min(4, q_before_pitch) + (3 if has("depth") else 0))
    qualification = min(10, (5 if has("qual") else 0) + (3 if has("depth") else 0) + (2 if n_q >= 3 else 0))
    objection = any(w in ctext for w in OBJ_WORDS)
    objections = (9 if has("counter") else 3 if has("discount") else 4 if has("value") else 2) if objection \
                 else (5 if has("close") else 4)
    deal_control = min(10, (6 if has("close") else 1) + (2 if n_q >= 2 else 0) + (2 if has("qual") else 0))
    expertise = min(10, 3 + (3 if has("value") else 0) + (2 if n_q >= 3 else 0) + (1 if len(mgr) > 5 else 0))
    share = len(mgr) / max(1, len(mgr) + len(cli))
    balance = 9 if .40 <= share <= .58 else 7 if .58 < share <= .65 else 4 if share > .65 else 6

    vals = dict(structure=structure, discovery=discovery, qualification=qualification,
                objections=objections, deal_control=deal_control, expertise=expertise, balance=balance)
    bant = {k: any(m in text for m in v) or bool(re.search(BANT_RX[k], text)) for k, v in BANT.items()}
    return vals, round(sum(vals.values()) / len(vals), 1), dict(
        depth=has("depth"), qual=has("qual"), close=has("close"), weak_open=has("weak"),
        discount=has("discount"), counter=has("counter"), objection=objection,
        n_q=n_q, q_before_pitch=q_before_pitch, share=round(share, 2), bant=bant)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile")
    ap.add_argument("--stage", help="фокусный этап; по умолчанию из cabinet/config.js")
    a = ap.parse_args()

    cfg_path = ROOT / "cabinet/config.js"
    cfg = cfg_path.read_text(encoding="utf-8") if cfg_path.exists() else ""
    prof = a.profile or (re.search(r'profile:\s*"(\w+)"', cfg) or [None, "b2b"])[1]
    focus = a.stage or (re.search(r'focus_stage:\s*"(\w+)"', cfg) or [None, None])[1]

    extra = load_profile_markers(prof)
    if extra:
        print(f"  маркеры из профиля компании: +{extra} формулировок")
    d = json.loads((ROOT / f"data/{prof}/dataset.json").read_text(encoding="utf-8"))
    stages = d["profile"]["stages"]
    labels = d["profile"].get("stage_labels", {})
    mgr_name = {m["id"]: m["name"] for m in d["managers"]}
    leads = {l["id"]: l for l in d["leads"]}
    if not focus or focus not in stages:
        focus = stages[1] if len(stages) > 1 else stages[0]
    qual_stage = stages[1] if len(stages) > 1 else stages[0]
    won, lost = stages[-2], stages[-1]

    items, flags = [], {}
    for c in d["calls"] + d["chats"]:
        kind = "chat" if "messages" in c else "call"
        vals, total, f = mark(c)
        items.append({"id": c["id"], "type": kind, "total": total, "stage": c["stage"],
                      "lead_id": c["lead_id"],
                      "evaluate": [{"id": k, "name": NAMES[k], "value": v, "max": 10} for k, v in vals.items()],
                      "bant": f["bant"], "comment": c.get("outcome", "")})
        flags[c["id"]] = dict(f, mgr=c["manager_id"], stage=c["stage"], kind=kind,
                              total=total, lead=c["lead_id"])

    n = len(items)
    agg = {"profile": prof, "total_contacts": n,
           "calls": sum(1 for f in flags.values() if f["kind"] == "call"),
           "chats": sum(1 for f in flags.values() if f["kind"] == "chat"),
           "focus_stage": focus, "focus_label": labels.get(focus, focus),
           "qualification_stage": qual_stage,
           "avg_total": round(st.mean(i["total"] for i in items), 1)}

    # ── разрез 1 · качество коммуникаций на фокусном этапе ────────────
    fs = [f for f in flags.values() if f["stage"] == focus]
    agg["focus"] = {
        "contacts": len(fs),
        "avg": round(st.mean(f["total"] for f in fs), 1) if fs else None,
        "with_depth": sum(1 for f in fs if f["depth"]),
        "with_close": sum(1 for f in fs if f["close"]),
        "pitch_first": sum(1 for f in fs if f["q_before_pitch"] == 0),
        "avg_q_before_pitch": round(st.mean(f["q_before_pitch"] for f in fs), 1) if fs else None,
        "by_manager": {mgr_name[m]: round(st.mean([f["total"] for f in fs if f["mgr"] == m]), 1)
                       for m in mgr_name if any(f["mgr"] == m for f in fs)},
    }

    # ── разрез 2 · вся воронка: где теряем контакты и где деньги ──────
    stage_rows = []
    for s in stages:
        g = [f for f in flags.values() if f["stage"] == s]
        lead_ids = {f["lead"] for f in g}
        money = sum(leads[l]["value_kzt"] for l in lead_ids if l in leads and leads[l]["stage"] == s)
        stuck = [l for l in lead_ids if l in leads and leads[l]["stage"] == s]
        stage_rows.append({"stage": s, "label": labels.get(s, s), "contacts": len(g),
                           "avg": round(st.mean(f["total"] for f in g), 1) if g else None,
                           "leads_on_stage": len(stuck), "money_on_stage": money,
                           "close_rate": round(sum(1 for f in g if f["close"]) / len(g), 2) if g else None})
    agg["funnel"] = stage_rows
    agg["channels"] = {"calls_avg": round(st.mean([f["total"] for f in flags.values() if f["kind"] == "call"]), 1),
                       "chats_avg": round(st.mean([f["total"] for f in flags.values() if f["kind"] == "chat"]), 1)
                       if agg["chats"] else None}
    agg["managers"] = {mgr_name[m]: {
        "contacts": sum(1 for f in flags.values() if f["mgr"] == m),
        "avg": round(st.mean([f["total"] for f in flags.values() if f["mgr"] == m]), 1),
        "close_rate": round(sum(1 for f in flags.values() if f["mgr"] == m and f["close"]) /
                            max(1, sum(1 for f in flags.values() if f["mgr"] == m)), 2),
        "depth_rate": round(sum(1 for f in flags.values() if f["mgr"] == m and f["depth"]) /
                            max(1, sum(1 for f in flags.values() if f["mgr"] == m)), 2),
    } for m in mgr_name}
    # связь поведения с исходом — по всей воронке
    far = {won, stages[-3]} if len(stages) > 3 else {won}
    moved = lambda pred: round(sum(1 for f in flags.values() if pred(f) and
                                   leads.get(f["lead"], {}).get("stage") in far) /
                               max(1, sum(1 for f in flags.values() if pred(f))), 2)
    agg["behaviour_vs_outcome"] = {
        "with_depth": moved(lambda f: f["depth"]), "without_depth": moved(lambda f: not f["depth"]),
        "with_close": moved(lambda f: f["close"]), "without_close": moved(lambda f: not f["close"]),
        "objection_counter": moved(lambda f: f["objection"] and f["counter"]),
        "objection_discount": moved(lambda f: f["objection"] and f["discount"]),
    }

    # ── разрез 3 · BANT на этапе квалификации ─────────────────────────
    qs = [f for f in flags.values() if f["stage"] == qual_stage]
    agg["bant"] = {
        "stage": qual_stage, "label": labels.get(qual_stage, qual_stage), "contacts": len(qs),
        "coverage": {k: round(sum(1 for f in qs if f["bant"][k]) / len(qs), 2) for k in BANT} if qs else {},
        "full": sum(1 for f in qs if all(f["bant"].values())),
        "none": sum(1 for f in qs if not any(f["bant"].values())),
        "full_vs_outcome": round(sum(1 for f in qs if all(f["bant"].values()) and
                                     leads.get(f["lead"], {}).get("stage") in far) /
                                 max(1, sum(1 for f in qs if all(f["bant"].values()))), 2),
    }

    # ── разрез 4 · SPSV по всей воронке, сырьё по сегментам ───────────
    seg_src = defaultdict(lambda: {"leads": 0, "contacts": 0, "won": 0, "lost": 0,
                                   "avg": [], "client_lines": Counter()})
    for l in d["leads"]:
        s = l.get("industry") or l.get("interest") or "—"
        seg_src[s]["leads"] += 1
        if l["stage"] == won: seg_src[s]["won"] += 1
        if l["stage"] == lost: seg_src[s]["lost"] += 1
    for c in d["calls"] + d["chats"]:
        l = leads.get(c["lead_id"])
        if not l: continue
        s = l.get("industry") or l.get("interest") or "—"
        seg_src[s]["contacts"] += 1
        seg_src[s]["avg"].append(flags[c["id"]]["total"])
        for x in turns_of(c):
            if x["who"] == "client" and len(x["text"]) > 45:
                seg_src[s]["client_lines"][x["text"].strip()] += 1
    # мелкие сегменты сворачиваем: пять лидов не дают основания для выводов
    ranked = sorted(seg_src.items(), key=lambda kv: -kv[1]["leads"])
    big = [(s, v) for s, v in ranked if v["leads"] >= 5][:6]
    rest = [(s, v) for s, v in ranked if (s, v) not in big]
    agg["segments"] = [{
        "segment": s, "leads": v["leads"], "contacts": v["contacts"],
        "won": v["won"], "lost": v["lost"],
        "win_rate": round(v["won"] / max(1, v["won"] + v["lost"]), 2),
        "avg_quality": round(st.mean(v["avg"]), 1) if v["avg"] else None,
        "top_client_lines": [t for t, _ in v["client_lines"].most_common(5)],
    } for s, v in big]
    if rest:
        agg["segments"].append({
            "segment": f"прочие ({len(rest)} мелких)",
            "leads": sum(v["leads"] for _, v in rest),
            "contacts": sum(v["contacts"] for _, v in rest),
            "won": sum(v["won"] for _, v in rest), "lost": sum(v["lost"] for _, v in rest),
            "win_rate": round(sum(v["won"] for _, v in rest) /
                              max(1, sum(v["won"] + v["lost"] for _, v in rest)), 2),
            "avg_quality": round(st.mean([x for _, v in rest for x in v["avg"]]), 1)
                           if any(v["avg"] for _, v in rest) else None,
            "top_client_lines": []})

    # ── BANT по всей воронке: сколько сделок на каждом этапе квалифицированы ──
    # Квалификация копится по сделке, а не живёт в одном разговоре: признак
    # мог прозвучать на первом звонке, а решение о КП принимается на четвёртом.
    lead_bant = defaultdict(lambda: {k: False for k in BANT})
    for f in flags.values():
        e = lead_bant[f["lead"]]          # сделка попадает в счёт, даже если не выяснено ничего
        for k, v in f["bant"].items():
            if v: e[k] = True
    worked = [l for l in d["leads"] if l["id"] in lead_bant]
    by_stage = []
    for s_ in stages:
        ls = [l for l in worked if l["stage"] == s_]
        full = [l for l in ls if all(lead_bant[l["id"]].values())]
        none_ = [l for l in ls if not any(lead_bant[l["id"]].values())]
        by_stage.append({
            "stage": s_, "label": labels.get(s_, s_), "leads": len(ls),
            "full": len(full), "partial": len(ls) - len(full) - len(none_), "none": len(none_),
            "money": sum(l["value_kzt"] for l in ls),
            "money_full": sum(l["value_kzt"] for l in full),
            "coverage": {k: sum(1 for l in ls if lead_bant[l["id"]][k]) for k in BANT} if ls else {},
        })
    agg["bant_by_stage"] = {"deals": len(worked), "stages": by_stage,
                            "labels": {"budget": "Бюджет", "authority": "Полномочия",
                                       "need": "Потребность", "timing": "Сроки"}}

    # ── о чём говорят в выигранных сделках и чего не было в проигранных ──
    # Сравниваются не свойства клиента, а поведение менеджера: свойства
    # повторить нельзя, поведение можно.
    def side(stage_id):
        ids = {l["id"] for l in d["leads"] if l["stage"] == stage_id and l["id"] in lead_bant}
        g = [f for f in flags.values() if f["lead"] in ids]
        return ids, g
    won_ids, won_g = side(won)
    lost_ids, lost_g = side(lost)
    share = lambda g, pred: round(sum(1 for f in g if pred(f)) / len(g), 2) if g else None
    num = lambda g, key: round(st.mean([f[key] for f in g]), 1) if g else None
    deal_share = lambda ids, pred: round(sum(1 for i in ids if pred(i)) / len(ids), 2) if ids else None
    rows = [
        ("Спросили, во что обходится проблема", "share", share(won_g, lambda f: f["depth"]), share(lost_g, lambda f: f["depth"])),
        ("Квалифицировали в разговоре", "share", share(won_g, lambda f: f["qual"]), share(lost_g, lambda f: f["qual"])),
        ("Зафиксировали следующий шаг", "share", share(won_g, lambda f: f["close"]), share(lost_g, lambda f: f["close"])),
        ("Открыли разговор слабо", "share", share(won_g, lambda f: f["weak_open"]), share(lost_g, lambda f: f["weak_open"])),
        ("На возражение — встречный вопрос", "share", share(won_g, lambda f: f["objection"] and f["counter"]),
                                                      share(lost_g, lambda f: f["objection"] and f["counter"])),
        ("На возражение — скидка", "share", share(won_g, lambda f: f["objection"] and f["discount"]),
                                            share(lost_g, lambda f: f["objection"] and f["discount"])),
        ("Полный BANT по сделке", "share", deal_share(won_ids, lambda i: all(lead_bant[i].values())),
                                           deal_share(lost_ids, lambda i: all(lead_bant[i].values()))),
        ("Вопросов до первого слова о продукте", "num", num(won_g, "q_before_pitch"), num(lost_g, "q_before_pitch")),
        ("Коммуникаций на сделку", "num", round(len(won_g) / len(won_ids), 1) if won_ids else None,
                                          round(len(lost_g) / len(lost_ids), 1) if lost_ids else None),
        ("Средний балл разговора", "num", num(won_g, "total"), num(lost_g, "total")),
    ]
    agg["won_vs_lost"] = {
        "won_label": labels.get(won, won), "lost_label": labels.get(lost, lost),
        "won_deals": len(won_ids), "lost_deals": len(lost_ids),
        "won_contacts": len(won_g), "lost_contacts": len(lost_g),
        "rows": [{"label": l, "kind": k, "won": w, "lost": ls_} for l, k, w, ls_ in rows
                 if w is not None and ls_ is not None],
    }

    out = ROOT / "active"; out.mkdir(exist_ok=True)
    (out / "aggregates.json").write_text(json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "scored.json").write_text(json.dumps({"items": items, "aggregates": agg},
                                            ensure_ascii=False), encoding="utf-8")
    # Разрезы, на которых кабинет рисует графики, кладём прямо рядом с ним.
    # Модель пишет scores.js сама и может не перенести цифры — тогда вкладки
    # «Дашборд» и «Глубокая аналитика» остались бы пустыми.
    cab = ROOT / "cabinet"; cab.mkdir(exist_ok=True)
    marks = {i["id"]: {"lead": i["lead_id"], "bant": i["bant"]} for i in items}
    (cab / "aggregates.js").write_text(
        "// Сгенерировано scripts/score_all.py — руками не править.\n"
        f"window.CABINET_AGG = {json.dumps(dict(agg, marks=marks), ensure_ascii=False)};\n",
        encoding="utf-8")

    print(f"Размечено {n} контактов ({agg['calls']} звонков, {agg['chats']} переписок), профиль {prof}")
    print(f"  фокусный этап «{agg['focus_label']}»: {agg['focus']['contacts']} контактов, средний {agg['focus']['avg']}")
    print(f"  квалификация на этапе «{agg['bant']['label']}»: полный BANT у {agg['bant']['full']} из {agg['bant']['contacts']}")
    print(f"  сегментов: {len(agg['segments'])}")
    q = agg["bant_by_stage"]
    print(f"  BANT по воронке: {sum(x['full'] for x in q['stages'])} из {q['deals']} сделок закрыты по всем четырём")
    w = agg["won_vs_lost"]
    print(f"  выигранные против проигранных: {w['won_deals']} и {w['lost_deals']} сделок, {len(w['rows'])} сравнений")
    print(f"→ active/aggregates.json (для инсайтов) · active/scored.json (оценки всех контактов)"
          f" · cabinet/aggregates.js (графики кабинета)")


if __name__ == "__main__":
    main()
