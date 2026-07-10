#!/usr/bin/env python3
"""
Maak automatisch pokemon_image_map.json met kandidaat-afbeeldingen per kaart.
Deze versie zet de officiële Pokémon TCG image-CDN eerst waar mogelijk.
Limitless blijft fallback, omdat die soms een kaartachterkant/placeholder teruggeeft.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "pokemon_cards_data.json"
OUT_PATH = ROOT / "pokemon_image_map.json"
DEBUG_PATH = ROOT / "pokemon_image_debug.json"

# Primaire bron: https://images.pokemontcg.io/{set_id}/{number}_hires.png
# Eerst exact op serie|set|afkorting, daarna fallback op serie|set.
POKEMON_TCG_IMAGE_SET_IDS = {
    "Base|Base|BS": "base1", "Base|Jungle|JU": "base2", "Base|Fossil|FO": "base3", "Base|Base Set 2|B2": "base4", "Base|Team Rocket|TR": "base5", "Other|Legendary Collection|LC": "base6", "Base|Wizards Black Star Promos|PR": "basep",
    "Gym|Gym Heroes|G1": "gym1", "Gym|Gym Challenge|G2": "gym2", "Neo|Neo Genesis|N1": "neo1", "Neo|Neo Discovery|N2": "neo2", "Neo|Neo Revelation|N3": "neo3", "Neo|Neo Destiny|N4": "neo4", "Other|Southern Islands|—": "si1",
    "E-Card|Expedition Base Set|EX": "ecard1", "E-Card|Aquapolis|AQ": "ecard2", "E-Card|Skyridge|SK": "ecard3",
    "EX|Ruby & Sapphire|RS": "ex1", "EX|Sandstorm|SS": "ex2", "EX|Dragon|DR": "ex3", "EX|Team Magma vs Team Aqua|MA": "ex4", "EX|Hidden Legends|HL": "ex5", "EX|FireRed & LeafGreen|RG": "ex6", "EX|Team Rocket Returns|TRR": "ex7", "EX|Deoxys|DX": "ex8", "EX|Emerald|EM": "ex9", "EX|Unseen Forces|UF": "ex10", "EX|Delta Species|DS": "ex11", "EX|Legend Maker|LM": "ex12", "EX|Holon Phantoms|HP": "ex13", "EX|Crystal Guardians|CG": "ex14", "EX|Dragon Frontiers|DF": "ex15", "EX|Power Keepers|PK": "ex16", "NP|Nintendo Black Star Promos|PR-NP": "np",
    "POP|POP Series 1|—": "pop1", "POP|POP Series 2|—": "pop2", "POP|POP Series 3|—": "pop3", "POP|POP Series 4|—": "pop4", "POP|POP Series 5|—": "pop5", "POP|POP Series 6|—": "pop6", "POP|POP Series 7|—": "pop7", "POP|POP Series 8|—": "pop8", "POP|POP Series 9|—": "pop9",
    "Diamond & Pearl|Diamond & Pearl|DP": "dp1", "Diamond & Pearl|Mysterious Treasures|MT": "dp2", "Diamond & Pearl|Secret Wonders|SW": "dp3", "Diamond & Pearl|Great Encounters|GE": "dp4", "Diamond & Pearl|Majestic Dawn|MD": "dp5", "Diamond & Pearl|Legends Awakened|LA": "dp6", "Diamond & Pearl|Stormfront|SF": "dp7", "Diamond & Pearl|DP Black Star Promos|PR-DPP": "dpp",
    "Platinum|Platinum|PL": "pl1", "Platinum|Rising Rivals|RR": "pl2", "Platinum|Supreme Victors|SV": "pl3", "Platinum|Arceus|AR": "pl4",
    "HeartGold & SoulSilver|HeartGold & SoulSilver|HS": "hgss1", "HeartGold & SoulSilver|HS—Unleashed|UL": "hgss2", "HeartGold & SoulSilver|HS—Undaunted|UD": "hgss3", "HeartGold & SoulSilver|HS—Triumphant|TM": "hgss4", "HeartGold & SoulSilver|Call of Legends|CL": "col1", "HeartGold & SoulSilver|HGSS Black Star Promos|PR-HS": "hsp",
    "Black & White|Black & White|BLW": "bw1", "Black & White|Emerging Powers|EPO": "bw2", "Black & White|Noble Victories|NVI": "bw3", "Black & White|Next Destinies|NXD": "bw4", "Black & White|Dark Explorers|DEX": "bw5", "Black & White|Dragons Exalted|DRX": "bw6", "Black & White|Dragon Vault|DRV": "dv1", "Black & White|Boundaries Crossed|BCR": "bw7", "Black & White|Plasma Storm|PLS": "bw8", "Black & White|Plasma Freeze|PLF": "bw9", "Black & White|Plasma Blast|PLB": "bw10", "Black & White|Legendary Treasures|LTR": "bw11", "Black & White|BW Black Star Promos|PR-BLW": "bwp",
    "XY|Kalos Starter Set|KSS": "xy0", "XY|XY|XY": "xy1", "XY|Flashfire|FLF": "xy2", "XY|Furious Fists|FFI": "xy3", "XY|Phantom Forces|PHF": "xy4", "XY|Primal Clash|PRC": "xy5", "XY|Double Crisis|DCR": "dc1", "XY|Roaring Skies|ROS": "xy6", "XY|Ancient Origins|AOR": "xy7", "XY|BREAKthrough|BKT": "xy8", "XY|BREAKpoint|BKP": "xy9", "XY|Generations|GEN": "g1", "XY|Fates Collide|FCO": "xy10", "XY|Steam Siege|STS": "xy11", "XY|Evolutions|EVO": "xy12", "XY|XY Black Star Promos|PR-XY": "xyp",
    "Sun & Moon|Sun & Moon|SUM": "sm1", "Sun & Moon|Guardians Rising|GRI": "sm2", "Sun & Moon|Burning Shadows|BUS": "sm3", "Sun & Moon|Shining Legends|SLG": "sm35", "Sun & Moon|Crimson Invasion|CIN": "sm4", "Sun & Moon|Ultra Prism|UPR": "sm5", "Sun & Moon|Forbidden Light|FLI": "sm6", "Sun & Moon|Celestial Storm|CES": "sm7", "Sun & Moon|Dragon Majesty|DRM": "sm75", "Sun & Moon|Lost Thunder|LOT": "sm8", "Sun & Moon|Team Up|TEU": "sm9", "Sun & Moon|Detective Pikachu|DET": "det1", "Sun & Moon|Unbroken Bonds|UNB": "sm10", "Sun & Moon|Unified Minds|UNM": "sm11", "Sun & Moon|Hidden Fates|HIF": "sm115", "Sun & Moon|Hidden Fates Shiny Vault|HIF": "sma", "Sun & Moon|Cosmic Eclipse|CEC": "sm12", "Sun & Moon|SM Black Star Promos|PR-SM": "smp",
    "Sword & Shield|Sword & Shield|SSH": "swsh1", "Sword & Shield|Rebel Clash|RCL": "swsh2", "Sword & Shield|Darkness Ablaze|DAA": "swsh3", "Sword & Shield|Champion's Path|CPA": "swsh35", "Sword & Shield|Vivid Voltage|VIV": "swsh4", "Sword & Shield|Shining Fates|SHF": "swsh45", "Sword & Shield|Shining Fates Shiny Vault|SHF": "swsh45sv", "Sword & Shield|Battle Styles|BST": "swsh5", "Sword & Shield|Chilling Reign|CRE": "swsh6", "Sword & Shield|Evolving Skies|EVS": "swsh7", "Sword & Shield|Celebrations|CEL": "cel25", "Sword & Shield|Celebrations: Classic Collection|CEL": "cel25c", "Sword & Shield|Fusion Strike|FST": "swsh8", "Sword & Shield|Brilliant Stars|BRS": "swsh9", "Sword & Shield|Brilliant Stars Trainer Gallery|BRS": "swsh9tg", "Sword & Shield|Astral Radiance|ASR": "swsh10", "Sword & Shield|Astral Radiance Trainer Gallery|ASR": "swsh10tg", "Sword & Shield|Pokémon GO|PGO": "pgo", "Sword & Shield|Lost Origin|LOR": "swsh11", "Sword & Shield|Lost Origin Trainer Gallery|LOR": "swsh11tg", "Sword & Shield|Silver Tempest|SIT": "swsh12", "Sword & Shield|Silver Tempest Trainer Gallery|SIT": "swsh12tg", "Sword & Shield|Crown Zenith|CRZ": "swsh12pt5", "Sword & Shield|Crown Zenith Galarian Gallery|CRZ": "swsh12pt5gg", "Sword & Shield|SWSH Black Star Promos|PR-SW": "swshp",
    "Scarlet & Violet|Scarlet & Violet|SVI": "sv1", "Scarlet & Violet|Scarlet & Violet Energies|SVE": "sve", "Scarlet & Violet|Scarlet & Violet Black Star Promos|PR-SV": "svp", "Scarlet & Violet|Paldea Evolved|PAL": "sv2", "Scarlet & Violet|Obsidian Flames|OBF": "sv3", "Scarlet & Violet|151|MEW": "sv3pt5", "Scarlet & Violet|Paradox Rift|PAR": "sv4", "Scarlet & Violet|Paldean Fates|PAF": "sv4pt5", "Scarlet & Violet|Temporal Forces|TEF": "sv5", "Scarlet & Violet|Twilight Masquerade|TWM": "sv6", "Scarlet & Violet|Shrouded Fable|SFA": "sv6pt5", "Scarlet & Violet|Stellar Crown|SCR": "sv7", "Scarlet & Violet|Surging Sparks|SSP": "sv8", "Scarlet & Violet|Prismatic Evolutions|PRE": "sv8pt5", "Scarlet & Violet|Journey Together|JTG": "sv9", "Scarlet & Violet|Destined Rivals|DRI": "sv10",
    "Mega Evolution|Mega Evolution|MEG": "me1", "Mega Evolution|Ascended Heroes|ASC": "me2pt5", "Mega Evolution|Perfect Order|POR": "me3", "Mega Evolution|Chaos Rising|CRI": "me4",
}


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        value = str(value or "").strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def safe_code(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def norm_num(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.isdigit():
        return str(int(raw))
    if raw.startswith("0") and raw.lstrip("0").isdigit():
        return str(int(raw))
    return raw


def num_candidates(value: Any) -> list[str]:
    raw = str(value or "").strip()
    out = [raw]
    n = norm_num(raw)
    if n:
        out.extend([n, n.zfill(2), n.zfill(3)])
    return unique(out)


def card_key(card: dict[str, Any]) -> str:
    return str(card.get("key") or "|".join(str(card.get(k, "")) for k in ("series", "set", "abbr", "num", "name")))


def tcg_set_id(card: dict[str, Any]) -> str:
    exact = f"{card.get('series','')}|{card.get('set','')}|{card.get('abbr','')}"
    by_set = f"{card.get('series','')}|{card.get('set','')}|—"
    if exact in POKEMON_TCG_IMAGE_SET_IDS:
        return POKEMON_TCG_IMAGE_SET_IDS[exact]
    if by_set in POKEMON_TCG_IMAGE_SET_IDS:
        return POKEMON_TCG_IMAGE_SET_IDS[by_set]
    # Laatste fallback: zelfde serie en set, ongeacht afkorting.
    prefix = f"{card.get('series','')}|{card.get('set','')}|"
    matches = [v for k, v in POKEMON_TCG_IMAGE_SET_IDS.items() if k.startswith(prefix)]
    return matches[0] if matches else ""


def image_candidates(card: dict[str, Any]) -> list[str]:
    abbr = safe_code(card.get("abbr"))
    nums = num_candidates(card.get("num"))
    urls: list[str] = []

    # 1) Eerst officiële Pokémon TCG image CDN. Die geeft veel minder placeholders/kaartachterkanten.
    set_id = tcg_set_id(card)
    if set_id:
        for n in nums:
            urls.append(f"https://images.pokemontcg.io/{set_id}/{n}_hires.png")
            urls.append(f"https://images.pokemontcg.io/{set_id}/{n}.png")

    # 2) Daarna Limitless als fallback. Eerst normale kaart, reverse pas daarna.
    if abbr and abbr not in {"", "—"}:
        for n in nums:
            urls.append(f"https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/tpci/{abbr}/{abbr}_{n}_EN_LG.png")
            urls.append(f"https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/tpci/{abbr}/{abbr}_{n}_R_EN_LG.png")

    return unique(urls)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="ignored; kept for GitHub workflow symmetry")
    parser.parse_args()

    if not DATA_PATH.exists():
        raise SystemExit(f"{DATA_PATH.name} niet gevonden")

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    cards = data.get("cards", data if isinstance(data, list) else [])
    if not isinstance(cards, list):
        raise SystemExit("pokemon_cards_data.json heeft geen bruikbare cards-lijst")

    mapping: dict[str, Any] = {}
    total_candidates = 0
    by_source = {"pokemontcg": 0, "limitless": 0}
    first_source = {"pokemontcg": 0, "limitless": 0}

    for card in cards:
        if not isinstance(card, dict):
            continue
        cands = image_candidates(card)
        if not cands:
            continue
        key = card_key(card)
        total_candidates += len(cands)
        by_source["pokemontcg"] += sum("images.pokemontcg.io" in u for u in cands)
        by_source["limitless"] += sum("limitlesstcg" in u for u in cands)
        if cands[0].startswith("https://images.pokemontcg.io"):
            first_source["pokemontcg"] += 1
        elif "limitlesstcg" in cands[0]:
            first_source["limitless"] += 1
        mapping[key] = {
            "name": card.get("name"),
            "series": card.get("series"),
            "set": card.get("set"),
            "abbr": card.get("abbr"),
            "num": card.get("num"),
            "bestUrl": cands[0],
            "candidates": cands[:10],
            "limitlessPage": f"https://limitlesstcg.com/cards/{abbr}/{norm_num(card.get('num'))}" if (abbr := safe_code(card.get("abbr"))) and norm_num(card.get("num")) else "",
        }

    out = {
        "source": "Automatische kandidaten: eerst Pokémon TCG image CDN, daarna Limitless fallback",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "totalCards": len(cards),
        "cardsWithImageCandidates": len(mapping),
        "totalCandidateUrls": total_candidates,
        "format": "image-map-candidates-v2",
        "images": mapping,
    }
    debug = {
        "updatedAt": out["updatedAt"],
        "totalCards": len(cards),
        "cardsWithImageCandidates": len(mapping),
        "bySourceCandidateUrls": by_source,
        "firstCandidateSource": first_source,
        "note": "V2 zet Pokémon TCG image CDN eerst om Limitless-placeholders/kaartachterkanten te vermijden. POP sets zijn toegevoegd.",
    }

    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    DEBUG_PATH.write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(debug, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
