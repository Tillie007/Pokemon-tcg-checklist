#!/usr/bin/env python3
"""
Maak de automatische afbeeldingsmap veiliger.
Voor sets waar automatische bronnen kaartachterkanten tonen, verwijderen we alle automatische kandidaten.
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

# Chaos Rising gaf nog kaartachterkanten via automatische kandidaten.
# Tot we een 100% betrouwbare bron hebben, tonen we voor deze set geen automatische afbeelding.
BLOCK_ALL_AUTOMATIC_IMAGES_FOR = {
    ("Mega Evolution", "Chaos Rising", "CRI"),
}


def safe(value: Any) -> str:
    return str(value or "").strip()


def should_block_all(entry: dict[str, Any]) -> bool:
    key = (safe(entry.get("series")), safe(entry.get("set")), safe(entry.get("abbr")))
    return key in BLOCK_ALL_AUTOMATIC_IMAGES_FOR


def main() -> int:
    if not MAP_PATH.exists():
        raise SystemExit("pokemon_image_map.json niet gevonden. Draai eerst update_images.py")

    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    images = data.get("images", {})
    if not isinstance(images, dict):
        raise SystemExit("pokemon_image_map.json bevat geen bruikbare images-map")

    cleaned_cards = 0
    removed_urls = 0
    examples: list[dict[str, Any]] = []

    for key, entry in images.items():
        if not isinstance(entry, dict) or not should_block_all(entry):
            continue

        old_candidates = [str(u) for u in entry.get("candidates", []) if str(u).strip()]
        if not old_candidates and not entry.get("bestUrl"):
            continue

        cleaned_cards += 1
        removed_urls += len(old_candidates)
        entry["candidates"] = []
        entry["bestUrl"] = ""
        entry["imageNote"] = "Automatische afbeeldingen uitgeschakeld voor Chaos Rising omdat ze kaartachterkanten konden tonen. Gebruik tijdelijk een eigen afbeeldingslink als je een correcte link hebt."

        if len(examples) < 10:
            examples.append({
                "key": key,
                "name": entry.get("name"),
                "set": entry.get("set"),
                "abbr": entry.get("abbr"),
                "num": entry.get("num"),
                "removedUrls": len(old_candidates),
                "remainingCandidates": 0,
            })

    cleanup = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "rule": "Geen automatische afbeeldingskandidaten voor Chaos Rising / CRI",
        "cleanedCards": cleaned_cards,
        "removedUrls": removed_urls,
        "emptiedCards": cleaned_cards,
    }
    data["cleanup"] = cleanup

    MAP_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    debug = {**cleanup, "examples": examples}
    DEBUG_PATH.write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(debug, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
