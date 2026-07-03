#!/usr/bin/env python3
"""
Dagelijkse Cardmarket prijsupdate voor de Pokémon TCG Checklist PWA.

Versie: 2026-07-03 FIX 7 — meer matches door Level/Lv-prefix toe te laten

Waarom deze versie?
- De publieke Cardmarket productlijst bevat vaak wel idProduct + idExpansion + naam,
  maar niet altijd kaartnummer/setcode als apart veld.
- De vorige versie eiste kaartnummer + setcode en koppelde daardoor 0 kaarten.
- Deze versie probeert eerst exact te koppelen op setcode + kaartnummer + naam.
- Als dat niet kan, zoekt ze automatisch welke Cardmarket idExpansion overeenkomt
  met jouw app-set op basis van kaartnamen, en koppelt daarna alleen veilige,
  unieke kaartnamen. Dubbele namen binnen een set worden bewust niet gekoppeld.
- Deze versie leest ook prijsbestanden die als object per idProduct zijn opgebouwd.
- Cardmarket-namen worden opgeslagen als cmName/cmRawName zodat de app ermee kan zoeken.
- Extra: app-sets worden nu ook gekoppeld via Cardmarket-setnaam/category + veilige aliasnamen.
- Nieuw: Cardmarket-namen met Lv./Level na de kaartnaam worden nu veilig toegelaten wanneer de kaartnaam uniek is binnen de set.

Geen Cardmarket API-sleutels nodig. Alleen publieke downloadbestanden.
"""
from __future__ import annotations

import argparse
import csv
import io
import datetime as dt
import gzip
import difflib
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
OUT_DEBUG = ROOT_DIR / "cardmarket_debug.json"
OUT_UNMATCHED_BY_SET = ROOT_DIR / "cardmarket_unmatched_by_set.csv"
OUT_SET_CANDIDATES = ROOT_DIR / "cardmarket_set_mapping_candidates.csv"
MANUAL_SET_MAP = ROOT_DIR / "cardmarket_manual_set_map.csv"
CACHE_DIR = ROOT_DIR / ".cache" / "cardmarket"

# Game id 6 = Pokémon in de publieke Cardmarket-downloadlinks.
PRODUCTS_URL = "https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json"
PRICE_GUIDE_URL = "https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json"

# De publieke bestanden kunnen oude API-veldbenamingen of nieuwe JSON-velden gebruiken.
PRICE_FIELDS = [
    "Trend Price", "trendPrice", "trend", "TREND", "priceTrend", "trend_price",
    "Avg. Sell Price", "avgSellPrice", "avgSell", "averageSellPrice", "avg", "average", "AVG",
    "AVG7", "avg7", "average7", "avg7Days",
    "AVG30", "avg30", "average30", "avg30Days", "avg30day",
    "Low Price", "lowPrice", "low", "LOW", "fromPrice", "min", "minPrice",
]
LOW_FIELDS = ["Low Price", "lowPrice", "low", "LOW", "fromPrice", "min", "minPrice", "lowestPrice", "lowest"]
TREND_FIELDS = ["Trend Price", "trendPrice", "trend", "TREND", "priceTrend", "trend_price"]
AVG30_FIELDS = ["AVG30", "avg30", "average30", "avg30Days", "avg30day", "thirtyDayAverage"]
AVG7_FIELDS = ["AVG7", "avg7", "average7", "avg7Days", "sevenDayAverage"]
AVG1_FIELDS = ["AVG1", "avg1", "average1", "avg1Days", "oneDayAverage"]
FOIL_LOW_FIELDS = ["Foil Low", "low-foil", "lowFoil", "LOWFOIL", "foilLowPrice"]
FOIL_TREND_FIELDS = ["Foil Trend", "trend-foil", "trendFoil", "TRENDFOIL", "foilTrendPrice"]
FOIL_AVG30_FIELDS = ["Foil AVG30", "avg30-foil", "avg30Foil", "foilAvg30"]
FOIL_AVG7_FIELDS = ["Foil AVG7", "avg7-foil", "avg7Foil", "foilAvg7"]
FOIL_AVG1_FIELDS = ["Foil AVG1", "avg1-foil", "avg1Foil", "foilAvg1"]
FOIL_SELL_FIELDS = ["Foil Sell", "foilSell", "foilSellPrice", "avgFoilSell"]

HISTORY_DAYS_TO_KEEP = 180

PRICE_GUIDE_COLUMNS = [
    "idProduct", "Avg. Sell Price", "Low Price", "Trend Price", "German Pro Low",
    "Suggested Price", "Foil Sell", "Foil Low", "Foil Trend", "Low Price Ex+",
    "AVG1", "AVG7", "AVG30", "Foil AVG1", "Foil AVG7", "Foil AVG30",
]
PRODUCT_LIST_COLUMNS = ["idProduct", "Name", "Category ID", "Category", "Expansion ID", "Date Added"]



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


def decode_downloaded_bytes(raw: bytes) -> str:
    """Decodeer downloads: gzip indien nodig, daarna UTF-8."""
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8-sig", errors="replace")


def parse_json_or_csv_text(text: str) -> Any:
    """Publieke Cardmarket-bestanden kunnen JSON of CSV-achtig zijn.

    De website toont .json-links, maar de oude documentatie spreekt over CSV.
    Deze functie accepteert daarom beide vormen.
    """
    stripped = text.lstrip()
    if not stripped:
        return []
    if stripped[0] in "[{":
        return json.loads(stripped)

    # CSV fallback. Cardmarket gebruikt doorgaans komma's met quote-velden,
    # maar we detecteren ook puntkomma's.
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except Exception:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if reader.fieldnames:
        return [dict(r) for r in reader]
    return []


