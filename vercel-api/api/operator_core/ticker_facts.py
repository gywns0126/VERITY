# -*- coding: utf-8 -*-
"""TickerFacts — 종목 하나에 대해 **우리가 가진 모든 사실**을 한 번에 조인하는 단일 레이어.

🚨 왜 만들었나 (2026-08-03 PM 지시)
  종목 질문 하나에 답하려고 kr_close_latest·stock_report_public·stock_flow_5d·
  dart_quarterly_public·공시피드·일봉청크를 매번 손으로 뒤졌다. 더 나쁜 건 소비자마다
  다른 걸 봐서 답이 달라진 것 — 배리티 챗(chat_hybrid)은 발행물 JSON 을 **0건** 조인하고
  Brain/Perplexity/Gemini 만 붙였다. 그래서 유니버스 밖 종목에서 LLM 기억으로 가격을
  지어내는 사고가 났다(2026-06-03 삼성전자 "65,000원 지지선", 실제 ~365,000원).
  → 조인은 **여기 한 곳**에만 둔다. 소비자(오퍼레이터 CLI·배치 빌더·챗)는 이걸 호출한다.

수집 범위 = 공개 발행물(Blob) + 로컬 data/ 미발행 + 오퍼레이터 private bucket.
  · 공개 Blob = 큐레이트 목록 + **제네릭 스캔**(신규 발행물이 늘어도 코드 수정 없이 잡힘).
  · private = Supabase `verity-reports/_operator/*` (service_role). 키 없으면 조용히 skip.

🚨 출력 규율
  · 모든 값에 **출처 파일 + 기준일**을 붙인다. 없는 정밀도를 있는 척하지 않는다.
  · 없는 항목은 넣지 않는다(0 으로 위장 금지 — 2026-08-03 ROE 0% 사고 계열).
  · 이 레이어는 **사실만** 모은다. 판단·전망·추천은 상위(오퍼레이터 종합)에서만.
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
]

# 오퍼레이터 private bucket (Supabase). 인증 없으면 skip.
PRIVATE_FILES = [
    ("_operator/portfolio_full.json", "포트폴리오(비공개)"),
    ("_operator/tri_synthesis.json", "3종 LLM 배치 종합(비공개)"),
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
    exact, prefix, part = [], [], []
    for r in rows:
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
    # US 심볼 패스스루 폴백 (2026-08-03 배선 감사) — 해석이 KR 전용이라 GOOGL 등 US 심볼이
    # 여기서 죽어 전 섹션 조인 0 이 되던 갭. KR 이름 매칭이 전부 실패했을 때만 진입하므로
    # 한글 질의 동작은 불변. 이름은 us_stock_names_ko(네이버 수집) 있으면 한글, 없으면 심볼.
    u = s.upper()
    if re.fullmatch(r"[A-Z]{1,5}([.-][A-Z])?", u):
        ko = _load_local("data/us_stock_names_ko.json")
        nm = ((ko or {}).get("names") or {}).get(u) if isinstance(ko, dict) else ""
        return u, str(nm or u)
    return "", ""


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
    urls = [(f, lab) for f, lab in CORE_FILES] + [(f, f[:-5]) for f in SCAN_FILES]
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
    else:
        out["missing"].append("실시간 시세 (KIS — 미도달·장 마감·비KR)")

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
    else:
        out["missing"].append("DART 공시 직조회 (키 없음·corp_code 미해석·호출 실패)")

    # 일봉 250일 + 산술 파생 (금융위 T+1) — 2026-08-03 배선 감사로 추가.
    bars = _daily_bars(tk)
    if bars is not None:
        out["sections"].append({
            "label": "일봉 (250일 · 산술 파생)", "source": "kr_chart_daily/chunk (금융위)",
            "as_of": bars.pop("_as_of", ""), "data": bars,
        })
    else:
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
    for rel, label, is_map in LOCAL_FILES:
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
        for k, v in list(d.items())[:20]:
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
        return out or ["(빈 값)"]
    if isinstance(d, list):
        if not d:
            return ["(빈 목록)"]
        if all(isinstance(x, dict) for x in d):
            rows = d[-4:] if depth == 0 else d[:3]   # 시계열 = 최근 우선
            out = []
            for x in rows:
                out.append("- " + " · ".join(f"{k} {_fmt_num(v)}" for k, v in list(x.items())[:8]
                                             if not isinstance(v, (dict, list))))
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
