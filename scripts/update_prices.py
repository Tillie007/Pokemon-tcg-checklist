#!/usr/bin/env python3
"""
Dagelijkse Cardmarket prijsupdate voor de Pokémon TCG Checklist PWA.

Versie: 2026-07-02 FIX

Waarom deze versie?
- De publieke Cardmarket productlijst bevat vaak wel idProduct + idExpansion + naam,
  maar niet altijd kaartnummer/setcode als apart veld.
- De vorige versie eiste kaartnummer + setcode en koppelde daardoor 0 kaarten.
- Deze versie probeert eerst exact te koppelen op setcode + kaartnummer + naam.
- Als dat niet kan, zoekt ze automatisch welke Cardmarket idExpansion overeenkomt
  met jouw app-set op basis van kaartnamen, en koppelt daarna alleen veilige,
  unieke kaartnamen. Dubbele namen binnen een set worden bewust niet gekoppeld.

Geen Cardmarket API-sleutels nodig. Alleen publieke downloadbestanden.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import math
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
CARDS_FILE = ROOT_DIR / "pokemon_cards_data.json"
OUT_PRICES = ROOT_DIR / "prices.json"
OUT_HISTORY = ROOT_DIR / "price_history.json"
OUT_REPORT = ROOT_DIR / "cardmarket_match_report.csv"
OUT_SETCODES = ROOT_DIR / "cardmarket_setcodes.csv"
CACHE_DIR = ROOT_DIR / ".cache" / "cardmarket"

# Game id 6 = Pokémon in de publieke Cardmarket-downloadlinks.
PRODUCTS_URL = "https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json"
PRICE_GUIDE_URL = "https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json"

# De publieke bestanden kunnen oude API-veldbenamingen of nieuwe JSON-velden gebruiken.
PRICE_FIELDS = [
    "Trend Price", "trendPrice", "trend", "TREND",
    "Avg. Sell Price", "avg", "average", "AVG",
    "AVG30", "avg30", "average30", "avg30Days",
    "Low Price", "lowPrice", "low", "LOW", "fromPrice", "min", "minPrice",
]
LOW_FIELDS = ["Low Price", "lowPrice", "low", "LOW", "fromPrice", "min", "minPrice"]
TREND_FIELDS = ["Trend Price", "trendPrice", "trend", "TREND"]
AVG30_FIELDS = ["AVG30", "avg30", "average30", "avg30Days", "avg30day"]
FOIL_LOW_FIELDS = ["Foil Low", "low-foil", "lowFoil", "LOWFOIL"]
FOIL_TREND_FIELDS = ["Foil Trend", "trend-foil", "trendFoil", "TRENDFOIL"]
FOIL_AVG30_FIELDS = ["Foil AVG30", "avg30-foil", "avg30Foil"]

HISTORY_DAYS_TO_KEEP = 180


def log(msg: str) -> None:
    print(msg, flush=True)


def norm_key(s: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def coerce_text(value: Any) -> str:
    """Maak van Cardmarket-waarden veilig tekst, ook bij lokalisatie-dicts/lijsten."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        # Vaak: {"1": "English name", "2": "French name", ...}
        preferred = [
            "enName", "english", "English", "en", "EN", "1",
            "name", "Name", "productName", "ProductName", "localName",
        ]
        for key in preferred:
            if key in value and value[key] not in (None, ""):
                return coerce_text(value[key])
        for v in value.values():
            txt = coerce_text(v)
            if txt:
                return txt
        return ""
    if isinstance(value, list):
        # Vaak: [{idLanguage:1, productName:"..."}, ...]
        for item in value:
            if isinstance(item, dict):
                lang = str(item.get("idLanguage", item.get("language", ""))).lower()
                if lang in {"1", "en", "english"}:
                    txt = coerce_text(item.get("productName") or item.get("name") or item.get("enName"))
                    if txt:
                        return txt
        for item in value:
            txt = coerce_text(item)
            if txt:
                return txt
        return ""
    return str(value).strip()