def download_data(url: str, cache_name: str, max_age_hours: float = 20.0, force: bool = False) -> Any:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / cache_name
    if cache_path.exists() and not force:
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours <= max_age_hours:
            log(f"Gebruik cache: {cache_path.name} ({age_hours:.1f} uur oud)")
            return parse_json_or_csv_text(cache_path.read_text(encoding="utf-8"))

    log(f"Download: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "PokemonTCGChecklistGitHub/1.2"})
    with urllib.request.urlopen(req, timeout=180) as response:
        raw = response.read()
        enc = response.headers.get("Content-Encoding", "").lower()
        if enc == "gzip":
            raw = gzip.decompress(raw)
        text = decode_downloaded_bytes(raw)
        cache_path.write_text(text, encoding="utf-8")
        return parse_json_or_csv_text(text)


# backwards compatible naam voor oudere code
下载_json_alias = download_data

def download_json(url: str, cache_name: str, max_age_hours: float = 20.0, force: bool = False) -> Any:
    return download_data(url, cache_name, max_age_hours=max_age_hours, force=force)


def load_cards() -> Dict[str, Any]:
    if not CARDS_FILE.exists():
        raise FileNotFoundError(f"Niet gevonden: {CARDS_FILE}")
    return json.loads(CARDS_FILE.read_text(encoding="utf-8"))


def rows_from_table_like(obj: Any, default_columns: List[str]) -> List[Dict[str, Any]]:
    """Zet zowel dict-lijsten als list-of-lists om naar records."""
    if isinstance(obj, list):
        if not obj:
            return []
        if all(isinstance(x, dict) for x in obj):
            return [x for x in obj if isinstance(x, dict)]
        if all(isinstance(x, (list, tuple)) for x in obj):
            first = list(obj[0])
            # Header aanwezig?
            first_norm = [norm_key(x) for x in first]
            has_header = any(x in {"idproduct", "name", "avgsellprice", "lowprice", "trendprice"} for x in first_norm)
            if has_header:
                headers = [coerce_text(x) or f"col{i}" for i, x in enumerate(first)]
                rows = obj[1:]
            else:
                headers = default_columns[:]
                rows = obj
            out = []
            for row in rows:
                d = {}
                for i, val in enumerate(row):
                    key = headers[i] if i < len(headers) else f"col{i}"
                    d[key] = val
                out.append(d)
            return out
    if isinstance(obj, dict):
        for key in ["products", "product", "data", "items", "records", "rows", "prices", "priceGuide", "priceguide"]:
            val = obj.get(key)
            if val is not None:
                rows = rows_from_table_like(val, default_columns)
                if rows:
                    return rows
        if obj and all(isinstance(v, dict) for v in obj.values()):
            rows = []
            for k, v in obj.items():
                row = dict(v)
                if not get_text(row, ["idProduct", "id_product", "productId", "id"]):
                    row["idProduct"] = str(k)
                rows.append(row)
            return rows
        if obj and all(isinstance(v, (list, tuple)) for v in obj.values()):
            # Soms als kolom-georiënteerd object: {idProduct:[...], AVG30:[...]}
            keys = list(obj.keys())
            max_len = max((len(v) for v in obj.values() if isinstance(v, (list, tuple))), default=0)
            rows = []
            for i in range(max_len):
                row = {}
                for k in keys:
                    v = obj[k]
                    if isinstance(v, (list, tuple)) and i < len(v):
                        row[k] = v[i]
                rows.append(row)
            return rows
    return []


def as_records(obj: Any) -> List[Dict[str, Any]]:
    return rows_from_table_like(obj, PRODUCT_LIST_COLUMNS)


def norm_text(value: Any) -> str:
    s = coerce_text(value)
    # Pokémon/Cardmarket gebruiken soms speciale tekens in kaartnamen.
    # Die willen we niet zomaar kwijtspelen bij het matchen.
    s = s.replace("♀", " female ").replace("♂", " male ")
    s = s.replace("’", "'").replace("`", "'")
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.lower().replace("pokémon", "pokemon").replace("pokémon", "pokemon")
    s = s.replace("&", " and ")
    # Cardmarket zet ex/V/VMAX enz. soms exact anders gespatieerd; woorden blijven wel bewaard.
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", norm_text(value))


SERIES_PREFIXES = [
    "scarlet violet", "sword shield", "sun moon", "black white",
    "heartgold soulsilver", "diamond pearl", "mega evolution",
]


def strip_series_prefixes(text: str) -> str:
    out = norm_text(text)
    changed = True
    while changed:
        changed = False
        for prefix in SERIES_PREFIXES:
            if out.startswith(prefix + " "):
                out = out[len(prefix):].strip()
                changed = True
            elif out == prefix:
                out = ""
                changed = True
    return out.strip()


def set_name_aliases(series: Any, set_name: Any, abbr: Any = "") -> List[str]:
    """Naamvarianten om app-sets voorzichtig aan Cardmarket-categorieën te koppelen.

    Cardmarket gebruikt in de productlijst meestal een Category/Expansion-naam,
    maar die kan licht verschillen van de dataset: dubbele punten, prefixen
    zoals 'Sword & Shield', accenten, promo-benamingen, enz.
    """
    raw_series = coerce_text(series)
    raw_set = coerce_text(set_name)
    raw_abbr = coerce_text(abbr)
    base = norm_text(raw_set)
    aliases = {base, strip_series_prefixes(base), norm_text(f"{raw_series} {raw_set}"), norm_text(f"{raw_set} {raw_series}")}

    # Veelvoorkomende officiële/Cardmarket-naamvarianten.
    manual: Dict[str, List[str]] = {
        "base": ["base set"],
        "scarlet violet": ["scarlet and violet"],
        "scarlet violet black star promos": ["sv black star promos", "scarlet and violet black star promos"],
        "swsh black star promos": ["sword and shield black star promos", "swsh promo", "sword shield promos"],
        "sm black star promos": ["sun and moon black star promos", "sm promo"],
        "xy black star promos": ["xy promos", "xy black star promo"],
        "bw black star promos": ["black and white black star promos", "bw promos"],
        "dp black star promos": ["diamond and pearl black star promos", "dp promos"],
        "hgss black star promos": ["heartgold soulsilver black star promos", "hgss promos"],
        "wizards black star promos": ["wizards promo", "wizards promos"],
        "expedition base set": ["expedition", "expedition base"],
        "hs triumphant": ["triumphant", "heartgold soulsilver triumphant"],
        "hs undaunted": ["undaunted", "heartgold soulsilver undaunted"],
        "hs unleashed": ["unleashed", "heartgold soulsilver unleashed"],
        "pokemon go": ["pokemon go"],
        "151": ["151", "scarlet and violet 151", "scarlet violet 151"],
        "celebrations classic collection": ["celebrations classic collection", "classic collection"],
        "crown zenith galarian gallery": ["crown zenith galarian gallery", "galarian gallery"],
        "brilliant stars trainer gallery": ["brilliant stars trainer gallery", "trainer gallery brilliant stars"],
        "astral radiance trainer gallery": ["astral radiance trainer gallery", "trainer gallery astral radiance"],
        "lost origin trainer gallery": ["lost origin trainer gallery", "trainer gallery lost origin"],
        "silver tempest trainer gallery": ["silver tempest trainer gallery", "trainer gallery silver tempest"],
        "hidden fates shiny vault": ["hidden fates shiny vault", "shiny vault"],
        "shining fates shiny vault": ["shining fates shiny vault", "shiny vault shining fates"],
        "team magma vs team aqua": ["team magma vs team aqua", "team magma and team aqua"],
        "firered leafgreen": ["firered leafgreen", "fire red leaf green", "firered and leafgreen", "fire red and leaf green"],
        "ruby sapphire": ["ruby sapphire", "ruby and sapphire"],
        "heartgold soulsilver": ["heartgold soulsilver", "heartgold and soulsilver"],
        "black white": ["black white", "black and white"],
        "diamond pearl": ["diamond pearl", "diamond and pearl"],
    }
    for a in manual.get(base, []):
        aliases.add(norm_text(a))
        aliases.add(strip_series_prefixes(a))

    # Afkorting zelf is alleen bruikbaar als Cardmarket die in de setnaam heeft opgenomen.
    if raw_abbr and raw_abbr not in {"—", "-"}:
        aliases.add(norm_text(raw_abbr))

    out = []
    seen = set()
    for a in aliases:
        a = re.sub(r"\s+", " ", a).strip()
        if a and a not in seen:
            seen.add(a)
            out.append(a)
    return out


def set_name_similarity(a: str, b: str) -> float:
    """Voorzichtige setnaam-score. Exacte aliasmatch blijft eerst komen."""
    a = norm_text(a)
    b = norm_text(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    jacc = len(ta & tb) / max(1, len(ta | tb))
    seq = difflib.SequenceMatcher(None, a, b).ratio()
    # Extra score wanneer één naam de andere bevat, bv. 'scarlet violet 151' vs '151'.
    contains = 0.92 if (len(a) >= 3 and len(b) >= 3 and (a in b or b in a)) else 0.0
    return max(seq, 0.65 * seq + 0.35 * jacc, contains)


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



VARIANT_WORDS_RE = re.compile(
    r"\b(reverse\s*holo|holofoil|holo|foil|non\s*foil|normal|reverse|stamped|promo|prerelease|staff|"
    r"1st\s*edition|first\s*edition|unlimited|alternate\s*art|full\s*art|secret\s*rare|rainbow\s*rare)\b",
    re.IGNORECASE,
)


def cardmarket_name_variants(value: Any) -> List[str]:
    """Maak veilige naamvarianten voor matching.

    Cardmarket-productnamen bevatten geregeld extra aanduidingen zoals (Holo),
    Reverse Holo of collector numbers. De app-data bevat meestal alleen de
    kaartnaam. Daarom bewaren we zowel de volledige Cardmarket-naam als een
    opgeschoonde matchnaam.
    """
    raw = coerce_text(value)
    clean, _code, _num = extract_code_number_from_text(raw)
    candidates = {raw, clean}

    # Verwijder enkel duidelijke variant-/finish-tags, niet zomaar elke haakjesinhoud.
    no_variant_parens = re.sub(
        r"\s*[\(\[]\s*(reverse\s*holo|holofoil|holo|foil|normal|stamped|promo|prerelease|staff|1st\s*edition|first\s*edition|unlimited)\s*[\)\]]\s*",
        " ",
        clean,
        flags=re.IGNORECASE,
    )
    candidates.add(no_variant_parens)

    # Verwijder trailing tags na een koppelteken of slash.
    no_trailing = re.sub(
        r"\s*[-–—/]\s*(reverse\s*holo|holofoil|holo|foil|normal|stamped|promo|prerelease|staff|1st\s*edition|first\s*edition|unlimited)\s*$",
        "",
        clean,
        flags=re.IGNORECASE,
    )
    candidates.add(no_trailing)

    # Laatste fallback: losse variantwoorden wegfilteren.
    no_words = VARIANT_WORDS_RE.sub(" ", clean)
    candidates.add(no_words)

    out = []
    seen = set()
    for c in candidates:
        n = norm_text(c)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _has_price_like_key(row: Dict[str, Any]) -> bool:
    flat = flatten(row)
    for k in flat:
        if any(token in k for token in ["price", "avg", "trend", "foil", "low", "sell"]):
            return True
    return False


def _has_id_like_key(row: Dict[str, Any]) -> bool:
    return bool(get_text(row, ["idProduct", "id_product", "productId", "Product ID", "ID Product", "id", "product"]))


def _row_with_id_from_key(key: Any, value: Any) -> Optional[Dict[str, Any]]:
    """Cardmarket kan de price guide als object per idProduct aanbieden.

    Mogelijke vormen die we hier opvangen:
    - {"12345": {"Trend Price": "1.23", ...}}
    - {"12345": [avgSell, low, trend, ...]}
    - {"12345": "1.23"}
    """
    key_txt = coerce_text(key).strip()
    if not re.fullmatch(r"\d+", key_txt):
        return None

    if isinstance(value, dict):
        row = dict(value)
        if not _has_id_like_key(row):
            row["idProduct"] = key_txt
        return row

    if isinstance(value, (list, tuple)):
        # Als de idProduct de sleutel is, start de kolomlijst na idProduct.
        headers = PRICE_GUIDE_COLUMNS[1:]
        row = {"idProduct": key_txt}
        for i, val in enumerate(value):
            header = headers[i] if i < len(headers) else f"col{i+1}"
            row[header] = val
        return row

    if isinstance(value, (int, float, str)) and parse_float(value) is not None:
        return {"idProduct": key_txt, "Trend Price": value}

    return None


def _deep_price_rows(obj: Any, depth: int = 0, max_depth: int = 8) -> List[Dict[str, Any]]:
    """Vind prijsregels ook wanneer Cardmarket de JSON dieper nest.

    De vorige parser las alleen klassieke tabellen. In jouw debug zagen we
    productRows > 0 maar priceRows = 0. Daarom zoeken we nu recursief naar
    records met idProduct + prijsvelden, én naar objecten die per product-id
    zijn opgebouwd.
    """
    if depth > max_depth or obj is None:
        return []

    # Directe tabelvorm eerst proberen.
    direct = rows_from_table_like(obj, PRICE_GUIDE_COLUMNS)
    direct_rows: List[Dict[str, Any]] = []
    for row in direct:
        if not isinstance(row, dict):
            continue
        r = dict(row)
        if not _has_id_like_key(r):
            for possible in ["0", "col0", "ID Product", "Product ID", "product"]:
                val = get_text(r, [possible])
                if val:
                    r["idProduct"] = val
                    break
        if _has_id_like_key(r) and _has_price_like_key(r):
            direct_rows.append(r)
    if direct_rows:
        return direct_rows

    found: List[Dict[str, Any]] = []

    if isinstance(obj, dict):
        # Vorm: {"12345": {...prijs...}} of {"12345": [prijzen...]}
        numeric_key_rows = []
        for k, v in obj.items():
            row = _row_with_id_from_key(k, v)
            if row is not None and _has_price_like_key(row):
                numeric_key_rows.append(row)
        if numeric_key_rows:
            return numeric_key_rows

        # Een losse dict kan zelf al een prijsrecord zijn.
        if _has_id_like_key(obj) and _has_price_like_key(obj):
            return [dict(obj)]

        # Recursief door alle waarden.
        for v in obj.values():
            found.extend(_deep_price_rows(v, depth + 1, max_depth))
            if len(found) > 1000000:
                break
        return found

    if isinstance(obj, list):
        # Als het een lijst van records is, zitten die mogelijk één niveau dieper.
        for item in obj:
            found.extend(_deep_price_rows(item, depth + 1, max_depth))
            if len(found) > 1000000:
                break
        return found

    return []


def price_records(obj: Any) -> List[Dict[str, Any]]:
    """Lees Cardmarket price guide zeer robuust.

    Ondersteunt nu ook geneste objecten en objecten per idProduct.
    """
    rows = _deep_price_rows(obj)
    normalized = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        r = dict(row)
        if not get_text(r, ["idProduct", "id_product", "productId", "id"]):
            for possible in ["0", "col0", "ID Product", "Product ID", "product"]:
                val = get_text(r, [possible])
                if val:
                    r["idProduct"] = val
                    break
        pid = get_text(r, ["idProduct", "id_product", "productId", "id"])
        if not pid:
            continue
        pid = re.sub(r"\.0$", "", str(pid).strip())
        if not pid or pid in seen:
            continue
        r["idProduct"] = pid
        seen.add(pid)
        normalized.append(r)
    return normalized


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
        "normNames": cardmarket_name_variants(raw_name),
        "cmName": clean_name,
        "cmRawName": raw_name,
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
    indexes: Dict[str, Any] = {
        "code_num_name": defaultdict(list),
        "exp_num_name": defaultdict(list),
        "exp_name": defaultdict(list),
        "set_num_name": defaultdict(list),
        # Nieuw: alle producten per Cardmarket-expansion, zodat we veilig kunnen
        # matchen op productnamen die beginnen met de kaartnaam. Cardmarket zet
        # vaak aanvallen achter de kaartnaam, bv. "Ampharos Synchro Pulse...".
        "exp_all_by_exp": defaultdict(list),
    }
    for p in products:
        names = p.get("normNames") or [p.get("normName", "")]
        names = [n for n in names if n]
        if not names:
            continue
        if p["idExpansion"]:
            indexes["exp_all_by_exp"][p["idExpansion"]].append(p)
        for nm in names:
            if p["cmSetCode"] and p["number"]:
                indexes["code_num_name"][(norm_compact(p["cmSetCode"]), p["number"], nm)].append(p)
            if p["idExpansion"] and p["number"]:
                indexes["exp_num_name"][(p["idExpansion"], p["number"], nm)].append(p)
            if p["idExpansion"]:
                indexes["exp_name"][(p["idExpansion"], "", nm)].append(p)
            if p["normSet"] and p["number"]:
                indexes["set_num_name"][(p["normSet"], p["number"], nm)].append(p)
    return indexes


def choose_unique(candidates: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    return candidates[0] if len(candidates) == 1 else None


def product_name_starts_with_card(product_name: str, card_name: str) -> bool:
    """Veilige prefix-match voor Cardmarket-productnamen.

    Cardmarket publiceert Pokémon-productnamen vaak als:
    "Ampharos Synchro Pulse Flashing Bolt" of
    "Beedrill ex Bee Rumble". In onze kaartlijst staat dan gewoon
    "Ampharos" of "Beedrill ex".

    We matchen daarom alleen wanneer de productnaam begint met de volledige
    kaartnaam + spatie. We weigeren verdachte variant-overgangen zoals
    "Mewtwo" -> "Mewtwo ex" als de app-kaart zelf geen ex/V/GX/... bevat.
    """
    pn = norm_text(product_name)
    cn = norm_text(card_name)
    if not pn or not cn or pn == cn:
        return False
    if not pn.startswith(cn + " "):
        return False
    rest = pn[len(cn):].strip()
    first = rest.split()[0] if rest else ""
    variant_tokens = {"ex", "v", "vmax", "vstar", "gx", "break", "prime"}
    card_tokens = set(cn.split())
    # Bescherm tegen foutieve matches zoals "Mewtwo" -> "Mewtwo ex".
    if first in variant_tokens and first not in card_tokens:
        return False
    # Lv./Level is geen echte variant maar onderdeel van oudere Cardmarket-productnamen.
    # Voorbeeld: app "Arcanine" tegenover Cardmarket "Arcanine Lv 32 Overrun Combustion".
    # Omdat we deze prefix-match alleen doen als de kaartnaam uniek is in de app-set
    # én er exact één passend Cardmarket-product is, is dit veilig genoeg om toe te laten.
    return True


def set_key_from_card(card: Dict[str, Any]) -> str:
    return f"{card.get('series','')}|{card.get('set','')}|{card.get('abbr','')}"


def set_key_from_set(row: Dict[str, Any]) -> str:
    return f"{row.get('series','')}|{row.get('set','')}|{row.get('abbr','')}"



def read_manual_set_map() -> Dict[str, Dict[str, Any]]:
    """Lees optionele handmatige setmapping.

    Bestand: cardmarket_manual_set_map.csv
    Vereiste kolommen: serie;set;appAfkorting;cardmarketExpansionId
    Optioneel: cardmarketSetcode;cardmarketSetnaam;opmerking

    Dit is de nieuwe aanpak: als automatische herkenning te voorzichtig blijft,
    leggen we per set één keer het juiste Cardmarket idExpansion vast.
    """
    if not MANUAL_SET_MAP.exists():
        return {}
    text = MANUAL_SET_MAP.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return {}
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except Exception:
        dialect = csv.excel
        dialect.delimiter = ";"
    rows = csv.DictReader(io.StringIO(text), dialect=dialect)
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        serie = coerce_text(row.get("serie") or row.get("series"))
        set_name = coerce_text(row.get("set") or row.get("setnaam"))
        abbr = coerce_text(row.get("appAfkorting") or row.get("abbr") or row.get("afkorting"))
        exp = coerce_text(row.get("cardmarketExpansionId") or row.get("idExpansion") or row.get("expansionId"))
        if not serie or not set_name or not exp:
            continue
        skey = f"{serie}|{set_name}|{abbr}"
        out[skey] = {
            "idExpansion": exp,
            "method": "manual-set-map",
            "score": "manual",
            "overlap": coerce_text(row.get("opmerking")) or "",
            "cmSetCode": coerce_text(row.get("cardmarketSetcode") or row.get("cmSetCode")),
            "cmSetName": coerce_text(row.get("cardmarketSetnaam") or row.get("cmSetName")),
        }
    return out


def write_manual_set_map_template(sets: List[Dict[str, Any]]) -> None:
    """Maak een leeg template als het nog niet bestaat."""
    if MANUAL_SET_MAP.exists():
        return
    with MANUAL_SET_MAP.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["serie", "set", "appAfkorting", "cardmarketExpansionId", "cardmarketSetcode", "cardmarketSetnaam", "opmerking"])
        for s in sets:
            writer.writerow([s.get("series", ""), s.get("set", ""), s.get("abbr", ""), "", "", "", ""])


def write_set_mapping_candidates(
    cards: List[Dict[str, Any]],
    sets: List[Dict[str, Any]],
    products: List[Dict[str, str]],
    current_map: Dict[str, Dict[str, Any]],
) -> None:
    """Schrijf per app-set de beste Cardmarket idExpansion-kandidaten weg.

    Dit bestand is bedoeld om door de gebruiker terug te sturen, zodat we éénmalig
    een betrouwbare manual_set_map kunnen invullen. Het verandert je prijzen niet.
    """
    app_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    app_raw_names: Dict[str, Dict[str, str]] = defaultdict(dict)
    for card in cards:
        skey = set_key_from_card(card)
        for nm in card_name_variants(card.get("name", "")):
            app_counts[skey][nm] += 1
            app_raw_names[skey].setdefault(nm, coerce_text(card.get("name", "")))

    exp_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    exp_meta: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"setCodes": Counter(), "setNames": Counter(), "products": 0, "rawNames": defaultdict(set)})
    for p in products:
        exp = p.get("idExpansion", "")
        names = p.get("normNames") or [p.get("normName", "")]
        names = [n for n in names if n]
        if not exp or not names:
            continue
        for nm in set(names):
            exp_counts[exp][nm] += 1
            exp_meta[exp]["rawNames"][nm].add(p.get("cmRawName") or p.get("cmName") or p.get("name") or "")
        exp_meta[exp]["products"] += 1
        if p.get("cmSetCode"):
            exp_meta[exp]["setCodes"][p["cmSetCode"]] += 1
        if p.get("cmSetName"):
            exp_meta[exp]["setNames"][p["cmSetName"]] += 1

    rows = [[
        "serie", "set", "appAfkorting", "huidigeMapping", "rang", "candidateExpansionId",
        "score", "overlap", "appUniekeNamen", "cmUniekeNamen", "cmProducten",
        "cardmarketSetcode", "cardmarketSetnaam", "sampleOverlap", "sampleAlleenApp", "sampleAlleenCardmarket", "advies"
    ]]

    for s in sets:
        skey = set_key_from_set(s)
        app_unique = set(app_counts.get(skey, Counter()))
        mapped = current_map.get(skey, {})
        candidates: List[Tuple[float, int, str, float]] = []
        for exp, pc in exp_counts.items():
            prod_unique = set(pc)
            if not app_unique or not prod_unique:
                continue
            overlap_names = app_unique & prod_unique
            overlap = len(overlap_names)
            if overlap < 2:
                continue
            score = overlap / math.sqrt(max(1, len(app_unique)) * max(1, len(prod_unique)))
            size_ratio = min(len(app_unique), len(prod_unique)) / max(len(app_unique), len(prod_unique))
            final_score = score * (0.85 + 0.15 * size_ratio)
            candidates.append((final_score, overlap, exp, size_ratio))
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)

        if not candidates:
            rows.append([s.get("series", ""), s.get("set", ""), s.get("abbr", ""), mapped.get("idExpansion", ""), "", "", "", "", len(app_unique), "", "", "", "", "", "", "", "geen kandidaat"])
            continue

        for rank, (score, overlap, exp, size_ratio) in enumerate(candidates[:8], start=1):
            prod_unique = set(exp_counts[exp])
            overlap_names = sorted(app_unique & prod_unique)[:18]
            only_app = sorted(app_unique - prod_unique)[:14]
            only_cm = sorted(prod_unique - app_unique)[:14]
            meta = exp_meta[exp]
            cm_code = meta["setCodes"].most_common(1)[0][0] if meta["setCodes"] else ""
            cm_set_name = meta["setNames"].most_common(1)[0][0] if meta["setNames"] else ""
            if rank == 1 and overlap >= max(8, int(len(app_unique) * 0.10)) and score >= 0.12:
                advies = "STERKE KANDIDAAT - controleer en zet in manual_set_map indien juist"
            elif rank == 1 and overlap >= 5:
                advies = "MOGELIJK - handmatig controleren"
            else:
                advies = "zwak/alternatief"
            rows.append([
                s.get("series", ""), s.get("set", ""), s.get("abbr", ""), mapped.get("idExpansion", ""),
                rank, exp, round(score, 4), overlap, len(app_unique), len(prod_unique), meta["products"], cm_code,
                cm_set_name, ", ".join(overlap_names), ", ".join(only_app), ", ".join(only_cm), advies
            ])

    with OUT_SET_CANDIDATES.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerows(rows)

