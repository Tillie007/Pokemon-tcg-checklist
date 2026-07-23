#!/usr/bin/env python3
"""
Synchroniseer pokemon_cards_data.json naar de embedded kaartdata in index.html.
De hoofdapp bevat nog een grote ingebouwde JSON-lijst; nieuwe sets in pokemon_cards_data.json
zijn pas zichtbaar als die embedded lijst ook wordt bijgewerkt.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "index.html"
DATA_PATH = ROOT / "pokemon_cards_data.json"
DEBUG_PATH = ROOT / "sync_card_data_debug.json"


def find_embedded_data_region(text: str) -> tuple[int, int, dict[str, Any]]:
    decoder = json.JSONDecoder()
    starts: list[int] = []
    needle = '{"sets":['
    pos = 0
    while True:
        idx = text.find(needle, pos)
        if idx == -1:
            break
        starts.append(idx)
        pos = idx + 1

    # Sommige versies hebben spaties na de dubbele punten.
    if not starts:
        for marker in ('{"sets"', '{\n  "sets"', '{\r\n  "sets"'):
            pos = 0
            while True:
                idx = text.find(marker, pos)
                if idx == -1:
                    break
                starts.append(idx)
                pos = idx + 1

    best: tuple[int, int, dict[str, Any]] | None = None
    best_cards = -1

    for start in starts:
        try:
            obj, end_rel = decoder.raw_decode(text[start:])
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        cards = obj.get("cards")
        sets = obj.get("sets")
        if not isinstance(cards, list) or not isinstance(sets, list):
            continue
        if len(cards) < 1000 or len(sets) < 20:
            continue
        if len(cards) > best_cards:
            best = (start, start + end_rel, obj)
            best_cards = len(cards)

    if best is None:
        raise SystemExit("Geen embedded kaartdata-object gevonden in index.html")
    return best


def load_json_data() -> dict[str, Any]:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("pokemon_cards_data.json is geen JSON-object")
    if not isinstance(data.get("cards"), list) or not isinstance(data.get("sets"), list):
        raise SystemExit("pokemon_cards_data.json bevat geen bruikbare sets/cards")
    return data


def main() -> int:
    if not INDEX_PATH.exists():
        raise SystemExit("index.html niet gevonden")
    if not DATA_PATH.exists():
        raise SystemExit("pokemon_cards_data.json niet gevonden")

    index = INDEX_PATH.read_text(encoding="utf-8")
    data = load_json_data()
    start, end, old_data = find_embedded_data_region(index)

    new_data = dict(data)
    new_data["embeddedSyncedAt"] = datetime.now(timezone.utc).isoformat()
    replacement = json.dumps(new_data, ensure_ascii=False, separators=(",", ":"))
    updated = index[:start] + replacement + index[end:]

    if updated == index:
        changed = False
    else:
        INDEX_PATH.write_text(updated, encoding="utf-8")
        changed = True

    def has_pitch_black(obj: dict[str, Any]) -> bool:
        return any(isinstance(c, dict) and c.get("set") == "Pitch Black" and c.get("abbr") == "PBL" for c in obj.get("cards", []))

    debug = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "changedIndex": changed,
        "oldCards": len(old_data.get("cards", [])),
        "newCards": len(new_data.get("cards", [])),
        "oldSets": len(old_data.get("sets", [])),
        "newSets": len(new_data.get("sets", [])),
        "oldHadPitchBlack": has_pitch_black(old_data),
        "newHasPitchBlack": has_pitch_black(new_data),
        "embeddedStart": start,
        "embeddedEnd": end,
    }
    DEBUG_PATH.write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(debug, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
