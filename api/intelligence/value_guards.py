# -*- coding: utf-8 -*-
"""value_guards — 신호 필터 F2(사이클 업종 가드)·F3(이익의 질 게이트) 평가.

사전등록 = docs/PREREG_SIGNAL_FILTERS_2026_08_04.md (PM 승인 2026-08-04 "승인하고").
RULE 7 동결 — 상수(3년/2배/0.3/0.5)·KSIC 목록 조정 = 재등록.

F2 사이클 업종 가드 (사례 = 동우팜 PER 2.0 피크 멀티플 함정):
  사이클 KSIC ∧ 피크 패턴(직전 3년 내 영업적자 존재 ∧ 당해 영업이익 > 5년 중앙값 × 2)
  → flag `cycle_peak_guard` → graham 가치 가점 무효 (감점 아님 — 싸다는 착시만 제거).
F3 이익의 질 게이트 (사례 = 제이엠티 순이익 40~50% 영업외):
  (순이익−영업이익)/|순이익| > 0.3 ∨ FCF/순이익 < 0.5 (연간)
  → flag `earnings_quality` → 가치 가점 50%.

적용점 = factors/graham.py 가점 스케일 단일 지점. 감점·재무건전성 가점 불변.
**결측 ≠ 발동** (5/20 측정 정화 원칙): 데이터 부족·API 실패·무키 = 가드 비활성. 트리거는
실측 음수/비율의 양성 증거가 있을 때만.

데이터: DART fnlttSinglAcnt 연간(reprt 11011, 파일당 3개년) + company.json induty(KSIC).
캐시 2층:
  ① data/dart_kr_cache/{corp}_{year}.json — 기존 backfill 산물(gitignore). 있으면 재사용,
     신규 fetch 도 동일 형식으로 적재 (로컬 개발 이득).
  ② data/value_guards_cache.json — 압축 파생(연도별 영업이익/순이익 + induty). git 추적이라
     CI run 간 지속 (daily_analysis*.yml broad `git add data/` 자동 포함 = RULE 4 정합).
"""
from __future__ import annotations

import json
import os
import re
import statistics
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

from api.config import DART_API_KEY, DATA_DIR, now_kst

CACHE_PATH = os.path.join(DATA_DIR, "value_guards_cache.json")
RAW_CACHE_DIR = os.path.join(DATA_DIR, "dart_kr_cache")
MAPPING_PATH = os.path.join(DATA_DIR, "mapping.json")

VERSION = "f2f3_v0"  # IC trail 분리 집계 태그 (등록 §검증 계획)

# ── 등록 상수 (LOCKED — 조정 = 재등록) ──────────────────────────────────────
# 축산/수산(01~03·10) 해운(50) 철강(24) 화학(20) 정유(19) 건설(41~42) 증권(66) 반도체(261)
CYCLE_KSIC_2 = {"01", "02", "03", "10", "19", "20", "24", "41", "42", "50", "66"}
CYCLE_KSIC_3 = {"261"}
PEAK_DEFICIT_LOOKBACK = 3
PEAK_MEDIAN_YEARS = 5
PEAK_MEDIAN_MULT = 2.0
NONOP_RATIO_MAX = 0.3
FCF_NI_MIN = 0.5

# DART 예산 보호 — 압축 캐시 적중 후엔 run 당 0콜. 첫 run 만 풀 미커버 종목 fetch.
_MAX_FETCH_PER_RUN = 200
_fetch_count = 0

_OP_NAMES = {"영업이익", "영업이익(손실)"}
_NET_NAMES = {"당기순이익", "당기순이익(손실)"}

_mapping: Optional[Dict[str, str]] = None
_cache: Optional[Dict[str, Any]] = None


def _load_json(path: str, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _get_mapping() -> Dict[str, str]:
    global _mapping
    if _mapping is None:
        _mapping = _load_json(MAPPING_PATH, {})
    return _mapping


def _get_cache() -> Dict[str, Any]:
    global _cache
    if _cache is None:
        _cache = _load_json(CACHE_PATH, {})
    return _cache


def _save_cache() -> None:
    if _cache is None:
        return
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_cache, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CACHE_PATH)


