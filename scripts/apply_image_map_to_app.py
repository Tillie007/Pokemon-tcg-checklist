#!/usr/bin/env python3
"""
Koppel pokemon_image_map.json veilig aan de bestaande app.
Dit script past alleen index.html en service-worker.js aan.
Collectiegegevens, prijzen en Supabase-sync blijven onaangeraakt.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
SW = ROOT / "service-worker.js"

text = INDEX.read_text(encoding="utf-8")
original = text

if "const IMAGE_MAP_ENDPOINT" not in text:
    text = text.replace(
        "const DEFAULT_PRICE_ENDPOINT = 'prices.json';\nconst PRICE_LAST_UPDATE_KEY = 'pokemon_tcg_price_last_update_v1';",
        "const DEFAULT_PRICE_ENDPOINT = 'prices.json';\nconst IMAGE_MAP_ENDPOINT = 'pokemon_image_map.json';\nconst PRICE_LAST_UPDATE_KEY = 'pokemon_tcg_price_last_update_v1';",
        1,
    )

if "let imageMap = {};" not in text:
    text = text.replace(
        "let cardDetails = loadCardDetails();\nlet priceAutoUpdate = localStorage.getItem(PRICE_AUTO_KEY) !== '0';",
        "let cardDetails = loadCardDetails();\nlet imageMap = {};\nlet priceAutoUpdate = localStorage.getItem(PRICE_AUTO_KEY) !== '0';",
        1,
    )

insert_after = """function limitlessCardUrl(card) {
  const ab = safeLimitlessCode(card.abbr || cardmarketCodeFor(card));
  const n = normalizedImageNumber(card.num) || String(card.num || '').trim();
  return ab && n ? `https://limitlesstcg.com/cards/${encodeURIComponent(ab)}/${encodeURIComponent(n)}` : '';
}
"""
insert_block = insert_after + """
function imageMapEntryFor(card) {
  if (!card || !imageMap) return null;
  return imageMap[card.key] || imageMap[`${card.series}|${card.set}|${card.abbr}|${card.num}|${card.name}`] || null;
}
function mappedImageCandidatesFor(card) {
  const entry = imageMapEntryFor(card);
  if (!entry) return [];
  if (typeof entry === 'string') return [entry];
  return uniqueNonEmpty([entry.bestUrl, entry.url, entry.imageUrl, ...(Array.isArray(entry.candidates) ? entry.candidates : [])]);
}
async function loadImageMap() {
  try {
    const res = await fetch(IMAGE_MAP_ENDPOINT + '?v=' + Date.now(), { cache: 'no-store' });
    if (!res.ok) {
      console.warn('pokemon_image_map.json niet gevonden of nog niet aangemaakt. De app gebruikt kandidaatlinks als fallback.');
      return 0;
    }
    const payload = await res.json();
    imageMap = payload.images || payload.data || payload || {};
    const count = Object.keys(imageMap).length;
    console.info('Afbeeldingsmap geladen:', count, 'kaarten');
    return count;
  } catch(e) {
    console.warn('Afbeeldingsmap laden mislukt. De app gebruikt kandidaatlinks als fallback.', e);
    return 0;
  }
}
"""
if "function imageMapEntryFor(card)" not in text:
    if insert_after not in text:
        raise SystemExit("Kon positie voor image-map functies niet vinden.")
    text = text.replace(insert_after, insert_block, 1)

if "...mappedImageCandidatesFor(card)," not in text:
    text = text.replace(
        "    p.cardImage,\n    card.imageUrl,\n    ...inferredLimitlessImageCandidates(card),",
        "    p.cardImage,\n    card.imageUrl,\n    ...mappedImageCandidatesFor(card),\n    ...inferredLimitlessImageCandidates(card),",
        1,
    )

text = text.replace(
    "Afbeelding automatisch gezocht via Limitless, PkmnCards en Pokémon TCG-data. Klopt ze niet? Gebruik de PkmnCards-knop of plak hieronder zelf de juiste afbeeldingslink.",
    "Afbeelding automatisch gezocht via de afbeeldingsmap, Limitless, PkmnCards en Pokémon TCG-data. Klopt ze niet? Gebruik de PkmnCards-knop of plak hieronder zelf de juiste afbeeldingslink.",
    1,
)

if "loadImageMap();" not in text:
    text = text.replace(
        "initSyncUi();\ninitFilters();\napplyFilters(true);\nmaybeAutoUpdatePrices();",
        "initSyncUi();\ninitFilters();\nloadImageMap();\napplyFilters(true);\nmaybeAutoUpdatePrices();",
        1,
    )

if text == original:
    print("index.html was al gekoppeld aan pokemon_image_map.json")
else:
    INDEX.write_text(text, encoding="utf-8")
    print("index.html bijgewerkt voor pokemon_image_map.json")

if SW.exists():
    sw = SW.read_text(encoding="utf-8")
    new_sw = re.sub(r"const CACHE_NAME = '[^']+';", "const CACHE_NAME = 'pokemon-tcg-checklist-step6c-image-map-v1';", sw, count=1)
    if new_sw != sw:
        SW.write_text(new_sw, encoding="utf-8")
        print("service-worker.js cacheversie bijgewerkt")
