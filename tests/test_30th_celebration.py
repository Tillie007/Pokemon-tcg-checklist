from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SET_NAMES = {
    "30th Celebration": 191,
    "Mega Evolution Energy": 16,
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
        self.assertEqual(len(self.cards), 207)
        self.assertEqual(len({card["key"] for card in self.cards}), 207)

    def test_main_classic_rgb_and_energy_numbers(self) -> None:
        main = [card for card in self.cards if card["set"] == "30th Celebration"]
        classic = [card for card in main if card.get("rarity") == "Classic Collection"]
        regular = [
            card for card in main
            if card.get("rarity") != "Classic Collection" and str(card.get("num", "")).isdigit()
        ]
        rgb = [
            card["num"] for card in main
            if card.get("rarity") != "Classic Collection" and not str(card.get("num", "")).isdigit()
        ]

        self.assertEqual([card["num"] for card in regular], [f"{number:03d}" for number in range(1, 159)])
        self.assertEqual(rgb, ["R/RGB", "G/RGB", "B/RGB"])
        self.assertEqual(len(classic), 30)
        classic_pairs = {(card["num"], card["name"]) for card in classic}
        self.assertIn(("004", "Charizard"), classic_pairs)
        self.assertIn(("097", "Genesect EX"), classic_pairs)
        self.assertIn(("203", "Magikarp"), classic_pairs)
        self.assertEqual(len(classic_pairs), 30)

        energy = [card for card in self.cards if card["set"] == "Mega Evolution Energy"]
        self.assertEqual([card["num"] for card in energy], [f"{number:03d}" for number in range(1, 17)])

    def test_every_card_has_an_image_and_price(self) -> None:
        keys = {card["key"] for card in self.cards}
        self.assertEqual(keys, keys & set(self.images))
        for key in keys:
            entry = self.images[key]
            self.assertTrue(entry.get("bestUrl"), key)
            self.assertTrue(entry.get("candidates"), key)

        prices = {row["key"]: row for row in self.prices if row.get("key") in keys}
        self.assertEqual(set(prices), keys)
        for key, row in prices.items():
            self.assertTrue(row.get("price") or row.get("trendPrice"), key)
            self.assertTrue(row.get("cmProductId"), key)

        # 158 hoofdkaarten + 30 Classic + 3 RGB + 8 jubileum-energies
        # moeten de gecontroleerde 30th-koppeling gebruiken.
        direct = [
            row for row in prices.values()
            if row.get("matchType") == "verified-30th-product"
        ]
        self.assertGreaterEqual(len(direct), 199)

    def test_dark_v3_uses_current_cache_strategy(self) -> None:
        app = (ROOT / "dark-v3-live.html").read_text(encoding="utf-8")
        worker = (ROOT / "service-worker.js").read_text(encoding="utf-8")
        self.assertIn("30th Celebration", app)
        self.assertIn("pokemon-tcg-checklist-scanner-v", worker)


if __name__ == "__main__":
    unittest.main()
