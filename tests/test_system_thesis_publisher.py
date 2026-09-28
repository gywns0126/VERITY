import importlib.util
import json
import random
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock


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
        self.assertTrue(record["note"].startswith("한줄로 보면\n"))
        self.assertNotIn("[알파네스트 관찰 노트]", record["note"])
        self.assertTrue(record["note"].endswith(rows[0].source_url))
        self.assertFalse(record["observation_meta"]["generated_by_ai"])
        self.assertEqual(record["content_version"], 2)
        self.assertIn("무슨 일이 있었나", record["note"])
        self.assertIn("아직 확인할 것", record["note"])
        self.assertIn("생각이 달라지는 조건", record["note"])
        self.assertIn("아직 판단하기 어려워요", record["note"][:220])
        self.assertEqual(record["observation_meta"]["quality_gate"], "event_type_signal_required_v1")
        self.assertNotIn("실제 규모·후속 실행·시장 반응", record["note"])
        self.assertLessEqual(len(record["note"]), 2000)
        self.assertIn("https://dart.fss.or.kr/", record["note"])
        for phrase in MOD.PROHIBITED_COPY:
            self.assertNotIn(phrase, record["note"])

    def test_selection_uses_unique_tickers_and_topics(self):
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

    def test_corrections_and_liquidity_provider_contracts_are_not_published(self):
        payload = self._feed()
        payload["items"][0]["disclosures"] = [
            {
                "date": "2026-09-22",
                "title": "[기재정정]주요사항보고서(유상증자결정)",
                "label": "주요사항보고",
                "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260922000011",
            },
            {
                "date": "2026-09-22",
                "title": "유동성공급계약의체결",
                "label": "거래소공시",
                "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260922000012",
            },
            {
                "date": "2026-09-22",
                "title": "단일판매ㆍ공급계약체결",
                "label": "거래소공시",
                "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260922000013",
            },
        ]
        payload["items"] = payload["items"][:1]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "feed.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            rows, report = MOD._load_candidates(path, "KR", self.now)
        self.assertEqual([row.title for row in rows], ["단일판매ㆍ공급계약체결"])
        self.assertEqual(report["rejects"]["correction_without_diff"], 1)
        self.assertEqual(report["rejects"]["insufficient_context"], 1)

    def test_original_and_follow_up_correction_family_are_both_excluded(self):
        payload = self._feed()
        payload["items"] = [{
            "ticker": "023410",
            "name": "유진기업",
            "disclosures": [
                {
                    "date": "2026-09-21",
                    "title": "주요사항보고서(회사합병결정)",
                    "label": "주요사항보고",
                    "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260921000001",
                },
                {
                    "date": "2026-09-22",
                    "title": "[기재정정] 주요사항보고서(회사합병결정)",
                    "label": "주요사항보고",
                    "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260922000002",
                },
                {
                    "date": "2026-09-22",
                    "title": "단일판매ㆍ공급계약체결",
                    "label": "거래소공시",
                    "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260922000003",
                },
            ],
        }]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "feed.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            rows, report = MOD._load_candidates(path, "KR", self.now)
        self.assertEqual([row.title for row in rows], ["단일판매ㆍ공급계약체결"])
        self.assertEqual(report["rejects"]["correction_without_diff"], 1)
        self.assertEqual(report["rejects"]["correction_family_without_diff"], 1)

    def test_earlier_correction_does_not_block_a_later_separate_filing(self):
        payload = self._feed()
        payload["items"] = [{
            "ticker": "042660",
            "name": "한화오션",
            "disclosures": [
                {
                    "date": "2026-09-21",
                    "title": "[기재정정]단일판매ㆍ공급계약체결",
                    "label": "거래소공시",
                    "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260921000001",
                },
                {
                    "date": "2026-09-28",
                    "title": "단일판매ㆍ공급계약체결",
                    "label": "거래소공시",
                    "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260928000002",
                },
            ],
        }]
        payload["_meta"]["generated_at"] = "2026-09-28T10:00:00+00:00"
        now = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "feed.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            rows, report = MOD._load_candidates(path, "KR", now)
        self.assertEqual([row.event_date.isoformat() for row in rows], ["2026-09-28"])
        self.assertEqual(report["rejects"]["correction_without_diff"], 1)
        self.assertNotIn("correction_family_without_diff", report["rejects"])

    def test_same_day_earlier_correction_does_not_block_later_receipt(self):
        payload = self._feed()
        payload["items"] = [{
            "ticker": "299660",
            "name": "셀리드",
            "disclosures": [
                {
                    "date": "2026-09-22",
                    "title": "[기재정정]주요사항보고서(유상증자결정)",
                    "label": "주요사항보고",
                    "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260922000158",
                },
                {
                    "date": "2026-09-22",
                    "title": "주요사항보고서(유상증자결정)",
                    "label": "주요사항보고",
                    "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260922000533",
                },
            ],
        }]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "feed.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            rows, report = MOD._load_candidates(path, "KR", self.now)
        self.assertEqual([row.source_url for row in rows], [
            "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260922000533",
        ])
        self.assertEqual(report["rejects"]["correction_without_diff"], 1)
        self.assertNotIn("correction_family_without_diff", report["rejects"])

    def test_us_8k_requires_meaningful_item_code(self):
        payload = {
            "_meta": {"generated_at": "2026-09-22T10:00:00+00:00"},
            "items": [{
                "ticker": "TEST",
                "name": "Test Corp",
                "disclosures": [
                    {
                        "date": "2026-09-22",
                        "title": "8-K",
                        "label": "8-K",
                        "item_codes": ["8.01", "9.01"],
                        "source_url": "https://www.sec.gov/Archives/edgar/data/1/generic.htm",
                    },
                    {
                        "date": "2026-09-22",
                        "title": "8-K",
                        "label": "8-K",
                        "item_codes": ["2.02", "9.01"],
                        "source_url": "https://www.sec.gov/Archives/edgar/data/1/results.htm",
                    },
                ],
            }],
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "feed.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            rows, report = MOD._load_candidates(path, "US", self.now)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].topic, "earnings")
        self.assertIn("SEC 항목 2.02, 9.01", MOD.make_note(rows[0], self.now))
        self.assertEqual(report["rejects"]["insufficient_context"], 1)

    def test_sec_item_codes_use_conservative_event_specific_topics(self):
        expected = {
            ("1.01",): "material_agreement",
            ("1.02",): "material_agreement_end",
            ("2.04",): "obligation_trigger",
            ("3.02",): "unregistered_equity_sale",
            ("5.01",): "control_change",
            ("5.02",): "governance",
            ("5.03",): "charter_or_fiscal_year_change",
        }
        for codes, topic in expected.items():
            with self.subTest(codes=codes):
                self.assertEqual(MOD._sec_topic(codes), topic)

    def test_sec_item_priority_prefers_higher_risk_specific_event(self):
        self.assertEqual(MOD._sec_topic(("1.01", "2.04", "9.01")), "obligation_trigger")
        self.assertEqual(MOD._sec_topic(("3.02", "5.01", "9.01")), "unregistered_equity_sale")
        self.assertEqual(MOD._sec_topic(("2.03", "3.02", "9.01")), "unregistered_equity_sale")
        self.assertEqual(MOD._sec_topic(("5.02", "5.03", "9.01")), "charter_or_fiscal_year_change")

    def test_long_company_name_keeps_uncertainty_in_first_220_characters(self):
        row = MOD.Candidate(
            ticker="LONG",
            market="us",
            name="긴 회사 이름 " * 40,
            event_date=date(2026, 9, 22),
            title="8-K",
            label="8-K",
            source_url="https://www.sec.gov/Archives/edgar/data/1/long.htm",
            source_name="SEC EDGAR",
            artifact_generated_at="2026-09-22T10:00:00+00:00",
            item_codes=("5.03",),
            is_correction=False,
            priority=100,
            topic="charter_or_fiscal_year_change",
        )
        self.assertIn("아직 판단하기 어려워요", MOD.make_note(row, self.now)[:220])

    def test_cb_lifecycle_event_is_not_mislabeled_as_new_financing(self):
        payload = self._feed()
        payload["items"] = [{
            "ticker": "000001",
            "name": "테스트",
            "disclosures": [{
                "date": "2026-09-22",
                "title": "주요사항보고서(자기전환사채만기전취득결정)",
                "label": "주요사항보고",
                "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260922000021",
            }],
        }]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "feed.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            rows, report = MOD._load_candidates(path, "KR", self.now)
        self.assertEqual(rows, [])
        self.assertEqual(report["rejects"]["insufficient_context"], 1)

    def test_due_run_requests_one_high_signal_note(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "feed.json"
            path.write_text(json.dumps(self._feed()), encoding="utf-8")
            rows, _ = MOD._load_candidates(path, "KR", self.now)
        with mock.patch.object(MOD, "collect_candidates", return_value=(rows, [])):
            result = MOD.run(self.now, dry_run=True, force=False, seed=7)
        self.assertEqual(result["requested_count"], 1)
        self.assertEqual(len(result["selected"]), 1)

    def test_live_due_run_posts_at_most_one_note(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "feed.json"
            path.write_text(json.dumps(self._feed()), encoding="utf-8")
            rows, _ = MOD._load_candidates(path, "KR", self.now)

        requests = []

        class FakeClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def request(self, method, path, body=None, prefer=""):
                requests.append((method, path, body, prefer))
                if method == "GET" and path.startswith("system_thesis_schedule"):
                    return [{"next_run_at": "2026-09-22T00:00:00+00:00"}]
                if method == "GET" and path.startswith("user_thesis?"):
                    return []
                if method == "POST":
                    return [{"id": "note-1"}]
                return None

        with mock.patch.object(MOD, "collect_candidates", return_value=(rows, [])), \
             mock.patch.object(MOD, "SupabaseRest", FakeClient), \
             mock.patch.dict(MOD.os.environ, {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "test"}):
            result = MOD.run(self.now, dry_run=False, force=True, seed=7)

        posts = [call for call in requests if call[0] == "POST" and call[1] == "user_thesis"]
        self.assertEqual(len(posts), 1)
        self.assertEqual(result["published_count"], 1)

    def test_every_publishable_topic_has_a_copy_contract(self):
        self.assertEqual(MOD.PUBLISHABLE_TOPICS, set(MOD.COPY_BY_TOPIC))
        for topic in sorted(MOD.PUBLISHABLE_TOPICS):
            row = MOD.Candidate(
                ticker="005930",
                market="kr",
                name="삼성전자",
                event_date=date(2026, 9, 22),
                title="검증용 공시",
                label="공시",
                source_url="https://dart.fss.or.kr/example",
                source_name="DART",
                artifact_generated_at="2026-09-22T10:00:00+00:00",
                item_codes=(),
                is_correction=False,
                priority=100,
                topic=topic,
            )
            note = MOD.make_note(row, self.now)
            self.assertLessEqual(len(note), 2000)
            for phrase in MOD.PROHIBITED_COPY:
                self.assertNotIn(phrase, note)

    def test_kr_treasury_and_listing_events_use_distinct_topics(self):
        self.assertEqual(MOD._topic("KR", "주요사항보고", "주요사항보고서(자기주식취득결정)"), "treasury_buyback")
        self.assertEqual(MOD._topic("KR", "주요사항보고", "주요사항보고서(자기주식처분결정)"), "treasury_sale")
        self.assertEqual(MOD._topic("KR", "주요사항보고", "주요사항보고서(회생절차개시신청)"), "distress")
        self.assertEqual(MOD._topic("KR", "거래소공시", "상장폐지 사유 발생"), "kr_listing_risk")

    def test_migration_keeps_system_rows_out_of_member_counts(self):
        migration = (Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "2026092201_alphaconsole_system_thesis.sql").read_text(encoding="utf-8")
        self.assertIn("author_kind = 'user'", migration)
        self.assertIn("user_thesis_author_contract", migration)
        self.assertNotIn("insert into auth.users", migration.lower())


if __name__ == "__main__":
    unittest.main()
