"""E·C·B 세 수정의 회귀 가드 (2026-08-21).

E — 조인 재무요약이 `현금`(현금성자산) 만 싣던 것 → `유동성(현금+투자)` 병기 + 런웨이 분모 신고
C — `is_us_mode` 분기의 dedup 순서가 주석("신규 우선")과 반대라 stale 이 이기던 것
B — 반대 시장 레코드 통째 이월분이 등급·거시캡을 달고 오는데 신고가 없던 것

실측 배경:
  E: MRNA 2026-06-30 현금 $1,723M 인데 매도가능증권 유동 3,415 + 비유동 1,772 = **$6,910M**.
     연 소진 ~$2.5B 기준 런웨이 **8개월 ↔ 2.7년**. 판단이 통째로 갈린다.
  C: 최근 full run 3/3 이 scope=all 이라 잠복이었으나 `a0d6105f0` 로 full_us 부활.
  B: 8/20 `kr_decoupling_weak` 캡이 KOSPI −5.8% 때 붙어, +6% 로 뒤집힌 뒤에도 이월로
     살아남아 BUY 7건을 WATCH 로 덮었다.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ── E ────────────────────────────────────────────────────────
def _merge_liquidity(cash, inv_c, inv_nc):
    """us_filing_probe 의 유동성 합산 규칙 재현 — 기간말 일치분만 더한다."""
    if not cash:
        return None
    parts = [("현금성", float(cash["val"]))]
    for label, rec in (("투자(유동)", inv_c), ("투자(비유동)", inv_nc)):
        if rec and rec.get("end") == cash["end"]:
            parts.append((label, float(rec["val"])))
    if len(parts) == 1:
        return None
    return {"val": sum(v for _, v in parts), "end": cash["end"], "parts": parts}


def test_liquidity_sums_cash_and_investments():
    liq = _merge_liquidity(
        {"val": 1_723_000_000, "end": "2026-06-30"},
        {"val": 3_415_000_000, "end": "2026-06-30"},
        {"val": 1_772_000_000, "end": "2026-06-30"},
    )
    assert liq["val"] == 6_910_000_000, "MRNA 실측 합계와 불일치"
    assert len(liq["parts"]) == 3


def test_liquidity_refuses_period_mismatch():
    """🚨 기간말이 어긋난 값을 더하면 안 된다 — RCAT 사고와 같은 계열."""
    liq = _merge_liquidity(
        {"val": 1_723_000_000, "end": "2026-06-30"},
        {"val": 9_999_000_000, "end": "2021-07-31"},   # 5년 전 값
        None,
    )
    assert liq is None, "기간말 불일치 값이 합산됐다"


def test_liquidity_none_when_no_investments():
    assert _merge_liquidity({"val": 100, "end": "2026-06-30"}, None, None) is None


def test_probe_source_reports_runway_basis():
    """런웨이 분모가 무엇인지 산출물이 말해야 한다 (RULE 12 자기신고)."""
    src = (ROOT / "api" / "intelligence" / "us_filing_probe.py").read_text(encoding="utf-8")
    assert "유동성(현금+투자)" in src
    assert "_base_label" in src, "런웨이 분모 신고 변수가 사라졌다"
    assert "분모={_base_label}" in src, "런웨이 문자열에 분모 표기가 없다"
    assert "_INVEST_CURRENT_TAGS" in src and "_INVEST_NONCURRENT_TAGS" in src


# ── C ────────────────────────────────────────────────────────
def _dedupe(merged):
    seen, out = set(), []
    for r in merged:
        if r["ticker"] not in seen:
            seen.add(r["ticker"])
            out.append(r)
    return out


def test_dedupe_prefers_fresh_over_carried():
    """주석이 '신규 우선' 이라 선언한다 — 순서가 그것을 지켜야 한다."""
    fresh = {"ticker": "GOOGL", "price": 342.42, "_src": "new"}
    stale = {"ticker": "GOOGL", "price": 340.93, "_src": "kept"}
    out = _dedupe([fresh, stale])          # candidates + kept
    assert out[0]["_src"] == "new"
    # 반대 순서(수정 전)면 stale 이 이긴다 — 그게 결함이었다
    assert _dedupe([stale, fresh])[0]["_src"] == "kept"


def test_main_py_both_branches_put_candidates_first():
    """🚨 두 분기 모두 candidates 가 먼저여야 한다. is_us_mode 분기가 반대였다."""
    src = (ROOT / "api" / "main.py").read_text(encoding="utf-8")
    assert "merged = kept + candidates" not in src, (
        "is_us_mode 분기가 kept 를 먼저 놓는다 — dedup 에서 stale 이 이긴다"
    )
    assert src.count("merged = candidates + kept") == 2, (
        "두 분기 모두 candidates 우선이어야 한다"
    )


# ── B ────────────────────────────────────────────────────────
def test_main_py_stamps_carried_records():
    src = (ROOT / "api" / "main.py").read_text(encoding="utf-8")
    assert 'r["_carried"] = {' in src, "이월 자기신고 스탬프가 사라졌다"
    assert '"frozen_fields"' in src
    assert 'r.pop("_carried", None)' in src, (
        "재분석된 레코드의 옛 이월 스탬프를 지우지 않으면 stale 신고가 남는다"
    )


def _stamp(candidates, kept, updated_at):
    fresh = {r["ticker"] for r in candidates}
    n = 0
    for r in kept:
        if r["ticker"] in fresh:
            continue
        r["_carried"] = {"as_of": r.get("collected_at") or updated_at,
                         "reason": "opposite_market_scope"}
        n += 1
    for r in candidates:
        r.pop("_carried", None)
    return n


def test_carried_stamp_skips_tickers_that_were_reanalyzed():
    cands = [{"ticker": "AAPL"}]
    kept = [{"ticker": "AAPL"}, {"ticker": "MSFT"}]
    n = _stamp(cands, kept, "2026-08-21T00:00:00+09:00")
    assert n == 1, "신규로 재분석된 티커까지 이월로 신고했다"
    assert "_carried" not in kept[0]
    assert kept[1]["_carried"]["reason"] == "opposite_market_scope"


def test_reanalyzed_record_drops_old_carried_stamp():
    cands = [{"ticker": "AAPL", "_carried": {"as_of": "옛날"}}]
    _stamp(cands, [], "2026-08-21T00:00:00+09:00")
    assert "_carried" not in cands[0], "재분석됐는데 옛 이월 스탬프가 남았다"
