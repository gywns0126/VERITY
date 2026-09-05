# -*- coding: utf-8 -*-
"""TickerFacts — 종목 하나에 대해 **우리가 가진 모든 사실**을 한 번에 조인하는 단일 레이어.

🚨 왜 만들었나 (2026-08-03 PM 지시)
  종목 질문 하나에 답하려고 kr_close_latest·stock_report_public·stock_flow_5d·
  dart_quarterly_public·공시피드·일봉청크를 매번 손으로 뒤졌다. 더 나쁜 건 소비자마다
  다른 걸 봐서 답이 달라진 것 — 배리티 챗(chat_hybrid)은 발행물 JSON 을 **0건** 조인하고
  Brain/Perplexity/Gemini 만 붙였다. 그래서 유니버스 밖 종목에서 LLM 기억으로 가격을
  지어내는 사고가 났다(2026-06-03 삼성전자 "65,000원 지지선", 실제 ~365,000원).
  → 조인은 **여기 한 곳**에만 둔다. 소비자(오퍼레이터 CLI·Codex 세션·챗)는 이걸 호출한다.

수집 범위 = 공개 발행물(Blob) + 로컬 data/ 미발행 + 오퍼레이터 private bucket.
  · 공개 Blob = 큐레이트 목록 + **제네릭 스캔**(신규 발행물이 늘어도 코드 수정 없이 잡힘).
  · private = Supabase `verity-reports/_operator/*` (service_role). 키 없으면 조용히 skip.

🚨 출력 규율
  · 모든 값에 **출처 파일 + 기준일**을 붙인다. 없는 정밀도를 있는 척하지 않는다.
  · 없는 항목은 넣지 않는다(0 으로 위장 금지 — 2026-08-03 ROE 0% 사고 계열).
  · 이 레이어는 **사실만** 모은다. 판단·전망·추천은 원문 검증 뒤 Codex 세션에서만 한다.
  · 오퍼레이터 전용 — 공개 노출 금지(PM 2026-08-03 "종목 상담·분석·추천이 들어가니 공개용 절대 안됨").
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
# 🚨 KIS 실시간 (Railway) — **오퍼레이터 본인 이용만**. 재배포 금지가 걸리는 건 제3자 배포이지
#   본인 조회가 아니다(2026-07 컴플라이언스: 공개 발행은 T+1 금융위, 본인 이용은 KIS 실시간 OK).
#   이 서버는 KIS_SHARED_TOKEN **순수 소비자**(발급 0) — RULE 1(1일 1토큰) 무관.
#   2026-08-03 추가 사유: 종가만 보다가 장중 급등을 못 봤다(PM 지적 "실시간가 보면 되는걸").
RAILWAY = os.environ.get("VERITY_REALTIME_URL", "https://verity-production-1e44.up.railway.app")
_KST = timezone(timedelta(hours=9))
# 캐시 위치 — Vercel 함수는 /tmp 만 쓰기 가능(레포 경로 read-only). 로컬 CLI 는 repo .cache.
_CACHE_BASE = os.environ.get("OPERATOR_CACHE_DIR") or (
    "/tmp/verity" if os.environ.get("VERCEL") else os.path.join(_ROOT, ".cache")
)
_CACHE_DIR = os.path.join(_CACHE_BASE, "ticker_facts")
_CACHE_TTL = 1800  # 30분 — 발행물은 5분~일단위 갱신이라 이 정도면 충분히 신선
_TIMEOUT = 25

# ── 핵심 발행물: 전용 포맷터가 있는 것 ───────────────────────────────────────
#   (파일, 라벨). 나머지는 제네릭 스캔이 잡는다.
CORE_FILES = [
    ("kr_close_latest.json", "종가"),
    ("stock_report_public.json", "리포트"),
    ("stock_flow_5d.json", "수급"),
    ("dart_quarterly_public.json", "분기추이"),
    ("universe_search_kr.json", "유니버스"),
    ("kr_stock_names.json", "종목명"),
]

# 제네릭 스캔 대상 — {_meta, stocks:{티커}} / stocks:[{ticker}] 패턴을 자동 인식.
#   신규 발행물을 여기 한 줄 추가하면 즉시 조인된다.
SCAN_FILES = [
    "supply_demand.json", "kr_forensics_public.json", "disclosure_forensics.json",
    "insider_trades.json", "securities_lending.json", "public_disclosure_feed.json",
    "calendar_public.json", "market_warnings.json", "ipo_watch.json",
    "commodity_exposure.json", "etf_flow.json", "perspective_maps.json",
    "hot_stock.json", "us_smallcap_corner_filters.json", "smallcap_corner_filters.json",
    "ai_synthesis.json", "kr_earnings_pattern.json", "nps_holdings.json",
    "us_major_holdings.json", "us_short_interest.json", "us_insider_trades.json",
    # 2026-08-03 배선 감사 (PM "뭘 더 안쓰고 있는지 확인해서 배선해") — 발행돼 있는데 조인 0 이던 것:
    "us_stock_report_public.json", "us_quarterly_public.json", "us_smart_money_13f.json",
    "us_disclosure_feed.json", "us_disclosure_forensics.json", "us_earnings_pattern.json",
    "event_study.json", "nps_employment.json",
    # 2026-08-09 배선 감사 2차 — US ETF 가 통째로 조인 0 이던 갭. JEPQ/QQQ/SPY/TLT 등
    #   682 종의 구성·보수·AUM·섹터 사실이 발행돼 있는데 챗이 한 건도 못 봤다(PM 실사용에서 발각).
    #   레코드에 as_of 가 실려 있다 — 회전 수집이라 파일 _meta.generated_at 은 쓰기 시각일 뿐
    #   그 종목의 기준일이 아니다. 반드시 레코드 as_of 를 읽을 것.
    "us_etf.json",
]

# 로컬 전용(미발행) — 발행물보다 원본에 가깝다.
# 🚨 PM 2026-08-03: "민감한 자료도 전부 종합해서 결과를 내라" — 본인 전용 경로이므로
#   비공개·미발행 자산을 빼지 않는다. 공개 발행 목록(action.yml)과는 정반대 판단이다.
LOCAL_FILES = [
    ("data/dart_fundamentals_kr.json", "DART 재무", True),      # True = 티커 키 dict
    ("data/dart_kr_fin_history.json", "DART 재무 시계열", False),
    ("data/kr_listed.json", "상장정보", True),
    ("data/recommendations.json", "운영풀", False),
    ("data/krx_mktcap.json", "시총", True),
    ("data/kr_sector_map.json", "섹터맵", False),
    ("data/report_summaries.json", "리포트 요약", False),
    ("data/dividends_kr.json", "배당", True),
    ("data/chain_snippets.json", "공급망 스니펫", False),
    ("data/group_structure.json", "그룹 지배구조", False),
    # 2026-08-03 배선 감사 — 로컬에 있는데 조인 0 이던 것:
    ("data/analyst_reports.json", "증권사 리포트(네이버 수집)", False),   # company_reports[] · 커버리지 존재 확인
    ("data/dart_kr_backfill_result.json", "DART 백필(연도별 팩터)", False),  # rows[] 1,061 records
    ("data/commodity_impact.json", "원자재 영향", False),                  # by_ticker 상관·MoM 알림
    ("data/us_fin_annual_compact.json", "US 연간재무", False),
    # 2026-08-09 배선 감사 2차 — 로컬에 쌓이는데 조인 0 이던 사실 축.
    #   DART 심화 4종은 2026-08-07-08 수집분이고 운영풀 종목만 커버한다(39~60종) —
    #   미수록 = 아직 수집 전이지 "해당 없음" 이 아니다. 없으면 섹션이 안 뜬다.
    ("data/dart_analysis_cache.json", "DART 사업건전성·해자(심화)", False),
    ("data/dart_litigation_cache.json", "DART 소송·우발채무(심화)", False),
    ("data/dart_related_party_cache.json", "DART 특수관계자 거래(심화)", False),
    ("data/dart_cb_bw_cache.json", "DART CB·BW 희석(심화)", False),
    # 🚨 2026-08-16 신설 — 감사인이 직접 지목한 위험. 2018년부터 의무 기재인데 우리가
    #   한 번도 읽지 않던 자료다(전수 grep 0건). 판정이 아니라 **사실**이라 조인에 싣는다.
    #   이 줄이 없으면 판독 산출이 스냅샷에만 남아 아무도 안 읽는다 — ai_verdict 가 그렇게 죽었다.
    ("data/dart_kam_cache.json", "핵심감사사항 KAM (감사인 지목 위험)", False),
    # 2026-08-09 중·소형주 채움 — `scripts/kr_company_facts_backfill.py` 산출.
    #   기존 group_structure(20종)는 ALL_STOCKS=45 에 묶여 있었다. 이쪽은 코너 전량 대상.
    ("data/kr_major_shareholders.json", "최대주주 현황(DART)", False),
    # Lynch 6분류 — 운영풀 20종에서만 계산되던 것을 전 종목(2,686)으로 확대.
    #   산식 무변경(2026-05-23 PM 사전등록 A3), 입력 조달 범위만 넓혔다.
    ("data/kr_lynch_class.json", "Lynch 분류(규칙 기반 사실)", False),
    ("data/us_form144.json", "US Form 144 (내부자 매도 예고)", False),
    ("data/us_options.json", "US 옵션 체인(IV·스큐·PC비율)", False),
    ("data/us_sector_cache.json", "US 섹터", True),
    # 🚨 2026-08-17 신설 — 미장 공매도 압력 3축(FINRA 일별 공매도 · Reg SHO 임계종목 · SEC FTD).
    #   FINRA 파일은 us_market_observations 가 **이미 매일 받고 있었는데** 시장 aggregate 한
    #   숫자로 접고 종목별 행을 버렸다. 같은 바이트에서 종목 축만 사라지던 것이라 수집이 아니라
    #   폐기가 결손이었다. threshold/FTD 는 신규. 상세 = api/collectors/us_short_pressure.py
    ("data/us_short_pressure.json", "US 공매도 압력(FINRA·Reg SHO·FTD)", True),
    # 🚨 2026-08-23 신설 — 사업보고서 「1. 사업의 개요」 원문 발췌(LLM 0, 정규식 슬라이스).
    #   PM 지적 = "원문을 이미 받아놓고 개요를 안 뽑고 있다". 종전 조인에는 회사가
    #   **무엇을 하는 회사인지** 말해 주는 축이 없었다 — 섹터 라벨(5자)이 전부였다.
    ("data/dart_business_overview.json", "사업의 개요(DART 사업보고서 원문)", False),
]

# 오퍼레이터 private bucket (Supabase). 인증 없으면 skip.
PRIVATE_FILES = [
    ("_operator/portfolio_full.json", "포트폴리오(비공개)"),
    ("_operator/verification_report.json", "검증 리포트(비공개)"),
    ("_operator/moderation_portfolio.json", "중용 목표비중(비공개)"),
    ("_operator/brain_kb_usage.json", "Brain KB 사용(비공개)"),
    ("_operator/history.json", "거래·판단 이력(비공개)"),
]


def _now() -> datetime:
    return datetime.now(_KST)


def _cache_path(key: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key)
    return os.path.join(_CACHE_DIR, safe)


def _fetch_json(url: str, cache_key: Optional[str] = None,
                headers: Optional[Dict[str, str]] = None) -> Optional[Any]:
    """URL → JSON. cache_key 주면 TTL 캐시. 실패는 None(조용히) — 한 소스가 죽어도 나머지는 산다."""
    if cache_key:
        p = _cache_path(cache_key)
        try:
            if os.path.exists(p) and time.time() - os.path.getmtime(p) < _CACHE_TTL:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
    try:
        req = urllib.request.Request(url, headers=headers or {"User-Agent": "verity-facts/1.0"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            body = r.read().decode("utf-8", "replace")
        doc = json.loads(body)
    except Exception:
        return None
    if cache_key:
        try:
            os.makedirs(_CACHE_DIR, exist_ok=True)
            with open(_cache_path(cache_key), "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
        except Exception:
            pass
    return doc


def _load_local(rel: str) -> Optional[Any]:
    try:
        with open(os.path.join(_ROOT, rel), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _meta_as_of(doc: Any) -> str:
    """발행물의 기준일 추출 — 필드명이 파일마다 달라 후보를 순회한다."""
    if not isinstance(doc, dict):
        return ""
    m = doc.get("_meta") if isinstance(doc.get("_meta"), dict) else doc
    for k in ("as_of", "bas_dd", "basDt", "generated_at", "updated_at", "collected_at", "date"):
        v = (m or {}).get(k)
        if v:
            return str(v)
    return ""


# ── 종목 해석 ────────────────────────────────────────────────────────────────
def resolve_ticker(q: str) -> Tuple[str, str]:
    """'제이엠티' / '094970' / 'jmt' → (티커, 종목명). 못 찾으면 ('','').

    KR 6자리 코드는 그대로 통과. 이름은 정확일치 > 접두 > 부분 순.
    """
    s = (q or "").strip()
    if not s:
        return "", ""
    names = _fetch_json(f"{BLOB}/kr_stock_names.json", "kr_stock_names") or {}
    if re.fullmatch(r"\d{6}", s):
        return s, str(names.get(s) or s)
    uni = _fetch_json(f"{BLOB}/universe_search_kr.json", "universe_kr") or {}
    rows = uni.get("stocks") if isinstance(uni, dict) else None
    if not isinstance(rows, list):
        rows = [{"ticker": k, "name": v} for k, v in names.items()] if isinstance(names, dict) else []
    low = s.lower()

    def _match(rowset: Any) -> Tuple[str, str]:
        exact, prefix, part = [], [], []
        for r in rowset or []:
            if not isinstance(r, dict):
                continue
            nm = str(r.get("name") or "")
            if not nm:
                continue
            n = nm.lower()
            if n == low:
                exact.append(r)
            elif n.startswith(low):
                prefix.append(r)
            elif low in n:
                part.append(r)
        for bucket in (exact, prefix, part):
            if bucket:
                r = bucket[0]
                return str(r.get("ticker") or ""), str(r.get("name") or "")
        return "", ""

    # 🚨 2026-08-23 순서 교정 — 종전엔 KR 이름 매칭(부분 포함)이 US 심볼 패스스루보다 **앞**이라
    # 심볼 모양 질의가 조용히 엉뚱한 KR 종목으로 끌려갔다. 실측 US 심볼 10,373 중 **252건(2.43%)**:
    # `AMG`→SAMG엔터 · `V`→NAVER · `KO`→KODEX 200 · `GE`→TIGER 200 · `CMG`→CMG제약.
    # 조인이 그 종목 사실로 가득 차 돌아와 **틀린 걸 알아챌 신호가 0** 이었다.
    # 교정 = KR **정확일치** → US 심볼(실재 확인) → KR 접두 → KR 부분 → US 이름.
    # 정확일치를 앞에 두어 'CMG제약' 처럼 이름을 다 친 질의는 종전대로 KR 로 간다. 되돌리지 말 것.
    exact_tk, exact_nm = _match_exact_only(rows, low)
    if exact_tk:
        return exact_tk, exact_nm
    u_early = s.upper()
    if re.fullmatch(r"[A-Z]{1,5}([.-][A-Z])?", u_early) and _is_known_us_symbol(u_early):
        return u_early, _us_display_name(u_early) or u_early

    tk, nm = _match(rows)
    if tk:
        return tk, nm
    # US 심볼 패스스루 폴백 (2026-08-03 배선 감사) — 해석이 KR 전용이라 GOOGL 등 US 심볼이
    # 여기서 죽어 전 섹션 조인 0 이 되던 갭. KR 이름 매칭이 전부 실패했을 때만 진입하므로
    # 한글 질의 동작은 불변. 이름은 us_stock_names_ko(네이버 수집) 있으면 한글, 없으면 심볼.
    u = s.upper()
    if re.fullmatch(r"[A-Z]{1,5}([.-][A-Z])?", u):
        return u, _us_display_name(u) or u
    # 이름으로 US·ETF 찾기 (2026-08-09) — 'Invesco QQQ' 처럼 심볼이 아닌 질의용.
    # 🚨 심볼 패스스루 **뒤**에 두는 것이 핵심이다. 앞에 두면 'MU' 가 'Municipal…' 접두
    #   매칭으로 MUB 에 끌려간다. 심볼 모양이면 심볼로 확정하고, 아닐 때만 이름을 뒤진다.
    uni_all = _fetch_json(f"{BLOB}/universe_search.json", "universe_all") or {}
    return _match(uni_all.get("stocks") if isinstance(uni_all, dict) else None)



def _match_exact_only(rowset: Any, low: str) -> Tuple[str, str]:
    """이름 **정확일치** 만. resolve_ticker 의 순서 교정용(2026-08-23)."""
    for r in rowset or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("name") or "").lower() == low:
            return str(r.get("ticker") or ""), str(r.get("name") or "")
    return "", ""


def _is_known_us_symbol(u: str) -> bool:
    """US 유니버스에 실재하는 심볼인가. 🚨 실재 확인 없이 심볼 모양만으로 US 로 보내면
    오타·약칭이 전부 US 로 새어 KR 조회가 죽는다(반대 방향 사고)."""
    uni = _fetch_json(f"{BLOB}/universe_search.json", "universe_all") or {}
    rows = uni.get("stocks") if isinstance(uni, dict) else None
    if not isinstance(rows, list):
        return False
    for r in rows:
        if isinstance(r, dict) and str(r.get("ticker") or "").upper() == u:
            return True
    return False


def _us_display_name(u: str) -> str:
    """US 심볼 → 표시명. 한글명 우선, 없으면 ETF 정식명, 없으면 빈 문자열.

    2026-08-09: JEPQ 조회 헤더가 'JEPQ (JEPQ)' 로 나오던 갭. us_stock_names_ko 는 개별주
    수집본이라 ETF 가 없는데 us_etf_universe.names 에 5,486 종 정식명이 이미 있었다.
    """
    for rel, path in (("data/us_stock_names_ko.json", "names"),
                      ("data/us_name_ko.json", ""),
                      ("data/us_etf_universe.json", "names")):
        d = _load_local(rel)
        if not isinstance(d, dict):
            continue
        src = d.get(path) if path else d
        v = src.get(u) if isinstance(src, dict) else None
        if isinstance(v, str) and v:
            return v
    return ""


# ── 제네릭 추출 ──────────────────────────────────────────────────────────────
def _extract_for_ticker(doc: Any, tk: str) -> Optional[Any]:
    """발행물 문서에서 해당 종목 항목만 뽑는다.

    지원 형태: {stocks:{티커:...}} · {stocks:[{ticker}]} · {티커:...} · [{ticker}] ·
               {items|events|warnings|feed:[{ticker}]}
    """
    if not isinstance(doc, (dict, list)):
        return None
    if isinstance(doc, list):
        hits = [x for x in doc if isinstance(x, dict) and str(x.get("ticker") or "") == tk]
        return hits or None
    for key in ("stocks", "map", "items", "events", "warnings", "feed", "flows",
                "prices", "etfs", "top", "rows", "recommendations",
                # 2026-08-03 실측 추가 — 오퍼레이터 전 자산 조인(PM "민감 자료도 전부")
                "summaries", "synth", "patterns", "by_ticker", "structure", "full",
                "holdings", "positions", "syntheses", "data", "fundamentals",
                "company_reports"):  # analyst_reports.json (2026-08-03 배선 감사)
        v = doc.get(key)
        if isinstance(v, dict) and tk in v:
            return v[tk]
        if isinstance(v, list):
            hits = [x for x in v if isinstance(x, dict) and str(x.get("ticker") or "") == tk]
            if hits:
                return hits
    if tk in doc:  # 최상위가 티커 맵
        return doc[tk]
    return None


def _trim(v: Any, cap: int = 12) -> Any:
    """긴 리스트는 최근 cap 개만 — 컨텍스트 폭주 방지."""
    if isinstance(v, list) and len(v) > cap:
        return {"_note": f"{len(v)}건 중 최근 {cap}건", "items": v[-cap:]}
    return v


def _us_realtime(tk: str) -> Optional[Dict[str, Any]]:
    """US 실시간 현재가 — KIS 해외 현재체결가(Railway 경유). 미도달/장 마감이면 None.

    🚨 왜 Railway 를 거치나 (RULE 1): KIS 토큰은 앱키에 묶인다. 로컬 `.env` 앱키 지문은
      GH Actions 발급분과 다르므로(2026-08-09 실측 c72f47d5… vs 728e2190…) 로컬 직접
      호출은 자체 발급을 요구하고 그건 하루 2토큰이다. Railway 는 공유 store 순수
      소비자(발급 0)라 여기를 거치는 것이 유일하게 정합한 경로다.
    🚨 이 값을 공개 발행물에 싣지 말 것 — 본인 이용 한정.
    """
    if not tk or re.fullmatch(r"\d{6}", tk):
        return None
    doc = _fetch_json(f"{RAILWAY}/us_quotes?tickers={urllib.parse.quote(tk)}", None)
    q = ((doc or {}).get("quotes") or {}).get(tk.upper())
    if not isinstance(q, dict) or not q.get("price"):
        return None
    out = {
        "현재가": q.get("price"), "전일종가": q.get("prev_close"),
        "등락": q.get("change"),
        "등락률": (f"{float(q['change_pct']):+.2f}%"
                 if q.get("change_pct") is not None else None),
        "거래량": q.get("volume"), "거래대금": q.get("amount"),
        "통화": q.get("currency"), "거래소": q.get("excd"),
        "_asof": (doc or {}).get("asof"),
        "_note": "KIS 해외 현재체결가 · 오퍼레이터 본인 이용 · 재배포 금지",
    }
    return {k: v for k, v in out.items() if v is not None}


def _us_quote(tk: str) -> Optional[Dict[str, Any]]:
    """US 시세·최근 5봉 — 발행물이 아니라 **연결된 소스 실호출**.

    🚨 2026-08-09 PM 지적으로 신설. 그 전까지 US 조회는 가격 축이 0 이었고, 나는 그걸
      "us_chart_history(Blob·월 1회) 배선이 필요한 신규 과제" 로 보고했다. 틀린 판정이다.
      이 챗의 설계는 **조인이 천장이 아니다** — 발행물로 못 채우는 축은 그 자리에서
      연결된 소스를 실호출해 채운다. 발행 파이프라인을 기다릴 이유가 없다.
      (같은 날 JEPQ 분석에서 내가 손으로 야후를 호출해 답을 만들었으면서, 정작 코드에는
       "가격 언급 금지" 가드를 넣었다. 손으로 되는 걸 코드가 못 하게 한 셈이다.)

    의존성 0(urllib) — yfinance 를 쓰지 않는 이유는 Vercel operator_core 복제본이
    같은 파일을 그대로 배포하기 때문이다. 실패는 None — 한 소스가 죽어도 조인은 산다.
    KIS 와 무관하므로 RULE 1 영향 0(토큰 발급 경로 아님).
    """
    if not tk or re.fullmatch(r"\d{6}", tk):
        return None  # KR 은 KIS 실시간 + 금융위 일봉이 담당
    doc = _fetch_json(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(tk)}"
        "?range=1mo&interval=1d",
        None,  # 가격은 캐시하지 않는다 — 신선도가 이 섹션의 존재 이유
        {"User-Agent": "Mozilla/5.0"},
    )
    try:
        res = ((doc or {}).get("chart") or {}).get("result") or []
        meta = res[0]["meta"]
        ts = res[0]["timestamp"]
        q = res[0]["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        return None
    px = meta.get("regularMarketPrice")
    if px is None:
        return None
    closes = [(t, c) for t, c in zip(ts, q.get("close") or []) if c is not None]
    if not closes:
        return None
    out: Dict[str, Any] = {"현재가": round(float(px), 4)}
    if len(closes) >= 2:
        prev = closes[-2][1]
        out["전일종가"] = round(float(prev), 4)
        out["등락률"] = f"{(float(px) / float(prev) - 1) * 100:+.2f}%"
    last_dt = datetime.fromtimestamp(int(meta.get("regularMarketTime") or closes[-1][0]), _KST)
    out["기준"] = _us_session_label(meta, last_dt)
    out.update({
        "통화": meta.get("currency"), "거래소": meta.get("exchangeName"),
        "52주고(장중)": meta.get("fiftyTwoWeekHigh"), "52주저(장중)": meta.get("fiftyTwoWeekLow"),
        "거래량": meta.get("regularMarketVolume"),
        "최근 5봉 [일,종가,거래량]": [
            [datetime.fromtimestamp(int(t), _KST).strftime("%Y%m%d"), round(float(c), 4),
             (q.get("volume") or [None])[ts.index(t)] if t in ts else None]
            for t, c in closes[-5:]
        ],
        "_as_of": last_dt.isoformat(timespec="seconds"),
        "_note": "야후 파이낸스 · 오퍼레이터 본인 이용, 재배포 금지",
    })
    return {k: v for k, v in out.items() if v is not None}


def _us_session_label(meta: Dict[str, Any], last_dt: datetime) -> str:
    """미국장 개폐 상태 + 그 값이 '장중가' 인지 '종가' 인지를 못 박아 돌려준다.

    🚨 2026-08-15 사고 고정. KST 09:24 에 SPCX 를 조회해 "미국 실시간 시세" 섹션의
    $140.00 을 현재가로 답했다. 실제는 8/14 종가다(`regularMarketTime` = 8/14 20:00 UTC
    = 16:00 ET). 미국장은 KST 22:30~05:00 이라 **한국 낮 시간 조회는 항상 마감 후**인데,
    섹션 제목이 "실시간" 이라 라벨만 보고 넘어갔다. 기존 `age_d` 판정도 KST 일자 차이로
    계산돼 05:00 종가를 "(당일)" 로 표시했다 — 틀린 위안이었다.

    판정은 시계 계산이 아니라 **야후가 주는 `currentTradingPeriod`** 로 한다.
    EDT/EST 전환을 우리가 흉내 낼 이유가 없고, 소스가 이미 정답을 준다.
    [[feedback_verify_by_load_bearing_not_surprise]] 규칙 2의 코드 강제분.
    """
    ctp = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    start, end = ctp.get("start"), ctp.get("end")
    off = ctp.get("gmtoffset")
    sess = ""
    if end is not None and off is not None:
        # 거래소 현지(ET) 기준 세션 일자 — KST 일자로 말하면 하루 어긋난다.
        sess = datetime.utcfromtimestamp(int(end) + int(off)).strftime("%Y-%m-%d")
    now_ep = int(_now().timestamp())
    if start is not None and end is not None:
        if int(start) <= now_ep <= int(end):
            return f"미국장 개장 중 · 장중 체결가 ({sess} ET 세션)"
        if now_ep < int(start):
            return f"미국장 개장 전 · 직전 거래일 종가 (다음 세션 {sess} ET)"
        return f"🚨 미국장 마감 · **{sess} (ET) 종가** — 현재가 아님"
    return f"미국장 개폐 판정 불가 · 최종 체결 {last_dt.strftime('%Y-%m-%d %H:%M KST')}"


# ── private bucket ───────────────────────────────────────────────────────────
def _realtime(tk: str) -> Optional[Dict[str, Any]]:
    """KIS 실시간 시세 (오퍼레이터 본인 이용). 미도달/장 마감이면 None — 조인을 막지 않는다.

    🚨 이 값을 공개 발행물에 싣지 말 것. 공개 경로의 평가 기준가는 T+1 kr_close_latest 유지.
    """
    if not re.fullmatch(r"\d{6}", tk or ""):
        return None  # v1 = KR 6자리만
    doc = _fetch_json(f"{RAILWAY}/quotes?tickers={tk}", None)
    q = ((doc or {}).get("quotes") or {}).get(tk)
    if not isinstance(q, dict) or not q.get("price"):
        return None
    out: Dict[str, Any] = {
        "현재가": q.get("price"),
        "전일종가": q.get("prev_close"),
        "등락": q.get("change"),
        "등락률": f"{float(q.get('change_pct', 0)):+.2f}%" if q.get("change_pct") is not None else None,
        "거래량": q.get("volume"),
        "시가": q.get("open"), "고가": q.get("high"), "저가": q.get("low"),
        "상한가": q.get("upper_limit"), "하한가": q.get("lower_limit"),
        "_asof": (doc or {}).get("asof"),
        "_note": "KIS 실시간 · 오퍼레이터 본인 이용 · 재배포 금지",
    }
    return {k: v for k, v in out.items() if v is not None}


_DART_WINDOW_DAYS = 30


def _dart_recent_filings(tk: str) -> Optional[Dict[str, Any]]:
    """OpenDART list.json 직조회 — '공시 없음'을 추정이 아니라 **단정**하기 위한 1차 소스.

    상설 배경 (PM 2026-08-03 "DART 직조회 상설로 넣어"):
      094970 +12% 급등일에 스냅샷 파일·Perplexity 모두 "공시 확인 불가"로 끝났는데,
      직조회는 1초 만에 "5/14 이후 공시 0건"을 확정했다. 스냅샷은 수집 시점 기준이라
      '오늘 공시 유무'를 원리적으로 못 단정한다. 1콜/조회 = 일 2만 쿼터 대비 무시 가능.

    corp_code = data/mapping.json 파일 직접 로드 — api.collectors import 금지
    (vercel operator_core 복제본은 repo 루트 api/ 패키지를 번들에 못 가져간다).
    캐시 없이 매번 신선 호출 — 장중 신규 공시가 이 섹션의 존재 이유다.
    """
    key = os.environ.get("DART_API_KEY")
    if not key:
        return None
    mapping = _load_local("data/mapping.json")
    cc = (mapping or {}).get(tk) if isinstance(mapping, dict) else None
    if not cc:
        return None
    end = _now()
    bgn = end - timedelta(days=_DART_WINDOW_DAYS)
    url = "https://opendart.fss.or.kr/api/list.json?" + urllib.parse.urlencode({
        "crtfc_key": key, "corp_code": cc,
        "bgn_de": bgn.strftime("%Y%m%d"), "end_de": end.strftime("%Y%m%d"),
        "page_count": 20,
    })
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            doc = json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None
    status = str(doc.get("status") or "")
    window = f"{bgn.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}"
    if status == "013":  # 조회된 데이터 없음 = 그 자체가 사실
        return {"조회구간": window, "건수": 0,
                "확정": "구간 내 공시 0건 — DART 직조회 확정 (추정 아님)"}
    if status != "000":  # 010 키오류 · 020 쿼터 초과 등 — 실패는 missing 으로
        return None
    rows = []
    for it in (doc.get("list") or []):
        dt = str(it.get("rcept_dt") or "")
        rows.append({
            "date": f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}" if len(dt) == 8 else dt,
            "title": str(it.get("report_nm") or "").strip(),
            "filer": it.get("flr_nm"),
            "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + str(it.get("rcept_no") or ""),
        })
    return {"조회구간": window, "건수": int(doc.get("total_count") or len(rows)), "공시": rows[:12]}


# 일봉 청크 — api/collectors/fsc_daily_prices._chunk_idx 와 동일 규칙 (import 대신 복제 —
# vercel operator_core 사유는 위와 동일. 규칙 변경 시 양쪽 동시 수정).
_N_CHART_CHUNKS = 40


def _chunk_idx(code: str) -> int:
    try:
        return int(code, 36) % _N_CHART_CHUNKS
    except (TypeError, ValueError):
        return -1


def _daily_bars(tk: str) -> Optional[Dict[str, Any]]:
    """kr_chart_daily 청크(금융위 T+1 · 250일)에서 일봉 + 산술 파생 사실.

    2026-08-03 배선 감사: 발행돼 있는데 조인 0 이던 자산. technical 미산출(관심종목 유래)
    종목이 "MA·고저·거래량 평균조차 없음" 상태로 나오던 갭의 입력을 여기서 공급한다.
    파생은 전부 산술(사실) — MA/고저/평균거래량. 해석·신호는 상위 레이어 몫.
    """
    idx = _chunk_idx(tk)
    if idx < 0:
        return None
    doc = _fetch_json(f"{BLOB}/kr_chart_daily/chunk_{idx:02d}.json", f"chart_chunk_{idx:02d}")
    c = (((doc or {}).get("stocks") or {}).get(tk) or {}).get("c")
    if not isinstance(c, list) or len(c) < 5:
        return None
    closes = [r[4] for r in c]
    vols = [r[5] for r in c]
    last = c[-1]

    def ma(n: int) -> Optional[int]:
        return round(sum(closes[-n:]) / n) if len(closes) >= n else None

    hi = max(r[2] for r in c)
    lo = min(r[3] for r in c)
    v20 = round(sum(vols[-20:]) / min(20, len(vols)))
    out: Dict[str, Any] = {
        "기준일": str(last[0]),
        "종가": last[4],
        "보유일수": len(c),
        "기간 최고/최저": f"{hi:,} / {lo:,}",
        "고점대비": f"{(last[4] / hi - 1) * 100:+.1f}%",
        "저점대비": f"{(last[4] / lo - 1) * 100:+.1f}%",
        "MA20/60/120": " / ".join(f"{x:,}" if x else "—" for x in (ma(20), ma(60), ma(120))),
        "거래량 20일평균": v20,
        "최근 5봉 [일,시,고,저,종,량]": c[-5:],
        "_note": "금융위 일봉 T+1 · MA/고저/평균거래량 = 산술 자체계산 (해석 아님)",
        "_as_of": str((doc or {}).get("as_of") or ""),
    }
    return out


def _private_json(path: str) -> Optional[Any]:
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        return None
    bucket = os.environ.get("OPERATOR_BUCKET", "verity-reports")
    full = f"{url}/storage/v1/object/{bucket}/{urllib.parse.quote(path)}"
    return _fetch_json(full, None, {"apikey": key, "Authorization": f"Bearer {key}"})


# ── 메인 ─────────────────────────────────────────────────────────────────────
PAST_DECISIONS_LIMIT = 5


def past_decisions_section(tk: str, limit: int = PAST_DECISIONS_LIMIT,
                           path: Optional[str] = None):
    """(섹션 dict | None, 오류 문구 | None) — 같은 종목의 과거 판단.

    🚨 왜 조인하나 (2026-08-09): 이게 없으면 매 질의가 처음이다. 사실을 아무리 잘 모아도
    "3개월 전에 뭐라고 했고 결과가 어땠나" 를 모르면 정보량만 많은 단발성 판단이다.
    도서관(사실)·학술지(검증)에 없던 **실험 노트** 자리다.

    · 기록이 없으면 섹션을 만들지 않는다 — 빈 섹션은 "없는 것을 넣지 않는다" 규율 위반이고,
      0 건을 있는 척하면 판단이 흔들린다.
    · 조회 실패는 삼키지 않고 문구로 돌려준다(호출부가 missing 에 남긴다).
    · 🚨 단 **모듈 부재는 실패가 아니다.** 이 파일은 sync_operator_ask.sh 로 vercel-api 에
      복제되는데 decision_journal 은 복제 대상이 아니다(실험 노트는 터미널 전용·비공개).
      배포본에서 ModuleNotFoundError 를 "실패" 로 보고하면 매 조회마다 없는 결함이 뜬다.
    · 지연 임포트 = 순환 차단(decision_journal → operator_ask → ticker_facts).
    """
    # 🚨 2026-08-12 fix — 임포트 경로 3단.
    #   스킬의 기본 명령이 `python3 api/intelligence/operator_ask.py` = **스크립트 모드**라
    #   sys.path[0] 이 이 디렉토리이고 repo 루트가 없다. 절대 임포트만 두면 여기서
    #   ImportError 가 나고, 아래 "배포본엔 없음" 분기가 그걸 삼켜 **주 경로에서 섹션이
    #   조용히 사라졌다**(2026-08-11 실측: collect 32섹션 / CLI 출력 31섹션).
    #   operator_ask 가 ticker_facts 에 쓰는 폴백 패턴과 동일하게 맞춘다.
    try:
        from api.intelligence import decision_journal as _dj   # 패키지 컨텍스트
    except ImportError:
        try:
            import decision_journal as _dj                     # 스크립트 모드
        except ImportError:
            return None, None  # 이 배포에는 실험 노트가 없다 — 설계상 정상(vercel 복제본)
    try:
        past = _dj.read_recent(tk, limit=limit, path=path)
    except Exception as e:  # noqa: BLE001
        return None, f"과거 판단 조회 실패 ({type(e).__name__})"
    if not past:
        return None, None
    return {
        "label": "과거 판단 (실험 노트 · 오퍼레이터)",
        "source": "private:decisions/verdicts.jsonl",
        "as_of": str(past[0].get("ts_kst") or "")[:10],
        "data": [{
            "ts": str(p.get("ts_kst") or "")[:16],
            "verdict": p.get("verdict"),
            "confidence": p.get("confidence"),
            "ref_price": p.get("ref_price"),
            "basis_axes": p.get("basis_axes"),
            "brain_verdict": p.get("brain_verdict"),
            "scored": p.get("scored"),
            "brief": p.get("reasoning_brief"),
        } for p in past],
    }, None


def collect(query: str, include_private: bool = True) -> Dict[str, Any]:
    """종목 하나에 대한 전 소스 사실 조인.

    반환 = {ticker, name, sections:[{label, source, as_of, data}], missing:[...], _meta}
    """
    tk, nm = resolve_ticker(query)
    out: Dict[str, Any] = {
        "query": query, "ticker": tk, "name": nm,
        "sections": [], "missing": [],
        "_meta": {"collected_at": _now().isoformat(timespec="seconds"),
                  "note": "사실 조인만 — 판단·전망·추천 없음(RULE 7). 오퍼레이터 전용."},
    }
    if not tk:
        out["missing"].append(f"종목 해석 실패: {query!r} — 유니버스에 없음")
        return out

    def _add(label: str, source: str, doc: Any, data: Any) -> None:
        if data in (None, {}, []):
            out["missing"].append(f"{label} ({source})")
            return
        out["sections"].append({
            "label": label, "source": source, "as_of": _meta_as_of(doc), "data": data,
        })

    # 1) 공개 발행물 — 병렬 fetch
    # 🚨 2026-08-06 전송량 fix (Vercel 과금 대응): 이전엔 종목 1건 조회에 발행물 **전체 35개
    # · 73.8MB** 를 내려받았다. 그중 US 전용 10개(27.0MB)는 KR 종목 조회에 전혀 쓰이지
    # 않고, KR 전용 파일도 US 조회엔 무용이다. 시장을 보고 필요한 것만 받는다.
    # 기능 손실 0 — 해당 시장에서 애초에 매칭되지 않던 파일만 제외한다.
    # (event_study 21.1MB 는 KR·US 공용이라 여기서 제외 대상 아님 — 청크 분할이 별건 과제.)
    _is_us_q = not re.fullmatch(r"\d{6}", str(tk or ""))
    def _needed(fname: str) -> bool:
        if fname.startswith("us_"):
            return _is_us_q                    # US 전용 → US 조회에만
        if fname.startswith(("kr_", "dart_")):
            return not _is_us_q                # KR 전용 → KR 조회에만
        return True                            # 공용(event_study 등)은 항상
    _scan = [f for f in SCAN_FILES if _needed(f)]
    _skipped = len(SCAN_FILES) - len(_scan)
    urls = [(f, lab) for f, lab in CORE_FILES if _needed(f)] + [(f, f[:-5]) for f in _scan]
    docs: Dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_fetch_json, f"{BLOB}/{f}", f.replace("/", "_")): f for f, _ in urls}
        for fut, f in futs.items():
            try:
                docs[f] = fut.result()
            except Exception:
                docs[f] = None

    # 실시간 — 있으면 **가장 먼저**. 종가만 보다가 장중을 놓치는 사고 방지(2026-08-03).
    rt = _realtime(tk) if include_private else None
    if rt:
        out["sections"].append({
            "label": "실시간 시세 (KIS · 본인 이용)", "source": "railway:quotes",
            "as_of": str(rt.pop("_asof", "") or ""), "data": rt,
        })
    elif not _is_us_q:
        # 🚨 '없는 것' 은 **적용 가능한데 비어 있는** 축만 적는다(2026-08-09). US 종목에
        #   KR 전용 축(KIS 실시간·DART 직조회·금융위 일봉)을 적으면 "찾아봤는데 없더라" 로
        #   읽혀 실제보다 결손이 커 보인다. 애초에 해당되지 않는 축은 침묵이 정직하다.
        out["missing"].append("실시간 시세 (KIS — 미도달·장 마감)")

    # US 시세 — 발행물이 아니라 연결 소스 실호출. KR 의 (KIS 실시간 + 금융위 일봉) 2층에 대응한다.
    #   ① KIS 해외 현재체결가 = 장중 현재가. ② 야후 = 최종 체결일 + 5봉 + 52주 고저.
    #   🚨 둘을 섞지 말 것 — ①이 있으면 그게 '지금', ②는 '마지막 마감' 이다(SKILL.md 규율 2 정합).
    if _is_us_q:
        urt = _us_realtime(tk) if include_private else None
        uq = _us_quote(tk)
        # 🚨 KIS 섹션 라벨이 "실시간" 이라 한국 낮 시간 조회에서 종가를 현재가로 읽는 사고가
        #    났다(2026-08-15 SPCX). 미국장은 KST 22:30~05:00 이라 한국 업무시간 조회는
        #    **항상 마감 후**다. 야후가 판정한 세션 상태를 KIS 섹션 라벨에도 그대로 얹어
        #    라벨만 보고도 틀릴 수 없게 한다.
        sess = (uq or {}).get("기준") or ""
        closed = "마감" in sess or "개장 전" in sess
        if urt:
            urt["기준"] = sess or "미국장 개폐 판정 불가 (야후 미응답)"
            out["sections"].append({
                "label": ("미국 시세 (KIS · 본인 이용) — 🚨 장 마감, 직전 거래일 종가"
                          if closed else "미국 실시간 시세 (KIS · 본인 이용) — 장중"),
                "source": "railway:us_quotes",
                "as_of": str(urt.pop("_asof", "") or ""), "data": urt,
            })
        if uq:
            out["sections"].append({
                "label": "미국 시세·일봉 (야후 실호출)", "source": "yahoo:chart",
                "as_of": str(uq.pop("_as_of", "") or ""), "data": uq,
            })
        elif not urt:
            out["missing"].append("미국 시세 (KIS 해외·야후 둘 다 실패 — 티커 오류·네트워크)")

        # SEC EDGAR 직조회 — KR 의 DART 직조회에 대응하는 상설 배선 (2026-08-12 신설).
        #   기존 `us_disclosure_feed` 는 8-K 만 수집해 10-Q/10-K/S-1/424B* 가 조인 밖이었다.
        #   SWMR 조회에서 재무·완전희석·락업 만기·유동성 라인이 **전부 사각지대**로 드러났고,
        #   그중 완전희석 결손은 시총을 2배 과소 계상시켰다(발행주식 $426M vs 완전희석 $863M).
        #   유니버스 파일에 의존하지 않으므로 커버리지 밖 신규 상장도 즉시 답이 나온다.
        #   import 은 operator_ask 와 같은 이중 경로다 — 스크립트 직접 실행 시 이 파일은
        #   패키지가 아니라 최상위 모듈로 로드되므로 `api.intelligence.*` 가 풀리지 않는다
        #   (2026-08-12 실측: 절대 import 하나만 두었더니 CLI 에서 조용히 섹션이 통째로 빠졌다).
        _ufp = None
        try:
            from . import us_filing_probe as _ufp  # type: ignore[attr-defined]
        except ImportError:  # noqa: BLE001
            try:
                import us_filing_probe as _ufp  # type: ignore[no-redef]
            except ImportError:
                _ufp = None
        try:
            sec = _ufp.probe(tk) if _ufp else None
        except Exception:  # noqa: BLE001
            sec = None
        if sec:
            cap = sec.pop("_capital", None)
            # 시총 사다리는 **실호출로 확보한 가격이 있을 때만** 만든다. 가격을 지어내지 않는다.
            px_now = None
            for _s in out["sections"]:
                if _s.get("source") in ("railway:us_quotes", "yahoo:chart"):
                    px_now = (_s.get("data") or {}).get("현재가")
                    if px_now:
                        break
            if cap and px_now:
                lad = _ufp.market_cap_ladder(cap, float(px_now))
                if lad and isinstance(sec.get("자본구조"), dict):
                    sec["자본구조"]["시가총액 (종가 × 주식수)"] = lad
            out["sections"].append({
                "label": f"SEC 공시·자본구조 (직조회 · {_ufp.WINDOW_DAYS}일)",
                "source": "sec:submissions+companyfacts",
                "as_of": _now().isoformat(timespec="seconds"), "data": sec,
            })
        elif _is_us_q:
            out["missing"].append("SEC 직조회 (CIK 미해석·호출 실패 — 미국 상장사가 아닐 수 있음)")

    # 종가 — 전 종목 동일 거래일(kr_close_latest). 등락은 prev 있을 때만.
    d = docs.get("kr_close_latest.json")
    if isinstance(d, dict):
        px = (d.get("prices") or {}).get(tk)
        prev = (d.get("prev") or {}).get(tk)
        if px:
            blk: Dict[str, Any] = {"종가": px}
            if prev:
                blk["전일종가"] = prev
            # 등락률 = 발행본 chg 우선(원천 fltRt=수정주가 기준). 자본변경 종목은 발행에서 빠지므로
            # 차분 재계산 금지 — 플루토스 +380% 같은 거짓이 되살아난다(2026-08-03).
            cg = (d.get("chg") or {}).get(tk)
            if cg is not None:
                blk["등락률"] = f"{float(cg):+.2f}%"
            _add("종가 (T+1 · 실시간 아님)", "kr_close_latest.json", d, blk)
        else:
            out["missing"].append("종가 (kr_close_latest.json — 당일 미거래·비수록)")

    # DART 공시 직조회 — 상설 (PM 2026-08-03). "0건" 도 사실 — 급변 사유 판단의 1차 관문.
    df = _dart_recent_filings(tk)
    if df is not None:
        out["sections"].append({
            "label": f"DART 공시 (직조회 · {_DART_WINDOW_DAYS}일)", "source": "opendart:list.json",
            "as_of": _now().isoformat(timespec="seconds"), "data": df,
        })
    elif not _is_us_q:
        out["missing"].append("DART 공시 직조회 (키 없음·corp_code 미해석·호출 실패)")

    # 일봉 250일 + 산술 파생 (금융위 T+1) — 2026-08-03 배선 감사로 추가.
    bars = _daily_bars(tk)
    if bars is not None:
        out["sections"].append({
            "label": "일봉 (250일 · 산술 파생)", "source": "kr_chart_daily/chunk (금융위)",
            "as_of": bars.pop("_as_of", ""), "data": bars,
        })
    elif not _is_us_q:
        out["missing"].append("일봉 청크 (kr_chart_daily — 비수록·미도달)")

    # 리포트 — facts/peer/재무 등 큰 블록이라 필요한 것만
    d = docs.get("stock_report_public.json")
    rep = _extract_for_ticker(d, tk)
    if isinstance(rep, list):
        rep = rep[0] if rep else None
    if isinstance(rep, dict):
        _add("리포트(사실)", "stock_report_public.json", d, {
            k: rep.get(k) for k in
            ("name", "market", "business", "facts", "facts_note", "peer", "overview",
             "real_estate", "financials", "dividend", "calendar", "disclosures", "ownership")
            if rep.get(k)
        })

    # 수급 — 회전 수집이라 **가격 용도 금지**(2026-08-01). 순매매만 쓴다.
    d = docs.get("stock_flow_5d.json")
    ser = _extract_for_ticker(d, tk)
    if isinstance(ser, list) and ser:
        _add("수급(외국인·기관 순매매)", "stock_flow_5d.json", d,
             {"_note": "회전 수집 — close 는 평가 기준가로 쓰지 말 것",
              "series": [{k: r.get(k) for k in ("date", "foreign_net", "inst_net")} for r in ser[-6:]]})

    # 분기 추이
    d = docs.get("dart_quarterly_public.json")
    q = _extract_for_ticker(d, tk)
    if isinstance(q, dict) and q.get("quarters"):
        qs = q["quarters"]
        _add("분기 추이(DART)", "dart_quarterly_public.json", d,
             {"_note": f"{len(qs)}분기 보유", "recent": qs[-8:]})

    # 나머지 발행물 — 제네릭
    for f in SCAN_FILES:
        d = docs.get(f)
        got = _extract_for_ticker(d, tk)
        if got:
            _add(f[:-5], f, d, _trim(got))

    # 2) 로컬 미발행
    # 🚨 시장 게이팅은 발행물(_needed)과 같은 규칙을 로컬에도 건다. 2026-08-09 에 US 3종·DART
    #   심화 4종을 추가하며 넣었다 — 없으면 KR 조회 1건마다 us_form144(2.1MB)·us_fin_annual
    #   (4.5MB)까지 매번 파싱해 애초에 매칭될 수 없는 파일에 시간을 쓴다(2026-08-06 전송량 fix 동형).
    for rel, label, is_map in LOCAL_FILES:
        if not _needed(os.path.basename(rel)):
            continue
        d = _load_local(rel)
        if d is None:
            continue
        got = (d.get(tk) if isinstance(d, dict) and is_map else None) or _extract_for_ticker(d, tk)
        if got:
            _add(label, rel, d, _trim(got))

    # 3) 오퍼레이터 private
    if include_private:
        for path, label in PRIVATE_FILES:
            d = _private_json(path)
            if d is None:
                continue
            got = _extract_for_ticker(d, tk)
            if got:
                _add(label, f"private:{path}", d, _trim(got))

    # 4) 과거 판단 (실험 노트) — 2026-08-09
    if include_private:
        sec, err = past_decisions_section(tk)
        if err:
            out["missing"].append(err)
        elif sec:
            out["sections"].append(sec)

    # 5) 🚨 가격 축 부재 신고 (2026-08-09) — 이 레이어가 존재하는 이유가 가격 환각 차단인데
    #   (2026-06-03 삼성전자 "65,000원 지지선"), US 조회는 시세·일봉이 **한 축도 배선돼 있지
    #   않다**. 그런데 위 시장 게이팅으로 KR 전용 결손을 침묵시키고 나니 US ETF 가 "섹션 1 ·
    #   없는 것 0" 으로 나와 **결손이 아예 없는 것처럼** 읽힌다 — 조용한 누락의 반대 방향
    #   함정이다. 가격이 안 잡혔으면 반드시 명시한다. 소비자(LLM 포함)가 "가격은 모른다" 를
    #   알아야 지어내지 않는다.
    _PRICE_LABELS = ("실시간 시세", "종가", "일봉", "미국 시세")
    if not any(str(s.get("label", "")).startswith(_PRICE_LABELS) for s in out["sections"]):
        out["missing"].append(
            "시세·일봉 — 이 종목의 가격 축이 하나도 잡히지 않았다. "
            "🚨 기억으로 가격을 지어내지 말 것. **연결된 소스를 직접 실호출해 채워라** "
            "(야후 chart API·KIS overseas_price·웹). 조인은 바닥이지 천장이 아니다 — "
            "발행물에 없다고 '모른다' 로 끝내면 그건 배선 핑계다"
        )

    return out


def _fmt_num(v: Any) -> str:
    if isinstance(v, bool):
        return "예" if v else "아니오"
    if isinstance(v, float) and v == int(v):
        v = int(v)
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def _fmt_data(d: Any, depth: int = 0) -> List[str]:
    """섹션 데이터 사람화 (PM 2026-08-04 'JSON 코드 형식으로 나옴' 수정).
    dict = 'k: v · k: v' 한 줄 / dict 배열 = 행당 한 줄(최근 4행 + 외 N) / 스칼라 배열 = 나열."""
    if isinstance(d, dict):
        parts = []
        long_items: List[str] = []
        items = list(d.items())
        for k, v in items[:20]:
            if isinstance(v, (dict, list)):
                inner = _fmt_data(v, depth + 1)
                long_items.append(f"- {k}:")
                long_items.extend("  " + x for x in inner)
            else:
                parts.append(f"{k} {_fmt_num(v)}")
        out = []
        if parts:
            out.append(" · ".join(parts))
        out.extend(long_items)
        if len(items) > 20:
            out.append(f"  (미표시 키 {len(items) - 20}: {', '.join(k for k, _ in items[20:26])})")
        return out or ["(빈 값)"]
    if isinstance(d, list):
        if not d:
            return ["(빈 목록)"]
        if all(isinstance(x, dict) for x in d):
            # 🚨 단일 레코드는 시계열이 아니라 '그 종목 사실 한 벌' 이다. 아래 행 포맷으로 접으면
            #   중첩 필드가 통째로 사라진다 — 2026-08-09 JEPQ 사고: 구성종목·섹터·자산배분·배당률·
            #   3년수익률이 전부 렌더에서 증발했는데 화면상으로는 멀쩡한 섹션으로 보였다.
            #   조인은 성공했는데 출력에서 잃는 형태라 "배선 0" 보다 발견이 늦다.
            if len(d) == 1:
                return _fmt_data(d[0], depth)
            rows = d[-4:] if depth == 0 else d[:10 if depth == 1 else 3]  # 시계열 = 최근 우선
            out = []
            for x in rows:
                flat = [(k, v) for k, v in x.items() if not isinstance(v, (dict, list))]
                line = "- " + " · ".join(f"{k} {_fmt_num(v)}" for k, v in flat[:8])
                # 잘라낸 것은 반드시 신고한다. 조용한 누락 = 없는 것보다 나쁘다.
                dropped = [k for k, _ in flat[8:]] + [k for k, v in x.items()
                                                      if isinstance(v, (dict, list))]
                if dropped:
                    line += f"  (미표시 {len(dropped)}: {', '.join(dropped[:6])})"
                out.append(line)
            rest = len(d) - len(rows)
            if rest > 0:
                out.append(f"  (외 {rest}행)")
            return out
        vals = ", ".join(_fmt_num(x) for x in d[:12])
        return [vals + (f" (외 {len(d)-12})" if len(d) > 12 else "")]
    return [_fmt_num(d)]


def render_text(res: Dict[str, Any]) -> str:
    """사람이 읽는 형태 — LLM 컨텍스트로도 그대로 쓴다(출처·기준일 포함)."""
    L: List[str] = []
    head = f"{res.get('name') or '?'} ({res.get('ticker') or '해석실패'})"
    L.append(f"# {head}")
    L.append(f"수집 {res['_meta']['collected_at']} · 섹션 {len(res['sections'])}개")
    L.append("")
    for sec in res["sections"]:
        stamp = f" · 기준 {sec['as_of']}" if sec.get("as_of") else ""
        L.append(f"## {sec['label']}  [{sec['source']}{stamp}]")
        L.extend(_fmt_data(sec["data"]))
        L.append("")
    if res["missing"]:
        L.append("## 없는 것 (지어내지 말 것)")
        for m in res["missing"]:
            L.append(f"- {m}")
    return "\n".join(L)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="종목 사실 조인 (오퍼레이터 전용)")
    ap.add_argument("query", help="종목명 또는 6자리 코드")
    ap.add_argument("--json", action="store_true", help="JSON 출력")
    ap.add_argument("--no-private", action="store_true", help="private bucket 제외")
    a = ap.parse_args()
    r = collect(a.query, include_private=not a.no_private)
    print(json.dumps(r, ensure_ascii=False, indent=1) if a.json else render_text(r))
