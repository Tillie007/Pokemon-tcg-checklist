#!/usr/bin/env python3
"""Zet Chaos Rising op de sterkste huidige Cardmarket-kandidaat.

De analyse toont voor Chaos Rising (CRI) momenteel expansionId 6596 als sterkste kandidaat.
Dit script past alleen die ene regel aan in cardmarket_manual_set_map.csv.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "cardmarket_manual_set_map.csv"

OLD_PREFIX = "Mega Evolution;Chaos Rising;CRI;"
NEW_LINE = (
    "Mega Evolution;Chaos Rising;CRI;6596;;;"
    "\"handmatig aangepast: sterkste kandidaat uit cardmarket_set_mapping_candidates; "
    "rang 1; score 0.132; overlap 10; cmProducten 74; vorige mapping 6517 gaf te veel ontbrekende prijzen\""
)


def main() -> int:
    if not MAP_PATH.exists():
        raise SystemExit("cardmarket_manual_set_map.csv niet gevonden")

    text = MAP_PATH.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    changed = False
    out: list[str] = []

    for line in lines:
        if line.startswith(OLD_PREFIX):
            out.append(NEW_LINE)
            changed = True
        else:
            out.append(line)

    if not changed:
        out.insert(1, NEW_LINE)
        changed = True

    MAP_PATH.write_text("\ufeff" + "\n".join(out) + "\n", encoding="utf-8")
    print("Chaos Rising mapping ingesteld op Cardmarket expansionId 6596")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