def _dart_get(endpoint: str, params: Dict[str, str]) -> Optional[Dict[str, Any]]:
    global _fetch_count
    if not DART_API_KEY or _fetch_count >= _MAX_FETCH_PER_RUN:
        return None
    _fetch_count += 1
    q = urllib.parse.urlencode({"crtfc_key": DART_API_KEY, **params})
    url = f"https://opendart.fss.or.kr/api/{endpoint}?{q}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        time.sleep(0.15)
        return data
    except Exception:  # noqa: BLE001 — 네트워크 실패 = 가드 비활성 (결측 ≠ 발동)
        return None


def _parse_amount(v: Any) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _extract_annual(raw: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, float]]:
    """fnlttSinglAcnt 연간 응답 → (영업이익 {연도: 값}, 당기순이익 {연도: 값}).

    파일당 당기/전기/전전기 3개년. CFS(연결) 우선, IS 행 없으면 OFS 폴백.
    """
    items = raw.get("list") or []
    for fs in ("CFS", "OFS"):
        op: Dict[str, float] = {}
        net: Dict[str, float] = {}
        for it in items:
            if it.get("fs_div") != fs or it.get("sj_div") not in ("IS", "CIS"):
                continue
            acct = str(it.get("account_nm") or "").strip()
            year = _parse_amount(it.get("bsns_year"))
            if year is None:
                continue
            y = int(year)
            tgt = op if acct in _OP_NAMES else (net if acct in _NET_NAMES else None)
            if tgt is None:
                continue
            for key, off in (("thstrm_amount", 0), ("frmtrm_amount", 1), ("bfefrmtrm_amount", 2)):
                amt = _parse_amount(it.get(key))
                if amt is not None:
                    tgt.setdefault(str(y - off), amt)
        if op:
            return op, net
    return {}, {}


def _fetch_annual_raw(corp: str, year: int) -> Optional[Dict[str, Any]]:
    """연간 파일 get-or-fetch — dart_kr_cache/{corp}_{year}.json (backfill 과 동일 형식·경로)."""
    path = os.path.join(RAW_CACHE_DIR, f"{corp}_{year}.json")
    cached = _load_json(path, None)
    if cached is not None:
        return cached
    raw = _dart_get("fnlttSinglAcnt.json", {
        "corp_code": corp, "bsns_year": str(year), "reprt_code": "11011"})
    if raw is None:
        return None
    try:
        os.makedirs(RAW_CACHE_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)
    except OSError:
        pass
    return raw


def _annual_series(corp: str) -> Tuple[Dict[str, float], Dict[str, float]]:
    """corp 의 연도별 영업이익/순이익 — 압축 캐시 → 로컬 raw 캐시 → DART fetch 순."""
    cache = _get_cache()
    ent = cache.get(corp) or {}
    op = dict(ent.get("op_income") or {})
    net = dict(ent.get("net_income") or {})
    cur_year = now_kst().year
    latest_fy = cur_year - 1  # 연간보고서 최신 = 전년도 (3월 제출)

    # 최신 FY 미보유 시에만 보충 (연 1회 자연 갱신). 파일당 3개년 → 2회 fetch 로 6개년.
    need_years = []
    if str(latest_fy) not in op:
        need_years.append(latest_fy)
    if len([y for y in op if int(y) >= latest_fy - (PEAK_MEDIAN_YEARS - 1)]) < PEAK_MEDIAN_YEARS:
        need_years.append(latest_fy - 3)
    fetched = False
    for y in need_years:
        raw = _fetch_annual_raw(corp, y)
        if raw is None:
            continue
        o2, n2 = _extract_annual(raw)
        if o2 or n2:
            fetched = True
        op.update({k: v for k, v in o2.items() if k not in op})
        net.update({k: v for k, v in n2.items() if k not in net})
    if fetched or (need_years and (op or net)):
        cache[corp] = {**ent, "op_income": op, "net_income": net,
                       "asof": now_kst().strftime("%Y-%m-%d")}
        _save_cache()
    return op, net


