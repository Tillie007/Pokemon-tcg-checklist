#!/usr/bin/env python3
"""
Voeg de Engelse Pokémon TCG set Pitch Black (PBL) toe aan pokemon_cards_data.json.
Bron voor namen/nummering: Limitless kaartpagina's PBL/1 t.e.m. PBL/120.
Deze stap raakt collectiegegevens, prices.json en Supabase niet aan.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "pokemon_cards_data.json"
DEBUG_PATH = ROOT / "pitch_black_debug.json"

SET_SERIES = "Mega Evolution"
SET_NAME = "Pitch Black"
SET_ABBR = "PBL"
SET_COUNT = 120
BASE_URL = "https://limitlesstcg.com/cards/PBL/{}"


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 pokemon-tcg-checklist-updater"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def parse_card(page: str, num: int) -> dict[str, Any]:
    # Voorbeeld title: Tropius - Pitch Black (PBL) #1 – Limitless
    name = ""
    m = re.search(r"<title>\s*(.*?)\s+-\s+Pitch Black\s*\(PBL\)\s*#\s*" + str(num) + r"\s*[–-]\s*Limitless", page, re.I | re.S)
    if m:
        name = clean_text(m.group(1))

    # Fallback op detailregel: <a ...>Tropius</a> - Grass - 110 HP
    if not name:
        m = re.search(r">([^<>]+)</a>\s*-\s*[^<>]+\s*-\s*\d+\s*HP", page, re.I | re.S)
        if m:
            name = clean_text(m.group(1))

    rarity = "Onbekend"
    m = re.search(r"Pitch Black\s*\(PBL\)\s*#\s*" + str(num) + r"\s*·\s*([^<\n]+)", page, re.I)
    if m:
        rarity = clean_text(m.group(1))

    if not name:
        name = f"Pitch Black #{num:03d}"

    num3 = f"{num:03d}"
    key = f"{SET_SERIES}|{SET_NAME}|{SET_ABBR}|{num3}|{name}"
    return {
        "key": key,
        "series": SET_SERIES,
        "set": SET_NAME,
        "abbr": SET_ABBR,
        "num": num3,
        "name": name,
        "rarity": rarity,
        "type": rarity,
    }


def load_data() -> dict[str, Any]:
    if not DATA_PATH.exists():
        raise SystemExit("pokemon_cards_data.json niet gevonden")
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("pokemon_cards_data.json moet een JSON-object zijn")
    data.setdefault("sets", [])
    data.setdefault("cards", [])
    if not isinstance(data["sets"], list) or not isinstance(data["cards"], list):
        raise SystemExit("pokemon_cards_data.json bevat geen bruikbare sets/cards-lijsten")
    return data


def upsert_set(data: dict[str, Any]) -> None:
    sets = data["sets"]
    existing = None
    for s in sets:
        if isinstance(s, dict) and s.get("series") == SET_SERIES and s.get("set") == SET_NAME:
            existing = s
            break
    if existing:
        existing["abbr"] = SET_ABBR
        existing["count"] = SET_COUNT
    else:
        sets.insert(0, {"series": SET_SERIES, "set": SET_NAME, "abbr": SET_ABBR, "count": SET_COUNT})


def remove_existing_pitch_black(data: dict[str, Any]) -> int:
    old_len = len(data["cards"])
    data["cards"] = [
        c for c in data["cards"]
        if not (isinstance(c, dict) and c.get("series") == SET_SERIES and c.get("set") == SET_NAME)
    ]
    return old_len - len(data["cards"])


def main() -> int:
    data = load_data()
    upsert_set(data)
    removed = remove_existing_pitch_black(data)

    cards: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for num in range(1, SET_COUNT + 1):
        url = BASE_URL.format(num)
        try:
            page = fetch_text(url)
            cards.append(parse_card(page, num))
        except Exception as exc:
            failures.append({"num": num, "url": url, "error": str(exc)})
            # Voeg toch een placeholder toe zodat de checklist compleet blijft.
            num3 = f"{num:03d}"
            name = f"Pitch Black #{num3}"
            cards.append({
                "key": f"{SET_SERIES}|{SET_NAME}|{SET_ABBR}|{num3}|{name}",
                "series": SET_SERIES,
                "set": SET_NAME,
                "abbr": SET_ABBR,
                "num": num3,
                "name": name,
                "rarity": "Onbekend",
                "type": "Onbekend",
            })
        time.sleep(0.05)

    # Nieuwe set bovenaan in de kaartlijst, zodat hij snel zichtbaar is.
    data["cards"] = cards + data["cards"]
    data["updatedAt"] = datetime.now(timezone.utc).isoformat()

    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    debug = {
        "updatedAt": data["updatedAt"],
        "set": {"series": SET_SERIES, "set": SET_NAME, "abbr": SET_ABBR, "count": SET_COUNT},
        "addedCards": len(cards),
        "removedExistingCards": removed,
        "failures": failures[:20],
        "firstCards": cards[:5],
        "lastCards": cards[-5:],
    }
    DEBUG_PATH.write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(debug, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
