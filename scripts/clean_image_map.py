#!/usr/bin/env python3
"""
Maak de automatische afbeeldingsmap veiliger.
Voor reeksen waar Limitless soms Pokémon-kaartachterkanten teruggeeft, verwijderen we die kandidaten.
Liever geen afbeelding dan een foute kaartachterkant.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "pokemon_image_map.json"
DEBUG_PATH = ROOT / "pokemon_image_cleanup_debug.json"

# Chaos Rising gaf in de app meerdere kaartachterkanten via Limitless.
# Deze set laten we voorlopig alleen via officiële Pokémon TCG CDN-kandidaten lopen.
BLOCK_LIMITLESS_FOR = {
    ("Mega Evolution", "Chaos Rising", "CRI"),
}


def safe(value: Any) -> str:
    return str(value or "").strip()


def should_block_limitless(entry: dict[str, Any]) -> bool:
    key = (safe(entry.get("series")), safe(entry.get("set")), safe(entry.get("abbr")))
    return key in BLOCK_LIMITLESS_FOR


def main() -> int:
    if not MAP_PATH.exists():
        raise SystemExit("pokemon_image_map.json niet gevonden. Draai eerst update_images.py")

    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    images = data.get("images", {})
    if not isinstance(images, dict):
        raise SystemExit("pokemon_image_map.json bevat geen bruikbare images-map")

    cleaned_cards = 0
    removed_urls = 0
    emptied_cards = 0
    examples: list[dict[str, Any]] = []

    for key, entry in images.items():
        if not isinstance(entry, dict) or not should_block_limitless(entry):
            continue

        old_candidates = [str(u) for u in entry.get("candidates", []) if str(u).strip()]
        new_candidates = [u for u in old_candidates if "limitlesstcg" not in u.lower()]
        removed = len(old_candidates) - len(new_candidates)

        if removed:
            cleaned_cards += 1
            removed_urls += removed
            entry["candidates"] = new_candidates
            entry["bestUrl"] = new_candidates[0] if new_candidates else ""
            entry["imageNote"] = "Limitless-kandidaten verwijderd voor deze set omdat ze kaartachterkanten konden tonen."
            if not new_candidates:
                emptied_cards += 1
            if len(examples) < 10:
                examples.append({
                    "key": key,
                    "name": entry.get("name"),
                    "set": entry.get("set"),
                    "abbr": entry.get("abbr"),
                    "num": entry.get("num"),
                    "removedUrls": removed,
                    "remainingCandidates": len(new_candidates),
                })

    data["cleanup"] = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "rule": "Geen Limitless-kandidaten voor Chaos Rising / CRI",
        "cleanedCards": cleaned_cards,
        "removedUrls": removed_urls,
        "emptiedCards": emptied_cards,
    }

    MAP_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    debug = {**data["cleanup"], "examples": examples}
    DEBUG_PATH.write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(debug, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
