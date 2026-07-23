#!/usr/bin/env python3
"""
Zorg dat Pitch Black (PBL) gekoppeld is aan de juiste Cardmarket-expansion.
Daarna kan scripts/update_prices.py de prijzen koppelen.
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "cardmarket_manual_set_map.csv"

PBL_ROW = {
    "serie": "Mega Evolution",
    "set": "Pitch Black",
    "appAfkorting": "PBL",
    "cardmarketExpansionId": "6569",
    "cardmarketSetcode": "",
    "cardmarketSetnaam": "",
    "opmerking": "handmatig toegevoegd: sterke kandidaat uit cardmarket_set_mapping_candidates; score 0.1591; overlap 14; cmProducten 120",
}

FIELDS = [
    "serie",
    "set",
    "appAfkorting",
    "cardmarketExpansionId",
    "cardmarketSetcode",
    "cardmarketSetnaam",
    "opmerking",
]


def main() -> int:
    if not MAP_PATH.exists():
        raise SystemExit("cardmarket_manual_set_map.csv niet gevonden")

    rows: list[dict[str, str]] = []
    with MAP_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            rows.append({k: (row.get(k) or "") for k in FIELDS})

    found = False
    for row in rows:
        if row.get("serie") == "Mega Evolution" and row.get("set") == "Pitch Black" and row.get("appAfkorting") == "PBL":
            row.update(PBL_ROW)
            found = True
            break

    if not found:
        rows.insert(0, PBL_ROW.copy())

    with MAP_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter=";", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print("Pitch Black price mapping klaar: Mega Evolution / Pitch Black / PBL -> Cardmarket expansion 6569")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
