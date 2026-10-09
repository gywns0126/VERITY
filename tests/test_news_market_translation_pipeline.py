"""Offline: PYTHONDONTWRITEBYTECODE=1 python3 -B tests/test_news_market_translation_pipeline.py.

Exercise the real translation helper and collectors; model, persistence and HTTP
seams are mocked. No credentials, production cache, network or exporter writes.
"""
from copy import deepcopy
from inspect import Parameter, signature
from io import StringIO
from pathlib import Path
import json
import socket
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, mock_open, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from api.collectors import news_headlines as nh
from api.collectors import news_translation as nt


def article(title="Global fixture headline", **fields):
    return {"title": title, "link": "https://publisher.example.test/story",
            "time": "Fri, 09 Oct 2026 06:00:00 GMT", "source": "Fixture publisher",
            "category": "market", **fields}


def facts(row):
    return {key: row.get(key) for key in ("title", "link", "url", "time", "source", "category")}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.cache = {}
        self.expected_batches = self.expected_saves = 0
        self.real_load_cache = nt._load_cache
        self.batch = self.start(patch.object(nt, "_gemini_translate",
            side_effect=AssertionError("REAL MODEL CALL FORBIDDEN")))
        self.save = self.start(patch.object(nt, "_save_cache",
            side_effect=AssertionError("CACHE WRITE FORBIDDEN")))
        self.start(patch.object(nt, "_load_cache", side_effect=lambda: deepcopy(self.cache)))
        self.network = self.start(patch.object(nh.requests.sessions.Session, "request",
            side_effect=AssertionError("LIVE HTTP FORBIDDEN")))
        self.connect = self.start(patch.object(socket.socket, "connect",
            side_effect=AssertionError("LIVE SOCKET FORBIDDEN")))

    def start(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def tearDown(self):
        self.assertEqual(self.batch.call_count, self.expected_batches, "unexpected model seam call")
        self.assertEqual(self.save.call_count, self.expected_saves, "unexpected cache write seam call")
        self.network.assert_not_called()
        self.connect.assert_not_called()

    def generation(self, translations, *, save=True):
        self.expected_batches = 1
        self.expected_saves = int(save)
        self.batch.side_effect = lambda titles: {title: translations[title] for title in titles if title in translations}
        self.save.side_effect = None  # Mock only: no cache file is written.

    def market(self, items, max_items=20):
        # Keep unrelated source blocking/novelty behavior out of this contract test.
        tiers = ModuleType("api.intelligence.source_tiers")
        tiers.is_blocked = lambda _value: False
        novelty = ModuleType("api.intelligence.novelty")
        novelty.NoveltyTracker = lambda: None
        with patch.dict(sys.modules, {tiers.__name__: tiers, novelty.__name__: novelty}), \
                patch.object(nh, "_naver_market_news", return_value=deepcopy(items)), \
                patch.object(nh, "_naver_economy_news", return_value=[]), \
                patch.object(nh, "_korea_google_news", return_value=[]), \
                patch.object(nh, "_korea_publisher_rss", return_value=[]):
            return nh.collect_headlines(max_items=max_items)

    def bloomberg(self, items, max_items=20):
        entries = [{"title": row["title"], "link": row["link"], "published": row["time"],
                    "source": {"title": row["source"]}} for row in items]
        response = Mock(content=b"fixture RSS response")
        with patch.object(nh.requests, "get", return_value=response), \
                patch.object(nh.feedparser, "parse", return_value=SimpleNamespace(entries=entries)):
            return nh.collect_bloomberg_google_news_rss(max_items=max_items)

    def test_cache_only_is_keyword_only_and_default_preserves_existing_calls(self):
        arg = signature(nt.translate_headlines_ko).parameters["cache_only"]
        self.assertEqual(arg.kind, Parameter.KEYWORD_ONLY)
        self.assertIs(arg.default, False)

    def test_cache_only_hit_miss_and_korean_never_call_model_or_save(self):
        self.cache = {"Cached headline": "저장된 번역 제목"}
        titles = ["Cached headline", "Uncached headline", "한국어 원문 제목"]
        before = deepcopy(titles), deepcopy(self.cache)
        result = nt.translate_headlines_ko(titles, cache_only=True)
        self.assertEqual(result, {"Cached headline": "저장된 번역 제목", "한국어 원문 제목": "한국어 원문 제목"})
        self.assertEqual((titles, self.cache), before)

    def test_cache_only_rejects_invalid_cached_values(self):
        for value in (None, 42, {}, [], "", "   ", "Another English headline"):
            with self.subTest(value=value):
                self.cache = {"English fixture headline": value}
                self.assertEqual(nt.translate_headlines_ko(["English fixture headline"], cache_only=True), {})

    def test_korean_and_mixed_originals_take_priority_over_wrong_cache_values(self):
        titles = ["한국어 원문 제목", "Global 시장 원문 제목"]
        self.cache = {title: "원문과 다른 저장 번역" for title in titles}
        self.assertEqual(nt.translate_headlines_ko(titles, cache_only=True), {title: title for title in titles})

    def test_cache_only_requires_exact_raw_title_not_publisher_or_html_guessing(self):
        self.cache = {"Europe's fixture headline": "저장된 유럽 제목"}
        self.assertEqual(nt.translate_headlines_ko([
            "Europe&#39;s fixture headline", "Europe's fixture headline - Fixture publisher",
            "EUROPE'S fixture headline"], cache_only=True), {})

    def test_cached_lookup_trims_outer_whitespace_without_rewriting_input_titles(self):
        self.cache = {"Fixture title": "  저장된 제목  "}
        titles = ["  Fixture title  ", "Fixture title"]
        self.assertEqual(nt.translate_headlines_ko(titles, cache_only=True), {"Fixture title": "저장된 제목"})
        self.assertEqual(titles, ["  Fixture title  ", "Fixture title"])

    def test_empty_and_invalid_title_inputs_do_not_trigger_calls(self):
        for titles in ([], [None, 42, "", "   "]):
            self.assertEqual(nt.translate_headlines_ko(titles, cache_only=True), {})

    def test_unavailable_or_malformed_cache_preserves_korean_and_returns_no_english_translation(self):
        for data in ("not JSON", "[]", "null", "{}"):
            with self.subTest(data=data), patch.object(nt, "_load_cache", self.real_load_cache), \
                    patch("builtins.open", mock_open(read_data=data)):
                self.assertEqual(nt.translate_headlines_ko(["English fixture", "한국어 원문"], cache_only=True),
                                 {"한국어 원문": "한국어 원문"})
        with patch.object(nt, "_load_cache", self.real_load_cache), patch("builtins.open", side_effect=OSError("unavailable")):
            self.assertEqual(nt.translate_headlines_ko(["English fixture"], cache_only=True), {})

    def test_default_translation_still_batches_only_misses_once_and_saves_once(self):
        self.cache = {"Cached headline": "기존 번역"}
        self.generation({"New headline": "새 번역"})
        result = nt.translate_headlines_ko(["Cached headline", "New headline", "New headline", "한국어 원문"])
        self.assertEqual(result, {"Cached headline": "기존 번역", "New headline": "새 번역", "한국어 원문": "한국어 원문"})
        self.batch.assert_called_once_with(["New headline"])
        self.save.assert_called_once_with({"Cached headline": "기존 번역", "New headline": "새 번역"})

    def test_curated_mapping_is_separate_and_overrides_dynamic_cache(self):
        dynamic, curated = "/fixture/dynamic-cache.json", "/fixture/curated-mapping.json"
        documents = {dynamic: {"Shared fixture": "동적 캐시 번역", "Dynamic fixture": "동적 전용 번역"},
                     curated: {"Shared fixture": "수동 우선 번역", "Curated fixture": "수동 전용 번역"}}
        opened = []

        def read_fixture(path, *args, **kwargs):
            opened.append(path)
            self.assertIn(path, documents)
            return StringIO(json.dumps(documents[path], ensure_ascii=False))

        before = deepcopy(documents)
        with patch.object(nt, "CACHE_PATH", dynamic), patch.object(nt, "CURATED_PATH", curated), \
                patch.object(nt, "_load_cache", self.real_load_cache), patch("builtins.open", side_effect=read_fixture):
            result = nt.translate_headlines_ko(["Shared fixture", "Dynamic fixture", "Curated fixture", "Missing fixture"], cache_only=True)
        self.assertEqual(result, {"Shared fixture": "수동 우선 번역", "Dynamic fixture": "동적 전용 번역",
                                  "Curated fixture": "수동 전용 번역"})
        self.assertEqual(opened, [dynamic, curated])
        self.assertEqual(documents, before)

    def test_corrupt_or_unavailable_dynamic_cache_keeps_curated_mapping(self):
        dynamic, curated = "/fixture/broken-dynamic.json", "/fixture/valid-curated.json"
        manual = {"Curated fixture": "수동 매핑 보존 번역"}
        for unavailable in (False, True):
            opened = []

            def read_fixture(path, *args, **kwargs):
                opened.append(path)
                if path == dynamic:
                    if unavailable:
                        raise OSError("fixture unavailable")
                    return StringIO("{broken JSON")
                self.assertEqual(path, curated)
                return StringIO(json.dumps(manual, ensure_ascii=False))

            with self.subTest(unavailable=unavailable), patch.object(nt, "CACHE_PATH", dynamic), \
                    patch.object(nt, "CURATED_PATH", curated), patch.object(nt, "_load_cache", self.real_load_cache), \
                    patch("builtins.open", side_effect=read_fixture):
                self.assertEqual(nt.translate_headlines_ko(["Curated fixture", "Missing fixture"], cache_only=True), manual)
            self.assertEqual(opened, [dynamic, curated])

    def test_explicit_false_keeps_existing_model_batch_path(self):
        self.generation({"New fixture": "새 검증 번역"})
        self.assertEqual(nt.translate_headlines_ko(["New fixture"], cache_only=False), {"New fixture": "새 검증 번역"})
        self.batch.assert_called_once_with(["New fixture"])

    def test_market_collector_preserves_facts_prior_translation_and_korean_originals(self):
        rows = [article("Cached market fixture", link="https://publisher.example.test/cached"),
                article("Uncached market fixture", link="https://publisher.example.test/missing"),
                article("Already translated fixture", title_ko="이미 보존된 시장 번역"),
                article("한국어 원문 기사", link="https://publisher.example.test/korean")]
        self.cache = {rows[0]["title"]: "저장된 시장 번역", rows[2]["title"]: "덮어쓰면 안 되는 번역",
                      rows[3]["title"]: "한국어 원문과 다른 번역"}
        with patch.object(nt, "translate_headlines_ko", wraps=nt.translate_headlines_ko) as translate:
            result = self.market(rows)
        self.assertTrue(translate.called)
        self.assertTrue(all(call.kwargs.get("cache_only") is True for call in translate.call_args_list))
        by_title = {row["title"]: row for row in result}
        self.assertEqual(len(by_title), len(rows))
        for row in rows:
            self.assertEqual(facts(by_title[row["title"]]), facts(row))
        self.assertEqual(by_title[rows[0]["title"]]["title_ko"], "저장된 시장 번역")
        self.assertEqual(by_title[rows[2]["title"]]["title_ko"], "이미 보존된 시장 번역")
        self.assertFalse(by_title[rows[1]["title"]].get("title_ko"))
        self.assertIn(by_title[rows[3]["title"]].get("title_ko"), (None, rows[3]["title"]))

    def test_market_cache_attachment_keeps_existing_collection_limit(self):
        rows = [article("Fixture news " + str(index), link="https://publisher.example.test/" + str(index)) for index in range(4)]
        self.cache = {row["title"]: "검증 번역 " + str(index) for index, row in enumerate(rows)}
        result = self.market(rows, max_items=2)
        self.assertEqual([row["title"] for row in result], [row["title"] for row in rows[:2]])
        self.assertTrue(all(row.get("title_ko") for row in result))

    def test_bloomberg_collector_attaches_only_cache_hits_and_preserves_raw_identity(self):
        rows = [article("Europe&#39;s fixture headline - Fixture publisher"),
                article("Another uncached RSS headline", link="https://publisher.example.test/missing"),
                article("한국어 원문 RSS 제목", link="https://publisher.example.test/korean")]
        self.cache = {rows[0]["title"]: "저장된 유럽 제목"}
        with patch.object(nt, "translate_headlines_ko", wraps=nt.translate_headlines_ko) as translate:
            result = self.bloomberg(rows)
        self.assertTrue(translate.called)
        self.assertTrue(all(call.kwargs.get("cache_only") is True for call in translate.call_args_list))
        self.assertEqual(len(result), len(rows))
        for before, after in zip(rows, result):
            self.assertEqual(facts(after), facts({**before, "category": "bloomberg_google"}))
        self.assertEqual(result[0]["title_ko"], "저장된 유럽 제목")
        self.assertFalse(result[1].get("title_ko"))
        self.assertIn(result[2].get("title_ko"), (None, rows[2]["title"]))

    def test_bloomberg_cache_attachment_does_not_change_limit(self):
        rows = [article("RSS fixture news " + str(index)) for index in range(4)]
        self.cache = {row["title"]: "검증 번역 " + str(index) for index, row in enumerate(rows)}
        result = self.bloomberg(rows, max_items=2)
        self.assertEqual(len(result), 2)
        self.assertEqual([row["title"] for row in result], [row["title"] for row in rows[:2]])

    def test_both_market_collectors_survive_unavailable_cache_without_paid_calls(self):
        row = article("Uncached fixture headline")
        with patch.object(nt, "_load_cache", self.real_load_cache), patch("builtins.open", side_effect=OSError("unavailable")):
            market, bloomberg = self.market([row]), self.bloomberg([row])
        self.assertEqual(facts(market[0]), facts(row))
        self.assertEqual(facts(bloomberg[0]), facts({**row, "category": "bloomberg_google"}))
        self.assertFalse(market[0].get("title_ko")); self.assertFalse(bloomberg[0].get("title_ko"))

    def test_bloomberg_mocked_request_failure_returns_empty_without_translation_side_effects(self):
        with patch.object(nh.requests, "get", side_effect=nh.requests.RequestException("fixture offline")):
            self.assertEqual(nh.collect_bloomberg_google_news_rss(), [])

    def test_market_and_bloomberg_add_no_batches_before_the_existing_us_batch(self):
        self.cache = {"Fed cached fixture headline": "기존 번역 제목"}
        market = self.market([article("Fed cached fixture headline"),
                              article("Fed new fixture headline", link="https://publisher.example.test/new")])
        bloomberg = self.bloomberg([article("Global unselected fixture headline", link="https://publisher.example.test/unselected")])
        self.batch.assert_not_called(); self.save.assert_not_called()
        before = [facts(row) for row in market + bloomberg]
        self.generation({"Fed new fixture headline": "새 연준 검증 번역"})
        result = nh.collect_us_headlines(kr_headlines=market, bloomberg_rss=bloomberg, max_items=2)
        self.assertEqual(len(result), 2)
        self.batch.assert_called_once_with(["Fed new fixture headline"])
        self.assertEqual(market[1]["title_ko"], "새 연준 검증 번역")
        self.assertFalse(bloomberg[0].get("title_ko"))
        self.assertEqual([facts(row) for row in market + bloomberg], before)

    def test_us_writeback_reuses_only_exact_title_and_url_and_keeps_existing_market_translation(self):
        first = article("Global anchor fixture headline", composite_score=1)
        other_url = {**first, "link": "https://publisher.example.test/other"}
        other_title = article("Different global fixture headline", composite_score=0)
        existing = {**first, "title_ko": "원본 시장에 이미 있던 번역"}
        rows = [first, other_url, other_title, existing]
        before = [facts(row) for row in rows]
        self.generation({first["title"]: "새 합본 검증 번역"})
        result = nh.collect_us_headlines(bloomberg_rss=rows, max_items=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(first["title_ko"], "새 합본 검증 번역")
        self.assertFalse(other_url.get("title_ko")); self.assertFalse(other_title.get("title_ko"))
        self.assertEqual(existing["title_ko"], "원본 시장에 이미 있던 번역")
        self.assertEqual([facts(row) for row in rows], before)

    def test_us_korean_original_does_not_create_new_translation_calls(self):
        row = article("미국 한국어 원문 기사")
        self.cache = {row["title"]: "원문과 다른 번역"}
        before = facts(row)
        result = nh.collect_us_headlines(kr_headlines=[row])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], row["title"])
        self.assertEqual(facts(row), before)
        self.assertIn(row.get("title_ko"), (None, row["title"]))

    def test_us_model_unavailable_keeps_originals_and_does_not_save(self):
        row = article("Uncached US fixture headline")
        before = deepcopy(row)
        self.generation({}, save=False)
        result = nh.collect_us_headlines(bloomberg_rss=[row])
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0].get("title_ko"))
        self.assertEqual(row, before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
