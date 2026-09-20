#!/usr/bin/env python3
"""Выборка контактов для разбора.

База большая — читать её целиком агенту дорого и незачем: сравнивать всё
равно можно только контакты одного этапа воронки. Скрипт достаёт срез
и кладёт в active/sample.json, дальше агент работает с ним.

    python3 scripts/sample.py                       # фокусный этап, 30 контактов
    python3 scripts/sample.py --stage demo --n 20
    python3 scripts/sample.py --profile b2c --manager m2
"""
import json, argparse, pathlib, random, re

ROOT = pathlib.Path(__file__).resolve().parent.parent

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None)
    ap.add_argument("--stage", default=None)
    ap.add_argument("--manager", default=None)
    ap.add_argument("--kind", choices=["call", "chat"], default=None)
    ap.add_argument("--n", type=int, default=30)
    a = ap.parse_args()

    cfg = (ROOT / "cabinet/config.js").read_text(encoding="utf-8")
    prof = a.profile or (re.search(r'profile:\s*"(\w+)"', cfg) or [None, "b2b"])[1]
    stage = a.stage or (re.search(r'focus_stage:\s*"(\w+)"', cfg) or [None, None])[1]

    d = json.loads((ROOT / f"data/{prof}/dataset.json").read_text(encoding="utf-8"))
    items = [dict(c, _kind="call") for c in d["calls"]] + [dict(c, _kind="chat") for c in d["chats"]]
    if stage:     items = [c for c in items if c["stage"] == stage] or items
    if a.manager: items = [c for c in items if c["manager_id"] == a.manager]
    if a.kind:    items = [c for c in items if c["_kind"] == a.kind]

    random.seed(42)
    picked = random.sample(items, min(a.n, len(items)))
    out = ROOT / "active"; out.mkdir(exist_ok=True)
    (out / "sample.json").write_text(json.dumps({
        "profile": prof, "stage": stage, "total_in_base": len(d["calls"]) + len(d["chats"]),
        "picked": len(picked), "managers": d["managers"],
        "funnel": d["profile"].get("funnel", []), "items": picked
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    kb = (out / "sample.json").stat().st_size // 1024
    print(f"{prof} · этап {stage or 'все'} · {len(picked)} из {len(d['calls'])+len(d['chats'])} → active/sample.json ({kb} KB)")

if __name__ == "__main__":
    main()
