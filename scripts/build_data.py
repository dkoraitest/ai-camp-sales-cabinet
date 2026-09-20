#!/usr/bin/env python3
"""Собирает cabinet/data.js из data/*/dataset.json.

Кабинет открывается как file://, поэтому fetch() к локальным файлам блокируется
браузером. Данные подключаются тегом <script>, отсюда и этот сборщик.

Запускать после любой правки датасетов:
    python3 scripts/build_data.py
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROFILES = ("b2b", "b2c", "own")   # own — база участника, появляется после шага 0


def main() -> None:
    bundle = {}
    for profile in PROFILES:
        path = ROOT / "data" / profile / "dataset.json"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as fh:
            bundle[profile] = json.load(fh)
        calls = len(bundle[profile]["calls"])
        leads = len(bundle[profile]["leads"])
        print(f"  {profile}: {calls} звонков, {leads} лидов")

    out = ROOT / "cabinet" / "data.js"
    out.parent.mkdir(exist_ok=True)
    payload = json.dumps(bundle, ensure_ascii=False, indent=2)
    out.write_text(
        "// Сгенерировано scripts/build_data.py — руками не править.\n"
        "// Правьте data/<profile>/dataset.json и пересоберите.\n"
        f"window.CABINET_DATA = {payload};\n",
        encoding="utf-8",
    )
    demo = ROOT / "demo" / "data.js"
    if demo.parent.exists():
        demo.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"→ {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)" +
          (" · demo/data.js обновлён" if demo.parent.exists() else ""))


if __name__ == "__main__":
    main()
