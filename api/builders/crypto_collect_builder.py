"""crypto_collect_builder — TIDE 크립토 공개 표면 데이터 (별도 cron).

산출 3종 (전부 공개 Blob publish 대상, 사실만 — RULE 7 점수 비노출):
  - data/crypto_macro.json     : 레짐센서 5종(공포탐욕/펀딩/김프/상관/스테이블) — crypto_macro.py
  - data/crypto_universe.json  : 코인 히트맵용 시총+sparkline (CoinGecko 50) — crypto_universe.py
  - data/crypto_news.json      : 코인 뉴스 팩트 헤드라인 (RSS) — crypto_news.py

거짓말 트랩 정합 (feedback_data_collection_verification_mandatory):
  - try/finally + stderr 표식, silent skip 금지, 직전 산출 보존(last-good)
  - feedback_macro_timestamp_policy: collected_at + source 메타
RULE 1 무관(KIS 비참조), RULE 6(뉴스=헤드라인 팩트만), RULE 8(신규 cron N=2 audit).
외부 API 스키마는 실호출 검증 완료(Bybit/OKX/CoinGecko/RSS, feedback_real_call_over_llm_consensus).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(_REPO_ROOT, "data")
MACRO_PATH = os.path.join(DATA_DIR, "crypto_macro.json")
UNIVERSE_PATH = os.path.join(DATA_DIR, "crypto_universe.json")
NEWS_PATH = os.path.join(DATA_DIR, "crypto_news.json")
DEFILLAMA_PATH = os.path.join(DATA_DIR, "crypto_defillama.json")
GOVERNANCE_PATH = os.path.join(DATA_DIR, "crypto_governance.json")
ETF_FLOW_PATH = os.path.join(DATA_DIR, "crypto_etf_flow.json")

KST = timezone(timedelta(hours=9))


def _now_kst_iso() -> str:
    return datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _safe_call(fn: Callable[[], Any], name: str, timeout_s: int) -> tuple[Any, str | None]:
    """ThreadPoolExecutor + timeout. fail 시 (None, reason). silent skip 방지(stderr 표식)."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn)
    outcome: str | None = None
    result: Any = None
    try:
        result = future.result(timeout=timeout_s)
        if result is None:
            outcome = "returned_none"
    except FutTimeout:
        outcome = f"timeout_{timeout_s}s"
    except Exception as e:  # noqa: BLE001
        outcome = f"exception:{type(e).__name__}:{str(e)[:120]}"
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
        ok = result is not None and outcome is None
        sys.stderr.write(f"[crypto_collect] collector={name} ok={ok} outcome={outcome or 'success'}\n")
    return (result, outcome)


