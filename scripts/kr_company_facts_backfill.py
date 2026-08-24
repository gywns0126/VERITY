#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KR 기업사실 축 백필 — 중·소형주까지 커버리지 확대.

🚨 왜 필요한가 (2026-08-09 전수 감사)
  KR 유니버스 2,700종(대형 307·중형 353·소형 1,540·초소형 486) 대비 실측 커버리지:

      배당(dividends_kr)          중+소 5/1,893  (0.3%)
      지배구조(group_structure)         7/1,893  (0.4%)
      CB·BW 희석                       10/1,893  (0.5%)
      특수관계자                        14/1,893  (0.7%)
      소송·우발채무                     15/1,893  (0.8%)
      사업건전성                        16/1,893  (0.8%)

  원인은 소스 부재가 아니라 **순회 유니버스**다:
    · `api/collectors/stock_data.ALL_STOCKS` = KOSPI_MAJOR 30 + KOSDAQ_MAJOR 15 = **45종 하드코딩**
      (전부 대형주). DartScout·group_structure·ReportScout·dart_report_analyzer 가 이걸 돈다.
    · 배당은 그보다 좁아서 **VAMS 보유 종목만**(`api/main.py` 배당 훅, 11종).
    · funnel 최종은 `FILTER_KR_TOP_N=10` → 운영풀 20종.
  → [[feedback_coverage_check_collector_filter_first]] 와 동형(ETF 25→1,150, 쿼터 0).

설계
  분석기 4종은 이미 **배치 함수**(`analyze_all_*(stocks_dict)`)이고 캐시·스킵·원자저장을
  자체 처리한다. 코드를 고치지 않고 **유니버스만 갈아끼운다.** 출력도 기존 파일 그대로라
  소비자(빌더·리포트) 배선 변경이 0 이다.

  · LLM 0 축 = dividends · cb_bw · shareholders  (DART 호출만, 비용 0)
  · LLM 축   = related_party · litigation · business (Gemini, 명시 opt-in)
    실단가 = 자체 원장(`data/metadata/llm_cost.jsonl`) gemini-2.5-flash $0.00186/콜 기준
    코너 1,274 × 3축 ≈ $7 (1회성). 입력 3만자 상한이라 최대 $30 선.

  DART 쿼터 = 20,000/일 (공유). `--limit` 로 1회 종목수를 끊고 여러 날 나눠 돌린다.
  전 축 캐시 기반이라 **재실행이 멱등**이다 — 이미 채운 종목은 호출 없이 skip.

사용
  python3 scripts/kr_company_facts_backfill.py --universe corner --axes dividends --limit 300
  python3 scripts/kr_company_facts_backfill.py --universe corner --axes cb_bw,shareholders
  python3 scripts/kr_company_facts_backfill.py --axes related_party,litigation --limit 100   # LLM
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

DATA = os.path.join(_ROOT, "data")
CORNER_PATH = os.path.join(DATA, "smallcap_corner.json")
MKTCAP_PATH = os.path.join(DATA, "krx_mktcap.json")
MAPPING_PATH = os.path.join(DATA, "mapping.json")
LISTED_PATH = os.path.join(DATA, "kr_listed.json")
DIVIDENDS_PATH = os.path.join(DATA, "dividends_kr.json")

# 🚨 2026-08-17 kam 을 LLM → FREE 로 이동. PM 지시 "재미나이 호출이 무의미하면 아예 배제해".
#   실측 근거: Gemini 가 5/5 종목을 `kam_count=0` 으로 냈고, 원인은 모델이 아니라 슬라이스가
#   사업보고서 표지를 담은 것이었다(`'핵심감사사항'` = raw_text 8회 vs kam_text 0회).
#   그런데 필요한 사실이 **이미 정형 표**('V. 회계감사인의 감사의견', 8열 고정)에 있어
#   LLM 이 할 일이 없다. 결정론 파서가 감사인·의견·계속기업·강조사항·KAM 을
#   3개 연도 × 개별/연결 6행으로 준다 — LLM 보다 많고, 비용 0, 검증 가능.
#   ⚠️ 종전 주석의 "추가 DART 호출 0" 도 틀렸다 — raw 캐시가 없었다(7d4e3ff01 에서 신설).
LLM_AXES = {"related_party", "litigation", "business"}
# 🚨 2026-08-23 `overview` 신설 — 사업보고서 「1. 사업의 개요」 원문 발췌.
#   kam 과 같은 원천(`raw_text`)이라 LLM 0 · 과금 0. 요약이 아니라 **원문 발췌**라
#   모델이 손댈수록 사실이 흐려진다 (KAM 선례 = 구조가 있으면 결정론이 이긴다).
FREE_AXES = {"dividends", "cb_bw", "shareholders", "chain", "kam", "overview"}
ALL_AXES = FREE_AXES | LLM_AXES


