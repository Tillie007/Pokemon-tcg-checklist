#!/usr/bin/env python3
"""
Dagelijkse Cardmarket prijsupdate voor de Pokémon TCG Checklist PWA.

Dit script gebruikt alleen publieke Cardmarket-downloadbestanden:
- Pokémon Singles productcatalogus
- Pokémon price guide

Geen API-sleutels nodig.
Het script schrijft de output in de root van de GitHub-repository:
- prices.json
- price_history.json
- cardmarket_match_report.csv
- cardmarket_setcodes.csv
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
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

PRICE_FIELDS = [
    "trendPrice", "trend", "avg30", "average30", "avg30Days", "avg7", "avg1",
    "avg", "average", "price", "lowPrice", "low", "min", "fromPrice",
]
LOW_FIELDS = ["lowPrice", "low", "min", "fromPrice", "minPrice"]
TREND_FIELDS = ["trendPrice", "trend"]
AVG30_FIELDS = ["avg30", "average30", "avg30Days", "avg30day"]
HISTORY_DAYS_TO_KEEP = 180


def log(msg: str) -> None:
    print(msg, flush=True)


def download_json(url: str, cache_name: str, max_age_hours: float = 20.0, force: bool = False) -> Any:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / cache_name
    if cache_path.exists() and not force:
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours <= max_age_hours:
            log(f"Gebruik cache: {cache_path.name} ({age_hours:.1f} uur oud)")
            return json.loads(cache_path.read_text(encoding="utf-8"))

    log(f"Download: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "PokemonTCGChecklistGitHub/1.0"})
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


def norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def flatten(obj: Any, prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not isinstance(obj, dict):
        return out
    for k, v in obj.items():
        nk = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
        out[norm_key(nk)] = v
        out[norm_key(k)] = v
        if isinstance(v, dict):
            out.update(flatten(v, nk))
    return out


def get_any(row: Dict[str, Any], names: Iterable[str]) -> Any:
    flat = flatten(row)
    for name in names:
        key = norm_key(name)
        if key in flat and flat[key] not in (None, ""):
            return flat[key]
    return ""


def norm_text(value: Any) -> str:
    s = str(value or "")
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.lower().replace("pokémon", "pokemon")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", norm_text(value))


def norm_num(value: Any) -> str:
    s = str(value or "").upper().strip()
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
    s = str(value).strip().replace("€", "").replace(" ", "")
    if not s:
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
        val = get_any(row, [field])
        parsed = parse_float(val)
        if parsed is not None:
            return f"{parsed:.2f}"
    return ""


def extract_code_number_from_text(text: str) -> Tuple[str, str, str]:
    raw = str(text or "")
    code = ""
    number = ""
    for inside in re.findall(r"\(([^()]*)\)", raw):
        m = re.search(r"\b([A-Za-z0-9]{1,8}(?:[-_][A-Za-z0-9]{1,8})?)\s*[- ]?\s*([A-Za-z]{0,4}\d+[A-Za-z]?|\d+[A-Za-z]?)\b", inside)
        if m:
            code, number = m.group(1), m.group(2)
    clean = re.sub(r"\s*\([^()]*\)\s*$", "", raw).strip()
    return clean or raw, code.upper(), norm_num(number)


def product_url(product: Dict[str, Any], name: str, product_id: str = "") -> str:
    url = get_any(product, ["url", "website", "link", "productUrl", "permalink"])
    if url:
        url = str(url)
        if url.startswith("http"):
            return url
        if url.startswith("/"):
            return "https://www.cardmarket.com" + url
    if product_id:
        return f"https://www.cardmarket.com/en/Pokemon/Products?idProduct={urllib.parse.quote_plus(product_id)}"
    q = urllib.parse.quote_plus(name)
    return f"https://www.cardmarket.com/en/Pokemon/Products/Search?searchString={q}"


def product_record(row: Dict[str, Any]) -> Dict[str, str]:
    raw_name = str(get_any(row, ["name", "Name", "productName", "enName", "localName"]))
    clean_name, code_from_name, num_from_name = extract_code_number_from_text(raw_name)
    cm_code = get_any(row, [
        "expansion.abbreviation", "expansionAbbreviation", "expansion abbreviation", "abbreviation",
        "expansionCode", "expansion code", "setCode", "set code", "code",
    ]) or code_from_name
    cm_set = get_any(row, ["expansion.name", "expansionName", "Expansion", "expansion", "setName", "set", "category"])
    cm_num = get_any(row, ["number", "cardNumber", "collectorNumber", "localId", "nr"]) or num_from_name
    product_id = str(get_any(row, ["idProduct", "id_product", "productId", "id"]) or "")
    exp_id = get_any(row, ["idExpansion", "expansionId", "Expansion ID", "id expansion"])
    category = get_any(row, ["category", "categoryName", "Category"])
    rarity = get_any(row, ["rarity", "rarityName", "cardRarity"])
    image = get_any(row, ["image", "imageUrl", "imageURL", "picture", "thumbnail"])
    return {
        "idProduct": product_id,
        "name": clean_name,
        "rawName": raw_name,
        "normName": norm_text(clean_name),
        "cmSetCode": str(cm_code or "").upper().strip(),
        "cmSetName": str(cm_set or "").strip(),
        "normSet": norm_text(cm_set),
        "number": norm_num(cm_num),
        "idExpansion": str(exp_id or ""),
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
        "code_num_name": {},
        "set_num_name": {},
        "num_name": {},
    }
    for p in products:
        if not p["number"] or not p["normName"]:
            continue
        for key, tup in [
            ("code_num_name", (norm_compact(p["cmSetCode"]), p["number"], p["normName"])),
            ("set_num_name", (p["normSet"], p["number"], p["normName"])),
            ("num_name", ("", p["number"], p["normName"])),
        ]:
            if all(tup):
                indexes[key].setdefault(tup, []).append(p)
    return indexes


def choose_unique(candidates: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    if len(candidates) == 1:
        return candidates[0]
    return None


def find_product(card: Dict[str, Any], indexes: Dict[str, Dict[Tuple[str, str, str], List[Dict[str, str]]]], products: List[Dict[str, str]]) -> Tuple[Optional[Dict[str, str]], str, int]:
    num = norm_num(card.get("num"))
    abbr = norm_compact(card.get("abbr"))
    set_name = norm_text(card.get("set"))
    names = card_name_variants(str(card.get("name", "")))

    for nm in names:
        cands = indexes["code_num_name"].get((abbr, num, nm), [])
        prod = choose_unique(cands)
        if prod:
            return prod, "code+number+name", len(cands)
        cands = indexes["set_num_name"].get((set_name, num, nm), [])
        prod = choose_unique(cands)
        if prod:
            return prod, "set+number+name", len(cands)
        cands = indexes["num_name"].get(("", num, nm), [])
        prod = choose_unique(cands)
        if prod:
            return prod, "number+name", len(cands)

    relaxed = []
    for p in products:
        if p["number"] != num:
            continue
        if abbr and norm_compact(p["cmSetCode"]) != abbr:
            continue
        pn = p["normName"]
        cn = names[0] if names else ""
        if cn and (pn in cn or cn in pn):
            relaxed.append(p)
    prod = choose_unique(relaxed)
    if prod:
        return prod, "relaxed-code+number+name", len(relaxed)
    return None, "unmatched", 0


def build_price_map(price_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for row in price_rows:
        product_id = str(get_any(row, ["idProduct", "id_product", "productId", "id"]) or "")
        if product_id:
            by_id[product_id] = row
    return by_id


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
    price_by_key = {p["key"]: p for p in prices if p.get("key")}
    for key, p in price_by_key.items():
        row = {
            "date": today,
            "price": str(p.get("price", "")),
            "trendPrice": str(p.get("trendPrice", "")),
            "avg30": str(p.get("avg30", "")),
            "lowPrice": str(p.get("lowPrice", "")),
            "currency": str(p.get("currency", "EUR")),
        }
        rows = [r for r in existing.get(key, []) if isinstance(r, dict) and str(r.get("date", "")) >= cutoff and str(r.get("date", "")) != today]
        rows.append(row)
        rows.sort(key=lambda r: str(r.get("date", "")), reverse=True)
        existing[key] = rows
    # Oude keys zonder recente prijzen opschonen.
    for key in list(existing.keys()):
        rows = [r for r in existing[key] if isinstance(r, dict) and str(r.get("date", "")) >= cutoff]
        if rows:
            existing[key] = rows
        else:
            del existing[key]
    return existing


def build(force: bool = False) -> None:
    cards_data = load_cards()
    cards = cards_data.get("cards", [])
    sets = cards_data.get("sets", [])
    log(f"Kaarten in app-data: {len(cards):,}".replace(",", "."))

    products_obj = download_json(PRODUCTS_URL, "products_singles_6.json", force=force)
    prices_obj = download_json(PRICE_GUIDE_URL, "price_guide_6.json", force=force)
    product_rows = as_records(products_obj)
    price_rows = as_records(prices_obj)
    log(f"Cardmarket producten: {len(product_rows):,}".replace(",", "."))
    log(f"Cardmarket prijsregels: {len(price_rows):,}".replace(",", "."))

    products = [product_record(r) for r in product_rows]
    products = [p for p in products if p["idProduct"] and p["normName"]]
    indexes = make_product_indexes(products)
    price_map = build_price_map(price_rows)
    now_dt = dt.datetime.now(dt.timezone.utc)
    now = now_dt.isoformat()
    today = now_dt.date().isoformat()

    output: List[Dict[str, Any]] = []
    report_rows: List[List[str]] = [[
        "status", "matchType", "appKey", "serie", "set", "abbr", "kaartnr", "kaartnaam",
        "cmProductId", "cmSetCode", "cmSetName", "cmNumber", "cmName", "price", "url"
    ]]

    matched = 0
    priced = 0
    for card in cards:
        prod, match_type, _cand_count = find_product(card, indexes, products)
        if not prod:
            report_rows.append(["niet gekoppeld", match_type, card.get("key", ""), card.get("series", ""), card.get("set", ""), card.get("abbr", ""), card.get("num", ""), card.get("name", ""), "", "", "", "", "", "", ""])
            continue
        matched += 1
        price_row = price_map.get(prod["idProduct"], {})
        price = pick_price(price_row, PRICE_FIELDS)
        low = pick_price(price_row, LOW_FIELDS)
        trend = pick_price(price_row, TREND_FIELDS)
        avg30 = pick_price(price_row, AVG30_FIELDS)
        if price or low or trend or avg30:
            priced += 1
        item = {
            "key": card["key"],
            "series": card.get("series", ""),
            "set": card.get("set", ""),
            "abbr": card.get("abbr", ""),
            "cmSetCode": prod["cmSetCode"],
            "cmSetName": prod["cmSetName"],
            "cmProductId": prod["idProduct"],
            "num": card.get("num", ""),
            "name": card.get("name", ""),
            "price": price or trend or avg30 or low,
            "lowPrice": low,
            "trendPrice": trend,
            "avg30": avg30,
            "currency": "EUR",
            "url": prod["url"],
            "imageUrl": prod.get("imageUrl", ""),
            "rarity": prod.get("rarity", ""),
            "source": "Cardmarket publieke bestanden",
            "updatedAt": now,
            "matchType": match_type,
        }
        output.append(item)
        report_rows.append(["gekoppeld", match_type, card.get("key", ""), card.get("series", ""), card.get("set", ""), card.get("abbr", ""), card.get("num", ""), card.get("name", ""), prod["idProduct"], prod["cmSetCode"], prod["cmSetName"], prod["number"], prod["name"], item["price"], prod["url"]])

    payload = {
        "source": "Cardmarket publieke bestanden",
        "updatedAt": now,
        "totalCards": len(cards),
        "matchedCards": matched,
        "pricedCards": priced,
        "prices": output,
    }
    OUT_PRICES.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    history = update_history(load_history(), output, today)
    history_payload = {"source": "Cardmarket publieke bestanden", "updatedAt": now, "history": history}
    OUT_HISTORY.write_text(json.dumps(history_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with OUT_REPORT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerows(report_rows)

    set_rows = [["serie", "set", "appAfkorting", "cardmarketSetcode", "cardmarketSetnaam", "gekoppeldeKaarten"]]
    for s in sets:
        related = [item for item in output if item["series"] == s.get("series") and item["set"] == s.get("set") and item["abbr"] == s.get("abbr")]
        counts: Dict[Tuple[str, str], int] = {}
        for item in related:
            key = (item.get("cmSetCode", ""), item.get("cmSetName", ""))
            counts[key] = counts.get(key, 0) + 1
        if counts:
            (code, name), cnt = max(counts.items(), key=lambda kv: kv[1])
        else:
            code, name, cnt = "", "", 0
        set_rows.append([s.get("series", ""), s.get("set", ""), s.get("abbr", ""), code, name, str(cnt)])
    with OUT_SETCODES.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerows(set_rows)

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