def _load_existing(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_write(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ── 1. 레짐센서 (crypto_macro.json) ──
def build_macro() -> tuple[Dict[str, Any], bool]:
    """crypto_macro.py 5센서 → crypto_macro.json 페이로드. (payload, ok) 반환.
    전체 fail(ok_count 0) 시 직전 산출 보존."""
    from api.collectors.crypto_macro import collect_crypto_macro

    res, err = _safe_call(collect_crypto_macro, "crypto_macro", timeout_s=45)
    ok_count = (res or {}).get("ok_count", 0) if isinstance(res, dict) else 0
    if not res or ok_count == 0:
        prev = _load_existing(MACRO_PATH)
        if prev:
            prev.setdefault("diagnostics", {})["used_prev_snapshot"] = True
            prev["diagnostics"]["last_attempt_at"] = _now_kst_iso()
            prev["diagnostics"]["last_error"] = err or "ok_count_0"
            return prev, False
        return {"collected_at": _now_kst_iso(), "schema_version": "v0", "available": False,
                "ok_count": 0, "total": 5, "diagnostics": {"error": err or "ok_count_0"}}, False
    payload = dict(res)
    payload["collected_at"] = _now_kst_iso()
    payload["schema_version"] = "v0"
    payload["diagnostics"] = {"ok_count": ok_count, "used_prev_snapshot": False}
    return payload, True


# ── 2. 코인 universe (crypto_universe.json) ──
def build_universe() -> tuple[Dict[str, Any], bool]:
    """CoinGecko 시총 상위 50 → crypto_universe.json. fail 시 직전 산출 보존."""
    from api.collectors.crypto_universe import collect_crypto_universe

    coins, err = _safe_call(lambda: collect_crypto_universe(50), "crypto_universe", timeout_s=20)
    if not coins:
        prev = _load_existing(UNIVERSE_PATH)
        if prev and prev.get("coins"):
            prev.setdefault("diagnostics", {})["used_prev_snapshot"] = True
            prev["diagnostics"]["last_error"] = err or "empty"
            return prev, False
        return {"collected_at": _now_kst_iso(), "schema_version": "v0", "source": "coingecko",
                "coins": [], "diagnostics": {"error": err or "empty"}}, False
    return {
        "collected_at": _now_kst_iso(),
        "schema_version": "v0",
        "source": "coingecko",
        "coins": coins,
        "diagnostics": {"count": len(coins), "used_prev_snapshot": False},
    }, True


# ── 3. 코인 뉴스 (crypto_news.json) ──
def build_news() -> tuple[Dict[str, Any], bool]:
    """크립토 RSS 헤드라인(팩트만) → crypto_news.json. fail 시 직전 산출 보존."""
    from api.collectors.crypto_news import collect_crypto_news

    items, err = _safe_call(lambda: collect_crypto_news(20), "crypto_news", timeout_s=30)
    if not items:
        prev = _load_existing(NEWS_PATH)
        if prev and prev.get("items"):
            prev.setdefault("diagnostics", {})["used_prev_snapshot"] = True
            prev["diagnostics"]["last_error"] = err or "empty"
            return prev, False
        return {"collected_at": _now_kst_iso(), "schema_version": "v0",
                "items": [], "diagnostics": {"error": err or "empty"}}, False
    return {
        "collected_at": _now_kst_iso(),
        "schema_version": "v0",
        "items": items,
        "diagnostics": {"count": len(items), "used_prev_snapshot": False},
    }, True


# ── 4. 프로토콜 펀더멘털 (crypto_defillama.json) ──
def build_defillama() -> tuple[Dict[str, Any], bool]:
    """DefiLlama 무료 API → 프로토콜 매출/수수료 + 체인 TVL (코인별 펀더멘털 = 주식 재무 대응).
    fail 시 직전 산출 보존."""
    from api.collectors.crypto_defillama import collect_crypto_defillama

    res, err = _safe_call(lambda: collect_crypto_defillama(25), "crypto_defillama", timeout_s=30)
    ok = bool(res and isinstance(res, dict) and res.get("ok"))
    if not ok:
        prev = _load_existing(DEFILLAMA_PATH)
        if prev and prev.get("protocols"):
            prev.setdefault("diagnostics", {})["used_prev_snapshot"] = True
            prev["diagnostics"]["last_error"] = err or (res or {}).get("error") or "not_ok"
            return prev, False
        return {"collected_at": _now_kst_iso(), "schema_version": "v0", "source": "defillama",
                "protocols": [], "chains": [], "diagnostics": {"error": err or (res or {}).get("error") or "not_ok"}}, False
    payload = dict(res)
    payload["collected_at"] = _now_kst_iso()
    payload["schema_version"] = "v0"
    payload["diagnostics"] = {"protocols": len(payload.get("protocols") or []), "used_prev_snapshot": False}
    return payload, True


# ── 5. DAO 거버넌스 (crypto_governance.json) ──
def build_governance() -> tuple[Dict[str, Any], bool]:
    """Snapshot GraphQL → 주요 DAO 거버넌스 제안/투표 (코인판 공시). fail 시 직전 산출 보존.
    ok=True + proposals 0건(현재 active 없음)도 정상 — fail 아님."""
    from api.collectors.crypto_governance import collect_crypto_governance

    res, err = _safe_call(lambda: collect_crypto_governance(25), "crypto_governance", timeout_s=25)
    ok = bool(res and isinstance(res, dict) and res.get("ok"))
    if not ok:
        prev = _load_existing(GOVERNANCE_PATH)
        if prev and prev.get("proposals"):
            prev.setdefault("diagnostics", {})["used_prev_snapshot"] = True
            prev["diagnostics"]["last_error"] = err or (res or {}).get("error") or "not_ok"
            return prev, False
        return {"collected_at": _now_kst_iso(), "schema_version": "v0", "source": "snapshot",
                "proposals": [], "diagnostics": {"error": err or (res or {}).get("error") or "not_ok"}}, False
    payload = dict(res)
    payload["collected_at"] = _now_kst_iso()
    payload["schema_version"] = "v0"
    payload["diagnostics"] = {"proposals": len(payload.get("proposals") or []), "used_prev_snapshot": False}
    return payload, True


# ── 6. 현물 ETF 자금흐름 (crypto_etf_flow.json) ──
def build_etf_flow() -> tuple[Dict[str, Any], bool]:
    """SoSoValue → BTC/ETH 현물 ETF net inflow + AUM (주식 ETFFlow 대응).
    SOSOVALUE_API_KEY 미등록 시 ok=False(no_api_key) → graceful. fail 시 직전 산출 보존."""
    from api.collectors.crypto_etf_flow import collect_crypto_etf_flow

    res, err = _safe_call(collect_crypto_etf_flow, "crypto_etf_flow", timeout_s=25)
    ok = bool(res and isinstance(res, dict) and res.get("ok"))
    if not ok:
        prev = _load_existing(ETF_FLOW_PATH)
        if prev and (prev.get("btc") or prev.get("eth")):
            prev.setdefault("diagnostics", {})["used_prev_snapshot"] = True
            prev["diagnostics"]["last_error"] = err or (res or {}).get("error") or "not_ok"
            return prev, False
        return {"collected_at": _now_kst_iso(), "schema_version": "v0", "source": "sosovalue",
                "btc": None, "eth": None,
                "diagnostics": {"error": err or (res or {}).get("error") or "not_ok"}}, False
    payload = dict(res)
    payload["collected_at"] = _now_kst_iso()
    payload["schema_version"] = "v0"
    payload["diagnostics"] = {"ok_count": payload.get("ok_count", 0), "used_prev_snapshot": False}
    return payload, True


def main() -> int:
    started = time.time()
    results = {}

    macro, macro_ok = build_macro()
    _atomic_write(MACRO_PATH, macro)
    results["macro"] = macro_ok

    universe, uni_ok = build_universe()
    _atomic_write(UNIVERSE_PATH, universe)
    results["universe"] = uni_ok

    news, news_ok = build_news()
    _atomic_write(NEWS_PATH, news)
    results["news"] = news_ok

    defillama, defillama_ok = build_defillama()
    _atomic_write(DEFILLAMA_PATH, defillama)
    results["defillama"] = defillama_ok

    governance, gov_ok = build_governance()
    _atomic_write(GOVERNANCE_PATH, governance)
    results["governance"] = gov_ok

    etf_flow, etf_ok = build_etf_flow()
    _atomic_write(ETF_FLOW_PATH, etf_flow)
    results["etf_flow"] = etf_ok

    elapsed = round(time.time() - started, 2)
    sys.stderr.write(f"[crypto_collect] 적재 완료 {results} elapsed={elapsed}s\n")

    if not any(results.values()):
        sys.stderr.write("[crypto_collect] FATAL — 전체 collector fail\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