def _load(path: str, default: Any = None) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def build_universe(kind: str, limit: int | None, only: str | None) -> List[Tuple[str, str]]:
    """(ticker, name) 목록. corner = 소형주 코너 1,274 / market = 전 상장 / reco = 운영풀."""
    out: List[Tuple[str, str]] = []
    if kind == "corner":
        for s in (_load(CORNER_PATH, {}) or {}).get("stocks") or []:
            tk = str(s.get("ticker") or "")
            if tk.isdigit() and len(tk) == 6:
                out.append((tk, s.get("name") or tk))
    elif kind == "market":
        listed = _load(LISTED_PATH, {}) or {}
        src = listed if any(str(k).isdigit() for k in list(listed)[:20]) else {}
        if not src:
            src = next((v for v in listed.values() if isinstance(v, dict)), {})
        for tk, meta in src.items():
            if str(tk).isdigit() and len(str(tk)) == 6:
                nm = meta.get("name") if isinstance(meta, dict) else str(meta)
                out.append((str(tk), nm or str(tk)))
    else:  # reco
        for r in _load(os.path.join(DATA, "recommendations.json"), []) or []:
            tk = str(r.get("ticker") or "")
            if tk.isdigit() and len(tk) == 6:
                out.append((tk, r.get("name") or tk))
    if only:
        out = [x for x in out if x[0] == only]
    # 시총 큰 순 — 정보 가치가 큰 쪽부터 쿼터를 쓴다
    mk = (_load(MKTCAP_PATH, {}) or {}).get("map") or {}
    out.sort(key=lambda x: -((mk.get(x[0]) or {}).get("mktcap") or 0))
    # 🚨 limit 을 여기서 자르지 않는다. 시총 정렬 상위 N 을 고정으로 집으면 그 N 이
    #   다 채워진 뒤 매 run 이 no-op 이 되어 진도가 영영 안 나간다. 상한은 축별로
    #   "미보유 필터를 통과한 목록" 에 적용한다(아래 _cap).
    return out


def _cap(todo, limit):
    """미보유 목록에 상한 적용 — 매 run 앞에서부터 채우고 다음 run 이 이어받는다."""
    return todo[:limit] if limit else todo


def _stocks_dict(univ: List[Tuple[str, str]], year: str) -> Dict[str, Dict[str, Any]]:
    """분석기 4종이 요구하는 {ticker: {corp_code, name, bsns_year, shares_outstanding}}."""
    mapping = _load(MAPPING_PATH, {}) or {}
    mk = (_load(MKTCAP_PATH, {}) or {}).get("map") or {}
    out: Dict[str, Dict[str, Any]] = {}
    for tk, nm in univ:
        cc = mapping.get(tk)
        if not cc:
            continue  # corp_code 미해석 = DART 조회 불가
        out[tk] = {
            "corp_code": cc,
            "name": nm,
            "bsns_year": year,
            "shares_outstanding": (mk.get(tk) or {}).get("shares"),
        }
    return out


