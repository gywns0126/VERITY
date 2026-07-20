"""perspective_maps_builder — 관점 지도 3종 (욕구·경기 체질·자사주) public 빌더 (2026-07-04 PM 발제).

랭킹/점수 아님 — 사실 기반 분류 + 계층별 실측 집계 (RULE 7):
  ① 욕구 지도: 업종(사실) → 매슬로우 5계층 + '기반·인프라'(욕구 비직결 산업재 정직 분리).
     분류 근거 = 업종 키워드 규칙(yfinance industry) + KSIC 2자리 — 자체 점수 0.
  ② 경기 체질: 연간 매출 YoY 변동성 실측 (fin_series ≥4년) → 측정 종목 내 3분위 라벨.
     "방어주" 남의 라벨이 아니라 우리 실측. 측정 불가 종목 = 미표시 (가짜 라벨 0).
  ③ 자사주 지도(KR): 포렌식 공시 사실 — 자기주식취득/처분 건수 → 활동 버킷.

입력(로컬, 전부 발행 산출물): stock_report_public(+us) / kr_sector_map / disclosure_forensics
출력: data/perspective_maps.json (publish 등재)

투자론 배경(관점 제안의 출처 표기용): 기초 수요 밀착 기업의 장기 성과 논의 (Hong & Kacperczyk 2009
sin-stock premium 등) — 본 지도는 검증된 신호가 아니라 탐색용 분류 관점 (검증은 관측 큐).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from statistics import median, pstdev
from typing import Any, Dict, List, Optional

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA = os.path.join(_ROOT, "data")
OUTPUT_PATH = os.path.join(_DATA, "perspective_maps.json")

LEADERS_N = 20         # 프런트 기본 15개(5×3) 노출 + 더보기 여유 (2026-07-04 enrich)
MIN_YEARS = 4          # 경기 체질 측정 최소 연수
MIN_TIER_N = 3         # 표시 최소 종목 수

# ── 욕구 계층 정의 ──────────────────────────────────────────────
TIERS = [
    # label = 사용자 친화 간결 명사형(2026-07-04). key/분류 로직 불변, 표시 라벨만 자연스럽게.
    ("survival", "필수·건강", "먹고 마시고 아프지 않게 — 수요가 유행을 안 탐"),
    ("safety", "안전·보장", "지키고 대비하는 수요 — 보험·방산·보안"),
    ("belonging", "관계·연결", "잇고 어울리는 수요 — 통신·콘텐츠·모임"),
    ("esteem", "프리미엄·품격", "돋보이고 싶은 수요 — 명품·뷰티·프리미엄"),
    ("growth", "성장·교육", "배우고 성장하는 수요 — 교육·자기계발"),
    ("infra", "산업 기반", "욕구를 직접 팔진 않지만 위 전부를 떠받치는 산업 — B2B·부품·장비"),
]

# yfinance industry(영문) 키워드 규칙 — 위에서부터 첫 매치. 업종 사실 → 계층 분류 (주관 최소화, 기준 공개)
_KW_RULES = [
    ("survival", ["food", "beverage", "grocer", "farm", "agricult", "packaged", "confection",
                  "drug", "pharma", "biotech", "medical", "health", "hospital", "diagnostic",
                  "utilities", "water", "gas", "electric", "tobacco", "household", "personal products"]),
    ("safety", ["insurance", "bank", "defense", "aerospace", "security", "safety", "waste"]),
    ("belonging", ["telecom", "internet content", "social", "entertainment", "media", "broadcasting",
                   "gaming", "restaurant", "resorts", "lodging", "airlines", "travel", "leisure"]),
    ("esteem", ["luxury", "apparel", "footwear", "cosmetic", "beauty", "jewel", "auto manufacturers",
                "department", "specialty retail"]),
    ("growth", ["education", "publishing"]),
]
# KSIC 2자리 → 계층 (DART 폴백 종목용)
_KSIC_TIER = {
    **{k: "survival" for k in ["01", "02", "03", "10", "11", "21", "27", "35", "36", "86", "87"]},
    **{k: "safety" for k in ["64", "65", "66"]},
    **{k: "belonging" for k in ["55", "56", "58", "59", "60", "61", "90", "91"]},
    **{k: "esteem" for k in ["13", "14", "15"]},
    **{k: "growth" for k in ["85"]},
}
# US SIC 2자리 → 계층 (us report 의 peer.sector 가 아닌 원 SIC 필요 — _summary 조인)
_SIC_TIER = {
    **{k: "survival" for k in ["01", "02", "07", "09", "20", "21", "28", "49", "54", "80"]},
    **{k: "safety" for k in ["60", "61", "62", "63", "64"]},  # 37(운송장비)은 방산/자동차 2자리 분리 불가 → infra (오분류 방지)
    **{k: "belonging" for k in ["48", "58", "70", "78", "79"]},
    **{k: "esteem" for k in ["23", "31", "56", "39"]},
    **{k: "growth" for k in ["82", "27"]},
}


def _now() -> str:
    return datetime.now(KST).isoformat()


def _load(name: str, default):
    try:
        with open(os.path.join(_DATA, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _tier_of_kr(industry: str, sector_code: str) -> str:
    low = (industry or "").lower()
    for tier, kws in _KW_RULES:
        if any(k in low for k in kws):
            return tier
    if industry.startswith("KSIC "):
        code2 = industry.replace("KSIC ", "")[:2]
        t = _KSIC_TIER.get(code2)
        if t:
            return t
    return "infra"


def _tier_of_us(sic: str) -> str:
    return _SIC_TIER.get((sic or "")[:2], "infra")


def _growth_vol(fin_series: List[Dict[str, Any]]) -> Optional[float]:
    """연간 매출 YoY(%) 표준편차 — 경기 체질 실측. 매출 ≥4년 필요."""
    rev = [(p.get("year"), p.get("revenue")) for p in (fin_series or []) if p.get("revenue")]
    rev = [(y, v) for y, v in rev if y is not None and v and v > 0]
    if len(rev) < MIN_YEARS:
        return None
    rev.sort()
    yoy = []
    for (y0, v0), (y1, v1) in zip(rev, rev[1:]):
        if y1 - y0 == 1 and v0:
            yoy.append((v1 / v0 - 1.0) * 100.0)
    if len(yoy) < MIN_YEARS - 1:
        return None
    return round(pstdev(yoy), 1) if len(yoy) > 1 else None


def _cap_of(s: Dict[str, Any]) -> float:
    v = (s.get("facts") or {}).get("시가총액") or ""
    t = str(v)
    try:
        if "조" in t:
            return float(t.replace("조", "").replace(",", "")) * 1e4
        if "억" in t:
            return float(t.replace("억", "").replace(",", ""))
        if t.startswith("$"):
            x = t.replace("$", "")
            if x.endswith("T"):
                return float(x[:-1]) * 1e6
            if x.endswith("B"):
                return float(x[:-1]) * 1e3
            if x.endswith("M"):
                return float(x[:-1])
    except ValueError:
        return 0.0
    return 0.0


# cross-market 합산·share 시각화용 시총 정규화 (억원). _cap_of 는 정렬 전용이라 KR억 vs US$ 를
# 통일 안 함 → 합산 시 US 크게 왜곡. 여기선 US$ 를 FX 로 억원 환산해 카테고리별 cap_sum 산출.
FX_USD_KRW = 1350.0  # 근사 환율 (규모 분포 share 용 — 정밀치 아님, 상대 비교 목적)


def _cap_krw(s: Dict[str, Any]) -> float:
    t = str((s.get("facts") or {}).get("시가총액") or "")
    try:
        if "조" in t:
            return float(t.replace("조", "").replace(",", "")) * 1e4      # 조 → 억
        if "억" in t:
            return float(t.replace("억", "").replace(",", ""))
        if t.startswith("$"):
            x = t.replace("$", "").replace(",", "")
            mult = 1e12 if x.endswith("T") else (1e9 if x.endswith("B") else (1e6 if x.endswith("M") else 1.0))
            usd = float(x.rstrip("TBM")) * mult                            # 절대 USD (T=1e12·B=1e9·M=1e6)
            return usd * FX_USD_KRW / 1e8                                  # KRW → 억원
    except ValueError:
        return 0.0
    return 0.0


def _rev_latest(s: Dict[str, Any]) -> Optional[float]:
    """최근 연도 매출 (KR=억원 / US=$M 원 단위 — 분류·탐색용, 랭킹 아님). fin_series 최신 연도."""
    rev = [(p.get("year"), p.get("revenue")) for p in (s.get("fin_series") or []) if p.get("revenue")]
    if not rev:
        return None
    rev.sort()
    try:
        return float(rev[-1][1])
    except (TypeError, ValueError):
        return None


def _pct_fact(facts: Dict[str, Any], key: str) -> Optional[float]:
    v = facts.get(key)
    try:
        return float(str(v).rstrip("%").lstrip("+"))
    except (TypeError, ValueError):
        return None


def _leader(s: Dict[str, Any]) -> Dict[str, Any]:
    # 카드 요약 enrich (2026-07-04): 규모(시총)·수익성(마진)·섹터·매출 — 프런트 커스텀 정렬(규모/수익)용.
    # 전부 이미 발행 산출물의 사실. 점수·랭킹 아님(RULE 7) — 정렬은 탐색 편의(사실값 나열).
    # KR=영업이익률·overview.sector / US=순이익률·peer.sector (시장별 필드 위치 상이 → 폴백으로 커버리지 확보).
    mkt = s.get("_mkt") or ("KR" if str(s.get("ticker", "")).isdigit() else "US")
    facts = s.get("facts") or {}
    d: Dict[str, Any] = {
        "ticker": s.get("ticker"),
        "name": s.get("name_ko") or s.get("name"),
        "mkt": mkt,
        "cap": round(_cap_of(s)),                              # 규모 정렬 키 (억원 정규화)
        "cap_disp": facts.get("시가총액") or "",               # 표시용 원문
        "op_margin": _op_margin(s),                            # 영업이익률 % (KR)
        "net_margin": _pct_fact(facts, "순이익률"),            # 순이익률 % (US·일부 KR)
        "sector": (s.get("overview") or {}).get("sector")
                  or (s.get("peer") or {}).get("sector") or facts.get("업종") or "",
    }
    rev = _rev_latest(s)
    if rev is not None:
        d["revenue"] = round(rev)
    return d


def _op_margin(s: Dict[str, Any]) -> Optional[float]:
    v = (s.get("facts") or {}).get("영업이익률")
    try:
        return float(str(v).rstrip("%").lstrip("+"))
    except (TypeError, ValueError):
        return None


def build() -> Dict[str, Any]:
    kr = [s for s in (_load("stock_report_public.json", {}).get("stocks") or [])
          if str(s.get("ticker", "")).isdigit()]
    us = _load("us_stock_report_public.json", {}).get("stocks") or []
    sector_map = (_load("kr_sector_map.json", {}) or {}).get("map") or {}
    us_sic = {r.get("ticker"): str(r.get("sic") or "")
              for r in (_load(os.path.join("us_financials", "_summary.json"), {}) or {}).get("rows") or []}

    # ① 욕구 지도 — 분류 + 계층 집계
    assign: Dict[str, List[Dict[str, Any]]] = {t[0]: [] for t in TIERS}
    for s in kr:
        m = sector_map.get(s.get("ticker")) or {}
        assign[_tier_of_kr(m.get("industry") or "", m.get("sector") or "")].append({**s, "_mkt": "KR"})
    for s in us:
        assign[_tier_of_us(us_sic.get(s.get("ticker"), ""))].append({**s, "_mkt": "US"})

    desire_tiers = []
    for key, label, desc in TIERS:
        members = assign[key]
        if len(members) < MIN_TIER_N:
            continue
        margins = [m for m in (_op_margin(s) for s in members) if m is not None and -200 < m < 200]
        members.sort(key=_cap_of, reverse=True)
        desire_tiers.append({
            "key": key, "label": label, "desc": desc,
            "n_kr": sum(1 for s in members if s["_mkt"] == "KR"),
            "n_us": sum(1 for s in members if s["_mkt"] == "US"),
            "median_op_margin": round(median(margins), 1) if margins else None,
            "cap_sum": round(sum(_cap_krw(s) for s in members)),   # 카테고리 합산 시총(억원, FX 정규화) — 규모 분포 share 용
            "leaders": [_leader(s) for s in members[:LEADERS_N]],
        })

    # ② 경기 체질 — 매출 YoY 변동성 실측 3분위
    vols = []
    for s in kr + us:
        v = _growth_vol(s.get("fin_series") or [])
        if v is not None:
            vols.append((v, s))
    cycle_buckets = []
    if len(vols) >= 30:
        vols.sort(key=lambda x: x[0])
        n = len(vols)
        cuts = [(0, n // 3, "steady", "매출 꾸준", "실측 변동성 하위 1/3"),
                (n // 3, 2 * n // 3, "middle", "중간", "중위 1/3"),
                (2 * n // 3, n, "swing", "매출 출렁", "상위 1/3")]
        for a, b, key, label, desc in cuts:
            grp = vols[a:b]
            members = sorted((s for _v, s in grp), key=_cap_of, reverse=True)
            cycle_buckets.append({
                "key": key, "label": label, "desc": desc,
                "n": len(grp),
                "n_kr": sum(1 for s in members if str(s.get("ticker", "")).isdigit()),
                "n_us": sum(1 for s in members if not str(s.get("ticker", "")).isdigit()),
                "vol_range": [grp[0][0], grp[-1][0]] if grp else None,
                "cap_sum": round(sum(_cap_krw(s) for s in members)),
                "leaders": [_leader(s) for s in members[:LEADERS_N]],
            })

    # ③ 자사주 지도 (KR) — 포렌식 공시 사실
    foren = {s.get("ticker"): s for s in (_load("disclosure_forensics.json", {}).get("stocks") or [])}
    buy_rows = []
    for s in kr:
        f = foren.get(s.get("ticker"))
        if not f:
            continue
        buys = sum(1 for e in (f.get("events") or []) if e.get("category") == "자기주식취득")
        sells = sum(1 for e in (f.get("events") or []) if e.get("category") == "자기주식처분")
        if buys or sells:
            buy_rows.append((buys, sells, s))
    def _bucketize(pred, key, label, desc):
        grp = [(b, sl, s) for b, sl, s in buy_rows if pred(b, sl)]
        members = sorted((s for _b, _s, s in grp), key=_cap_of, reverse=True)
        return {"key": key, "label": label, "desc": desc, "n": len(grp),
                "n_kr": len(grp), "n_us": 0,  # 자사주 지도 = KR 포렌식 전용
                "cap_sum": round(sum(_cap_krw(s) for s in members)),
                "leaders": [_leader(s) for s in members[:LEADERS_N]]}
    buyback_buckets = [
        _bucketize(lambda b, sl: b >= 2 and b > sl, "steady_buy", "꾸준히 매입", "수집 창 내 자기주식취득 공시 2건 이상 · 취득 > 처분"),
        _bucketize(lambda b, sl: b == 1 and b >= sl, "some_buy", "가끔 매입", "취득 공시 1건"),
        _bucketize(lambda b, sl: sl > b, "net_sell", "처분 많음", "처분 공시가 취득보다 많음"),
    ]

    return {
        "_meta": {
            "generated_at": _now(),
            "source": "업종(kr_sector_map·SIC)·연간 매출 실측(fin_series)·자기주식 공시(DART 포렌식) — 분류·집계 사실만",
            "note": "관점 지도 = 탐색용 분류 · 점수·랭킹·추천 아님 · 분류 기준 공개(업종 키워드 규칙)",
        },
        "desire": {"tiers": desire_tiers},
        "cycle": {"buckets": cycle_buckets, "basis": f"연간 매출 YoY 변동성(≥{MIN_YEARS}년 실측 종목만) · 측정 불가 = 미표시"},
        "buyback": {"buckets": buyback_buckets, "basis": "DART 자기주식 취득·처분 공시 건수 (포렌식 수집 창)"},
    }


def main() -> None:
    out = build()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    d = out["desire"]["tiers"]
    c = out["cycle"]["buckets"]
    b = out["buyback"]["buckets"]
    print(f"[perspective_maps] logged=True · 욕구 {len(d)}계층 · 경기 {sum(x['n'] for x in c) if c else 0}종목 측정 · "
          f"자사주 {sum(x['n'] for x in b)}종목 → {OUTPUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
