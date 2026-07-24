#!/usr/bin/env python3
"""
Maak de automatische afbeeldingsmap veiliger én bruikbaarder.

Eerdere aanpak: Chaos Rising volledig leegmaken omdat sommige automatische
kandidaten kaartachterkanten toonden. Dat was veilig, maar daardoor bleef de
controlelijst veel kaarten zonder afbeelding tonen.

Nieuwe aanpak: voor nieuwe Mega Evolution-sets gebruiken we gericht de
Limitless-beeldlink die de kaartpagina zelf gebruikt:
  https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/tpci/CRI/CRI_005_R_EN_LG.png

We gebruiken dus alleen de _R_EN_LG-variant met driecijferig kaartnummer.
De oudere/niet-R kandidaten worden verwijderd omdat die in de app soms als
Pokémon-kaartachterkant zichtbaar werden.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "pokemon_image_map.json"
DEBUG_PATH = ROOT / "pokemon_image_cleanup_debug.json"

# Voor deze sets is Limitless betrouwbaar wanneer we uitsluitend de _R_EN_LG-link gebruiken.
LIMITLESS_R_ONLY_FOR = {
    ("Mega Evolution", "Chaos Rising", "CRI"),
    ("Mega Evolution", "Pitch Black", "PBL"),
}


def safe(value: Any) -> str:
    return str(value or "").strip()


def norm_num(value: Any) -> str:
    raw = safe(value)
    if "/" in raw:
        raw = raw.split("/", 1)[0]
    raw = re.sub(r"\s+", "", raw)
    if raw.isdigit():
        return str(int(raw))
    m = re.match(r"^0*(\d+)([A-Za-z]?)$", raw)
    if m:
        return str(int(m.group(1))) + m.group(2).upper()
    return raw.upper()


def num_variants(value: Any) -> list[str]:
    n = norm_num(value)
    out: list[str] = []
    if n:
        out.append(n)
        # Voor gewone numerieke nummers gebruikt Limitless meestal 001, 005, 087, ...
        if n.isdigit():
            out.insert(0, n.zfill(3))
            out.append(n.zfill(2))
    seen: set[str] = set()
    result: list[str] = []
    for item in out:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def set_tuple(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (safe(entry.get("series")), safe(entry.get("set")), safe(entry.get("abbr")))


def safe_limitless_urls(entry: dict[str, Any]) -> list[str]:
    _series, _set_name, abbr = set_tuple(entry)
    if not abbr:
        return []
    abbr_clean = "".join(ch for ch in abbr.upper() if ch.isalnum())
    if not abbr_clean:
        return []
    urls: list[str] = []
    for n in num_variants(entry.get("num")):
        urls.append(
            f"https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/tpci/"
            f"{abbr_clean}/{abbr_clean}_{n}_R_EN_LG.png"
        )
    return urls


def main() -> int:
    if not MAP_PATH.exists():
        raise SystemExit("pokemon_image_map.json niet gevonden. Draai eerst update_images.py")

    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    images = data.get("images", {})
    if not isinstance(images, dict):
        raise SystemExit("pokemon_image_map.json bevat geen bruikbare images-map")

    improved_cards = 0
    removed_urls = 0
    examples: list[dict[str, Any]] = []

    for key, entry in images.items():
        if not isinstance(entry, dict):
            continue
        if set_tuple(entry) not in LIMITLESS_R_ONLY_FOR:
            continue

        old_candidates = [str(u) for u in entry.get("candidates", []) if str(u).strip()]
        new_candidates = safe_limitless_urls(entry)
        if not new_candidates:
            continue

        entry["candidates"] = new_candidates[:10]
        entry["bestUrl"] = new_candidates[0]
        entry["imageSource"] = "Limitless veilige R-image"
        entry["imageNote"] = (
            "Voor deze nieuwe Mega Evolution-set worden alleen veilige Limitless "
            "_R_EN_LG-afbeeldingen gebruikt. Oude automatische kandidaten werden "
            "verwijderd omdat die soms kaartachterkanten toonden."
        )

        improved_cards += 1
        removed_urls += max(0, len(old_candidates) - len(new_candidates))
        if len(examples) < 12:
            examples.append({
                "key": key,
                "name": entry.get("name"),
                "set": entry.get("set"),
                "abbr": entry.get("abbr"),
                "num": entry.get("num"),
                "oldCandidates": len(old_candidates),
                "newBestUrl": entry.get("bestUrl"),
            })

    cleanup = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "rule": "Chaos Rising en Pitch Black gebruiken uitsluitend veilige Limitless _R_EN_LG-afbeeldingen",
        "improvedCards": improved_cards,
        "removedUnsafeUrlsApprox": removed_urls,
        "sets": ["Mega Evolution | Chaos Rising | CRI", "Mega Evolution | Pitch Black | PBL"],
    }
    data["cleanup"] = cleanup

    MAP_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    debug = {**cleanup, "examples": examples}
    DEBUG_PATH.write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(debug, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