# ── 축별 실행 ────────────────────────────────────────────────────────────────
def run_dividends(univ, year, delay, dry, limit=None) -> Dict[str, int]:
    """DART 사업보고서 배당 = 종목당 1콜. 기존 dividends_kr.json 에 upsert."""
    from api.collectors.dividend_kr import sweep_annual_plans, load_dividends_db
    db = load_dividends_db()

    def _done(tk: str) -> bool:
        """실배당 레코드가 있거나, 같은 사업연도 '무배당 확정' 마커가 있으면 완료."""
        for r in (db.get(tk) or []):
            if not r.get("_meta"):
                return True
            if r.get("_meta") == _NO_DIV and str(r.get("bsns_year")) == str(year):
                return True
        return False

    todo = [tk for tk, _ in univ if not _done(tk)]
    total_todo = len(todo)
    todo = _cap(todo, limit)
    print(f"  [dividends] 대상 {len(univ)} · 미보유 {total_todo} · 이번 run {len(todo)}")
    if dry or not todo:
        return {"todo": len(todo), "ok": 0}
    # 🚨 청크 저장 — `sweep_annual_plans` 는 루프 종료 후 한 번만 save 한다.
    #   1,244종을 한 번에 넘기면 15~20분간 진도가 메모리에만 있고 중단 1회로 전량 소멸한다
    #   (2026-08-08 '백필 체크포인트 유실'과 동형). 공유 라이브러리는 소량 cron 이 쓰므로
    #   건드리지 않고 여기서 끊는다.
    CH = 100
    ok = tried = nodiv = 0
    for i in range(0, len(todo), CH):
        chunk = todo[i:i + CH]
        res = sweep_annual_plans(chunk, int(year))
        ok += sum(1 for v in res.values() if v in ("insert", "update"))
        tried += len(res)
        # 🚨 '무배당 확정' 을 남긴다. 안 남기면 흔적이 0이라 (a) 매 run 재조회하고
        #   (b) "조회했는데 없음" 과 "아직 안 함" 이 구분되지 않아 완주 판정이 영영 안 선다.
        #   CB/BW 는 이미 '오버행 없음' 을 확정으로 남긴다 — 배당만 빠져 있었다.
        nodiv += _mark_no_dividend([t for t, v in res.items() if v == "fail"], year)
        print(f"  [dividends] {min(i+CH, len(todo))}/{len(todo)} · 누적 갱신 {ok} "
              f"· 무배당 확정 {nodiv}", flush=True)
    print(f"  [dividends] 갱신 {ok} · 무배당 확정 {nodiv} / 시도 {tried}")
    q = quarantine_implausible_dividends()
    if q:
        print(f"  [dividends] 🚨 비현실 DPS {q}건 격리 (implausible=true 표기, 값 보존)")
    # 🚨 '무배당 확정' 도 진도다 — ok 에 합산하지 않으면 아래 완주 가드가 오작동한다
    #   (배당 없는 종목만 남은 run 을 '전량 실패' 로 오판해 exit 1).
    return {"todo": len(todo), "ok": ok, "no_dividend": nodiv,
            "progressed": ok + nodiv, "quarantined": q}


_NO_DIV = "no_dividend"


def _mark_no_dividend(tickers, year) -> int:
    """DART 사업보고서에 배당 기재가 없는 종목에 '무배당 확정' 마커를 남긴다.

    `_meta` 키를 쓰므로 기존 소비자(실배당 레코드만 읽는 쪽)는 영향이 없다.
    """
    if not tickers:
        return 0
    from datetime import datetime, timedelta, timezone
    db = _load(DIVIDENDS_PATH, {}) or {}
    now = datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds")
    n = 0
    for tk in tickers:
        arr = db.setdefault(tk, [])
        if any(r.get("_meta") == _NO_DIV and str(r.get("bsns_year")) == str(year) for r in arr):
            continue
        arr.append({"_meta": _NO_DIV, "bsns_year": str(year), "checked_at": now,
                    "note": "DART 사업보고서 배당 기재 없음 — 미조회가 아니라 '무배당 확정'"})
        n += 1
    if n:
        tmp = DIVIDENDS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False)
        os.replace(tmp, DIVIDENDS_PATH)
    return n


# 배당수익률 상한 — 이 위는 '주당 배당금' 이 아니라 총액/누적 행을 잘못 집은 것이다.
# 실측 2026-08-09: 706종 중 4종 초과, 최악은 DPS 1,809,965,900원(수익률 3,047만%).
_MAX_PLAUSIBLE_YIELD = 0.50


