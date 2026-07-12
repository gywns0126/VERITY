"""KR↔US 교차피어 (Tier B B-5) — GICS 섹터 공통축 교차시장 중앙값 헬퍼.

각 리포트 빌더가 (1) 자기 시장 종목을 표준 11 GICS 섹터로 태깅하고 (2) 자기 시장의
GICS 섹터별 중앙값 파일을 출력한다. 프론트는 **반대 시장** 중앙값 파일을 읽어 현재 종목과
비교한다 (KR 종목 → US 중앙값, US 종목 → KR 중앙값). 두 빌더가 서로의 산출물을 읽지 않아
빌드 순서·경합 의존이 없다.

RULE 7 = 사실(중앙값·표본수 N)만 노출, 자체 등급·추천 0.
비교 지표 = PER/PBR/ROE/영업이익률 4종. 부채 지표는 KR 부채비율(%)과 US D/E(배율)의 단위·정의가
달라 교차 비교에서 제외 (사과-오렌지 방지).
US GICS = us_sector_cache(yfinance .info 실측) 우선 → 미캐시분은 SIC 2자리 근사 폴백(정직 표기).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 교차 비교 지표 (라벨, 접미사, 소수자릿수). KR/US 공통 단위 4종만.
CROSS_METRICS = [("PER", "", 1), ("PBR", "", 1), ("ROE", "%", 1), ("영업이익률", "%", 1)]

# 표준 11 GICS 섹터 (yfinance .info sector) 영문 → 한글.
# kr_sector_map.sector 와 us_sector.get_ticker_sector 가 공유하는 동일 축.
GICS_KO = {
    "Technology": "기술",
    "Communication Services": "커뮤니케이션",
    "Consumer Cyclical": "경기소비재",
    "Consumer Defensive": "필수소비재",
    "Financial Services": "금융",
    "Healthcare": "헬스케어",
    "Industrials": "산업재",
    "Energy": "에너지",
    "Basic Materials": "소재",
    "Real Estate": "부동산",
    "Utilities": "유틸리티",
}

# SIC 2자리 대분류 → GICS 영문 (us_sector_cache 미스 시 폴백). 섹터 단위 근사 —
# 캐시(실측 yfinance GICS)가 주요사를 커버하고, 이 폴백은 미캐시 tail 만 처리한다.
SIC2_TO_GICS = {
    "01": "Consumer Defensive", "02": "Consumer Defensive", "07": "Consumer Defensive",
    "08": "Basic Materials", "09": "Consumer Defensive",
    "10": "Basic Materials", "12": "Energy", "13": "Energy", "14": "Basic Materials",
    "15": "Industrials", "16": "Industrials", "17": "Industrials",
    "20": "Consumer Defensive", "21": "Consumer Defensive", "22": "Consumer Cyclical",
    "23": "Consumer Cyclical", "24": "Basic Materials", "25": "Consumer Cyclical",
    "26": "Basic Materials", "27": "Communication Services", "28": "Basic Materials",
    "29": "Energy", "30": "Basic Materials", "31": "Consumer Cyclical", "32": "Basic Materials",
    "33": "Basic Materials", "34": "Industrials", "35": "Industrials", "36": "Technology",
    "37": "Consumer Cyclical", "38": "Healthcare", "39": "Consumer Cyclical",
    "40": "Industrials", "41": "Industrials", "42": "Industrials", "44": "Industrials",
    "45": "Industrials", "46": "Energy", "47": "Industrials", "48": "Communication Services",
    "49": "Utilities",
    "50": "Consumer Cyclical", "51": "Consumer Defensive",
    "52": "Consumer Cyclical", "53": "Consumer Cyclical", "54": "Consumer Defensive",
    "55": "Consumer Cyclical", "56": "Consumer Cyclical", "57": "Consumer Cyclical",
    "58": "Consumer Cyclical", "59": "Consumer Cyclical",
    "60": "Financial Services", "61": "Financial Services", "62": "Financial Services",
    "63": "Financial Services", "64": "Financial Services", "65": "Real Estate",
    "67": "Financial Services",
    "70": "Consumer Cyclical", "72": "Consumer Cyclical", "73": "Technology",
    "75": "Consumer Cyclical", "78": "Communication Services", "79": "Consumer Cyclical",
    "80": "Healthcare", "81": "Industrials", "82": "Consumer Cyclical", "83": "Healthcare",
    "86": "Industrials", "87": "Industrials", "89": "Industrials",
}

# SIC 4자리 override — 2자리 대분류가 GICS 를 크게 오분류하는 고빈도 케이스만 교정 (2자리보다 우선).
SIC4_TO_GICS = {
    "6798": "Real Estate",  # REIT (SIC 67 대분류=지주·투자=금융이나 REIT 실체=부동산)
    "2833": "Healthcare", "2834": "Healthcare", "2835": "Healthcare", "2836": "Healthcare",  # 제약·바이오 (28 대분류=화학=소재)
    "3570": "Technology", "3571": "Technology", "3572": "Technology", "3575": "Technology",
    "3576": "Technology", "3577": "Technology", "3578": "Technology",  # 컴퓨터·주변기기 (35 대분류=산업기계=산업재)
    "3661": "Technology", "3663": "Technology", "3669": "Technology",  # 통신장비 (36 은 이미 Technology지만 명시)
}


def normalize_gics(sector: Optional[str]) -> Optional[str]:
    """yfinance sector 문자열 → 표준 11 GICS 영문. KSIC-* 폴백/미상 = None."""
    if not sector or not isinstance(sector, str):
        return None
    return sector if sector in GICS_KO else None


_us_sector_cache: Optional[Dict[str, str]] = None


def _load_us_sector_cache() -> Dict[str, str]:
    global _us_sector_cache
    if _us_sector_cache is None:
        try:
            with open(os.path.join(_ROOT, "data", "us_sector_cache.json"), encoding="utf-8") as f:
                _us_sector_cache = json.load(f) or {}
        except (OSError, json.JSONDecodeError):
            _us_sector_cache = {}
    return _us_sector_cache


def us_ticker_gics(ticker: str, sic: Any) -> Optional[str]:
    """US 종목 GICS 영문 — yfinance 캐시(실측) 우선 → SIC 2자리 근사 폴백."""
    cache = _load_us_sector_cache()
    g = normalize_gics(cache.get((ticker or "").upper()))
    if g:
        return g
    try:
        s4 = str(int(sic)).zfill(4)
    except (ValueError, TypeError):
        s4 = str(sic or "")
    return SIC4_TO_GICS.get(s4) or SIC2_TO_GICS.get(s4[:2])


def _median(vals: List[float]) -> Optional[float]:
    vs = sorted(v for v in vals if v is not None)
    n = len(vs)
    if n == 0:
        return None
    mid = n // 2
    return vs[mid] if n % 2 else (vs[mid - 1] + vs[mid]) / 2.0


def compute_gics_medians(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """records = [{"gics": <영문>, "metrics": {label: float|None}}].
    GICS 섹터별 CROSS_METRICS 중앙값 + N. N≥5 섹터-지표만 (표본 부족 중앙값 무의미)."""
    buckets: Dict[str, Dict[str, List[float]]] = {}
    for r in records:
        g = r.get("gics")
        if not g:
            continue
        m = r.get("metrics") or {}
        b = buckets.setdefault(g, {lab: [] for lab, _s, _d in CROSS_METRICS})
        for lab, _s, _d in CROSS_METRICS:
            v = m.get(lab)
            if v is None:
                continue
            try:
                b[lab].append(float(v))
            except (ValueError, TypeError):
                pass
    out: Dict[str, Dict[str, Any]] = {}
    for g, b in buckets.items():
        med: Dict[str, float] = {}
        ns: Dict[str, int] = {}
        for lab, _s, dg in CROSS_METRICS:
            vals = b[lab]
            mv = _median(vals)
            if mv is not None and len(vals) >= 5:  # N<5 = 중앙값 무의미
                med[lab] = round(mv, dg)
                ns[lab] = len(vals)
        if med:
            out[g] = {"median": med, "ns": ns, "sector_ko": GICS_KO.get(g, g)}
    return out


def write_medians(path: str, market: str, medians: Dict[str, Dict[str, Any]],
                  generated_at: str) -> int:
    """자기 시장 GICS 섹터 중앙값 파일 출력. 반환 = 섹터 수."""
    doc = {
        "_meta": {
            "market": market,
            "generated_at": generated_at,
            "metrics": [m[0] for m in CROSS_METRICS],
            "axis": "GICS sector (yfinance .info) 공통축",
            "note": "교차시장 동종 GICS 섹터 중앙값 · N≥5 · 자체 등급 아님(RULE 7)",
        },
        "medians": medians,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    return len(medians)
