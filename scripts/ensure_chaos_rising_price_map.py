#!/usr/bin/env python3
"""Zet Chaos Rising terug op de veiligere Cardmarket-mapping.

De test met expansionId 6596 gaf duidelijk slechter resultaat: Chaos Rising ging
van 67 naar 117 niet-gekoppelde kaarten. Daarom zetten we CRI terug op 6517.
Dit script past alleen die ene regel aan in cardmarket_manual_set_map.csv.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "cardmarket_manual_set_map.csv"

LINE_PREFIX = "Mega Evolution;Chaos Rising;CRI;"
NEW_LINE = (
    "Mega Evolution;Chaos Rising;CRI;6517;;;"
    "\"teruggezet na test: expansionId 6596 gaf slechter resultaat; "
    "6517 koppelde meer Chaos Rising-kaarten en blijft voorlopig de veiligere mapping\""
)


def main() -> int:
    if not MAP_PATH.exists():
        raise SystemExit("cardmarket_manual_set_map.csv niet gevonden")

    text = MAP_PATH.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    changed = False
    out: list[str] = []

    for line in lines:
        if line.startswith(LINE_PREFIX):
            out.append(NEW_LINE)
            changed = True
        else:
            out.append(line)

    if not changed:
        out.insert(1, NEW_LINE)
        changed = True

    MAP_PATH.write_text("\ufeff" + "\n".join(out) + "\n", encoding="utf-8")
    print("Chaos Rising mapping teruggezet op Cardmarket expansionId 6517")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
