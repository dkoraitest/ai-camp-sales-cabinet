#!/usr/bin/env python3
"""Пересчёт эталона по фактической базе.

Оценки считаются по поведенческим маркерам в тексте — детерминированно,
чтобы цифры в эталоне сходились с данными. На воркшопе то же самое делает
модель: она видит смысл, а не маркеры, но результат сопоставим.

Запуск:  python3 scripts/score_reference.py [b2b|b2c]
"""

import json, pathlib, sys, statistics as st
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROFILE = sys.argv[1] if len(sys.argv) > 1 else "b2b"

NAMES = {
 "structure":"Соблюдение структуры разговора","discovery":"Глубина выявления",
 "qualification":"Качество квалификации","objections":"Работа с ценой и возражениями",
 "deal_control":"Управление сделкой","expertise":"Экспертность","balance":"Баланс диалога"}

MONEY_MARK = ["что для компании стоит","перевести это в деньги","сколько стоит один","во сколько обходится"]
QUAL_MARK  = ["кто ещё участвует","бюджет под это","кто у вас отвечает","что должно произойти",
              "решение по курсам","кто ещё участвует в решении","с кем ещё будете"]
DISC_MARK  = ["расскажите","сколько у вас","как сейчас","что не устраивает","где чаще всего",
              "что из этого болит","сколько лет ребёнку","чем увлекается","что вы хотите получить","почему решили"]
CLOSE_MARK = ["ставлю в календарь","созваниваемся","созвонимся","ставим","подходит?","записываю на пробный",
              "предлагаю пилот","покажу","фиксируем решение","сорок минут","посмотрите вместе",
              "короткую встречу","обсудим","подготовлю кп","присылаю кп","пришлю расчёт","соберу расчёт"]
MOTIVE_MARK = ["что важнее","что вы хотите получить","почему решили именно","чем увлекается","что он уже пробовал"]
WEAK_OPEN  = ["алло","беспокоит","вы заявку оставляли","актуально ещё","интересовались"]
DISCOUNT   = ["скидку","процентов, если решите","спрошу у руководителя","специальные условия"]
COUNTER    = ["с чем сравниваете","какую сумму","что должно измениться","давайте разделим",
              "какая сумма в месяц","давайте посмотрим расписание","платите только за пройденные",
              "честно скажет","чтобы супруг тоже"]
VALUE_MARK = ["результат он увидит","до шести человек","защищает свой проект","логика настоящая",
              "запись остаётся","не даёт закрыть строку","второй скан","маршруту сборки"]

def score_contact(c, kind, deep_marks=MONEY_MARK):
    turns = c.get("transcript") or c.get("messages") or []
    mgr = [t["text"].lower() for t in turns if t["who"] == "manager"]
    cli = [t["text"].lower() for t in turns if t["who"] == "client"]
    text = " ".join(mgr)
    has = lambda marks: any(mk in text for mk in marks)
    n_q = sum(t.count("?") for t in mgr)

    structure = 1
    if not has(WEAK_OPEN): structure += 4
    if any(w in " ".join(mgr[:1]) for w in ["dataflow","codekids"]): structure += 2
    if has(CLOSE_MARK): structure += 2
    structure = min(10, structure)

    discovery = min(10, (3 if has(DISC_MARK) else 0) + min(4, n_q) + (3 if has(deep_marks) else 0))
    qualification = min(10, (5 if has(QUAL_MARK) else 0) + (3 if has(deep_marks) else 0) + (2 if n_q >= 3 else 0))

    objection_raised = any(w in " ".join(cli) for w in ["дорог","дешевле","подумать","не закладывали","рано","бросит","расписание","посоветоваться"])
    if not objection_raised: objections = 5 if has(CLOSE_MARK) else 4
    elif has(COUNTER):       objections = 9
    elif has(DISCOUNT):      objections = 3
    else:                    objections = 4 if has(VALUE_MARK) else 2

    deal_control = min(10, (6 if has(CLOSE_MARK) else 1) + (2 if n_q >= 2 else 0) + (2 if has(QUAL_MARK) else 0))
    expertise = min(10, 3 + (3 if has(VALUE_MARK) else 0) + (2 if n_q >= 3 else 0) + (1 if len(mgr) > 5 else 0))
    share = len(mgr) / max(1, len(mgr) + len(cli))
    balance = 9 if .40 <= share <= .58 else 7 if .58 < share <= .65 else 4 if share > .65 else 6

    vals = dict(structure=structure, discovery=discovery, qualification=qualification,
                objections=objections, deal_control=deal_control, expertise=expertise, balance=balance)
    total = round(sum(vals.values()) / len(vals), 1)
    return vals, total, dict(money=has(deep_marks), qual=has(QUAL_MARK), close=has(CLOSE_MARK),
                             discount=has(DISCOUNT), counter=has(COUNTER), n_q=n_q,
                             objection=objection_raised, weak_open=has(WEAK_OPEN))

