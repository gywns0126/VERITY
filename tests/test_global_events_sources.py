"""FRED calendar source links must survive collection without exposing credentials."""
from datetime import date, datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
import unittest

from api.collectors import global_events as events


class FredSourceTests(unittest.TestCase):
    def collect(self):
        today = date.today()
        response_dates = [
            {"date": (today + timedelta(days=n)).isoformat()}
            for n in (-1, 0, 7, 14, 21)
        ]
        with patch.object(events, "FRED_API_KEY", "test-private-key"), \
             patch.object(events.requests, "get") as get:
            get.return_value.status_code = 200
            get.return_value.json.return_value = {"release_dates": response_dates}
            rows = events._fetch_fred_releases()
        return rows, get.call_args_list

    def test_every_release_has_matching_public_link(self):
        rows, requests = self.collect()
        ids = {row["release_id"] for row in rows}
        self.assertEqual(ids, set(events.FRED_RELEASES))
        self.assertEqual(len(requests), len(events.FRED_RELEASES))
        self.assertEqual(len(rows), len(events.FRED_RELEASES) + 2)
        for row in rows:
            with self.subTest(release=row["release_id"], date=row["date"]):
                url = urlparse(row["source_url"])
                self.assertEqual((url.scheme, url.netloc, url.path),
                                 ("https", "fred.stlouisfed.org", "/release"))
                self.assertEqual(parse_qs(url.query), {"rid": [str(row["release_id"])]})
                self.assertNotIn("test-private-key", str(row))
                self.assertEqual(row["source_kind"], "release")
                self.assertGreaterEqual(row["date"], date.today().isoformat())

    def test_pce_requests_personal_income_not_money_stock(self):
        rows, requests = self.collect()
        requested_ids = {call.kwargs["params"]["release_id"] for call in requests}
        pce = next(row for row in rows if row["name"] == "미국 PCE 물가지수")
        self.assertEqual(pce["release_id"], 54)
        self.assertIn(54, requested_ids)
        self.assertNotIn(21, requested_ids)

    def test_normalization_preserves_links(self):
        rows, _ = self.collect()
        fixed_now = datetime.combine(date.today(), datetime.min.time(), events._KST)
        with patch.object(events, "_fetch_fred_releases", return_value=rows), \
             patch.object(events, "_fixed_schedule_events", return_value=[]), \
             patch.object(events, "_monthly_calendar_events", return_value=[]), \
             patch.object(events, "_now_kst", return_value=fixed_now):
            normalized = events.collect_global_events()
        self.assertEqual(len(normalized), len(rows))
        self.assertTrue(all(row["source_url"] for row in normalized))
        retail = next(row for row in normalized if row["release_id"] == 9)
        self.assertEqual(retail["source_url"], "https://fred.stlouisfed.org/release?rid=9")

    def test_failed_fetch_does_not_invent_linked_events(self):
        with patch.object(events, "FRED_API_KEY", "test-private-key"), \
             patch.object(events.requests, "get", side_effect=RuntimeError("unavailable")):
            self.assertEqual(events._fetch_fred_releases(), [])


if __name__ == "__main__":
    unittest.main()
