"""
틈새 정보(niche intel) 수집·조립기.

기존 수집기에서 파생한 데이터를 종목별로 3개 영역으로 정제한다:
  - trends : 관심도/뉴스량 기반 대체 지표
  - legal  : 소송·판결·제재 관련 헤드라인·키워드 매칭
  - credit : 한국 회사채 등급별 스프레드 기반 참고값 (KR) / SEC 부채비율 (US)

또한 시장 전체(macro.niche_credit)를 bonds.kr_corp_spreads에서 파생한다.

참고: 공공데이터포털 "나라장터 입찰공고정보서비스"는 bidNtceNm 검색 필터가
서버 측에서 무시되고, 공고 단계에서는 낙찰 기업명이 제목에 없기 때문에
종목별 G2B 매칭은 불가능하다고 판단되어 기능을 제거함 (2026-04 검증).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from api.config import now_kst

_LEGAL_KEYWORDS_KO: List[str] = [
    "소송", "고소", "고발", "피소", "제소", "판결", "선고", "유죄", "무죄",
    "가압류", "가처분", "압수수색", "수사", "기소", "구속", "영장",
    "과징금", "과태료", "제재", "시정명령", "영업정지", "인허가 취소",
    "검찰", "공정위", "금감원", "특별감리", "회계감리", "상장폐지", "관리종목",
    "횡령", "배임", "분식회계", "담합", "불공정",
]

_LEGAL_KEYWORDS_EN: List[str] = [
    "lawsuit", "sued", "litigation", "settlement", "injunction",
    "subpoena", "investigation", "indictment", "criminal",
    "fraud", "fine", "penalty", "sanction", "recall",
    "class action", "securities fraud", "SEC investigation",
    "FTC", "DOJ", "antitrust", "delisting",
]

_TRUSTED_SOURCES = (
    "newsapi", "yahoofinance", "reuters", "bloomberg",
    "dart", "edaily", "hankyung", "mk", "chosunbiz", "yna", "yonhap",
)


def _is_us(stock: Dict[str, Any]) -> bool:
    if stock.get("currency") == "USD":
        return True
    market = (stock.get("market") or "").upper()
    return any(tag in market for tag in ("NYSE", "NASDAQ", "AMEX", "NMS", "NGM", "NCM", "ARCA"))


def _build_trends(stock: Dict[str, Any]) -> Dict[str, Any]:
    """검색/관심도 대체 지표: headline_count를 interest_index로, 감성 변화를 week_change로."""
    sent = stock.get("sentiment") or {}
    headline_count = int(sent.get("headline_count") or 0)
    score = sent.get("score")

    interest_index: Optional[int] = headline_count if headline_count > 0 else None

    base_keyword = (stock.get("name") or stock.get("ticker") or "").strip()
    tagline = (stock.get("company_tagline") or "").strip()
    keyword = base_keyword or tagline or ""

    out: Dict[str, Any] = {}
    if keyword:
        out["keyword"] = keyword
    if interest_index is not None:
        out["interest_index"] = interest_index

    if score is not None and headline_count > 0:
        delta = int(score) - 50
        out["week_change_pct"] = delta

    notes = []
    if headline_count >= 10:
        notes.append("뉴스 언급 활발")
    elif headline_count == 0:
        notes.append("최근 뉴스 부재")
    if score is not None:
        if int(score) >= 65:
            notes.append("감성 긍정")
        elif int(score) <= 35:
            notes.append("감성 부정")
    if notes:
        out["note"] = " · ".join(notes)

    return out


def _extract_legal_hits(stock: Dict[str, Any], global_headlines: List[Dict[str, Any]]) -> Dict[str, Any]:
    """detected_risk_keywords + 종목별/시장 헤드라인에서 법률 리스크 매칭."""
    is_us = _is_us(stock)
    keywords = _LEGAL_KEYWORDS_EN if is_us else _LEGAL_KEYWORDS_KO

    hits: List[str] = []
    seen: set = set()

    risk_kw = stock.get("detected_risk_keywords") or []
    for kw in risk_kw:
        s = str(kw).strip()
        if not s:
            continue
        for lk in keywords:
            if lk.lower() in s.lower():
                if s not in seen:
                    hits.append(f"[AI] {s}")
                    seen.add(s)
                break

    sent = stock.get("sentiment") or {}
    for src in ("top_headlines", "top_headline_links", "detail"):
        raw = sent.get(src) or []
        for item in raw[:30]:
            title = item if isinstance(item, str) else (item.get("title") if isinstance(item, dict) else "")
            if not title:
                continue
            if any(lk.lower() in title.lower() for lk in keywords):
                t = str(title).strip()
                if t and t not in seen:
                    hits.append(t)
                    seen.add(t)
                    if len(hits) >= 8:
                        break
        if len(hits) >= 8:
            break

    if len(hits) < 8 and global_headlines:
        name = (stock.get("name") or "").strip()
        ticker = (stock.get("ticker") or "").strip()
        for h in global_headlines[:100]:
            if not isinstance(h, dict):
                continue
            title = str(h.get("title") or "")
            if not title:
                continue
            mentions_company = (name and name in title) or (ticker and ticker.upper() in title.upper())
            if not mentions_company:
                continue
            if any(lk.lower() in title.lower() for lk in keywords):
                if title not in seen:
                    hits.append(title)
                    seen.add(title)
                    if len(hits) >= 8:
                        break

    risk_flag = len(hits) >= 2 or any("[AI]" in h for h in hits)
    return {"hits": hits[:8], "risk_flag": risk_flag}


def _build_credit(stock: Dict[str, Any], bonds_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """회사채 크레딧 참고값. KR은 bonds.kr_corp_spreads에서, US는 sec_financials.debt_ratio에서."""
    out: Dict[str, Any] = {}

    if _is_us(stock):
        fin = stock.get("sec_financials") or {}
        dr = fin.get("debt_ratio")
        if isinstance(dr, (int, float)):
            out["debt_ratio_pct"] = round(float(dr), 1)
            if dr >= 200:
                out["alert"] = True
                out["note"] = f"부채비율 {dr:.0f}% — 높은 레버리지"
            elif dr >= 100:
                out["note"] = f"부채비율 {dr:.0f}% — 평균 이상"
        return out

    if not bonds_data:
        return out
    kr_cs = (bonds_data.get("kr_corp_spreads") or {})
    grades = kr_cs.get("grades") or {}
    aa = grades.get("AA-") or {}
    spread = aa.get("spread_vs_3y")
    if isinstance(spread, (int, float)):
        out["ig_spread_pp"] = round(float(spread), 2)
        if spread >= 2.0:
            out["alert"] = True
            out["note"] = "시장 전체 IG 스프레드 확대 — 조달 여건 악화"
        elif spread >= 1.2:
            out["note"] = "스프레드 상승세 — 모니터링 필요"
    return out


def build_niche_data(
    stock: Dict[str, Any],
    global_headlines: Optional[List[Dict[str, Any]]] = None,
    bonds_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """종목 1개에 대한 niche_data 블록 조립.

    portfolio.json에 이미 수집된 필드(sentiment, detected_risk_keywords,
    sec_financials, bonds)를 재활용하므로 추가 네트워크 호출 없음.
    """
    trends = _build_trends(stock)
    legal = _extract_legal_hits(stock, global_headlines or [])
    credit = _build_credit(stock, bonds_data)

    return {
        "trends": trends,
        "legal": legal,
        "credit": credit,
        "updated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }


def build_macro_niche_credit(bonds_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """macro.niche_credit — 시장 전체 회사채-국고 스프레드 스냅샷."""
    if not bonds_data:
        return {}
    kr_cs = (bonds_data.get("kr_corp_spreads") or {})
    grades = kr_cs.get("grades") or {}

    aa = grades.get("AA-") or {}
    spread = aa.get("spread_vs_3y")
    if not isinstance(spread, (int, float)):
        return {}

    out: Dict[str, Any] = {
        "corporate_spread_vs_gov_pp": round(float(spread), 2),
        "base_grade": "AA-",
        "updated_at": kr_cs.get("date") or now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }
    if spread >= 2.0:
        out["alert"] = True
    return out


__all__ = ["build_niche_data", "build_macro_niche_credit"]
