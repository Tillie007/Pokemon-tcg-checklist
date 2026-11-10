#!/usr/bin/env python3
"""Voeg/update de Engelse Pokémon TCG-set Delta Reign (DLR / ME06).

Bron: TCGdex set-endpoint. De updater schrijft:
- 141 kaarten (103 hoofdset + 38 secret rares) naar pokemon_cards_data.json;
- TCGdex-afbeeldingskandidaten rechtstreeks naar pokemon_image_map.json;
- debuginformatie naar delta_reign_debug.json.

Collectiegegevens en Supabase worden niet aangeraakt.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "pokemon_cards_data.json"
IMAGE_PATH = ROOT / "pokemon_image_map.json"
DEBUG_PATH = ROOT / "delta_reign_debug.json"

SERIES = "Mega Evolution"
SET_NAME = "Delta Reign"
SET_ABBR = "DLR"
SET_COUNT = 141
MAIN_COUNT = 103
TCGDEX_SET_URL = "https://api.tcgdex.net/v2/en/sets/me06"


def fetch_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 pokemon-tcg-checklist-updater"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise SystemExit("TCGdex antwoord is geen JSON-object")
    return payload


def load_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return fallback
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else fallback


def infer_secret_rarity(number: int, raw: str) -> str:
    if raw:
        return raw
    if 104 <= number <= 117:
        return "Illustration Rare"
    if 118 <= number <= 134:
        return "Ultra Rare"
    if 135 <= number <= 140:
        return "Special Illustration Rare"
    if number == 141:
        return "Mega Hyper Rare"
    return "Unknown"


def image_candidates(image_base: str) -> list[str]:
    base = str(image_base or "").strip().rstrip("/")
    if not base:
        return []
    # TCGdex kaartlijsten geven doorgaans de assetbasis zonder /high.webp.
    if base.endswith((".webp", ".png", ".jpg", ".jpeg")):
        return [base]
    return [
        base + "/high.webp",
        base + "/high.png",
        base + "/low.webp",
    ]


def main() -> int:
    source = fetch_json(TCGDEX_SET_URL)
    source_name = str(source.get("name") or "").strip()
    source_id = str(source.get("id") or "").strip()
    if source_name != SET_NAME:
        raise SystemExit(f"Onverwachte TCGdex-set: {source_name!r} ({source_id!r})")

    raw_cards = source.get("cards")
    if not isinstance(raw_cards, list):
        raise SystemExit("TCGdex bevat geen kaartenlijst")

    cards: list[dict[str, Any]] = []
    images: dict[str, dict[str, Any]] = {}
    seen_numbers: set[int] = set()

    for raw in raw_cards:
        if not isinstance(raw, dict):
            continue
        local = str(raw.get("localId") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not local or not name:
            continue
        try:
            number = int(local)
        except ValueError:
            raise SystemExit(f"Ongeldig Delta Reign kaartnummer: {local!r}")

        num = f"{number:03d}"
        rarity = infer_secret_rarity(number, str(raw.get("rarity") or "").strip())
        key = f"{SERIES}|{SET_NAME}|{SET_ABBR}|{num}|{name}"
        card = {
            "key": key,
            "series": SERIES,
            "set": SET_NAME,
            "abbr": SET_ABBR,
            "num": num,
            "name": name,
            "rarity": rarity,
            "type": rarity,
        }
        cards.append(card)
        seen_numbers.add(number)

        candidates = image_candidates(str(raw.get("image") or ""))
        if candidates:
            images[key] = {
                "bestUrl": candidates[0],
                "candidates": candidates,
                "source": "TCGdex",
            }

    cards.sort(key=lambda card: int(card["num"]))
    expected = set(range(1, SET_COUNT + 1))
    if len(cards) != SET_COUNT or seen_numbers != expected:
        missing = sorted(expected - seen_numbers)
        extra = sorted(seen_numbers - expected)
        raise SystemExit(
            f"Delta Reign onvolledig: {len(cards)}/{SET_COUNT}; "
            f"ontbrekend={missing[:12]}, extra={extra[:12]}"
        )

    data = load_json(DATA_PATH, {"sets": [], "cards": []})
    data.setdefault("sets", [])
    data.setdefault("cards", [])

    data["sets"] = [
        row for row in data["sets"]
        if not (
            isinstance(row, dict)
            and row.get("series") == SERIES
            and row.get("set") == SET_NAME
        )
    ]
    data["sets"].insert(
        0,
        {
            "series": SERIES,
            "set": SET_NAME,
            "abbr": SET_ABBR,
            "count": SET_COUNT,
            "mainCount": MAIN_COUNT,
            "releaseDate": "2026-11-06",
        },
    )

    removed = sum(
        1 for row in data["cards"]
        if isinstance(row, dict)
        and row.get("series") == SERIES
        and row.get("set") == SET_NAME
    )
    data["cards"] = [
        row for row in data["cards"]
        if not (
            isinstance(row, dict)
            and row.get("series") == SERIES
            and row.get("set") == SET_NAME
        )
    ]
    data["cards"] = cards + data["cards"]
    data["updatedAt"] = datetime.now(timezone.utc).isoformat()

    all_keys = [str(row.get("key")) for row in data["cards"] if isinstance(row, dict)]
    if len(all_keys) != len(set(all_keys)):
        raise SystemExit("Dubbele kaart-sleutel gevonden; update afgebroken")

    DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    image_payload = load_json(IMAGE_PATH, {"images": {}})
    image_payload.setdefault("images", {})
    # Verwijder eventuele oudere/onvolledige Delta Reign image entries.
    prefix = f"{SERIES}|{SET_NAME}|{SET_ABBR}|"
    image_payload["images"] = {
        key: value for key, value in image_payload["images"].items()
        if not str(key).startswith(prefix)
    }
    image_payload["images"].update(images)
    image_payload["updatedAt"] = data["updatedAt"]
    IMAGE_PATH.write_text(
        json.dumps(image_payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    debug = {
        "updatedAt": data["updatedAt"],
        "source": TCGDEX_SET_URL,
        "sourceId": source_id,
        "set": {
            "series": SERIES,
            "set": SET_NAME,
            "abbr": SET_ABBR,
            "count": SET_COUNT,
            "mainCount": MAIN_COUNT,
        },
        "addedCards": len(cards),
        "removedExistingCards": removed,
        "cardsWithTcgDexImage": len(images),
        "firstCards": cards[:5],
        "lastCards": cards[-5:],
    }
    DEBUG_PATH.write_text(
        json.dumps(debug, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(debug, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