def _induty(corp: str) -> Optional[str]:
    """KSIC 업종코드 (company.json induty_code) — 압축 캐시 영구 보관 ('' = 조회했으나 없음)."""
    cache = _get_cache()
    ent = cache.get(corp) or {}
    if "induty" in ent:
        return ent["induty"] or None
    d = _dart_get("company.json", {"corp_code": corp})
    if d is None or d.get("status") != "000":
        return None  # 미조회 상태 유지 (다음 run 재시도)
    code = str(d.get("induty_code") or "").strip()
    cache[corp] = {**ent, "induty": code}
    _save_cache()
    return code or None


def _is_cycle_sector(ksic: Optional[str]) -> bool:
    if not ksic:
        return False
    return ksic[:3] in CYCLE_KSIC_3 or ksic[:2] in CYCLE_KSIC_2


def _latest_common_year(op: Dict[str, float]) -> Optional[int]:
    years = sorted((int(y) for y in op), reverse=True)
    return years[0] if years else None


def evaluate_value_guards(stock: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """KR 종목 1건 평가 → value_guards dict (KR 아니면 None). 예외 = 비활성 (결측 ≠ 발동)."""
    ticker = str(stock.get("ticker") or "")
    if stock.get("currency") == "USD" or not re.fullmatch(r"\d{6}", ticker):
        return None
    out: Dict[str, Any] = {"version": VERSION, "cycle_peak_guard": False,
                           "earnings_quality": False, "active": False}
    try:
        corp = _get_mapping().get(ticker)
        if not corp:
            out["reason"] = "no_corp_code"
            return out
        ksic = _induty(corp)
        out["ksic"] = ksic
        op, net = _annual_series(corp)
        if not op:
            out["reason"] = "no_annual_series"
            return out
        out["active"] = True
        cur = _latest_common_year(op)
        cur_op = op.get(str(cur)) if cur is not None else None

        # ── F2: 사이클 업종 ∧ 피크 패턴 ──
        if cur is not None and cur_op is not None and _is_cycle_sector(ksic):
            prior3 = [op[str(y)] for y in range(cur - 1, cur - 1 - PEAK_DEFICIT_LOOKBACK, -1)
                      if str(y) in op]
            win5 = [op[str(y)] for y in range(cur, cur - PEAK_MEDIAN_YEARS, -1) if str(y) in op]
            if any(v < 0 for v in prior3) and len(win5) == PEAK_MEDIAN_YEARS:
                med5 = statistics.median(win5)
                if cur_op > med5 * PEAK_MEDIAN_MULT:
                    out["cycle_peak_guard"] = True
                    out["detail_f2"] = {"year": cur, "op": cur_op, "median5": med5,
                                        "deficit_years": [y for y in range(cur - 1, cur - 4, -1)
                                                          if op.get(str(y), 0) < 0]}

        # ── F3: 이익의 질 (당해 연간, 순이익 > 0 일 때만 — 음수 PER 엔 저PER 가점 자체가 없음) ──
        cur_net = net.get(str(cur)) if cur is not None else None
        if cur_net is not None and cur_net > 0 and cur_op is not None:
            nonop_ratio = (cur_net - cur_op) / abs(cur_net)
            if nonop_ratio > NONOP_RATIO_MAX:
                out["earnings_quality"] = True
                out["detail_f3"] = {"leg": "nonop_ratio", "ratio": round(nonop_ratio, 3), "year": cur}
            else:
                cf = ((stock.get("dart_financials") or {}).get("cashflow") or {})
                fcf = cf.get("free_cashflow")
                extracted = any(cf.get(k) for k in ("operating", "investing", "financing"))
                if extracted and isinstance(fcf, (int, float)) and fcf / cur_net < FCF_NI_MIN:
                    out["earnings_quality"] = True
                    out["detail_f3"] = {"leg": "fcf_ni", "ratio": round(fcf / cur_net, 3)}
        return out
    except Exception as e:  # noqa: BLE001 — 평가 실패 = 비활성, 채점 파이프 무영향
        out["active"] = False
        out["reason"] = f"error:{type(e).__name__}"
        return out