def quarantine_implausible_dividends() -> int:
    """비현실 DPS 를 **삭제하지 않고** 표기만 한다.

    삭제하면 왜 빠졌는지 추적이 끊긴다. 소비자는 implausible 를 보고 거르면 된다
    (없는 것보다 나쁜 건 '조용히 틀린 값'이지 '표시된 이상값'이 아니다).
    """
    mk = (_load(MKTCAP_PATH, {}) or {}).get("map") or {}
    db = _load(DIVIDENDS_PATH, {}) or {}
    n = 0
    for tk, arr in db.items():
        if tk == "_meta" or not isinstance(arr, list):
            continue
        close = (mk.get(tk) or {}).get("close")
        if not close:
            continue
        for r in arr:
            if r.get("_meta") or r.get("implausible"):
                continue
            a = r.get("confirmed_amount_per_share") or r.get("announced_amount_per_share")
            try:
                if a and float(a) / float(close) > _MAX_PLAUSIBLE_YIELD:
                    r["implausible"] = True
                    r["implausible_reason"] = (
                        f"DPS {float(a):,.0f} / 종가 {close:,} = 배당수익률 "
                        f"{float(a)/float(close)*100:,.1f}% — 총액 행 오파싱 의심")
                    n += 1
            except (TypeError, ValueError, ZeroDivisionError):
                continue
    if n:
        tmp = DIVIDENDS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False)
        os.replace(tmp, DIVIDENDS_PATH)
    return n


def run_cb_bw(univ, year, delay, dry, limit=None) -> Dict[str, int]:
    """CB/BW 오버행 — LLM 0 (공시 파싱 + 발행주식수 비율)."""
    from api.analyzers.dart_cb_bw import analyze_all_cb_bw
    sd = _stocks_dict(univ, year)
    sd = {k: v for k, v in sd.items() if v.get("shares_outstanding")}
    cur = (_load(os.path.join(DATA, "dart_cb_bw_cache.json"), {}) or {}).get("by_ticker") or {}
    rest = [k for k in sd if k not in cur]
    if limit:
        sd = {k: sd[k] for k in _cap(rest, limit)}
    print(f"  [cb_bw] 대상 {len(sd)} · 미보유 {len(rest)} (발행주식수 보유분)")
    if dry or not sd:
        return {"todo": len(sd), "ok": 0}
    # 🚨 청크 — `analyze_all_cb_bw` 는 루프 종료 후 캐시를 1회만 저장한다(dart_cb_bw.py:171).
    #   1,255종을 통으로 넘기면 종목당 2콜 × 약 2.5초 = 50분 넘게 진도가 메모리에만 남고
    #   중단 1회로 전량 소멸한다(배당·8/8 백필 체크포인트 사고와 동형).
    keys = list(sd)
    CH = 100
    total = 0
    for i in range(0, len(keys), CH):
        part = {k: sd[k] for k in keys[i:i + CH]}
        res = analyze_all_cb_bw(part)
        total += len(res)
        print(f"  [cb_bw] {min(i+CH, len(keys))}/{len(keys)} · 누적 오버행 {total}", flush=True)
    print(f"  [cb_bw] 결과 {total}")
    return {"todo": len(sd), "ok": total}


def run_shareholders(univ, year, delay, dry, limit=None) -> Dict[str, int]:
    """최대주주 현황 — DART hyslrSttus, 종목당 1콜. LLM 0."""
    from api.collectors.DartScout import fetch_major_shareholders
    out_path = os.path.join(DATA, "kr_major_shareholders.json")
    cur = _load(out_path, {}) or {}
    by = cur.get("by_ticker") or {}
    sd = _stocks_dict(univ, year)
    todo = [(tk, v) for tk, v in sd.items() if tk not in by]
    total_todo = len(todo)
    todo = _cap(todo, limit)
    print(f"  [shareholders] 대상 {len(sd)} · 미보유 {total_todo} · 이번 run {len(todo)}")
    if dry or not todo:
        return {"todo": len(todo), "ok": 0}
    ok = 0
    for i, (tk, v) in enumerate(todo, 1):
        try:
            rows = fetch_major_shareholders(v["corp_code"], year)
        except Exception as e:  # noqa: BLE001 — 한 종목 실패가 전체를 막지 않는다
            print(f"    {tk} 실패 {type(e).__name__}: {str(e)[:60]}", file=sys.stderr)
            rows = None
        if rows:
            # 🚨 DART hyslrSttus 응답에는 '계/합계/소계' 집계행이 섞인다. 그대로 실으면
            #   조인 출력에 "nm 계 · stock_rate -" 같은 잡음이 뜬다.
            #   group_structure._is_aggregate_row 와 같은 규칙을 적용한다.
            from api.collectors.group_structure import _is_aggregate_row
            rows = [r for r in rows if not _is_aggregate_row(str(r.get("nm") or ""))]
        if rows:
            by[tk] = {"name": v["name"], "bsns_year": year, "shareholders": rows[:20]}
            ok += 1
        if i % 100 == 0:
            _save_shareholders(out_path, by, year)
            print(f"    … {i}/{len(todo)} (누적 {ok})")
        time.sleep(delay)
    _save_shareholders(out_path, by, year)
    print(f"  [shareholders] 신규 {ok} · 누계 {len(by)}")
    return {"todo": len(todo), "ok": ok}


