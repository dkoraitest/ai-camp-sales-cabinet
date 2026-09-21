#!/usr/bin/env python3
"""«Включи демо» на любом шаге.

Если у участника что-то не получилось, он не должен выпасть из потока.
Скрипт смотрит, какие шаги уже собраны, кладёт в кабинет эталон текущего
шага из reference/ и собирает вкладку. Дальше участник идёт по шагам.

    python3 scripts/demo_step.py            # определить шаг и включить демо
    python3 scripts/demo_step.py --step 3   # включить демо конкретного шага
    python3 scripts/demo_step.py --status   # только показать, что собрано

Эталоны построены на демо-базе B2B, поэтому кабинет целиком переключается
на неё. Файлы участника не пропадают: они сохраняются в active/before-demo/.
"""

import argparse, json, pathlib, shutil, subprocess, sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAB, REF = ROOT / "cabinet", ROOT / "reference"
STEPS = {
    1: {"name": "разбор коммуникаций", "blocks": ["me", "overview", "contacts", "insights"], "file": "scores.js",
        "next": "подключи тренера", "see": "Менеджер → выберите себя в «Я» → Мои звонки"},
    2: {"name": "тренер", "blocks": ["managers"], "file": "coach.js",
        "next": "следующее касание", "see": "Менеджер → Мой тренер; Руководитель → Команда"},
    3: {"name": "следующее касание", "blocks": ["leads"], "file": "enrich.js",
        "next": "глубокая аналитика", "see": "Менеджер → Мои сделки → сделка с пометкой «касание готово» (демо-база — B2B)"},
    4: {"name": "глубокая аналитика", "blocks": ["deep"], "file": "deep.js",
        "next": None, "see": "Руководитель → Глубокая аналитика"},
}


def built():
    f = CAB / ".blocks.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("blocks", [])
    except Exception:
        return []


def done(step, blocks):
    s = STEPS[step]
    return all(b in blocks for b in s["blocks"]) and (CAB / s["file"]).exists()


def current():
    """Текущий шаг — первый несобранный. Шаг 0 — если базы ещё нет."""
    blocks = built()
    cfg = CAB / "config.js"
    has_base = cfg.exists() and ((ROOT / "data/own/dataset.json").exists() or
                                 'profile: "b2b"' in cfg.read_text(encoding="utf-8") or
                                 'profile: "b2c"' in cfg.read_text(encoding="utf-8"))
    if not has_base and not blocks:
        return 0
    for n in (1, 2, 3, 4):
        if not done(n, blocks):
            return n
    return 5


def backup(names):
    dst = ROOT / "active" / "before-demo" / datetime.now().strftime("%H%M%S")
    saved = []
    for n in names:
        f = CAB / n
        if f.exists():
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst / n); saved.append(n)
    return dst if saved else None


def run(*cmd):
    r = subprocess.run([sys.executable, *cmd], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stdout + r.stderr)


MARK = CAB / ".demo.json"


def repeat_guard(step):
    """Повторный вызов без собственных действий не должен перескакивать шаг.
    Участник мог просто не обновить страницу и сказать «не работает».
    Тогда пересобираем тот же шаг и просим обновить страницу."""
    try:
        m = json.loads(MARK.read_text(encoding="utf-8"))
    except Exception:
        return None
    if m.get("blocks") == built() and step == m.get("step", -1) + 1:
        return m["step"]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, choices=[0, 1, 2, 3, 4])
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    step = a.step if a.step is not None else current()

    if a.status:
        blocks = built()
        print("Собрано:", ", ".join(blocks) or "ничего")
        print("Текущий шаг:", step if step < 5 else "все шаги пройдены")
        return
    again = repeat_guard(step) if a.step is None else None
    if step == 5 and again is None:
        print("Все шаги уже собраны. Полный эталон: откройте demo/index.html")
        return
    if again is not None:
        step = again
    was_b2c = False
    try:
        was_b2c = json.loads((ROOT / "active/profile.json").read_text(encoding="utf-8")).get("audience") == "b2c" \
                  and 'profile: "own"' in (CAB / "config.js").read_text(encoding="utf-8")
    except Exception:
        pass

    CAB.mkdir(exist_ok=True)
    touched = ["config.js"] + [STEPS[n]["file"] for n in range(1, max(step, 1) + 1) if n <= step]
    saved = None if again is not None else backup(touched)

    # эталоны построены на демо-базе B2B — переключаем кабинет на неё целиком
    shutil.copy2(REF / "config.js", CAB / "config.js")
    run("scripts/build_data.py")
    if again is not None:
        s = STEPS.get(step)
        print(f"Эталон шага {step} уже был в кабинете — пересобрал его ещё раз, вперёд не шагаю.")
        print("  Обновите страницу: Cmd+R (Mac) или Ctrl+R (Windows)" +
              (f" — {s['see']}." if s else ", дальше говорите `разбери коммуникации`."))
        if s and s["next"]:
            print(f"  Следующий шаг — `{s['next']}`.")
    if step == 0 and again is None:
        print("✓ Демо: подключена база DataFlow Solutions (B2B, 271 разговор).")
        print("  Дальше: скажите `шаг 1` (или `разбери коммуникации`).")
    elif step > 0:
        blocks = []
        for n in range(1, step + 1):
            shutil.copy2(REF / STEPS[n]["file"], CAB / STEPS[n]["file"])
            blocks += STEPS[n]["blocks"]
        if step < 4:
            # выводы по всей базе появляются на шаге 4: раньше «инсайты выросли» не случится
            f = CAB / "scores.js"; t = f.read_text(encoding="utf-8")
            head, body = t.split("{", 1)
            j = json.loads("{" + body[:body.rindex("}") + 1])
            j["insights"] = [x for x in j.get("insights", []) if x.get("scope") != "base"]
            f.write_text(head + json.dumps(j, ensure_ascii=False, indent=2) + ";\n", encoding="utf-8")
        first = not (CAB / "index.html").exists()
        run("scripts/build_cabinet.py", "--blocks", ",".join(blocks))   # впервые — откроет сам
        s = STEPS[step]
        if again is None: print(f"✓ Демо шага {step} ({s['name']}): эталон в кабинете, вкладки собраны.")
        if again is None:
            print(f"  {'Кабинет открылся в браузере (если нет — cabinet/index.html двойным кликом)' if first else 'Обновите вкладку кабинета: Cmd+R или F5'}: {s['see']}.")
            if s["next"]:
                print(f"  Дальше — следующий шаг: `{s['next']}`.")
    MARK.write_text(json.dumps({"step": step, "blocks": built()}, ensure_ascii=False), encoding="utf-8")
    if was_b2c:
        print("  Демо-база — продажи компаниям (B2B): вместо «Моей очереди» будут «Мои сделки». "
              "Механика та же, для потока заявок всё сработает на вашей базе.")
    if saved:
        print(f"  Ваши файлы сохранены в {saved.relative_to(ROOT)} — к своей базе можно вернуться после конференции.")


if __name__ == "__main__":
    main()