def infer_expansion_map(cards: List[Dict[str, Any]], sets: List[Dict[str, Any]], products: List[Dict[str, str]]) -> Dict[str, Dict[str, Any]]:
    """Koppel app-sets aan Cardmarket idExpansion.

    Deze versie gebruikt drie veilige lagen:
    1. exacte/alias-match op Cardmarket Category/Setnaam;
    2. duidelijke fuzzy match op setnaam;
    3. naamoverlap op kaartnamen.

    Zo koppelen we meer sets dan alleen de paar sets die toevallig via unieke
    kaartnamen werden herkend, maar vermijden we nog steeds risicovolle gokken.
    """
    app_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    for card in cards:
        nm = norm_text(card.get("name"))
        if nm:
            app_counts[set_key_from_card(card)][nm] += 1

    exp_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    exp_meta: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"setCodes": Counter(), "setNames": Counter(), "products": 0})
    for p in products:
        exp = p.get("idExpansion", "")
        names = p.get("normNames") or [p.get("normName", "")]
        names = [n for n in names if n]
        if not exp or not names:
            continue
        for nm in set(names):
            exp_counts[exp][nm] += 1
        exp_meta[exp]["products"] += 1
        if p.get("cmSetCode"):
            exp_meta[exp]["setCodes"][p["cmSetCode"]] += 1
        if p.get("cmSetName"):
            exp_meta[exp]["setNames"][p["cmSetName"]] += 1

    mapping: Dict[str, Dict[str, Any]] = {}

    def meta_row(exp: str, method: str, score: Any = "", overlap: Any = "") -> Dict[str, Any]:
        meta = exp_meta[exp]
        return {
            "idExpansion": exp,
            "method": method,
            "score": score,
            "overlap": overlap,
            "cmSetCode": meta["setCodes"].most_common(1)[0][0] if meta["setCodes"] else "",
            "cmSetName": meta["setNames"].most_common(1)[0][0] if meta["setNames"] else "",
        }

    # Kandidaten per genormaliseerde Cardmarket-setnaam/category.
    by_set_name: Dict[str, List[str]] = defaultdict(list)
    all_exp_names: Dict[str, List[str]] = defaultdict(list)
    for exp, meta in exp_meta.items():
        for raw_name, cnt in meta["setNames"].items():
            if cnt < 1:
                continue
            variants = {norm_text(raw_name), strip_series_prefixes(raw_name)}
            for v in list(variants):
                variants.add(re.sub(r"\bthe\b", "", v).strip())
            for v in variants:
                v = re.sub(r"\s+", " ", v).strip()
                if v:
                    by_set_name[v].append(exp)
                    all_exp_names[exp].append(v)

    # Pass 1: exacte aliasmatch op setnaam/category.
    for st in sets:
        skey = set_key_from_set(st)
        aliases = set_name_aliases(st.get("series", ""), st.get("set", ""), st.get("abbr", ""))
        hits: List[str] = []
        for alias in aliases:
            hits.extend(by_set_name.get(alias, []))
        uniq = sorted(set(hits))
        if len(uniq) == 1:
            mapping[skey] = meta_row(uniq[0], "set-name-alias", 1.0, "")

    # Pass 2: zeer duidelijke fuzzy setnaam. Alleen gebruiken als er één winnaar is.
    for st in sets:
        skey = set_key_from_set(st)
        if skey in mapping:
            continue
        aliases = set_name_aliases(st.get("series", ""), st.get("set", ""), st.get("abbr", ""))
        scored: List[Tuple[float, str, str, str]] = []
        for exp, names in all_exp_names.items():
            best_for_exp = 0.0
            best_alias = ""
            best_name = ""
            for alias in aliases:
                for exp_name in names:
                    score = set_name_similarity(alias, exp_name)
                    if score > best_for_exp:
                        best_for_exp = score
                        best_alias = alias
                        best_name = exp_name
            if best_for_exp >= 0.93:
                scored.append((best_for_exp, exp, best_alias, best_name))
        scored.sort(reverse=True)
        if scored:
            best_score, best_exp, best_alias, best_name = scored[0]
            second = scored[1][0] if len(scored) > 1 else 0.0
            if best_score >= 0.95 or best_score >= second + 0.04:
                mapping[skey] = meta_row(best_exp, "set-name-fuzzy", round(best_score, 4), f"{best_alias} -> {best_name}")

    # Pass 3: setcode uit productnamen, indien beschikbaar.
    by_code: Dict[str, List[str]] = defaultdict(list)
    for exp, meta in exp_meta.items():
        if meta["setCodes"]:
            code, cnt = meta["setCodes"].most_common(1)[0]
            if cnt >= 3:
                by_code[norm_compact(code)].append(exp)

    for st in sets:
        skey = set_key_from_set(st)
        if skey in mapping:
            continue
        abbr = norm_compact(st.get("abbr"))
        possible = by_code.get(abbr, [])
        if len(possible) == 1:
            mapping[skey] = meta_row(possible[0], "setcode", 1.0, "")

    # Pass 4: naamoverlap op kaartnamen. Dit blijft voorzichtig.
    for st in sets:
        skey = set_key_from_set(st)
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
            min_overlap = max(5, min(12, int(len(app_unique) * 0.12)))
            if overlap >= min_overlap and score >= 0.18 and score >= second_score + 0.03:
                mapping[skey] = meta_row(exp, "name-overlap", round(score, 4), overlap)

    return mapping

