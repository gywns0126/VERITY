"""dart_catalyst_backfill — 공시 forensics 과거 이력 백필 (2015~).

2026-06-19 신설. disclosure_forensics_builder 의 시간깊이(현 rolling ~5주) 한계 해소 = 종목별 과거
공시 이벤트(유상증자/CB/감자/정정 등)를 2015~ 전체로 1회 수집 → data/dart_catalyst_backfill.jsonl.
forensics 빌더가 alerts.jsonl + 이 백필 둘 다 읽어 빈도/타임라인 심화.

🚨 DART 20K/일 쿼터 — 분기 윈도우 × 종목 × 타입(B/C/D) 루프. 기본 유니버스 = recommendations(소수).
  전종목은 --universe market 인자(corp_cls 페이지네이션) 별도. throttle 내장(dart_catalyst).
사용:
  python scripts/dart_catalyst_backfill.py --start-year 2015 [--max N] [--ticker 005930]
멱등 — rcept_no dedup(기존 백필 + alerts 와 합산은 빌더가 처리). append-merge.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

OUT_PATH = os.path.join(_ROOT, "data", "dart_catalyst_backfill.jsonl")
# resume marker — 완전 스캔 끝낸 ticker(이벤트 0 포함). quota-cap 다일 분할 시 재스캔 방지(쿼터 절약).
DONE_PATH = os.path.join(_ROOT, "data", "dart_catalyst_backfill_done.json")
RECO_PATH = os.path.join(_ROOT, "data", "recommendations.json")
CORNER_PATH = os.path.join(_ROOT, "data", "smallcap_corner.json")
CORNER_FILTERS_PATH = os.path.join(_ROOT, "data", "smallcap_corner_filters.json")


def _kr_universe(max_n=None, only=None):
    try:
        with open(RECO_PATH, "r", encoding="utf-8") as f:
            recs = json.load(f)
    except (OSError, json.JSONDecodeError):
        recs = []
    out = []
    for r in (recs if isinstance(recs, list) else []):
        tk = str(r.get("ticker") or "").strip()
        if only and tk != only:
            continue
        if tk.isdigit() and len(tk) == 6:
            out.append((tk, r.get("name") or tk))
    if max_n:
        out = out[:max_n]
    return out


def _corner_universe(max_n=None, only=None, neglected=False):
    """소형주 코너 유니버스 (Phase 1 forensic 백필). neglected=True → 방치우량 501 subset."""
    try:
        with open(CORNER_PATH, "r", encoding="utf-8") as f:
            stocks = json.load(f).get("stocks") or []
    except (OSError, json.JSONDecodeError):
        stocks = []
    keep = None
    if neglected:
        keep = set()
        try:
            with open(CORNER_FILTERS_PATH, "r", encoding="utf-8") as f:
                for flt in (json.load(f).get("filters") or []):
                    if flt.get("key") == "neglected_quality":
                        keep = {str(t.get("ticker")) for t in (flt.get("tickers") or []) if t.get("ticker")}
                        break
        except (OSError, json.JSONDecodeError):
            keep = set()
    out = []
    for s in stocks:
        tk = str(s.get("ticker") or "").strip()
        if only and tk != only:
            continue
        if keep is not None and tk not in keep:
            continue
        if tk.isdigit() and len(tk) == 6:
            out.append((tk, s.get("name") or tk))
    if max_n:
        out = out[:max_n]
    return out


def _load_done():
    """완전 스캔 끝낸 ticker set (resume). 부재/손상 = 빈 set."""
    try:
        with open(DONE_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f).get("tickers") or [])
    except (OSError, json.JSONDecodeError):
        return set()


def _save_done(done):
    tmp = DONE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"tickers": sorted(done)}, f, ensure_ascii=False)
    os.replace(tmp, DONE_PATH)


def _quarters(start_year):
    """start_year-01-01 ~ 오늘, 3개월 윈도우 (DART list.json 단일쿼리 max 3개월)."""
    cur = date(start_year, 1, 1)
    today = date.today()
    while cur < today:
        nxt = cur + timedelta(days=90)
        end = min(nxt, today)
        yield cur.strftime("%Y%m%d"), end.strftime("%Y%m%d")
        cur = nxt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2015)
    ap.add_argument("--max", type=int, default=None, help="유니버스 상한(테스트)")
    ap.add_argument("--ticker", default=None, help="단일 종목만")
    ap.add_argument("--delay", type=float, default=0.15, help="요청 간 지연(쿼터·anti-bot)")
    ap.add_argument("--universe", choices=["reco", "corner"], default="reco",
                    help="reco=추천(기본) / corner=소형주 코너(Phase 1 forensic)")
    ap.add_argument("--neglected", action="store_true", help="corner 한정 — 방치우량 501 subset")
    ap.add_argument("--quota-cap", type=int, default=None,
                    help="이번 run DART 요청 상한(공유 쿼터 throttle, 다일 멱등 분할). 도달 시 중단")
    args = ap.parse_args()

    from api.collectors.dart_catalyst import _fetch_catalyst_by_type, _classify_severity, PBLNTF_LABELS
    from api.collectors.dart_corp_code import get_corp_code
    from api.config import now_kst

    if args.universe == "corner":
        universe = _corner_universe(args.max, args.ticker, neglected=args.neglected)
    else:
        universe = _kr_universe(args.max, args.ticker)
    if not universe:
        print("[backfill] 유니버스 0 — skip", file=sys.stderr)
        return 0
    print(f"[backfill] universe={args.universe}{'(neglected)' if args.neglected else ''} "
          f"종목={len(universe)} start={args.start_year} quota_cap={args.quota_cap}", file=sys.stderr)

    # 기존 백필 dedup
    seen = set()
    if os.path.isfile(OUT_PATH):
        with open(OUT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    seen.add(json.loads(line).get("rcept_no"))
                except (json.JSONDecodeError, AttributeError):
                    pass

    windows = list(_quarters(args.start_year))
    done = _load_done()
    skipped = sum(1 for tk, _ in universe if tk in done)
    if skipped:
        print(f"[backfill] resume — 이미 스캔 {skipped}종목 skip(잔여 {len(universe) - skipped})", file=sys.stderr)
    new_n, req_n = 0, 0
    capped = False
    with open(OUT_PATH, "a", encoding="utf-8") as out:
        for tk, name in universe:
            if tk in done:
                continue  # 이미 완전 스캔(resume) — 재호출 방지
            # 공유 쿼터 throttle — cap 도달 시 종목 경계에서 중단(멱등, 다음 run 이 done marker 로 이어받음).
            if args.quota_cap is not None and req_n >= args.quota_cap:
                capped = True
                print(f"[backfill] quota-cap {args.quota_cap} 도달 — 중단(다음 run 이 이어받음)", file=sys.stderr)
                break
            cc = get_corp_code(tk)
            if not cc:
                print(f"[backfill] {tk} corp_code 없음 — skip", file=sys.stderr)
                continue
            tk_n = 0
            for bgn_de, end_de in windows:
                for ty in ("B", "C", "D"):
                    req_n += 1
                    try:
                        events = _fetch_catalyst_by_type(cc, bgn_de, end_de, ty) or []
                    except Exception as e:  # noqa: BLE001
                        print(f"[backfill] {tk} {bgn_de}-{end_de} {ty} 실패: {str(e)[:80]}", file=sys.stderr)
                        time.sleep(args.delay)
                        continue
                    for e in events:
                        rc = e.get("rcept_no")
                        if not rc or rc in seen:
                            continue
                        seen.add(rc)
                        is_corr = (e.get("corr_yn") == "Y")
                        rec = {
                            "ticker": tk, "name": name,
                            "rcept_no": rc, "report_nm": e.get("report_nm", ""),
                            "rcept_dt": e.get("rcept_dt", ""), "flr_nm": e.get("flr_nm", ""),
                            "pblntf_ty": ty, "pblntf_label": PBLNTF_LABELS.get(ty, ty),
                            "severity": _classify_severity(pblntf_ty=ty, report_nm=e.get("report_nm", ""), is_correction=is_corr),
                            "is_correction": is_corr,
                            "detected_at": now_kst().isoformat(timespec="seconds"),
                            "_backfill": True,
                        }
                        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        new_n += 1
                        tk_n += 1
                    time.sleep(args.delay)
            done.add(tk)
            _save_done(done)  # 종목 완전 스캔 완료 — resume marker(crash-safe, 종목당 갱신)
            print(f"[backfill] {name}({tk}) +{tk_n}건", file=sys.stderr)
    print(f"[backfill] logged=True · 신규 {new_n}건 · req {req_n} · done={len(done)} · capped={capped} · -> {os.path.relpath(OUT_PATH, _ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