def _save_shareholders(path, by, year):
    from datetime import datetime, timedelta, timezone
    tmp = path + ".tmp"
    payload = {
        "updated_at": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
        "bsns_year": year,
        "count": len(by),
        "source": "DART hyslrSttus (최대주주 현황) — 사실만, 점수·판단 0 (RULE 7)",
        "by_ticker": by,
    }
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, path)


def run_chain(univ, year, delay, dry, limit=None) -> Dict[str, int]:
    """주요 매출처 스니펫 — DART 사업보고서 원문 앵커 추출. LLM 0.

    기존 파이프라인은 full run 당 `candidates[:5]` 만 돌아 31종에서 멈춰 있었다.
    """
    from api.collectors.ChainScout import scout_major_customer_snippets, save_snippets_payload
    cur = _load(os.path.join(DATA, "chain_snippets.json"), {}) or {}
    have = set((cur.get("by_ticker") or {}).keys())
    corner = {s["ticker"]: s for s in (_load(CORNER_PATH, {}) or {}).get("stocks") or []}
    todo = [(tk, nm) for tk, nm in univ if tk not in have]
    total_todo = len(todo)
    todo = _cap(todo, limit)
    print(f"  [chain] 대상 {len(univ)} · 미보유 {total_todo} · 이번 run {len(todo)}", flush=True)
    if dry or not todo:
        return {"todo": len(todo), "ok": 0}
    ok = 0
    for i, (tk, nm) in enumerate(todo, 1):
        mkt = (corner.get(tk) or {}).get("market") or "KS"
        try:
            r = scout_major_customer_snippets(f"{tk}.{mkt}")
            if isinstance(r, dict) and r.get("snippets"):
                save_snippets_payload(r)   # by_ticker 병합 저장 = 종목마다 영속
                ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"    {tk} 실패 {type(e).__name__}: {str(e)[:60]}", file=sys.stderr)
        if i % 100 == 0:
            print(f"    … {i}/{len(todo)} (스니펫 확보 {ok})", flush=True)
        time.sleep(delay)
    print(f"  [chain] 신규 {ok} / 시도 {len(todo)}")
    return {"todo": len(todo), "ok": ok}