def build_price_map(price_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    id_fields = ["idProduct", "id_product", "productId", "id", "Product ID", "ID Product", "id_product"]
    for row in price_rows:
        product_id = get_text(row, id_fields)
        if product_id:
            product_id = re.sub(r"\.0$", "", str(product_id).strip())
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

        # Nieuwe veilige fallback: Cardmarket-productnamen bevatten vaak de
        # kaartnaam gevolgd door aanvalsnamen. Voorbeeld: app "Ampharos" tegenover
        # Cardmarket "Ampharos Synchro Pulse Flashing Bolt".
        # We doen dit alleen als de kaartnaam uniek is in de app-set én er exact
        # één passend product in de Cardmarket-expansion bestaat.
        exp_products = indexes.get("exp_all_by_exp", {}).get(exp, [])
        for nm in names:
            if app_set_name_counts.get(skey, Counter()).get(nm, 0) != 1:
                continue
            cands = [p for p in exp_products if product_name_starts_with_card(p.get("normName", ""), nm)]
            prod = choose_unique(cands)
            if prod:
                return prod, "mapped-expansion+unique-prefix-name", len(cands)
            if cands:
                return None, "ambiguous-prefix-name-in-expansion", len(cands)

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
    price_rows = price_records(prices_obj)
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
    sample_price_keys = []
    for row in price_rows[:5]:
        if isinstance(row, dict):
            sample_price_keys.append(list(row.keys())[:20])


    app_set_name_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    for card in cards:
        for nm in card_name_variants(card.get("name", "")):
            app_set_name_counts[set_key_from_card(card)][nm] += 1

    set_map = infer_expansion_map(cards, sets, products)
    manual_set_map = read_manual_set_map()
    if manual_set_map:
        set_map.update(manual_set_map)
        log(f"Handmatige Cardmarket setmappings toegepast: {len(manual_set_map)}")
    write_manual_set_map_template(sets)
    write_set_mapping_candidates(cards, sets, products, set_map)
    log(f"Automatisch/handmatig herkende Cardmarket expansions: {len(set_map)}/{len(sets)}")

    now_dt = dt.datetime.now(dt.timezone.utc)
    now = now_dt.isoformat()
    today = now_dt.date().isoformat()

    output: List[Dict[str, Any]] = []
    report_rows: List[List[str]] = [[
        "status", "matchType", "candidateCount", "appKey", "serie", "set", "abbr", "kaartnr", "kaartnaam",
        "cmProductId", "cmExpansionId", "cmSetCode", "cmSetName", "cmNumber", "cmName", "cmRawName", "price", "foilTrendPrice", "url"
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
                "", "", "", "", "", "", "", "", "", ""
            ])
            continue

        matched += 1
        price_row = price_map.get(prod["idProduct"], {})
        low = pick_price(price_row, LOW_FIELDS)
        trend = pick_price(price_row, TREND_FIELDS)
        avg1 = pick_price(price_row, AVG1_FIELDS)
        avg7 = pick_price(price_row, AVG7_FIELDS)
        avg30 = pick_price(price_row, AVG30_FIELDS)
        foil_sell = pick_price(price_row, FOIL_SELL_FIELDS)
        foil_low = pick_price(price_row, FOIL_LOW_FIELDS)
        foil_trend = pick_price(price_row, FOIL_TREND_FIELDS)
        foil_avg1 = pick_price(price_row, FOIL_AVG1_FIELDS)
        foil_avg7 = pick_price(price_row, FOIL_AVG7_FIELDS)
        foil_avg30 = pick_price(price_row, FOIL_AVG30_FIELDS)
        price = pick_price(price_row, PRICE_FIELDS) or trend or avg30 or avg7 or low

        if price or low or trend or avg1 or avg7 or avg30 or foil_sell or foil_low or foil_trend or foil_avg1 or foil_avg7 or foil_avg30:
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
            "cmName": prod.get("cmName", "") or prod.get("name", ""),
            "cmRawName": prod.get("cmRawName", "") or prod.get("rawName", ""),
            "num": card.get("num", ""),
            "name": card.get("name", ""),
            "price": price,
            "lowPrice": low,
            "trendPrice": trend,
            "avg1": avg1,
            "avg7": avg7,
            "avg30": avg30,
            "foilSellPrice": foil_sell,
            "foilLowPrice": foil_low,
            "foilTrendPrice": foil_trend,
            "foilAvg1": foil_avg1,
            "foilAvg7": foil_avg7,
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
            prod.get("number", ""), prod.get("cmName", "") or prod.get("name", ""), prod.get("cmRawName", ""), item["price"], item["foilTrendPrice"], prod["url"]
        ])

    payload = {
        "source": "Cardmarket publieke bestanden",
        "updatedAt": now,
        "totalCards": len(cards),
        "matchedCards": matched,
        "pricedCards": priced,
        "matchTypes": dict(match_type_counts),
        "note": "Dubbele kaartnamen zonder betrouwbaar kaartnummer worden bewust niet gekoppeld om foute prijzen te vermijden.",
        "format": "direct-key-map-v2",
        "prices": output,
        "pricesByKey": {item["key"]: item for item in output if item.get("key")},
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

    # Compacte diagnose zodat we zonder gokken kunnen zien waarom iets niet koppelt.
    unmatched_by_set = Counter()
    for row in report_rows[1:]:
        if row[0] != "gekoppeld":
            unmatched_by_set[f"{row[4]} | {row[5]} | {row[6]}"] += 1
    with OUT_UNMATCHED_BY_SET.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["serie_set_afkorting", "aantalNietGekoppeld"])
        for key, count in unmatched_by_set.most_common():
            writer.writerow([key, count])

    def shape_info(obj: Any) -> Dict[str, Any]:
        info: Dict[str, Any] = {"type": type(obj).__name__}
        if isinstance(obj, dict):
            keys = list(obj.keys())[:30]
            info["topKeys"] = [coerce_text(k) for k in keys]
            info["valueTypes"] = {coerce_text(k): type(obj[k]).__name__ for k in keys[:10]}
        elif isinstance(obj, list):
            info["length"] = len(obj)
            if obj:
                info["firstType"] = type(obj[0]).__name__
                if isinstance(obj[0], dict):
                    info["firstKeys"] = list(obj[0].keys())[:30]
                elif isinstance(obj[0], list):
                    info["firstListLength"] = len(obj[0])
                    info["firstListSample"] = [coerce_text(x) for x in obj[0][:20]]
        return info

    price_cache = CACHE_DIR / "price_guide_6.json"
    raw_sample = ""
    raw_cache_size = 0
    if price_cache.exists():
        try:
            raw_text = price_cache.read_text(encoding="utf-8", errors="replace")
            raw_cache_size = len(raw_text)
            raw_sample = raw_text[:500]
        except Exception as exc:
            raw_sample = f"Kon cache niet lezen: {exc}"

    debug_payload = {
        "updatedAt": now,
        "productRows": len(product_rows),
        "priceRows": len(price_rows),
        "usableProducts": len(products),
        "priceMapIds": len(price_map),
        "matchedCards": matched,
        "pricedCards": priced,
        "samplePriceKeys": sample_price_keys,
        "priceObjectShape": shape_info(prices_obj),
        "priceCacheSizeChars": raw_cache_size,
        "priceCacheFirst500Chars": raw_sample,
        "matchTypes": dict(match_type_counts),
        "setMappingCandidates": OUT_SET_CANDIDATES.name,
        "manualSetMapFile": MANUAL_SET_MAP.name,
    }
    OUT_DEBUG.write_text(json.dumps(debug_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    log("Match-types:")
    for k, v in match_type_counts.most_common():
        log(f"  {k}: {v}")
    log(f"Klaar: {matched:,}/{len(cards):,} kaarten gekoppeld, {priced:,} met prijs.".replace(",", "."))
    log(f"Bestanden gemaakt: {OUT_PRICES.name}, {OUT_HISTORY.name}, {OUT_REPORT.name}, {OUT_SETCODES.name}, {OUT_DEBUG.name}, {OUT_SET_CANDIDATES.name}, {MANUAL_SET_MAP.name}")


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