def flatten(obj: Any, prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not isinstance(obj, dict):
        return out
    for k, v in obj.items():
        full = f"{prefix}.{k}" if prefix else str(k)
        out[norm_key(full)] = v
        out[norm_key(k)] = v
        if isinstance(v, dict):
            out.update(flatten(v, full))
    return out


def get_any(row: Dict[str, Any], names: Iterable[str]) -> Any:
    flat = flatten(row)
    for name in names:
        key = norm_key(name)
        if key in flat and flat[key] not in (None, ""):
            return flat[key]
    return ""


def get_text(row: Dict[str, Any], names: Iterable[str]) -> str:
    return coerce_text(get_any(row, names))


def download_json(url: str, cache_name: str, max_age_hours: float = 20.0, force: bool = False) -> Any:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / cache_name
    if cache_path.exists() and not force:
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours <= max_age_hours:
            log(f"Gebruik cache: {cache_path.name} ({age_hours:.1f} uur oud)")
            return json.loads(cache_path.read_text(encoding="utf-8"))

    log(f"Download: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "PokemonTCGChecklistGitHub/1.1"})
    with urllib.request.urlopen(req, timeout=180) as response:
        raw = response.read()
        enc = response.headers.get("Content-Encoding", "").lower()
        if enc == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        text = raw.decode("utf-8-sig")
        cache_path.write_text(text, encoding="utf-8")
        return json.loads(text)


def load_cards() -> Dict[str, Any]:
    if not CARDS_FILE.exists():
        raise FileNotFoundError(f"Niet gevonden: {CARDS_FILE}")
    return json.loads(CARDS_FILE.read_text(encoding="utf-8"))


def as_records(obj: Any) -> List[Dict[str, Any]]:
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        for key in ["products", "product", "data", "items", "prices", "priceGuide", "priceguide"]:
            val = obj.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
        if obj and all(isinstance(v, dict) for v in obj.values()):
            return list(obj.values())
    return []


def norm_text(value: Any) -> str:
    s = coerce_text(value)
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.lower().replace("pokémon", "pokemon")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", norm_text(value))


def norm_num(value: Any) -> str:
    s = coerce_text(value).upper().strip()
    s = re.sub(r"\s+", "", s)
    if "/" in s:
        s = s.split("/", 1)[0]

    def repl(m: re.Match[str]) -> str:
        prefix, digits = m.group(1), m.group(2)
        return prefix + str(int(digits)) if digits else prefix

    s = re.sub(r"^([A-Z]*)(0*\d+)$", repl, s)
    return s


def parse_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = coerce_text(value).strip().replace("€", "").replace(" ", "")
    if not s or s.upper() == "N/A":
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def pick_price(row: Dict[str, Any], fields: Iterable[str]) -> str:
    for field in fields:
        parsed = parse_float(get_any(row, [field]))
        if parsed is not None:
            return f"{parsed:.2f}"
    return ""


def extract_code_number_from_text(text: str) -> Tuple[str, str, str]:
    raw = coerce_text(text)
    code = ""
    number = ""
    # Voorbeelden op Cardmarket: "Poké Pad (POR 081)", "Mega Greninja ex (CRI 116)"
    for inside in re.findall(r"\(([^()]*)\)", raw):
        m = re.search(r"\b([A-Za-z0-9]{1,8}(?:[-_][A-Za-z0-9]{1,8})?)\s*[- ]?\s*([A-Za-z]{0,4}\d+[A-Za-z]?|\d+[A-Za-z]?)\b", inside)
        if m:
            code, number = m.group(1), m.group(2)
    clean = re.sub(r"\s*\([A-Za-z0-9_-]{1,10}\s*[- ]?\s*[A-Za-z]{0,4}\d+[A-Za-z]?\)\s*$", "", raw).strip()
    return clean or raw, code.upper(), norm_num(number)


def product_url(product: Dict[str, Any], name: str, product_id: str = "") -> str:
    url = get_text(product, ["url", "website", "link", "productUrl", "permalink"])
    if url:
        if url.startswith("http"):
            return url
        if url.startswith("/"):
            return "https://www.cardmarket.com" + url
    if product_id:
        return f"https://www.cardmarket.com/en/Pokemon/Products?idProduct={urllib.parse.quote_plus(product_id)}"
    q = urllib.parse.quote_plus(name)
    return f"https://www.cardmarket.com/en/Pokemon/Products/Search?searchString={q}"


def product_record(row: Dict[str, Any]) -> Dict[str, str]:
    raw_name = get_text(row, ["enName", "name", "Name", "productName", "localName", "localization", "localizations"])
    clean_name, code_from_name, num_from_name = extract_code_number_from_text(raw_name)

    cm_code = get_text(row, [
        "expansion.abbreviation", "expansionAbbreviation", "expansion abbreviation",
        "abbreviation", "expansionCode", "expansion code", "setCode", "set code", "code",
    ]) or code_from_name

    cm_set = get_text(row, ["expansion.name", "expansion.enName", "expansionName", "Expansion", "expansion", "setName", "set", "category"])
    cm_num = get_text(row, ["number", "cardNumber", "collectorNumber", "localId", "nr"]) or num_from_name
    product_id = get_text(row, ["idProduct", "id_product", "productId", "id"])
    exp_id = get_text(row, ["idExpansion", "expansionId", "Expansion ID", "id expansion", "expansion.idExpansion"])
    category = get_text(row, ["category", "categoryName", "Category"])
    rarity = get_text(row, ["rarity", "rarityName", "cardRarity"])
    image = get_text(row, ["image", "imageUrl", "imageURL", "picture", "thumbnail"])

    return {
        "idProduct": product_id,
        "name": clean_name,
        "rawName": raw_name,
        "normName": norm_text(clean_name),
        "cmSetCode": str(cm_code or "").upper().strip(),
        "cmSetName": str(cm_set or "").strip(),
        "normSet": norm_text(cm_set),
        "number": norm_num(cm_num),
        "idExpansion": str(exp_id or "").strip(),
        "category": str(category or ""),
        "rarity": str(rarity or ""),
        "imageUrl": str(image or ""),
        "url": product_url(row, f"{clean_name} {cm_code} {cm_num}", product_id),
    }


def card_name_variants(name: str) -> List[str]:
    base = norm_text(name)
    variants = {base, base.replace(" pokemon ", " ")}
    return [v for v in variants if v]


def make_product_indexes(products: List[Dict[str, str]]) -> Dict[str, Dict[Tuple[str, str, str], List[Dict[str, str]]]]:
    indexes: Dict[str, Dict[Tuple[str, str, str], List[Dict[str, str]]]] = {
        "code_num_name": defaultdict(list),
        "exp_num_name": defaultdict(list),
        "exp_name": defaultdict(list),
        "set_num_name": defaultdict(list),
    }
    for p in products:
        if not p["normName"]:
            continue
        if p["cmSetCode"] and p["number"]:
            indexes["code_num_name"][(norm_compact(p["cmSetCode"]), p["number"], p["normName"])].append(p)
        if p["idExpansion"] and p["number"]:
            indexes["exp_num_name"][(p["idExpansion"], p["number"], p["normName"])].append(p)
        if p["idExpansion"]:
            indexes["exp_name"][(p["idExpansion"], "", p["normName"])].append(p)
        if p["normSet"] and p["number"]:
            indexes["set_num_name"][(p["normSet"], p["number"], p["normName"])].append(p)
    return indexes


def choose_unique(candidates: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    return candidates[0] if len(candidates) == 1 else None


def set_key_from_card(card: Dict[str, Any]) -> str:
    return f"{card.get('series','')}|{card.get('set','')}|{card.get('abbr','')}"


def set_key_from_set(row: Dict[str, Any]) -> str:
    return f"{row.get('series','')}|{row.get('set','')}|{row.get('abbr','')}"


def infer_expansion_map(cards: List[Dict[str, Any]], sets: List[Dict[str, Any]], products: List[Dict[str, str]]) -> Dict[str, Dict[str, Any]]:
    """Koppel app-sets aan Cardmarket idExpansion op basis van overlap in unieke kaartnamen."""
    app_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    for card in cards:
        nm = norm_text(card.get("name"))
        if nm:
            app_counts[set_key_from_card(card)][nm] += 1

    exp_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    exp_meta: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"setCodes": Counter(), "setNames": Counter(), "products": 0})
    for p in products:
        exp = p.get("idExpansion", "")
        nm = p.get("normName", "")
        if not exp or not nm:
            continue
        exp_counts[exp][nm] += 1
        exp_meta[exp]["products"] += 1
        if p.get("cmSetCode"):
            exp_meta[exp]["setCodes"][p["cmSetCode"]] += 1
        if p.get("cmSetName"):
            exp_meta[exp]["setNames"][p["cmSetName"]] += 1

    # Eerste pass: als Cardmarket-setcode uit namen komt, gebruik die meteen.
    by_code: Dict[str, List[str]] = defaultdict(list)
    for exp, meta in exp_meta.items():
        if meta["setCodes"]:
            code, cnt = meta["setCodes"].most_common(1)[0]
            if cnt >= 3:
                by_code[norm_compact(code)].append(exp)

    mapping: Dict[str, Dict[str, Any]] = {}
    used: set[str] = set()
    for s in sets:
        skey = set_key_from_set(s)
        abbr = norm_compact(s.get("abbr"))
        possible = by_code.get(abbr, [])
        if len(possible) == 1:
            exp = possible[0]
            meta = exp_meta[exp]
            mapping[skey] = {
                "idExpansion": exp,
                "method": "setcode",
                "score": 1.0,
                "overlap": "",
                "cmSetCode": meta["setCodes"].most_common(1)[0][0] if meta["setCodes"] else s.get("abbr", ""),
                "cmSetName": meta["setNames"].most_common(1)[0][0] if meta["setNames"] else "",
            }
            used.add(exp)

    # Tweede pass: naamoverlap. Dit is voorzichtig: alleen kiezen bij voldoende duidelijke score.
    for s in sets:
        skey = set_key_from_set(s)
        if skey in mapping:
            continue
        ac = app_counts.get(skey, Counter())
        if not ac:
            continue
        app_unique = set(ac)
        best: Optional[Tuple[float, int, str]] = None
        second_score = 0.0
        for exp, pc in exp_counts.items():
            prod_unique = set(pc)
            overlap = len(app_unique & prod_unique)
            if overlap < 3:
                continue
            score = overlap / math.sqrt(max(1, len(app_unique)) * max(1, len(prod_unique)))
            # Geef kleine bonus als aantallen dicht bij elkaar liggen.
            size_ratio = min(len(app_unique), len(prod_unique)) / max(len(app_unique), len(prod_unique))
            final_score = score * (0.85 + 0.15 * size_ratio)
            if best is None or final_score > best[0]:
                if best is not None:
                    second_score = best[0]
                best = (final_score, overlap, exp)
            else:
                second_score = max(second_score, final_score)

        if best:
            score, overlap, exp = best
            # Vereist duidelijke marge zodat een verkeerde set niet snel gekozen wordt.
            min_overlap = max(8, int(len(app_unique) * 0.18))
            if overlap >= min_overlap and score >= 0.28 and score >= second_score + 0.05:
                meta = exp_meta[exp]
                mapping[skey] = {
                    "idExpansion": exp,
                    "method": "name-overlap",
                    "score": round(score, 4),
                    "overlap": overlap,
                    "cmSetCode": meta["setCodes"].most_common(1)[0][0] if meta["setCodes"] else s.get("abbr", ""),
                    "cmSetName": meta["setNames"].most_common(1)[0][0] if meta["setNames"] else "",
                }
                used.add(exp)

    return mapping


def build_price_map(price_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for row in price_rows:
        product_id = get_text(row, ["idProduct", "id_product", "productId", "id"])
        if product_id:
            by_id[product_id] = row
    return by_id


def find_product(
    card: Dict[str, Any],
    indexes: Dict[str, Dict[Tuple[str, str, str], List[Dict[str, str]]]],
    set_map: Dict[str, Dict[str, Any]],
    app_set_name_counts: Dict[str, Counter[str]],
) -> Tuple[Optional[Dict[str, str]], str, int]:
    num = norm_num(card.get("num"))
    abbr = norm_compact(card.get("abbr"))
    set_name = norm_text(card.get("set"))
    skey = set_key_from_card(card)
    names = card_name_variants(str(card.get("name", "")))

    for nm in names:
        cands = indexes["code_num_name"].get((abbr, num, nm), [])
        prod = choose_unique(cands)
        if prod:
            return prod, "code+number+name", len(cands)

    mapped = set_map.get(skey, {})
    exp = str(mapped.get("idExpansion", ""))
    if exp:
        for nm in names:
            cands = indexes["exp_num_name"].get((exp, num, nm), [])
            prod = choose_unique(cands)
            if prod:
                return prod, "mapped-expansion+number+name", len(cands)

        # Veilige fallback: alleen als naam uniek is in de app-set én in Cardmarket-expansion.
        # Zo vermijden we foute prijzen bij kaarten als Charizard ex met meerdere arts/nummers.
        for nm in names:
            if app_set_name_counts.get(skey, Counter()).get(nm, 0) != 1:
                continue
            cands = indexes["exp_name"].get((exp, "", nm), [])
            prod = choose_unique(cands)
            if prod:
                return prod, "mapped-expansion+unique-name", len(cands)
            if cands:
                return None, "ambiguous-name-in-expansion", len(cands)

    for nm in names:
        cands = indexes["set_num_name"].get((set_name, num, nm), [])
        prod = choose_unique(cands)
        if prod:
            return prod, "set+number+name", len(cands)

    return None, "unmatched", 0


def load_history() -> Dict[str, List[Dict[str, str]]]:
    if not OUT_HISTORY.exists():
        return {}
    try:
        payload = json.loads(OUT_HISTORY.read_text(encoding="utf-8"))
        hist = payload.get("history", payload) if isinstance(payload, dict) else {}
        return hist if isinstance(hist, dict) else {}
    except Exception:
        return {}


def update_history(existing: Dict[str, List[Dict[str, str]]], prices: List[Dict[str, Any]], today: str) -> Dict[str, List[Dict[str, str]]]:
    cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=HISTORY_DAYS_TO_KEEP)).isoformat()
    for p in prices:
        key = p.get("key")
        if not key:
            continue
        row = {
            "date": today,
            "price": str(p.get("price", "")),
            "trendPrice": str(p.get("trendPrice", "")),
            "avg30": str(p.get("avg30", "")),
            "lowPrice": str(p.get("lowPrice", "")),
            "foilTrendPrice": str(p.get("foilTrendPrice", "")),
            "currency": str(p.get("currency", "EUR")),
        }
        rows = [r for r in existing.get(key, []) if isinstance(r, dict) and str(r.get("date", "")) >= cutoff and str(r.get("date", "")) != today]
        rows.append(row)
        rows.sort(key=lambda r: str(r.get("date", "")), reverse=True)
        existing[key] = rows

    for key in list(existing.keys()):
        rows = [r for r in existing[key] if isinstance(r, dict) and str(r.get("date", "")) >= cutoff]
        if rows:
            existing[key] = rows
        else:
            del existing[key]
    return existing