def run_overview(univ, year, delay, dry, limit=None, retry_exhausted=False) -> Dict[str, int]:
    """사업의 개요 원문 발췌 — `dart_business_overview.json` upsert. LLM 0 · 과금 0.

    🚨 `--limit` 은 **미보유 종목에만** 적용한다. `run_llm_axis` 처럼 전체에 걸면
    이미 채운 앞쪽 종목이 한도를 다 먹어 뒤쪽이 영원히 안 채워진다 (2026-08-17 kam 학습의
    같은 계열 함정). 보유 판정 = 같거나 더 최신 사업연도 행 + 본문 존재.

    🚨 2026-08-24 — **반려 원장(`misses`)을 대상 산정에서 뺀다.** 종전엔 보유 판정이
    "성공 행 존재" 하나뿐이라 게이트 반려 종목이 매 run 다시 문서를 받아 다시 반려됐다
    (실측 한화에어로·고려아연·한국항공우주·오뚜기·남선알미늄). 드립이 수렴하면 매 run
    예산이 **전부** 같은 반려 재조회에 쓰인다. 상한 도달분은 `--retry-exhausted` 로만 연다.
    """
    from api.analyzers.dart_business_overview import (
        MAX_OVERVIEW_ATTEMPTS, analyze_all_overview, load_cache)

    sd = _stocks_dict(univ, year)
    total = len(sd)
    _cache = load_cache()
    have = (_cache.get("rows") or {})
    misses = (_cache.get("misses") or {})
    rest = [tk for tk in sd
            if not (str((have.get(tk) or {}).get("bsns_year") or "") >= str(year)
                    and (have.get(tk) or {}).get("text"))]
    n_have = total - len(rest)
    if not retry_exhausted:
        _before = len(rest)
        rest = [tk for tk in rest
                if int((misses.get(tk) or {}).get("n", 0)) < MAX_OVERVIEW_ATTEMPTS]
        n_exh = _before - len(rest)
    else:
        n_exh = 0
    if limit:
        rest = _cap(rest, limit)
    sd = {tk: sd[tk] for tk in rest}
    print(f"  [overview] 대상 {len(sd)}/{total} (보유 {n_have} · 시도소진 {n_exh} 제외)"
          + (f" · --limit {limit}" if limit else "")
          + (" · --retry-exhausted" if retry_exhausted else "")
          + "  결정론 파싱 (LLM 0 · 과금 0)")
    if dry or not sd:
        return {"todo": len(sd), "ok": 0}
    res = analyze_all_overview(sd, retry_exhausted=retry_exhausted)
    ok = sum(1 for tk in sd if tk in res)
    print(f"  [overview] 결과 {ok}/{len(sd)}")
    return {"todo": len(sd), "ok": ok}


def run_llm_axis(axis, univ, year, delay, dry, limit=None) -> Dict[str, int]:
    """related_party / litigation / business / kam — Gemini. 캐시 스킵 내장.

    🚨 2026-08-17 — `limit` 을 **인자로 받고 쓰지 않고 있었다**. LLM 축 4종 전부 `--limit`
    이 무시돼, "5회로 나눠 실행(쿼터 20,000/일 공유)" 이라는 문서화된 운용이 성립하지
    않았다. `--limit 5` 로 파일럿을 돌렸는데 대상 1,498 전량이 시작됐다 (실측, 9분 만에 중단.
    Gemini 호출 전이라 비용 소모 $0). 자유축이 쓰는 `_cap` 을 동일하게 적용한다.
    """
    sd = _stocks_dict(univ, year)
    total = len(sd)
    if limit:
        sd = {tk: sd[tk] for tk in _cap(list(sd.keys()), limit)}
    # 🚨 축마다 실제 과금 여부가 다르다 — kam 은 2026-08-17 부터 결정론 파서(LLM 0)다.
    #   전 축에 "Gemini 호출 발생" 을 찍으면 경고가 거짓이 되고, 거짓 경고는 무시된다.
    _paid = axis in LLM_AXES
    print(f"  [{axis}] 대상 {len(sd)}/{total}"
          + (f" (--limit {limit} 적용)" if limit else "")
          + ("  🚨 Gemini 호출 발생" if _paid else "  결정론 파싱 (LLM 0 · 과금 0)"))
    if dry or not sd:
        return {"todo": len(sd), "ok": 0}
    if axis == "related_party":
        from api.analyzers.dart_related_party import analyze_all_related_party as fn
    elif axis == "litigation":
        from api.analyzers.dart_litigation import analyze_all_litigation as fn
    elif axis == "kam":
        from api.analyzers.dart_kam import analyze_all_kam as fn
    else:
        from api.analyzers.dart_report_analyzer import analyze_all_business_reports as fn
    res = fn(sd)
    print(f"  [{axis}] 결과 {len(res)}")
    return {"todo": len(sd), "ok": len(res)}


