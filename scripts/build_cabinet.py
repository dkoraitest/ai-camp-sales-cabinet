#!/usr/bin/env python3
"""Сборка кабинета из заготовок.

Кабинет растёт по ходу воркшопа: на каждом шаге подключается новый блок,
а собранный файл остаётся одним самодостаточным HTML — его можно отправить
руководителю вложением, и он откроется двойным кликом.

    python3 scripts/build_cabinet.py --blocks overview,contacts,insights   # шаг 1
    python3 scripts/build_cabinet.py --add managers                        # шаг 2
    python3 scripts/build_cabinet.py --add leads                           # шаг 3
    python3 scripts/build_cabinet.py --add deep                            # шаг 4
    python3 scripts/build_cabinet.py --list                                # что подключено
    python3 scripts/build_cabinet.py --rebuild                             # пересобрать то же самое
    python3 scripts/build_cabinet.py --blocks ... --out demo               # собрать в другую папку
"""

import argparse, pathlib, re, json, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BLOCKS = ROOT / "blocks"
OUT_DIR = ROOT / "cabinet"
STATE = OUT_DIR / ".blocks.json"

KNOWN = {
    "overview": "Обзор — метрики, воронка, матрица оценки",
    "contacts": "Коммуникации — звонки и переписка с разбором",
    "insights": "Инсайты — закономерности, которые нашла система",
    "managers": "Менеджеры — карта навыков, обратная связь, тренировки",
    "leads":    "Лиды — карточки, обогащение, готовые сообщения",
    "deep":     "Глубокая аналитика — кросс-аналитика по всей базе",
}
ORDER = ["overview", "contacts", "insights", "managers", "leads", "deep"]


def read_state(state=None):
    state = state or STATE
    if state.exists():
        try: return json.loads(state.read_text(encoding="utf-8")).get("blocks", [])
        except Exception: return []
    return []


def build(blocks, out_dir=None):
    out_dir = out_dir or OUT_DIR
    state = out_dir / ".blocks.json"
    blocks = [b for b in ORDER if b in blocks]
    core = (BLOCKS / "_core.html").read_text(encoding="utf-8")
    parts = []
    for b in blocks:
        f = BLOCKS / f"{b}.js"
        if not f.exists():
            sys.exit(f"Нет заготовки blocks/{b}.js")
        parts.append(f"<script>\n{f.read_text(encoding='utf-8')}\n</script>")
    html = core.replace("<!-- BLOCKS -->", "\n".join(parts))

    out_dir.mkdir(exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    state.write_text(json.dumps({"blocks": blocks}, ensure_ascii=False, indent=2), encoding="utf-8")

    # config.js создаётся один раз и дальше правится шагом 0
    cfg = out_dir / "config.js"
    if not cfg.exists():
        tpl = ROOT / "blocks/config.template.js"
        if tpl.exists(): cfg.write_text(tpl.read_text(encoding="utf-8"), encoding="utf-8")

    return blocks, html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", help="список блоков через запятую (пересобрать с нуля)")
    ap.add_argument("--add", help="добавить блок к уже собранным")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--rebuild", action="store_true",
                    help="пересобрать с теми же вкладками — после обновления заготовок")
    ap.add_argument("--out", help="папка сборки; по умолчанию cabinet/. Демо собирается в demo/, "
                                  "чтобы не трогать кабинет участника")
    a = ap.parse_args()

    out_dir = (ROOT / a.out) if a.out else OUT_DIR
    current = read_state(out_dir / ".blocks.json")

    if a.list:
        if not current:
            print("Кабинет ещё не собран. Первый блок подключается на шаге 1.")
        else:
            print("Подключено:")
            for b in current: print(f"  ✓ {b:9} — {KNOWN[b]}")
            rest = [b for b in ORDER if b not in current]
            if rest:
                print("Ещё не подключено:")
                for b in rest: print(f"  · {b:9} — {KNOWN[b]}")
        return

    if a.add:
        wanted = [x.strip() for x in a.add.split(",")]
        unknown = [x for x in wanted if x not in KNOWN]
        if unknown: sys.exit(f"Неизвестный блок: {', '.join(unknown)}. Доступны: {', '.join(ORDER)}")
        blocks = current + [x for x in wanted if x not in current]
    elif a.rebuild:
        if not current:
            sys.exit("Пересобирать нечего: кабинет ещё не собирался. Первый блок подключается на шаге 1.")
        blocks = current
    elif a.blocks:
        wanted = [x.strip() for x in a.blocks.split(",")]
        unknown = [x for x in wanted if x not in KNOWN]
        if unknown: sys.exit(f"Неизвестный блок: {', '.join(unknown)}. Доступны: {', '.join(ORDER)}")
        blocks = wanted
    else:
        sys.exit("Нужен --blocks, --add или --rebuild. Что подключено сейчас: --list")

    blocks, html = build(blocks, out_dir)
    new = [b for b in blocks if b not in current]
    print(f"✓ Кабинет собран: {len(blocks)} вкладок, {len(html)//1024} KB")
    for b in blocks:
        mark = "+" if b in new else " "
        print(f"  {mark} {b:9} — {KNOWN[b]}")
    print(f"\n  Открыть: {(out_dir / 'index.html').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
