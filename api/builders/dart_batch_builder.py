"""dart_batch_builder — KR universe DART fundamentals 주 1회 batch.

배경 (2026-05-10):
  메모리 결정 7 — DART 펀더멘털 갱신 주기 = 주 1회 (월). FUND-CHANGE 측정에서
  PBR/ROE/debt/op_margin median 0% (분기 의존). 매일 풀 갱신은 동일 데이터 반복 호출.

  현재 main.py:2700 의 DART fetch 는 30 candidates 에만 적용 (Phase 2-A 필터 *후*).
  wide_scan 의 5,000 raw 단계에는 미도달 → F-Score Δ + ROIC + GP/A trend 정량 불가.

  해결: 주 1회 (일요일 KST 22:00 = UTC 13:00) KR universe (KOSPI 700 + KOSDAQ 1,300 = ~2,000)
        DART batch fetch → data/dart_fundamentals_kr.json 적재.
        universe_scan_builder 가 fast path 로 stock dict 에 attach.

스케줄:
  - cron: 매주 일요일 KST 22:00 (UTC 13:00) — 주말 KRX 휴장 후 안정
  - 주 1회만 — KIS 토큰 / DART rate limit 부담 X
  - 산출: data/dart_fundamentals_kr.json
  - 직전 snapshot 보존 (이번 run 0건이면 file 덮어쓰기 X)

거짓말 트랩 정합 (feedback_data_collection_verification_mandatory):
  - try/finally + logged stderr 표식
  - silent skip 절대 금지
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_REPO_ROOT, "data", "dart_fundamentals_kr.json")


def _now_kst() -> datetime:
    return datetime.now(KST)


def _load_existing() -> Dict[str, Any]:
    if not os.path.isfile(OUTPUT_PATH):
        return {}
    try:
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _build_kr_universe_tickers() -> List[str]:
    """Phase 2-A KR universe builder 호출 → 6자리 ticker 리스트.

    universe_builder 가 주 1회 KRX OpenAPI K1 호출로 KR 시총 상위 + 코어 union 반환.
    DART fetch 대상은 KR 종목만 — KOSPI + KOSDAQ.
    """
    from api.config import UNIVERSE_RAMP_UP_STAGE
    from api.collectors.universe_builder import build_extended_universe

    stage = max(int(UNIVERSE_RAMP_UP_STAGE or 0), 500)
    kr_target = max(int(stage * 0.4), 100)  # KR 비중 40% (stock_filter 와 정합)
    # KRX OpenAPI 가 transient 로 빈 결과/예외 → 재시도. 1회 빈값이 dart_batch 를
    # kr_universe_empty exit 1 로 떨구던 false 실패 방지(진짜 다운이면 3회 다 빈값 → 여전히 loud).
    kr_entries: list = []
    for attempt in range(3):
        try:
            kr_entries = build_extended_universe("KR", target_size=kr_target, apply_hard_floor=True)
            if kr_entries:
                break
            sys.stderr.write(f"[dart_batch] KR universe 빈값 (시도 {attempt+1}/3) — 재시도\n")
        except Exception as e:
            sys.stderr.write(f"[dart_batch] KR universe build 실패 (시도 {attempt+1}/3): {e}\n")
        if attempt < 2:
            time.sleep(3 * (attempt + 1))
    return [str(e["ticker"]).zfill(6) for e in kr_entries if e.get("ticker")]


def _current_bsns_year() -> str:
    """DART 조회 사업연도 = 직전 연도 (연간보고서 3월 확정, collector 와 동일 규칙)."""
    return str(_now_kst().year - 1)


def _is_fresh_dart(rec: Any, bsns_year: str) -> bool:
    """직전 snapshot 의 종목 record 가 현 bsns_year DART 정식 데이터인가.

    연간보고서(reprt_code 11011)는 해당 연도 내 불변 → 재사용 정합(stale 아님).
    """
    return (
        isinstance(rec, dict)
        and str(rec.get("source", "")).startswith("DART")
        and str(rec.get("report_date", "")) == str(bsns_year)
        and (rec.get("total_assets") or 0) > 0
    )


def build() -> Dict[str, Any]:
    """KR universe DART 증분 fetch → snapshot dict.

    증분 (2026-06-06 fix): 연간 데이터는 해당 연도 불변이므로, 직전 snapshot 에 현
    bsns_year DART 정식 record 가 있는 종목은 재사용하고 누락분만 fetch. 매주 1874종목
    전체 재호출이 DART throttle(GH IP, 48s/콜)을 자초하던 문제 해소.
    실패 시에도 항상 dict 반환 (diagnostics 에 source 명시).
    """
    from api.collectors.dart_fundamentals import fetch_dart_fundamentals_batch

    now = _now_kst()
    started = time.time()
    error: str | None = None
    bsns_year = _current_bsns_year()

    tickers = _build_kr_universe_tickers()
    if not tickers:
        error = "kr_universe_empty"
        sys.stderr.write(f"[dart_batch] FAIL: {error}\n")

    # 증분: 직전 snapshot 에서 현 bsns_year DART 정식분 재사용, 누락분만 fetch.
    prev = _load_existing()
    prev_funds = prev.get("fundamentals") if isinstance(prev.get("fundamentals"), dict) else {}
    reuse: Dict[str, Dict] = {t: prev_funds[t] for t in tickers if _is_fresh_dart(prev_funds.get(t), bsns_year)}
    to_fetch = [t for t in tickers if t not in reuse]
    sys.stderr.write(
        f"[dart_batch] 증분: 재사용 {len(reuse)} / fetch 대상 {len(to_fetch)} (bsns_year={bsns_year})\n"
    )

    fetched: Dict[str, Dict] = {}
    if to_fetch:
        try:
            # max_workers 6 — throttle 압력 완화 (기존 10).
            fetched = fetch_dart_fundamentals_batch(to_fetch, max_workers=6, bsns_year=bsns_year) or {}
        except BaseException as e:
            error = f"{type(e).__name__}: {str(e)[:200]}"
            sys.stderr.write(f"[dart_batch] fetch 일부 실패 (graceful): {error}\n")

    fundamentals: Dict[str, Dict] = {**reuse, **fetched}

    elapsed = round(time.time() - started, 2)

    # 0건 fallback — 직전 snapshot 보존
    used_prev = False
    if not fundamentals and prev_funds:
        fundamentals = prev_funds
        used_prev = True
        sys.stderr.write(
            f"[dart_batch] used_prev=True (이번 run 0건, 직전 snapshot {len(fundamentals)}건)\n"
        )

    # source 별 카운트 (silent skip 차단)
    source_counts: Dict[str, int] = {}
    for f in fundamentals.values():
        src = f.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1

    diagnostics = {
        "ok": error is None and bool(fundamentals),
        "tickers_attempted": len(tickers),
        "reused_count": len(reuse),
        "fetched_count": len(fetched),
        "fundamentals_count": len(fundamentals),
        "source_counts": source_counts,
        "elapsed_s": elapsed,
        "used_prev_snapshot": used_prev,
        "bsns_year": bsns_year,
        "error": error,
    }

    return {
        "collected_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "fundamentals": fundamentals,
        "diagnostics": diagnostics,
        "schema_version": "v0",
    }


def _atomic_write(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, path)


_REPRT_END_MMDD = {"11013": "03-31", "11012": "06-30", "11014": "09-30", "11011": "12-31"}


def _quarter_end_iso(report_date, reprt_code, fetched_at: str) -> str:
    """진짜 분기 종료일 (YYYY-MM-DD) 산출.

    [WHY] 2026-05-20 fscore_delta 인프라 audit — 이전 = fetched_at[:10] (수집 날짜)
          설정되어 1867 종목 모두 quarter_end="2026-05-17". YoY find_yoy_prior(±30일)
          가 진짜 1년 전 분기 매칭 불가 = N 누적 의미 X.

    report_date format: "YYYY" 또는 "YYYY-MM-DD" 또는 None.
    reprt_code: "11013" 1Q / "11012" 반기 / "11014" 3Q / "11011" 연간 (기본).
    """
    rd = str(report_date) if report_date else ""
    if len(rd) >= 10 and rd[4] == "-" and rd[7] == "-":
        return rd[:10]
    if len(rd) == 4 and rd.isdigit():
        suffix = _REPRT_END_MMDD.get(str(reprt_code) if reprt_code else "11011", "12-31")
        return f"{rd}-{suffix}"
    return fetched_at[:10] if fetched_at else _now_kst().strftime("%Y-%m-%d")


def _append_quarterly_snapshots(snapshot: Dict[str, Any]) -> int:
    """F-Score Δ 시계열 누적 (2026-05-17 Perplexity Q1 인프라 prep, 5/20 quarter_end 정정).

    매주 dart_batch 결과를 data/dart_quarterly_snapshots.jsonl 에 append.
    api/utils/fscore_delta.py 의 load_quarterly_snapshots 가 ticker 별 YoY 비교.

    schema (jsonl 1줄):
        {ticker, quarter_end (진짜 분기 종료일 YYYY-MM-DD), reprt_code,
         roa, debt_ratio, current_ratio, gross_margin, asset_turnover, fetched_at}

    중복 누적 OK — load 시 (ticker + quarter_end) 별 최신 fetched_at 만 사용 (dedupe).
    """
    snapshots_path = os.path.join(
        os.path.dirname(OUTPUT_PATH), "dart_quarterly_snapshots.jsonl"
    )
    fundamentals = snapshot.get("fundamentals", {})
    fetched_at = snapshot.get("collected_at", "")
    written = 0
    try:
        with open(snapshots_path, "a", encoding="utf-8") as f:
            for ticker, fund in fundamentals.items():
                reprt_code = fund.get("reprt_code") or "11011"  # 연간 default
                quarter_end = _quarter_end_iso(fund.get("report_date"), reprt_code, fetched_at)
                entry = {
                    "ticker": ticker,
                    "quarter_end": quarter_end,
                    "reprt_code": reprt_code,
                    "fs_div": fund.get("fs_div"),
                    "roa": fund.get("roa"),
                    "debt_ratio": fund.get("debt_ratio"),
                    "current_ratio": fund.get("current_ratio"),
                    "gross_margin": fund.get("gross_margin") or fund.get("gross_margins"),
                    "asset_turnover": fund.get("asset_turnover"),
                    "operating_cashflow": fund.get("operating_cashflow"),
                    "net_income": fund.get("net_income"),
                    "fetched_at": fetched_at,
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                written += 1
        sys.stderr.write(
            f"[dart_batch] quarterly_snapshots appended={written} → {snapshots_path}\n"
        )
    except Exception as e:
        sys.stderr.write(f"[dart_batch] quarterly snapshot append fail: {e}\n")
    return written


# ── 전방 분기 refresh (backfill 의 leading edge) ─────────────────────────────
# backfill(dart_quarterly_backfill) = 과거 완료연도 일회성 소유. 전방 refresh = 당해년도~
# 최신 reportable 분기만 주간 재fetch → 새 분기 공시 자동 편입 + 정정 반영(dedup).
# 과거 확정 분기는 재fetch 안 함(backfill 영구 소유) → 주간 비용 = N 기간뿐.
# 공시 마감 lag: 분기/반기 45일, 연간 90일 (자본시장법) + 미제출 회피 버퍼 15일.
_FILING_LAG_DAYS = {"11013": 45, "11012": 45, "11014": 45, "11011": 90}
_FILING_BUFFER_DAYS = 15
# reprt: 연간(12-31) → 3Q(09-30) → 반기(06-30) → 1Q(03-31), 연내 최신순.
_REPRT_ORDER = [("12-31", "11011"), ("09-30", "11014"), ("06-30", "11012"), ("03-31", "11013")]


def _trailing_reportable_periods(n: int = 2, today: date = None) -> List[Dict[str, str]]:
    """오늘 기준 마감 지난 최신 reportable (year, reprt_code) 기간 N개 (최신순)."""
    today = today or _now_kst().date()
    out: List[Dict[str, str]] = []
    for y in range(today.year, today.year - 4, -1):
        for mmdd, code in _REPRT_ORDER:
            end = date(y, int(mmdd[:2]), int(mmdd[3:]))
            lag = _FILING_LAG_DAYS.get(code, 45) + _FILING_BUFFER_DAYS
            if end + timedelta(days=lag) <= today:
                out.append({"year": str(y), "reprt_code": code})
                if len(out) >= n:
                    return out
    return out


def refresh_forward_quarters(n: int = None) -> int:
    """당해년도~ 최신 reportable 분기 N개 재fetch → dart_quarterly_snapshots.jsonl append.
    DART 정식분(source DART* + total_assets>0)만 — yfinance fallback 은 분기추이 부적합.
    """
    from api.collectors.dart_fundamentals import fetch_dart_fundamentals_batch
    if n is None:
        n = int(os.environ.get("DART_FORWARD_QUARTERS_N", "2"))
    periods = _trailing_reportable_periods(n)
    if not periods:
        sys.stderr.write("[dart_forward] logged=True · reportable 기간 0 — skip\n")
        return 0
    tickers = _build_kr_universe_tickers()
    total = 0
    for prd in periods:
        funds = fetch_dart_fundamentals_batch(
            tickers, max_workers=6, bsns_year=prd["year"], reprt_code=prd["reprt_code"]
        ) or {}
        dart_funds = {
            tk: f for tk, f in funds.items()
            if str(f.get("source", "")).startswith("DART") and (f.get("total_assets") or 0) > 0
        }
        appended = _append_quarterly_snapshots({
            "collected_at": _now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            "fundamentals": dart_funds,
        }) if dart_funds else 0
        total += appended
        sys.stderr.write(
            f"[dart_forward] period year={prd['year']} reprt={prd['reprt_code']} "
            f"dart={len(dart_funds)}/{len(tickers)} appended={appended}\n"
        )
    sys.stderr.write(f"[dart_forward] logged=True · {len(periods)}기간 · appended_total={total}\n")
    return total


def main() -> int:
    snapshot = build()
    _atomic_write(OUTPUT_PATH, snapshot)
    diag = snapshot.get("diagnostics", {})
    sys.stderr.write(
        f"[dart_batch] snapshot OK at={snapshot.get('collected_at')} "
        f"tickers={diag.get('tickers_attempted')} fundamentals={diag.get('fundamentals_count')} "
        f"sources={diag.get('source_counts')} elapsed={diag.get('elapsed_s')}s "
        f"used_prev={diag.get('used_prev_snapshot')}\n"
    )
    # F-Score Δ 시계열 누적 (Perplexity Q1)
    _append_quarterly_snapshots(snapshot)
    # 편승 — data_pipeline_health 갱신 (별도 cron 추가 X)
    try:
        from api.observability.data_pipeline_health import write_data_pipeline_health
        write_data_pipeline_health()
    except Exception as _e:
        sys.stderr.write(f"[dart_batch] data_pipeline_health 갱신 실패(무시): {_e}\n")

    if not diag.get("ok"):
        sys.stderr.write(f"[dart_batch] FATAL — error={diag.get('error')}\n")
        return 1
    return 0


if __name__ == "__main__":
    if "--forward" in sys.argv:
        refresh_forward_quarters()
        sys.exit(0)
    sys.exit(main())
