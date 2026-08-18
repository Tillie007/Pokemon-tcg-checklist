import datetime as dt
import unittest

from scripts.update_prices import (
    HISTORY_DAILY_DAYS,
    HISTORY_DAYS_TO_KEEP,
    compact_history_rows,
    normalize_history_row,
    update_history,
)


class PriceHistoryTests(unittest.TestCase):
    def test_legacy_object_becomes_compact_array(self):
        row = normalize_history_row({
            "date": "2026-08-18",
            "price": "1.20",
            "trendPrice": "1.10",
            "avg30": "1.00",
            "lowPrice": "0.80",
            "foilTrendPrice": "",
            "currency": "EUR",
        })
        self.assertEqual(row, ["2026-08-18", "1.20", "1.10", "1.00", "0.80"])

    def test_recent_days_stay_daily_and_older_days_become_weekly(self):
        today = dt.date(2026, 8, 18)
        rows = []
        for days_back in range(HISTORY_DAYS_TO_KEEP):
            day = today - dt.timedelta(days=days_back)
            rows.append([day.isoformat(), str(days_back)])

        compacted = compact_history_rows(rows, today.isoformat())
        dates = [dt.date.fromisoformat(row[0]) for row in compacted]
        recent_cutoff = today - dt.timedelta(days=HISTORY_DAILY_DAYS - 1)
        recent = [day for day in dates if day >= recent_cutoff]
        older = [day for day in dates if day < recent_cutoff]

        self.assertEqual(len(recent), HISTORY_DAILY_DAYS)
        self.assertEqual(len({day.isocalendar()[:2] for day in older}), len(older))
        self.assertLessEqual(len(compacted), HISTORY_DAILY_DAYS + 45)

    def test_new_run_replaces_same_day_and_removes_expired_rows(self):
        existing = {
            "card-key": [
                ["2026-08-18", "1.00"],
                ["2025-01-01", "9.99"],
            ]
        }
        prices = [{"key": "card-key", "price": "2.50"}]
        result = update_history(existing, prices, "2026-08-18")

        self.assertEqual(result["card-key"], [["2026-08-18", "2.50"]])


if __name__ == "__main__":
    unittest.main()