def main() -> int:
    ap = argparse.ArgumentParser(description="KR 기업사실 축 백필 (중·소형주 확대)")
    ap.add_argument("--universe", choices=["corner", "market", "reco"], default="corner")
    ap.add_argument("--axes", default="dividends",
                    help=f"쉼표구분. 무료={sorted(FREE_AXES)} LLM={sorted(LLM_AXES)}")
    ap.add_argument("--year", default=str(__import__("datetime").date.today().year - 1))
    ap.add_argument("--limit", type=int, default=None, help="축별 1회 처리 상한 — 미보유분 앞에서부터 (DART 쿼터 제어)")
    ap.add_argument("--ticker", default=None, help="단일 종목만")
    ap.add_argument("--delay", type=float, default=0.15)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-llm", action="store_true", help="LLM 축 실행 명시 승인")
    ap.add_argument("--retry-exhausted", action="store_true",
                    help="overview: 시도 상한에 걸린 반려 종목까지 다시 조회(원장 초기화 없이 1회 강제)")
    a = ap.parse_args()

    axes = [x.strip() for x in a.axes.split(",") if x.strip()]
    bad = [x for x in axes if x not in ALL_AXES]
    if bad:
        print(f"알 수 없는 축: {bad} — 가능: {sorted(ALL_AXES)}", file=sys.stderr)
        return 2
    llm = [x for x in axes if x in LLM_AXES]
    if llm and not a.allow_llm:
        print(f"🚨 LLM 축 {llm} 은 --allow-llm 필요 (Gemini 과금). 중단.", file=sys.stderr)
        return 2

    univ = build_universe(a.universe, a.limit, a.ticker)
    if not univ:
        print("유니버스 비어 있음", file=sys.stderr)
        return 1
    print(f"[facts_backfill] universe={a.universe} 종목={len(univ)} year={a.year} "
          f"axes={axes} dry={a.dry_run}")

    t0 = time.time()
    summary = {}
    for ax in axes:
        try:
            if ax == "dividends":
                summary[ax] = run_dividends(univ, a.year, a.delay, a.dry_run, a.limit)
            elif ax == "cb_bw":
                summary[ax] = run_cb_bw(univ, a.year, a.delay, a.dry_run, a.limit)
            elif ax == "shareholders":
                summary[ax] = run_shareholders(univ, a.year, a.delay, a.dry_run, a.limit)
            elif ax == "chain":
                summary[ax] = run_chain(univ, a.year, a.delay, a.dry_run, a.limit)
            elif ax == "overview":
                # 🚨 2026-08-24 N=2 감사에서 발견 — 개요 축만 **market** 유니버스로 돈다.
                #   다른 축은 코너(중·소형주 채움)가 목적이지만 개요는 **공개 리포트 표면**
                #   자산이고, 리포트 유니버스(1,789) ⊄ corner(1,513) 다. 실측:
                #     corner 미보유 20 · report 미보유 243 · 그 243 중 corner 소속은 **16**.
                #   즉 코너로 돌면 다음 run 에 20건 채우고 **영구 no-op** 이 되면서 리포트는
                #   86.4% 에서 멈춘다 — 남은 227종목(대형주 다수)에 영영 못 닿는다.
                #   market 은 시총 내림차순이고 미보유 우선이라 **많이 보는 종목부터** 채운다
                #   ([[feedback_largest_names_break_heuristics_first]]).
                #   비용은 그대로 --limit 로 묶인다(200종목 ≈ 400콜).
                _univ_ov = (univ if a.universe == "market"
                            else build_universe("market", a.limit, (a.ticker or "").strip() or None))
                summary[ax] = run_overview(_univ_ov, a.year, a.delay, a.dry_run, a.limit,
                                           retry_exhausted=a.retry_exhausted)
            else:
                summary[ax] = run_llm_axis(ax, univ, a.year, a.delay, a.dry_run, a.limit)
        except Exception as e:  # noqa: BLE001 — 한 축 실패가 다른 축을 막지 않는다
            print(f"  [{ax}] 🚨 실패 {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
            summary[ax] = {"error": type(e).__name__}

    print(f"\n[facts_backfill] {time.time()-t0:.0f}초 · {json.dumps(summary, ensure_ascii=False)}")
    # 🚨 전량 실패는 성공으로 끝내지 않는다 ([[feedback_silent_total_failure_guard]])
    def _stalled(v):
        if "error" in v:
            return True
        # progressed 가 있으면 그걸 본다(배당: 갱신 + 무배당 확정). 없으면 ok.
        moved = v.get("progressed", v.get("ok", 0))
        return moved == 0 and v.get("todo", 0) > 0
    if summary and all(_stalled(v) for v in summary.values()) and not a.dry_run:
        print("🚨 모든 축이 0건 — 실패로 종료", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
