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
    tickers = [str(e["ticker"]).zfill(6) for e in kr_entries if e.get("ticker")]

    # 🚨 2026-08-22 — 발행 유니버스와 union. 두 유니버스가 어긋나 결손이 났다.
    #   실측: 수집 대상 1,611 vs 사이트 노출(stock_report_public) 1,790 → **179종목이 시도조차 안 됨**.
    #   그 결과 financials 채움율 80.2%, 미보유 355종목. 그중 '일반' 339 중 332(98%)는
    #   fin_series(재무 시계열)를 이미 갖고 있었다 — 데이터 부재가 아니라 **대상 목록 누락**이다.
    #   미수집 10종목을 DART 에 직접 물어보니 **10/10 존재**(계정 98~195행). 소스는 충분했다.
    #   같은 계열 재발 = 2026-08-09 중소형주 채움(ALL_STOCKS 45 하드코딩·pool 20).
    #     수집기 유니버스가 발행 유니버스보다 좁은 구조가 반복된다 → union 으로 구조적으로 막는다.
    #   비용: DART 호출 +179 (일 20K 한도의 0.9%) · 런타임 +~20초. reuse 캐시가 있어 2회차부턴 더 적다.
    try:
        pub = os.path.join(_REPO_ROOT, "data", "stock_report_public.json")
        with open(pub, "r", encoding="utf-8") as f:
            extra = [str(x.get("ticker") or "").zfill(6)
                     for x in (json.load(f).get("stocks") or [])
                     if str(x.get("ticker") or "").isdigit()]
        before = len(tickers)
        tickers = sorted(set(tickers) | set(extra))
        if len(tickers) > before:
            sys.stderr.write(f"[dart_batch] 발행 유니버스 union +{len(tickers)-before} "
                             f"({before} -> {len(tickers)})\n")
    except Exception as e:  # noqa: BLE001
        # 🚨 union 실패는 치명이 아니다 — 기존 유니버스로 계속 간다(결손이 늘 뿐 새로 깨지지 않음).
        sys.stderr.write(f"[dart_batch] 발행 유니버스 union 실패(무시): {e!r}\n")
    return tickers


def _current_bsns_year() -> str:
    """DART 조회 사업연도 = 직전 연도 (연간보고서 3월 확정, collector 와 동일 규칙)."""
    return str(_now_kst().year - 1)


def _is_fresh_dart(rec: Any, bsns_year: str) -> bool:
    """직전 snapshot 의 종목 record 가 현 bsns_year DART 정식 데이터인가.

    연간보고서(reprt_code 11011)는 해당 연도 내 불변 → 재사용 정합(stale 아님).
    단, 재무상태표는 있는데 현금흐름 3종이 전부 0 = CF 파싱 미스 신호(정상 기업은 CF 존재) →
    stale 취급해 재추출 강제. CF account_id 매칭 fix(2026-07) 를 기존 0값 record 에 소급 반영하는 경로.
    """
    if not (
        isinstance(rec, dict)
        and str(rec.get("source", "")).startswith("DART")
        and str(rec.get("report_date", "")) == str(bsns_year)
        and (rec.get("total_assets") or 0) > 0
    ):
        return False
    # 자산 有 · 영업/투자/재무 현금흐름 전부 0 = 파싱 미스 → 재추출(수정 파서가 소급 채움)
    if not (
        (rec.get("operating_cashflow") or 0)
        or (rec.get("investing_cashflow") or 0)
        or (rec.get("financing_cashflow") or 0)
    ):
        return False
    # 손익상세(2026-05-20 확장: sga/finance/income_tax) KEY 부재 = 확장 이전 수집 → 재추출
    if "income_tax" not in rec or "sga" not in rec:
        return False
    # net_income=0 인데 법인세차감전(pretax)!=0 = 적자기업 순이익 클램프/라벨 미스 잔재 → 재추출
    if (rec.get("net_income") or 0) == 0 and (rec.get("pretax_income") or 0) != 0:
        return False
    # op 오파싱 신호: 매출 큰데 영업이익이 극소(EPS/중단영업 오치환 꼴)/0 = 구 파서 오염 → 재추출
    #   (2026-07 op account_id 승격 소급 — LGES op 5,287원·GS 부호역전류)
    _rev = rec.get("revenue") or 0
    if _rev > 1e10 and abs(rec.get("operating_profit") or 0) < 1e6:
        return False
    # revenue 오파싱 신호: 자산 큰데 매출 0 = top-line '매출'(ifrs-full_Revenue) 누락 → 재추출(LG화학류)
    if (rec.get("total_assets") or 0) > 1e11 and _rev == 0:
        return False
    return True


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
    # 🚨 2026-08-07 — 산출 불가 시 **수집일을 쓰지 않는다**(빈 문자열 반환).
    #   5/20 에 같은 결함을 한 번 고쳤는데(1,867건) 이 폴백이 남아 계속 오염을 생산했다:
    #   실측 2026-06-07 298건 · 07-24 96건 · 08-02 90건 = 전부 수집일.
    #   가짜 분기말은 결측보다 나쁘다 — YoY 조회(±30일)를 빗나가게 해 델타 산출을
    #   통째로 막는다(KR 추천 23종 중 22종이 no_prior 였다).
    #   caller 가 빈 값이면 그 행을 기록하지 않는다.
    return ""


