#!/usr/bin/env python3
"""Voeg de Engelse Pokemon TCG-set 30th Celebration toe aan de app.

De release bestaat uit drie logische checklists:
* 158 genummerde kaarten plus drie ongenummerde RGB Mew-kaarten;
* 30 Classic Collection-herdrukken met het nummer dat op de kaart staat;
* acht 30th Celebration Energy-kaarten (Cardmarket MEE 009 t/m 016).

De 158 genummerde kaartnamen komen van de publieke TCGdex-set-API. De twee
speciale deelverzamelingen staan bewust vast in dit script, zodat een latere
API-wijziging geen kaartnummers of collectie-sleutels kan veranderen.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "pokemon_cards_data.json"
DEBUG_PATH = ROOT / "thirtieth_celebration_debug.json"

SERIES = "Mega Evolution"
MAIN_SET = "30th Celebration"
CLASSIC_SET = "30th Celebration: Classic Collection"
ENERGY_SET = "30th Celebration: Energy Collection"
MAIN_ABBR = "30C"
ENERGY_ABBR = "MEE"
TCGDEX_SET_URL = "https://api.tcgdex.net/v2/en/sets/30th"
# Handmatige refresh-trigger voor kaartdata, afbeeldingen, prijzen en PWA-cache: 2026-09-23.

RGB_CARDS = [
    ("R/RGB", "Mew"),
    ("G/RGB", "Mew"),
    ("B/RGB", "Mew"),
]

# De kaarten behouden op de herdruk hun oorspronkelijke verzamelnummer.
CLASSIC_CARDS = [
    ("058", "Pikachu"),
    ("004", "Charizard"),
    ("018", "Misty"),
    ("069", "Erika's Jigglypuff"),
    ("025", "Sneasel"),
    ("106", "Shining Celebi"),
    ("149", "Lugia"),
    ("005", "Delcatty"),
    ("019", "Dark Tyranitar"),
    ("108", "Scizor ex"),
    ("011", "Metagross δ"),
    ("106", "Palkia LV.X"),
    ("043", "Uxie"),
    ("047", "Crobat G"),
    ("094", "Gengar"),
    ("099", "Darkrai & Cresselia LEGEND"),
    ("100", "Darkrai & Cresselia LEGEND"),
    ("101", "N"),
    ("085", "Rayquaza EX"),
    ("011", "Genesect EX"),
    ("106", "M Gardevoir EX"),
    ("041", "Greninja BREAK"),
    ("089", "Solgaleo GX"),
    ("057", "Buzzwole GX"),
    ("033", "Pikachu & Zekrom GX"),
    ("138", "Zacian V"),
    ("050", "Raikou"),
    ("114", "Mew VMAX"),
    ("123", "Arceus VSTAR"),
    ("203", "Magikarp"),
]

# Cardmarket catalogiseert de acht nieuwe jubileumillustraties als V2,
# aansluitend op de bestaande MEE 001-008.
ENERGY_CARDS = [
    ("009", "Basic Grass Energy"),
    ("010", "Basic Fire Energy"),
    ("011", "Basic Water Energy"),
    ("012", "Basic Lightning Energy"),
    ("013", "Basic Psychic Energy"),
    ("014", "Basic Fighting Energy"),
    ("015", "Basic Darkness Energy"),
    ("016", "Basic Metal Energy"),
]

RARE_NUMBERS = {12, 14, 19, 20, 56, 62, 63, 65, 76, 80, 82, 86, 100, 103, 105, 106, 107, 121}
DOUBLE_RARE_NUMBERS = {15, 21, 53, 54, 64, 66, 70, 71, 90, 92, 102, 109}


def numbered_rarity(number: int) -> str:
    if 23 <= number <= 52:
        return "Pikachu Rare"
    if number in DOUBLE_RARE_NUMBERS:
        return "Double rare"
    if number in RARE_NUMBERS:
        return "Rare"
    if 129 <= number <= 146:
        return "Illustration rare"
    if 147 <= number <= 156:
        return "Special illustration rare"
    if 157 <= number <= 158:
        return "Futuristic Rare"
    return "Common"


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 pokemon-tcg-checklist-updater"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("TCGdex antwoord is geen JSON-object")
    return payload


def load_data() -> dict[str, Any]:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("pokemon_cards_data.json moet een JSON-object zijn")
    payload.setdefault("sets", [])
    payload.setdefault("cards", [])
    if not isinstance(payload["sets"], list) or not isinstance(payload["cards"], list):
        raise SystemExit("pokemon_cards_data.json bevat geen bruikbare sets/cards-lijsten")
    return payload


def make_card(set_name: str, abbr: str, num: str, name: str, rarity: str) -> dict[str, str]:
    return {
        "key": f"{SERIES}|{set_name}|{abbr}|{num}|{name}",
        "series": SERIES,
        "set": set_name,
        "abbr": abbr,
        "num": num,
        "name": name,
        "rarity": rarity,
        "type": rarity,
    }


def numbered_cards() -> list[dict[str, str]]:
    payload = fetch_json(TCGDEX_SET_URL)
    if payload.get("id") != "30th" or payload.get("name") != MAIN_SET:
        raise SystemExit("Onverwachte TCGdex-set ontvangen")
    raw_cards = payload.get("cards")
    if not isinstance(raw_cards, list):
        raise SystemExit("TCGdex bevat geen kaartenlijst")

    cards: list[dict[str, str]] = []
    for raw in raw_cards:
        if not isinstance(raw, dict):
            continue
        num = str(raw.get("localId") or "").strip().zfill(3)
        name = str(raw.get("name") or "").strip()
        if not num.isdigit() or not name:
            raise SystemExit(f"Ongeldige TCGdex-kaart: {raw!r}")
        cards.append(make_card(MAIN_SET, MAIN_ABBR, num, name, numbered_rarity(int(num))))

    expected = [f"{number:03d}" for number in range(1, 159)]
    actual = [card["num"] for card in cards]
    if actual != expected:
        raise SystemExit(f"Verwacht kaartnummers 001-158, ontvangen {actual[:3]} ... {actual[-3:]}")
    return cards


def upsert_sets(data: dict[str, Any]) -> int:
    target_names = {MAIN_SET, CLASSIC_SET, ENERGY_SET}
    before = len(data["sets"])
    data["sets"] = [
        item for item in data["sets"]
        if not (isinstance(item, dict) and item.get("series") == SERIES and item.get("set") in target_names)
    ]
    removed = before - len(data["sets"])
    new_sets = [
        {"series": SERIES, "set": MAIN_SET, "abbr": MAIN_ABBR, "count": 161},
        {"series": SERIES, "set": CLASSIC_SET, "abbr": MAIN_ABBR, "count": 30},
        {"series": SERIES, "set": ENERGY_SET, "abbr": ENERGY_ABBR, "count": 8},
    ]
    data["sets"] = new_sets + data["sets"]
    return removed


def remove_existing_cards(data: dict[str, Any]) -> int:
    target_names = {MAIN_SET, CLASSIC_SET, ENERGY_SET}
    before = len(data["cards"])
    data["cards"] = [
        card for card in data["cards"]
        if not (isinstance(card, dict) and card.get("series") == SERIES and card.get("set") in target_names)
    ]
    return before - len(data["cards"])


def main() -> int:
    data = load_data()
    main_cards = numbered_cards()
    main_cards.extend(
        make_card(MAIN_SET, MAIN_ABBR, num, name, "RGB Rare")
        for num, name in RGB_CARDS
    )
    classic_cards = [
        make_card(CLASSIC_SET, MAIN_ABBR, num, name, "Classic Collection")
        for num, name in CLASSIC_CARDS
    ]
    energy_cards = [
        make_card(ENERGY_SET, ENERGY_ABBR, num, name, "Energy")
        for num, name in ENERGY_CARDS
    ]

    removed_sets = upsert_sets(data)
    removed_cards = remove_existing_cards(data)
    added_cards = main_cards + classic_cards + energy_cards
    data["cards"] = added_cards + data["cards"]
    data["updatedAt"] = datetime.now(timezone.utc).isoformat()

    keys = [card.get("key") for card in data["cards"] if isinstance(card, dict)]
    if len(keys) != len(set(keys)):
        raise SystemExit("Dubbele kaart-sleutel gevonden; bestand niet opgeslagen")

    DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    debug = {
        "updatedAt": data["updatedAt"],
        "source": TCGDEX_SET_URL,
        "sets": data["sets"][:3],
        "addedCards": len(added_cards),
        "breakdown": {"mainAndRgb": len(main_cards), "classic": len(classic_cards), "energy": len(energy_cards)},
        "removedExistingSets": removed_sets,
        "removedExistingCards": removed_cards,
        "firstCards": added_cards[:5],
        "lastCards": added_cards[-5:],
    }
    DEBUG_PATH.write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(debug, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
