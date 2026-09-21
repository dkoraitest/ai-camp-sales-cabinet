#!/usr/bin/env python3
"""Контекст для следующего касания — шаг 3.

Агенту не нужно читать всю базу, чтобы подготовить одно касание. Скрипт
собирает всё про одну сделку: карточку из CRM, внешние события, все
разговоры по порядку и то, что из них уже извлёк разбор шага 1.

    python3 scripts/touch_context.py                 # предложить сделки для касания
    python3 scripts/touch_context.py --manager m2    # то же для конкретного менеджера
    python3 scripts/touch_context.py l042            # контекст одной сделки

Всё на синтетике и без веб-поиска: события по компании уже лежат в базе.
"""

import argparse, json, pathlib, re, sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load(prof=None):
    cfg = (ROOT / "cabinet/config.js").read_text(encoding="utf-8") if (ROOT / "cabinet/config.js").exists() else ""
    prof = prof or (re.search(r'profile:\s*[\'"](\w+)', cfg) or [None, "b2b"])[1]
    d = json.loads((ROOT / f"data/{prof}/dataset.json").read_text(encoding="utf-8"))
    sc = {}
    f = ROOT / "cabinet/scores.js"
    if f.exists():
        t = f.read_text(encoding="utf-8")
        try:
            sc = {i["id"]: i for i in json.loads(t[t.index("{"):t.rindex("}") + 1]).get("items", [])}
        except Exception:
            pass
    return prof, d, sc


def when(c):
    return c.get("date") or c.get("date_start")


def suggest(d, sc, manager=None):
    stages = d["profile"]["stages"]; term = set(stages[-2:])
    comms = d["calls"] + d["chats"]
    now = max(datetime.fromisoformat(when(c)) for c in comms)
    rows = []
    for l in d["leads"]:
        if l["stage"] in term:
            continue
        owner = l.get("owner") or l.get("manager_id")
        if manager and owner != manager:
            continue
        cs = [c for c in comms if c["lead_id"] == l["id"]]
        if len(cs) < 2:
            continue
        last = max(datetime.fromisoformat(when(c)) for c in cs)
        ns = l.get("next_step")
        why = []
        if ns and ns < now.date().isoformat(): why.append("следующий шаг просрочен")
        elif ns: why.append(f"шаг {ns}")
        else: why.append("следующего шага нет")
        if l.get("events"): why.append(f"событий у клиента: {len(l['events'])}")
        idle = (now - last).days
        weight = (3 if ns and ns < now.date().isoformat() else 0) + len(l.get("events", [])) + len(cs) / 3 + \
                 stages.index(l["stage"]) + (2 if idle > 7 else 0)
        rows.append((weight, l, len(cs), idle, why))
    rows.sort(key=lambda x: -x[0])
    name = {m["id"]: m["name"] for m in d["managers"]}
    print("Сделки, где касание сейчас нужнее всего:\n")
    for w, l, n, idle, why in rows[:5]:
        who = l.get("company") or l.get("parent") or l.get("contact")
        print(f"  {l['id']:<6} {who:<24} {d['profile']['stage_labels'].get(l['stage'], l['stage']):<22} "
              f"{name.get(l.get('owner') or l.get('manager_id'), ''):<18} разговоров {n}, тишина {idle} дн. · {', '.join(why)}")
    print("\nКонтекст одной: python3 scripts/touch_context.py <id>")


def context(d, sc, lid):
    l = next((x for x in d["leads"] if x["id"] == lid), None)
    if not l:
        sys.exit(f"Нет сделки {lid}. Список кандидатов: python3 scripts/touch_context.py")
    labels = d["profile"].get("stage_labels", {})
    name = {m["id"]: m["name"] for m in d["managers"]}
    print(f"# Сделка {lid} · {l.get('company') or l.get('parent') or l.get('contact')}")
    print(f"Этап: {labels.get(l['stage'], l['stage'])} · сумма {l.get('value_kzt')} ₸ · "
          f"ответственный {name.get(l.get('owner') or l.get('manager_id'), '—')} · следующий шаг {l.get('next_step') or 'нет'}")
    skip = {"id", "stage", "value_kzt", "owner", "manager_id", "next_step", "events"}
    print("Карточка CRM: " + "; ".join(f"{k}: {v}" for k, v in l.items() if k not in skip and v not in (None, "")))
    if l.get("events"):
        print("\n## Внешние события (синтетика: новости, hh.kz, goszakup)")
        for e in l["events"]:
            print(f"- {e['date']} · {e['type']} · {e['title']} ({e['source']})")
    comms = sorted([c for c in d["calls"] + d["chats"] if c["lead_id"] == lid], key=when)
    print(f"\n## Разговоры: {len(comms)}")
    for c in comms:
        kind = "звонок" if "transcript" in c else c.get("channel", "переписка")
        s = sc.get(c["id"])
        print(f"\n### {c['id']} · {when(c)[:16]} · {kind} · {labels.get(c['stage'], c['stage'])} · "
              f"{name.get(c['manager_id'], '')}" + (f" · балл {s['total']}" if s else ""))
        print(f"Итог: {c.get('outcome', '')}")
        ex = (s or {}).get("extracted")
        if ex:
            print("Извлечено разбором: " + json.dumps(ex, ensure_ascii=False))
        for t in c.get("transcript") or c.get("messages") or []:
            print(f"  {'М' if t['who'] == 'manager' else 'К'}: {t['text']}")
    print(f"\n## Что продаём: {d['profile'].get('what_we_sell', '')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lead", nargs="?")
    ap.add_argument("--manager")
    ap.add_argument("--profile", help="по умолчанию из cabinet/config.js")
    a = ap.parse_args()
    prof, d, sc = load(a.profile)
    if a.lead:
        context(d, sc, a.lead)
    else:
        suggest(d, sc, a.manager)


if __name__ == "__main__":
    main()