def build(force: bool = False) -> None:
    cards_data = load_cards()
    cards: List[Dict[str, Any]] = cards_data.get("cards", [])
    sets: List[Dict[str, Any]] = cards_data.get("sets", [])
    log(f"Kaarten in app-data: {len(cards):,}".replace(",", "."))

    products_obj = download_json(PRODUCTS_URL, "products_singles_6.json", force=force)
    prices_obj = download_json(PRICE_GUIDE_URL, "price_guide_6.json", force=force)
    product_rows = as_records(products_obj)
    price_rows = as_records(prices_obj)
    log(f"Cardmarket productregels: {len(product_rows):,}".replace(",", "."))
    log(f"Cardmarket prijsregels: {len(price_rows):,}".replace(",", "."))

    products = [product_record(r) for r in product_rows]
    products = [p for p in products if p["idProduct"] and p["normName"]]
    log(f"Bruikbare Cardmarket producten: {len(products):,}".replace(",", "."))

    with_number = sum(1 for p in products if p.get("number"))
    with_code = sum(1 for p in products if p.get("cmSetCode"))
    with_exp = sum(1 for p in products if p.get("idExpansion"))
    log(f"Producten met kaartnummer: {with_number:,}".replace(",", "."))
    log(f"Producten met setcode: {with_code:,}".replace(",", "."))
    log(f"Producten met idExpansion: {with_exp:,}".replace(",", "."))

    indexes = make_product_indexes(products)
    price_map = build_price_map(price_rows)
    log(f"Prijzen gekoppeld op idProduct: {len(price_map):,}".replace(",", "."))

    app_set_name_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    for card in cards:
        for nm in card_name_variants(card.get("name", "")):
            app_set_name_counts[set_key_from_card(card)][nm] += 1

    set_map = infer_expansion_map(cards, sets, products)
    log(f"Automatisch herkende Cardmarket expansions: {len(set_map)}/{len(sets)}")

    now_dt = dt.datetime.now(dt.timezone.utc)
    now = now_dt.isoformat()
    today = now_dt.date().isoformat()

    output: List[Dict[str, Any]] = []
    report_rows: List[List[str]] = [[
        "status", "matchType", "candidateCount", "appKey", "serie", "set", "abbr", "kaartnr", "kaartnaam",
        "cmProductId", "cmExpansionId", "cmSetCode", "cmSetName", "cmNumber", "cmName", "price", "foilTrendPrice", "url"
    ]]

    matched = 0
    priced = 0
    match_type_counts: Counter[str] = Counter()

    for card in cards:
        prod, match_type, cand_count = find_product(card, indexes, set_map, app_set_name_counts)
        match_type_counts[match_type] += 1
        if not prod:
            report_rows.append([
                "niet gekoppeld", match_type, str(cand_count), card.get("key", ""), card.get("series", ""),
                card.get("set", ""), card.get("abbr", ""), card.get("num", ""), card.get("name", ""),
                "", "", "", "", "", "", "", "", ""
            ])
            continue

        matched += 1
        price_row = price_map.get(prod["idProduct"], {})
        low = pick_price(price_row, LOW_FIELDS)
        trend = pick_price(price_row, TREND_FIELDS)
        avg30 = pick_price(price_row, AVG30_FIELDS)
        foil_low = pick_price(price_row, FOIL_LOW_FIELDS)
        foil_trend = pick_price(price_row, FOIL_TREND_FIELDS)
        foil_avg30 = pick_price(price_row, FOIL_AVG30_FIELDS)
        price = pick_price(price_row, PRICE_FIELDS) or trend or avg30 or low

        if price or low or trend or avg30 or foil_low or foil_trend or foil_avg30:
            priced += 1

        item = {
            "key": card["key"],
            "series": card.get("series", ""),
            "set": card.get("set", ""),
            "abbr": card.get("abbr", ""),
            "cmSetCode": prod.get("cmSetCode", "") or card.get("abbr", ""),
            "cmSetName": prod.get("cmSetName", ""),
            "cmExpansionId": prod.get("idExpansion", ""),
            "cmProductId": prod["idProduct"],
            "num": card.get("num", ""),
            "name": card.get("name", ""),
            "price": price,
            "lowPrice": low,
            "trendPrice": trend,
            "avg30": avg30,
            "foilLowPrice": foil_low,
            "foilTrendPrice": foil_trend,
            "foilAvg30": foil_avg30,
            "currency": "EUR",
            "url": prod["url"],
            "imageUrl": prod.get("imageUrl", ""),
            "rarity": prod.get("rarity", ""),
            "source": "Cardmarket publieke bestanden",
            "updatedAt": now,
            "matchType": match_type,
        }
        output.append(item)
        report_rows.append([
            "gekoppeld", match_type, str(cand_count), card.get("key", ""), card.get("series", ""),
            card.get("set", ""), card.get("abbr", ""), card.get("num", ""), card.get("name", ""),
            prod["idProduct"], prod.get("idExpansion", ""), prod.get("cmSetCode", ""), prod.get("cmSetName", ""),
            prod.get("number", ""), prod.get("name", ""), item["price"], item["foilTrendPrice"], prod["url"]
        ])

    payload = {
        "source": "Cardmarket publieke bestanden",
        "updatedAt": now,
        "totalCards": len(cards),
        "matchedCards": matched,
        "pricedCards": priced,
        "matchTypes": dict(match_type_counts),
        "note": "Dubbele kaartnamen zonder betrouwbaar kaartnummer worden bewust niet gekoppeld om foute prijzen te vermijden.",
        "prices": output,
    }
    OUT_PRICES.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    history = update_history(load_history(), output, today)
    history_payload = {"source": "Cardmarket publieke bestanden", "updatedAt": now, "history": history}
    OUT_HISTORY.write_text(json.dumps(history_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with OUT_REPORT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerows(report_rows)

    set_rows = [["serie", "set", "appAfkorting", "cardmarketExpansionId", "cardmarketSetcode", "cardmarketSetnaam", "methode", "score", "overlap", "gekoppeldeKaarten"]]
    output_by_set: Counter[str] = Counter()
    for item in output:
        output_by_set[f"{item.get('series','')}|{item.get('set','')}|{item.get('abbr','')}"] += 1

    for s in sets:
        skey = set_key_from_set(s)
        m = set_map.get(skey, {})
        set_rows.append([
            s.get("series", ""), s.get("set", ""), s.get("abbr", ""),
            m.get("idExpansion", ""), m.get("cmSetCode", ""), m.get("cmSetName", ""),
            m.get("method", ""), str(m.get("score", "")), str(m.get("overlap", "")),
            str(output_by_set.get(skey, 0)),
        ])
    with OUT_SETCODES.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerows(set_rows)

    log("Match-types:")
    for k, v in match_type_counts.most_common():
        log(f"  {k}: {v}")
    log(f"Klaar: {matched:,}/{len(cards):,} kaarten gekoppeld, {priced:,} met prijs.".replace(",", "."))
    log(f"Bestanden gemaakt: {OUT_PRICES.name}, {OUT_HISTORY.name}, {OUT_REPORT.name}, {OUT_SETCODES.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cardmarket publieke prijsbestanden koppelen aan de Pokémon TCG checklist.")
    parser.add_argument("--force", action="store_true", help="Forceer nieuwe download, ook als cache nog recent is.")
    args = parser.parse_args()
    build(force=args.force)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FOUT: {exc}", file=sys.stderr)
        raise
