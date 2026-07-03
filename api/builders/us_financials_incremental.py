"""us_financials_incremental — 미장 재무 이벤트 기반 증분 갱신 (2026-07-04 신선도 스프린트).

배경: 미장 재무 풀 리프레시 = 월 1회 cron → 어닝 시즌 최대 한 달 지연 (PM 지적 "신선도 치명적이지 않나").
해법: EDGAR daily master index(일 1~수 요청, 전 시장 공시 목록)에서 10-Q/10-K 신규 제출 CIK 를 감지 →
  우리 유니버스(_summary + _summary_smallcap CIK) 교집합 종목만 재수집 → 리포트/분기 재빌드.
  재무 신선도: 월 단위 → 공시 다음 날 (이벤트 기반).

파이프라인:
  1. state(data/metadata/us_fin_incremental_state.json) 이후 영업일들의 master.idx fetch (lookback ≤7일)
  2. form ∈ {10-K,10-Q,10-K/A,10-Q/A} 행 → CIK → 유니버스 ticker 매핑
  3. run 캡(기본 60종목) 내 us_financials_builder --ticker 재수집 (부분 실행 = _summary 병합 가드 완비)
  4. 성공 시 state 전진. 리포트 재빌드는 워크플로 후속 step (빌더 재사용)

RULE 7 = 수집 사실만. KIS/DART 무관. EDGAR = 일일 쿼터 없음(정중 throttle).
usage: python -m api.builders.us_financials_incremental [--cap N] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA = os.path.join(_ROOT, "data")
STATE_PATH = os.path.join(_DATA, "metadata", "us_fin_incremental_state.json")
EARN_PATTERN_PATH = os.path.join(_DATA, "us_earnings_pattern.json")
PATTERN_KEEP = 10
SUMMARY_PATHS = [
    os.path.join(_DATA, "us_financials", "_summary.json"),
    os.path.join(_DATA, "us_financials", "_summary_smallcap.json"),
]
SEC_USER_AGENT = "VERITY gywns0126@gmail.com"
TARGET_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A"}
LOOKBACK_MAX_DAYS = 7      # state 유실/장기 중단 시 폭주 방지
DEFAULT_CAP = 60           # run 당 재수집 종목 상한 (어닝 피크 방어 — 잔여는 다음 run이 이어감)
IDX_TIMEOUT = 20
THROTTLE_SEC = 0.4


def _quarter(d: date) -> int:
    return (d.month - 1) // 3 + 1


def _idx_url(d: date) -> str:
    return (f"https://www.sec.gov/Archives/edgar/daily-index/{d.year}/QTR{_quarter(d)}/"
            f"master.{d.strftime('%Y%m%d')}.idx")


def _load_state() -> Dict[str, Any]:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(st: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_PATH)


def _universe_cik_map() -> Dict[int, str]:
    """유니버스 CIK → ticker (sp1500 + smallcap _summary rows)."""
    out: Dict[int, str] = {}
    for p in SUMMARY_PATHS:
        try:
            with open(p, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        for r in (doc.get("rows") or []):
            cik, tk = r.get("cik"), r.get("ticker")
            if cik is None or not tk:
                continue
            try:
                out[int(cik)] = str(tk)
            except (TypeError, ValueError):
                continue
    return out


def _fetch_day_filers(d: date) -> Optional[List[Tuple[int, str]]]:
    """해당 일 master.idx → [(CIK, form)] (10-K/10-Q). 인덱스 미발행(주말·휴장·미완성) = None."""
    try:
        r = requests.get(_idx_url(d), headers={"User-Agent": SEC_USER_AGENT}, timeout=IDX_TIMEOUT)
    except requests.RequestException as e:
        print(f"[us_fin_incr] {d} idx fetch 실패: {e!r}", file=sys.stderr)
        return None
    if r.status_code != 200:
        return None
    out: List[Tuple[int, str]] = []
    for line in r.text.splitlines():
        parts = line.split("|")
        if len(parts) != 5:
            continue
        cik_s, _name, form, _filed, _fname = parts
        if form.strip() in TARGET_FORMS:
            try:
                out.append((int(cik_s), form.strip()))
            except ValueError:
                continue
    return out


def _append_patterns(hits: List[Tuple[str, str, str]]) -> None:
    """(ticker, form, filed) → us_earnings_pattern.json append (어닝 캘린더 일일 유지 — backfill 이후 무추가비용)."""
    if not hits:
        return
    try:
        with open(EARN_PATTERN_PATH, encoding="utf-8") as f:
            doc = json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        doc = {"_meta": {}, "patterns": {}}
    pats = doc.setdefault("patterns", {})
    for tk, form, filed in hits:
        rows = pats.setdefault(tk, [])
        if any(r.get("filed") == filed and r.get("form") == form for r in rows):
            continue
        rows.insert(0, {"form": form, "filed": filed})
        del rows[PATTERN_KEEP:]
    with open(EARN_PATTERN_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    print(f"[us_fin_incr] 어닝 패턴 갱신 {len(hits)}건 → {EARN_PATTERN_PATH}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP, help="run 당 재수집 종목 상한")
    ap.add_argument("--dry-run", action="store_true", help="감지만 출력, 재수집 없음")
    args = ap.parse_args()

    cik_map = _universe_cik_map()
    if not cik_map:
        print("[us_fin_incr] 유니버스 CIK 맵 부재(_summary) — skip", file=sys.stderr)
        return 0

    st = _load_state()
    today_et = (datetime.now(timezone.utc) - timedelta(hours=5)).date()  # EDGAR 일자 기준(ET 근사)
    last_s = st.get("last_processed")
    try:
        last = date.fromisoformat(last_s) if last_s else today_et - timedelta(days=2)
    except ValueError:
        last = today_et - timedelta(days=2)
    start = max(last + timedelta(days=1), today_et - timedelta(days=LOOKBACK_MAX_DAYS))

    tickers: List[str] = []
    pattern_hits: List[Tuple[str, str, str]] = []
    processed_through = last
    d = start
    while d < today_et:  # 당일(ET)은 인덱스 미완성 — 전일까지
        if d.weekday() < 5:
            filers = _fetch_day_filers(d)
            if filers is None:
                # 영업일인데 인덱스 부재 = 휴장 or 일시 오류 — 오류 가능성 있으므로 state 전진 중단
                print(f"[us_fin_incr] {d} 인덱스 없음 — 해당 일 이후 보류", file=sys.stderr)
                break
            hit = sorted({cik_map[c] for c, _f in filers if c in cik_map})
            pattern_hits.extend((cik_map[c], f, d.isoformat()) for c, f in filers if c in cik_map)
            print(f"[us_fin_incr] {d}: 10-K/Q 제출 {len(filers)} 건, 유니버스 교집합 {len(hit)}", file=sys.stderr)
            tickers.extend(t for t in hit if t not in tickers)
            time.sleep(THROTTLE_SEC)
        processed_through = d
        d += timedelta(days=1)

    if not args.dry_run:
        _append_patterns(pattern_hits)  # 어닝 캘린더 패턴 일일 유지 (재수집 성패 무관 — 제출 사실)

    if not tickers:
        print(f"[us_fin_incr] 신규 실적 공시 0 — state {processed_through} 전진", file=sys.stderr)
        if not args.dry_run and processed_through > last:
            _save_state({"last_processed": processed_through.isoformat(),
                         "updated_at": datetime.now(KST).isoformat(), "last_run_tickers": []})
        return 0

    capped = tickers[: args.cap]
    dropped = len(tickers) - len(capped)
    if dropped > 0:
        # 🚨 캡 초과 = 침묵 누락 금지 — 로그 + state 미전진으로 다음 run 이 이어감
        print(f"[us_fin_incr] 캡 {args.cap} 초과 — {dropped}종목 다음 run 이월 (state 미전진)", file=sys.stderr)

    if args.dry_run:
        print(f"[us_fin_incr] dry-run — 재수집 대상 {len(capped)}: {capped}", file=sys.stderr)
        return 0

    ok, fail = [], []
    for tk in capped:
        r = subprocess.run([sys.executable, "-m", "api.builders.us_financials_builder", "--ticker", tk],
                           capture_output=True, text=True, cwd=_ROOT, timeout=300)
        blob = (r.stderr or "") + (r.stdout or "")
        (ok if "saved" in blob else fail).append(tk)
        time.sleep(THROTTLE_SEC)

    print(f"[us_fin_incr] logged=True · 재수집 {len(ok)} OK / {len(fail)} FAIL"
          f"{' · FAIL=' + ','.join(fail) if fail else ''}", file=sys.stderr)

    # state 전진 = 이월 없고 실패 없을 때만 (실패분 다음 run 재시도 — 멱등)
    if dropped == 0 and not fail:
        _save_state({"last_processed": processed_through.isoformat(),
                     "updated_at": datetime.now(KST).isoformat(), "last_run_tickers": ok})
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main())
