"""ESTATE user watch complexes — 단위 테스트.

검증:
  ① endpoint normalize_apt_name (clustering 정합)
  ② builder _dedupe_watchlist (V0_WATCHLIST + user union, key 중복 제거)
  ③ builder _fetch_user_watch_complexes (env 부재 시 [])
  ④ migration 014 sql 문법 정합 (CREATE / RLS / index 키워드)
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_endpoint(monkeypatch):
    """endpoint module 동적 로드 — vercel-api `api.supabase_client` / `api.cors_helper` mock 주입.

    project root `api/` 패키지가 sys.path 우선이라 vercel-api 의 동명 패키지 import 충돌.
    필요한 dependency 만 stub 으로 inject.
    """
    import types
    # api 패키지는 project root 가 잡고 있음 — 누락 submodule 만 stub 추가
    import api as _api_pkg  # project root api
    if not hasattr(_api_pkg, "supabase_client"):
        sb_stub = types.ModuleType("api.supabase_client")
        sb_stub.verify_jwt = lambda jwt: None
        sb_stub.select = lambda *a, **kw: []
        sb_stub.insert = lambda *a, **kw: {}
        sb_stub.update = lambda *a, **kw: []
        sb_stub.delete = lambda *a, **kw: None
        monkeypatch.setitem(sys.modules, "api.supabase_client", sb_stub)
        monkeypatch.setattr(_api_pkg, "supabase_client", sb_stub, raising=False)
    if not hasattr(_api_pkg, "cors_helper"):
        cors_stub = types.ModuleType("api.cors_helper")
        cors_stub.resolve_origin = lambda origin: ""
        monkeypatch.setitem(sys.modules, "api.cors_helper", cors_stub)
        monkeypatch.setattr(_api_pkg, "cors_helper", cors_stub, raising=False)

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(repo, "vercel-api", "api", "estate_watch_complexes.py")
    spec = importlib.util.spec_from_file_location("ep_estate_watch_complexes", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ep_estate_watch_complexes"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestNormalizeAptName:
    @pytest.mark.parametrize("raw,expected", [
        ("래미안 강남(1단지)", "래미안강남"),
        ("은마", "은마"),
        ("도곡렉슬·1단지", "도곡렉슬"),
        ("강남 푸르지오 [104동]", "강남푸르지오"),
        ("힐스테이트2단지", "힐스테이트"),
    ])
    def test_normalize_matches_clustering(self, raw, expected, monkeypatch):
        ep = _load_endpoint(monkeypatch)
        assert ep._normalize_apt_name(raw) == expected

    def test_empty(self, monkeypatch):
        ep = _load_endpoint(monkeypatch)
        assert ep._normalize_apt_name("") == ""
        assert ep._normalize_apt_name(None) == ""


class TestEndpointConstants:
    def test_seoul_25(self, monkeypatch):
        ep = _load_endpoint(monkeypatch)
        assert len(ep.SEOUL_25) == 25
        assert "강남구" in ep.SEOUL_25

    def test_redev_stages_6(self, monkeypatch):
        ep = _load_endpoint(monkeypatch)
        assert len(ep.VALID_REDEV_STAGES) == 6
        assert "management_plan" in ep.VALID_REDEV_STAGES

    def test_project_types_2(self, monkeypatch):
        ep = _load_endpoint(monkeypatch)
        assert ep.VALID_PROJECT_TYPES == frozenset(["reconstruction", "redevelopment"])


class TestBuilderDedupe:
    def test_v0_only_no_user(self):
        from api.builders import estate_brain_builder as bld
        out = bld._dedupe_watchlist(bld.V0_WATCHLIST, [])
        assert len(out) == len(bld.V0_WATCHLIST)
        # V0_WATCHLIST 그대로 반환
        assert all("price_won_mock" in c for c in out)

    def test_user_complex_added(self):
        from api.builders import estate_brain_builder as bld
        user = [{
            "gu": "강남구", "dong": "도곡동", "apt": "도곡렉슬",
            "apt_normalized": "도곡렉슬", "build_year": 2006,
            "project_type": None, "redev_stage": None,
            "months_in_stage": 0, "valuation_pending": False,
            "subscription_announced": False,
        }]
        out = bld._dedupe_watchlist(bld.V0_WATCHLIST, user)
        assert len(out) == len(bld.V0_WATCHLIST) + 1
        new_item = out[-1]
        assert new_item["complex_id"] == "강남구_도곡동_도곡렉슬_2006"
        assert new_item["price_won_mock"] is None  # 사용자 등록 = 가격 mock 없음
        assert new_item["_source"] == "user_watchlist"

    def test_user_dup_with_v0_skipped(self):
        from api.builders import estate_brain_builder as bld
        # V0_WATCHLIST 의 첫 단지 = 강남구 대치동 은마 1979
        v0_first = bld.V0_WATCHLIST[0]
        user = [{
            "gu": v0_first["gu"], "dong": v0_first["dong"],
            "apt": v0_first["apt"],
            "apt_normalized": v0_first["apt"].replace(" ", ""),
            "build_year": v0_first["build_year"],
        }]
        out = bld._dedupe_watchlist(bld.V0_WATCHLIST, user)
        # V0 만 있고 사용자 중복 제거됨
        assert len(out) == len(bld.V0_WATCHLIST)

    def test_user_with_redev(self):
        from api.builders import estate_brain_builder as bld
        user = [{
            "gu": "송파구", "dong": "신천동", "apt": "신천파크리오",
            "apt_normalized": "신천파크리오", "build_year": 2008,
            "project_type": "reconstruction", "redev_stage": "union_setup",
            "months_in_stage": 6,
            "valuation_pending": True, "subscription_announced": False,
        }]
        out = bld._dedupe_watchlist(bld.V0_WATCHLIST, user)
        added = out[-1]
        assert added["redev"] is not None
        assert added["redev"]["stage"] == "union_setup"
        assert added["redev"]["type"] == "reconstruction"
        assert added["redev"]["valuation_pending"] is True


class TestFetchUserWatchComplexes:
    def test_no_supabase_env_returns_empty(self, monkeypatch):
        from api.builders import estate_brain_builder as bld
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        assert bld._fetch_user_watch_complexes() == []


class TestMigrationSql:
    def test_file_exists(self):
        path = _REPO_ROOT / "supabase" / "migrations" / "014_estate_user_watch_complexes.sql"
        assert path.exists()

    def test_required_keywords(self):
        path = _REPO_ROOT / "supabase" / "migrations" / "014_estate_user_watch_complexes.sql"
        sql = path.read_text(encoding="utf-8")
        for kw in [
            "CREATE TABLE IF NOT EXISTS estate_user_watch_complexes",
            "user_id",
            "gu",
            "apt_normalized",
            "build_year",
            "redev_stage",
            "ENABLE ROW LEVEL SECURITY",
            "CREATE POLICY",
            "auth.uid() = user_id",
            "CREATE UNIQUE INDEX",
        ]:
            assert kw in sql, f"missing: {kw}"

    def test_no_self_eXISTS_subquery(self):
        # feedback_supabase_rls_no_self_subquery 정합 — 같은 테이블 EXISTS 회귀 X
        path = _REPO_ROOT / "supabase" / "migrations" / "014_estate_user_watch_complexes.sql"
        sql = path.read_text(encoding="utf-8")
        # CREATE POLICY 안에 같은 테이블 EXISTS 가 없어야 함
        assert "FROM estate_user_watch_complexes" not in sql or \
               "EXISTS (SELECT 1 FROM estate_user_watch_complexes" not in sql


class TestClassifyRedevOrNone:
    """endpoint `_classify_redev_or_none` (estate_brain.classify_redevelopment_stage 래퍼)."""

    def test_full_input_returns_classification(self, monkeypatch):
        ep = _load_endpoint(monkeypatch)
        out = ep._classify_redev_or_none({
            "redev_stage": "management_plan",
            "project_type": "redevelopment",
            "months_in_stage": 4,
            "valuation_pending": False,
            "subscription_announced": True,
        })
        assert out is not None
        assert out["stage"] == "management_plan"
        assert out["stage_label_ko"] == "관리처분 인가"
        assert out["months_in_stage"] == 4
        assert "months_to_next_stage_estimated" in out
        assert out["monitoring"]["general_subscription_announced"] is True

    def test_missing_redev_stage_returns_none(self, monkeypatch):
        ep = _load_endpoint(monkeypatch)
        assert ep._classify_redev_or_none({
            "redev_stage": None, "project_type": "redevelopment",
        }) is None

    def test_missing_project_type_returns_none(self, monkeypatch):
        ep = _load_endpoint(monkeypatch)
        assert ep._classify_redev_or_none({
            "redev_stage": "union_setup", "project_type": None,
        }) is None

    def test_invalid_stage_returns_none(self, monkeypatch):
        """classify_redevelopment_stage 가 None 반환 시 (unknown enum) passthrough."""
        ep = _load_endpoint(monkeypatch)
        assert ep._classify_redev_or_none({
            "redev_stage": "not_a_real_stage",
            "project_type": "reconstruction",
        }) is None

    def test_months_in_stage_int_conversion(self, monkeypatch):
        """str months_in_stage (실수로 string 박힌 row) → int 변환."""
        ep = _load_endpoint(monkeypatch)
        out = ep._classify_redev_or_none({
            "redev_stage": "union_setup",
            "project_type": "reconstruction",
            "months_in_stage": "12",  # string
        })
        assert out is not None
        assert out["months_in_stage"] == 12


class TestBuildIntegration:
    def test_build_uses_full_watchlist(self):
        from api.builders import estate_brain_builder as bld
        from api.intelligence import estate_brain_backtest as bt  # noqa
        # SUPABASE env 없음 → user 등록 0 → V0_WATCHLIST 만
        payload = bld.build(_modules={}, _ecos=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock())
        assert payload["diagnostics"]["watchlist_size"] == len(bld.V0_WATCHLIST)
        assert payload["diagnostics"]["watchlist_v0_hardcoded_count"] == len(bld.V0_WATCHLIST)
        assert payload["diagnostics"]["watchlist_user_count"] == 0