def _append_quarterly_snapshots(snapshot: Dict[str, Any]) -> int:
    """F-Score Δ 시계열 누적 (2026-05-17 Perplexity Q1 인프라 prep, 5/20 quarter_end 정정).

    매주 dart_batch 결과를 data/dart_quarterly_snapshots.jsonl 에 append.
    api/utils/fscore_delta.py 의 load_quarterly_snapshots 가 ticker 별 YoY 비교.

    schema (jsonl 1줄):
        {ticker, quarter_end (진짜 분기 종료일 YYYY-MM-DD), reprt_code, fs_div,
         roa, debt_ratio, current_ratio, gross_margin, asset_turnover,
         revenue(8/19 추가), operating_profit(8/22 추가), operating_cashflow, net_income,
         fetched_at}
    🚨 이 목록이 **우리가 버리지 않기로 한 것의 명세**다. 수집기(dart_fundamentals)는
    이보다 훨씬 많이 파싱한다 — 필요해지면 여기 추가하고 재수집한다. 두 번 같은 자리에서
    필드를 버렸다(revenue 8/19 · operating_profit 8/22).

    중복 누적 OK — load 시 (ticker + quarter_end) 별 최신 fetched_at 만 사용 (dedupe).
    """
    snapshots_path = os.path.join(
        os.path.dirname(OUTPUT_PATH), "dart_quarterly_snapshots.jsonl"
    )
    fundamentals = snapshot.get("fundamentals", {})
    fetched_at = snapshot.get("collected_at", "")
    written = 0
    skipped_no_qend = 0
    try:
        with open(snapshots_path, "a", encoding="utf-8") as f:
            for ticker, fund in fundamentals.items():
                reprt_code = fund.get("reprt_code") or "11011"  # 연간 default
                quarter_end = _quarter_end_iso(fund.get("report_date"), reprt_code, fetched_at)
                if not quarter_end:
                    skipped_no_qend += 1
                    continue        # 분기말 미산출 = 시계열에 넣지 않는다(가짜 날짜 금지)
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
                    # 🚨 2026-08-19 — revenue 를 싣는다(PM 승인 "2Q 보강 배선").
                    #   수집기가 이미 파싱해 asset_turnover=rev/ta 까지 쓰고도 버리던 값이라
                    #   **추가 API 호출 0**. 이게 없어서 revenue_acceleration 의 2Q 연속가속
                    #   보강이 448/448 전량 미작동이었다(설계된 방어가 통째로 죽어 있었다).
                    #   소비 = api/utils/quarterly_revenue.build_series
                    "revenue": fund.get("revenue"),
                    # 🚨 2026-08-22 — operating_profit 을 싣는다. **추가 API 호출 0** (같은 이유).
                    #   실측 155,228행 중 operating_profit **0건**이었다. 수집기는 138행에서
                    #   `dart_OperatingIncomeLoss` 를 이미 파싱하고 209행에서 쓰기까지 하는데
                    #   스냅샷에만 안 실렸다 — 8/19 revenue 수리와 **정확히 같은 자리**다.
                    #   🚨 왜 치명적인가: net_income 은 98.8% 채워져 있지만 **본업을 못 본다.**
                    #   실사례 021820(세원정공) — 연간 순이익 488억 중 지분법 230 + 금융수익 135
                    #   이라 영업이익은 170억이고, 최근 분기는 **−6.7억 적자**다. 순이익만 보면
                    #   "PER 2 의 초저평가" 로 읽히고 적자 전환이 안 보인다.
                    "operating_profit": fund.get("operating_profit"),
                    "operating_cashflow": fund.get("operating_cashflow"),
                    "net_income": fund.get("net_income"),
                    "fetched_at": fetched_at,
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                written += 1
        sys.stderr.write(
            f"[dart_batch] quarterly_snapshots appended={written}"
            + (f" · 분기말 미산출 skip={skipped_no_qend}" if skipped_no_qend else "")
            + f" → {snapshots_path}\n"
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
