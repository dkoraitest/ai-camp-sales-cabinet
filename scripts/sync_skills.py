#!/usr/bin/env python3
"""Копия скиллов для Codex.

Источник — .claude/skills (Claude Code). Codex ищет скиллы в .agents/skills.
Копируем файлами, а не симлинком: на Windows симлинк превращается в
текстовый файл с путём, и Codex его не прочитает.

    python3 scripts/sync_skills.py          # обновить копию
    python3 scripts/sync_skills.py --check  # проверить, что копия свежая
"""

import argparse, filecmp, pathlib, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC, DST = ROOT / ".claude" / "skills", ROOT / ".agents" / "skills"


def stale():
    out = []
    for f in SRC.rglob("*"):
        if f.is_file():
            g = DST / f.relative_to(SRC)
            if not g.exists() or not filecmp.cmp(f, g, shallow=False):
                out.append(str(f.relative_to(SRC)))
    for g in DST.rglob("*") if DST.exists() else []:
        if g.is_file() and not (SRC / g.relative_to(DST)).exists():
            out.append(str(g.relative_to(DST)) + " (лишний)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    diff = stale()
    if a.check:
        if diff:
            print("Копия скиллов для Codex устарела:", *diff, sep="\n  ")
            print("Обновить: python3 scripts/sync_skills.py")
            sys.exit(1)
        print("✓ .agents/skills совпадает с .claude/skills")
        return
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)
    n = sum(1 for _ in DST.rglob("SKILL.md"))
    print(f"✓ Скиллы скопированы для Codex: {n} → .agents/skills")


if __name__ == "__main__":
    main()
