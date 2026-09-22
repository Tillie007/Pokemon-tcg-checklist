from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SET_NAMES = {
    "30th Celebration": 161,
    "30th Celebration: Classic Collection": 30,
    "30th Celebration: Energy Collection": 8,
}


class ThirtiethCelebrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads((ROOT / "pokemon_cards_data.json").read_text(encoding="utf-8"))
        cls.images = json.loads((ROOT / "pokemon_image_map.json").read_text(encoding="utf-8"))["images"]
        cls.prices = json.loads((ROOT / "prices.json").read_text(encoding="utf-8"))["prices"]
        cls.cards = [
            card for card in cls.data["cards"]
            if card.get("series") == "Mega Evolution" and card.get("set") in SET_NAMES
        ]

    def test_set_counts_and_unique_keys(self) -> None:
        sets = {
            row["set"]: row for row in self.data["sets"]
            if row.get("series") == "Mega Evolution" and row.get("set") in SET_NAMES
        }
        self.assertEqual(set(sets), set(SET_NAMES))
        self.assertEqual({name: row["count"] for name, row in sets.items()}, SET_NAMES)
        self.assertEqual(len(self.cards), 199)
        self.assertEqual(len({card["key"] for card in self.cards}), 199)

    def test_main_classic_rgb_and_energy_numbers(self) -> None:
        main = [card for card in self.cards if card["set"] == "30th Celebration"]
        numbered = [card["num"] for card in main if card["num"].isdigit()]
        rgb = [card["num"] for card in main if not card["num"].isdigit()]
        self.assertEqual(numbered, [f"{number:03d}" for number in range(1, 159)])
        self.assertEqual(rgb, ["R/RGB", "G/RGB", "B/RGB"])

        classic = [card for card in self.cards if card["set"].endswith("Classic Collection")]
        self.assertEqual(len(classic), 30)
        self.assertIn(("004", "Charizard"), {(card["num"], card["name"]) for card in classic})
        self.assertIn(("203", "Magikarp"), {(card["num"], card["name"]) for card in classic})

        energy = [card for card in self.cards if card["set"].endswith("Energy Collection")]
        self.assertEqual([card["num"] for card in energy], [f"{number:03d}" for number in range(9, 17)])

    def test_every_card_has_an_image_and_cardmarket_price(self) -> None:
        keys = {card["key"] for card in self.cards}
        self.assertEqual(keys, keys & set(self.images))
        for key in keys:
            entry = self.images[key]
            self.assertTrue(entry.get("bestUrl"), key)
            self.assertTrue(entry.get("candidates"), key)

        prices = {row["key"]: row for row in self.prices if row.get("key") in keys}
        self.assertEqual(set(prices), keys)
        for key, row in prices.items():
            self.assertEqual(row.get("matchType"), "verified-30th-product", key)
            self.assertTrue(row.get("price"), key)
            self.assertTrue(row.get("cmProductId"), key)

    def test_embedded_app_and_cache_version(self) -> None:
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        worker = (ROOT / "service-worker.js").read_text(encoding="utf-8")
        self.assertIn('"set":"30th Celebration"', index)
        self.assertIn("service-worker.js?v=4", index)
        self.assertIn("pokemon-tcg-checklist-scanner-v4", worker)


if __name__ == "__main__":
    unittest.main()