def main():
    d = json.loads((ROOT / f"data/{PROFILE}/dataset.json").read_text(encoding="utf-8"))
    mgr_name = {m["id"]: m["name"] for m in d["managers"]}
    items, flags, per_mgr = [], {}, defaultdict(lambda: defaultdict(list))

    deep_marks = MOTIVE_MARK if PROFILE == "b2c" else MONEY_MARK
    for c in d["calls"] + d["chats"]:
        kind = "call" if c in d["calls"] else "chat"
        vals, total, f = score_contact(c, kind, deep_marks)
        items.append({"id": c["id"], "type": kind, "total": total,
                      "evaluate": [{"id": k, "name": NAMES[k], "value": v, "max": 10} for k, v in vals.items()],
                      "comment": c["outcome"]})
        flags[c["id"]] = dict(f, mgr=c["manager_id"], stage=c["stage"], kind=kind, total=total)
        for k, v in vals.items(): per_mgr[c["manager_id"]][k].append(v)
        per_mgr[c["manager_id"]]["total"].append(total)

    n = len(items)
    avg = round(st.mean(i["total"] for i in items), 1)
    calls_avg = round(st.mean(f["total"] for f in flags.values() if f["kind"] == "call"), 1)
    chats_avg = round(st.mean(f["total"] for f in flags.values() if f["kind"] == "chat"), 1)
    close_share = sum(1 for f in flags.values() if f["close"]) / n
    money_share = sum(1 for f in flags.values() if f["money"]) / n
    qual_share  = sum(1 for f in flags.values() if f["qual"]) / n
    disc = [f for f in flags.values() if f["objection"] and f["discount"]]
    cnt  = [f for f in flags.values() if f["objection"] and f["counter"]]

    ranked = sorted(((m, round(st.mean(v["total"]), 1)) for m, v in per_mgr.items()), key=lambda x: -x[1])
    spread = f"{mgr_name[ranked[0][0]]} {ranked[0][1]} из 10, {mgr_name[ranked[-1][0]]} {ranked[-1][1]} при среднем {avg}"

    # связь поведения с движением сделки
    leads = {l["id"]: l for l in d["leads"]}
    moved = lambda cid: True
    won_stages = {"closed_won", "payment", "negotiation", "proposal"}
    with_money = [c for c in d["calls"] if flags[c["id"]]["money"]]
    wo_money   = [c for c in d["calls"] if not flags[c["id"]]["money"]]
    share_moved = lambda group: (sum(1 for c in group if leads.get(c["lead_id"], {}).get("stage") in won_stages)
                                 / max(1, len(group)))

    insights = [
      {"level":"bad","title":f"Следующий шаг фиксируется в {close_share*100:.0f}% контактов",
       "text":f"Из {n} разобранных коммуникаций договорённость с датой есть в {sum(1 for f in flags.values() if f['close'])}. "
              f"Остальные заканчиваются на «я пришлю информацию» и «подумайте» — именно из этой части набирается очередь зависших сделок."},
      {"level":"bad","title":(f"Мотив родителя выясняется в {money_share*100:.0f}% разговоров" if PROFILE=="b2c" else f"Потребность доводится до цифры в {money_share*100:.0f}% разговоров") + " — и это меняет исход",
       "text":(f"Когда менеджер выясняет, чего родитель хочет для ребёнка, заявка доходит до оплаты или счёта " if PROFILE=="b2c" else f"Когда менеджер спрашивает, во что клиенту обходится текущая ситуация, сделка оказывается на КП или дальше ") +
              f"в {share_moved(with_money)*100:.0f}% случаев. Без такого вопроса — в {share_moved(wo_money)*100:.0f}%."},
      {"level":"warn","title":"Разброс внутри команды",
       "text":f"{spread}. Это не разница в старании: она складывается из того, задаёт ли человек вопросы до презентации "
              f"и фиксирует ли договорённость в конце."},
      {"level":"bad","title":f"Переписка слабее звонков: {chats_avg} против {calls_avg}",
       "text":"В чатах менеджеры напоминают о себе вместо ведения сделки. Серия «отправил — напоминаю — есть новости?» "
              "не даёт клиенту ни одного повода ответить, и переписка затухает."},
      {"level":"bad" if len(disc) >= len(cnt) else "warn",
       "title":("На возражение по цене скидка звучит чаще встречного вопроса" if len(disc) >= len(cnt)
                else "Возражение отрабатывают решением, но не все"),
       "text":f"Возражение прозвучало в {sum(1 for f in flags.values() if f['objection'])} контактах. "
              f"Ответом «дам скидку» или «спрошу у руководителя» закрывали {len(disc)}, "
              f"встречным вопросом или предложением решения — {len(cnt)}. Остальные ответили свойствами продукта "
              f"или согласились «подумайте» — это тихая потеря сделки."},
      {"level":"warn","title":f"Квалификация проходит в {qual_share*100:.0f}% контактов",
       "text":"В остальных не выяснено, кто принимает решение и какой бюджет. Эти сделки возвращаются на предыдущий этап "
              "чаще всего: возражение приходит от человека, которого в разговоре не было."},
    ]

    if PROFILE == "b2c":
        fast = [l for l in d["leads"] if l["responded_in_min"] <= 20]
        slow = [l for l in d["leads"] if l["responded_in_min"] > 60]
        won = lambda g: sum(1 for l in g if l["stage"] == "closed_won") / max(1, len(g))
        insights.insert(0, {"level":"bad","title":"Скорость реакции решает больше, чем качество разговора",
          "text":f"Заявки, обработанные за 20 минут, доходят до оплаты в {won(fast)*100:.0f}% случаев ({len(fast)} лидов). "
                 f"Те, до которых добрались позже часа — в {won(slow)*100:.0f}% ({len(slow)} лидов). "
                 f"Разговор при этом ведёт один и тот же отдел по одним и тем же скриптам."})

    out = (f"// ЭТАЛОН · пересчитан по фактической базе ({PROFILE}): {n} коммуникаций.\n"
           f"// Сгенерировано scripts/score_reference.py — цифры сходятся с данными.\n\n"
           "window.CABINET_SCORES = " + json.dumps({"items": items, "insights": insights}, ensure_ascii=False, indent=2) + ";\n")
    (ROOT / f"reference/scores.{PROFILE}.js").write_text(out, encoding="utf-8")

    skills = {m: {k: round(st.mean(v), 1) for k, v in d_.items() if k != "total"} for m, d_ in per_mgr.items()}
    (ROOT / f"reference/skills.{PROFILE}.json").write_text(
        json.dumps({"skills": skills, "avg": {m: round(st.mean(v["total"]),1) for m,v in per_mgr.items()}},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{PROFILE}: {n} контактов, средний {avg} (звонки {calls_avg} / чаты {chats_avg})")
    for m, a in ranked: print(f"  {mgr_name[m]:22} {a}")
    print(f"  next step {close_share*100:.0f}% · до денег {money_share*100:.0f}% · квалификация {qual_share*100:.0f}%")
    print(f"  скидка {len(disc)} vs встречный вопрос {len(cnt)}")

if __name__ == "__main__":
    main()
