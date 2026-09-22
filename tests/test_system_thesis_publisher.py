import importlib.util
import json
import random
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish_system_thesis.py"
SPEC = importlib.util.spec_from_file_location("publish_system_thesis", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


class SystemThesisPublisherTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)

    def _feed(self, host="dart.fss.or.kr", generated="2026-09-22T10:00:00+00:00"):
        return {
            "_meta": {"generated_at": generated},
            "items": [
                {
                    "ticker": "005930",
                    "name": "삼성전자",
                    "disclosures": [{
                        "date": "2026-09-22",
                        "title": "단일판매ㆍ공급계약체결",
                        "label": "거래소공시",
                        "source_url": f"https://{host}/dsaf001/main.do?rcpNo=20260922000001",
                        "why_it_matters": "계약 사실이 확인됐어요. 규모와 기간은 원문 확인이 필요해요.",
                    }],
                },
                {
                    "ticker": "000660",
                    "name": "SK하이닉스",
                    "disclosures": [{
                        "date": "2026-09-21",
                        "title": "분기보고서",
                        "label": "정기보고서",
                        "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260921000002",
                    }],
                },
            ],
        }

    def test_only_recent_official_sources_are_eligible(self):
        with tempfile.TemporaryDirectory() as temp:
            good = Path(temp) / "good.json"
            bad = Path(temp) / "bad.json"
            good.write_text(json.dumps(self._feed()), encoding="utf-8")
            bad.write_text(json.dumps(self._feed(host="example.com")), encoding="utf-8")
            rows, report = MOD._load_candidates(good, "KR", self.now)
            blocked, blocked_report = MOD._load_candidates(bad, "KR", self.now)
        self.assertEqual(len(rows), 2)
        self.assertEqual(report["eligible"], 2)
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0].ticker, "000660")
        self.assertEqual(blocked_report["rejects"]["source_not_official"], 1)

    def test_system_copy_is_neutral_and_traceable(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "feed.json"
            path.write_text(json.dumps(self._feed()), encoding="utf-8")
            rows, _ = MOD._load_candidates(path, "KR", self.now)
        record = MOD.make_row(rows[0], self.now)
        self.assertEqual(record["author_kind"], "system")
        self.assertEqual(record["stance"], "watch")
        self.assertIsNone(record["user_id"])
        self.assertEqual(record["system_label"], "알파네스트 관찰 노트")
        self.assertTrue(record["note"].startswith("[알파네스트 관찰 노트]"))
        self.assertFalse(record["observation_meta"]["generated_by_ai"])
        self.assertIn("확인한 사실", record["note"])
        self.assertIn("반대 근거", record["note"])
        self.assertIn("다음 확인", record["note"])
        self.assertIn("https://dart.fss.or.kr/", record["note"])
        for phrase in MOD.PROHIBITED_COPY:
            self.assertNotIn(phrase, record["note"])

    def test_batch_uses_unique_tickers_and_one_to_three_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "feed.json"
            payload = self._feed()
            payload["items"][0]["disclosures"].append({
                "date": "2026-09-20",
                "title": "임원ㆍ주요주주특정증권등소유상황보고서",
                "label": "지분공시",
                "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260920000003",
            })
            path.write_text(json.dumps(payload), encoding="utf-8")
            rows, _ = MOD._load_candidates(path, "KR", self.now)
        selected = MOD.select_candidates(rows, 3, random.Random(7))
        self.assertGreaterEqual(len(selected), 1)
        self.assertLessEqual(len(selected), 3)
        self.assertEqual(len({row.ticker for row in selected}), len(selected))
        self.assertEqual(len({row.topic for row in selected}), len(selected))

    def test_stale_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "feed.json"
            path.write_text(json.dumps(self._feed(generated="2026-09-18T00:00:00+00:00")), encoding="utf-8")
            rows, report = MOD._load_candidates(path, "KR", self.now)
        self.assertEqual(rows, [])
        self.assertEqual(report["rejects"]["artifact_stale"], 2)

    def test_migration_keeps_system_rows_out_of_member_counts(self):
        migration = (Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "2026092201_alphaconsole_system_thesis.sql").read_text(encoding="utf-8")
        self.assertIn("author_kind = 'user'", migration)
        self.assertIn("user_thesis_author_contract", migration)
        self.assertNotIn("insert into auth.users", migration.lower())


if __name__ == "__main__":
    unittest.main()
