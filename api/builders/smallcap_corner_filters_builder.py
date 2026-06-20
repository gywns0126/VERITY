"""KR 소형주 코너 특화 필터 (골든구스 병렬 트랙 Phase 2).

코너 유니버스(smallcap_corner.json, 1120) 위에서 사실/패턴 필터를 만든다.
핵심 = "방치 우량" — 재무 양호 + 공시 조용 + 소형 = 기관 capacity 못 드는 + 깨끗한 + 무관심 보석.
토스/증권사가 구조적으로 못 만드는 필터(소형주 forensic + 방치 코너).

입력(read-only): data/smallcap_corner.json + data/disclosure_forensics.json
출력: data/smallcap_corner_filters.json

규율: 점수/랭킹 0, 사실/패턴만(RULE 7). LLM 0(RULE 6). 임계는 투명 동봉.
Brain 통과(verdict)는 Phase 3(별도 trail), 공개 노출은 사실만(점수 held 2027).
"""
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORNER_PATH = os.path.join(_ROOT, "data", "smallcap_corner.json")
FORENSICS_PATH = os.path.join(_ROOT, "data", "disclosure_forensics.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "smallcap_corner_filters.json")

KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    return datetime.now(KST)


def _count(counts: Dict[str, int], *keys: str) -> int:
    return sum(int(counts.get(k, 0) or 0) for k in keys)


def _healthy(fin: Dict[str, Any]) -> bool:
    """재무 양호 코어 = 부채비율<100 AND 순이익>0 (roa 는 결손 잦아 보조만)."""
    dr = fin.get("debt_ratio")
    ni = fin.get("net_income")
    return dr is not None and dr < 100 and (ni or 0) > 0


FILTERS = [
    {
        "key": "neglected_quality",
        "name": "방치된 우량 소형주",
        "badge": "방치·우량",
        "why": "재무는 멀쩡하고 위험 공시도 없는데 시총이 작아 애널리스트·기관이 안 보는 회사.",
        "criteria_text": "시총 300~3000억 · 부채비율 100% 미만 · 순이익 > 0 · 최근 위험 공시 이벤트 없음",
    },
    {
        "key": "smallcap_dilution",
        "name": "소형주 희석 경계",
        "badge": "희석",
        "why": "소형주는 유상증자·전환사채 남발이 최대 독소조항 — 기존 주주 지분이 빠르게 희석된다.",
        "criteria_text": "코너 종목 중 유상증자 2건+ 또는 CB·BW 2건+",
    },
    {
        "key": "smallcap_distress",
        "name": "소형주 부실 신호",
        "badge": "부실",
        "why": "적자 또는 회생·감자 공시는 소형주에서 상폐 위험의 직접 신호다.",
        "criteria_text": "순이익 < 0 또는 회생·상장폐지·감자 공시 보유",
    },
    {
        "key": "clean_fin_risky_disc",
        "name": "재무 양호 · 공시 적신호",
        "badge": "교차",
        "why": "실적은 멀쩡한데 희석·구조 공시가 잦은 소형주 — 재무 화면만 보면 안 보인다.",
        "criteria_text": "부채 100% 미만 · 순이익 > 0 · (유상증자 2건+ 또는 감자/합병/분할 공시)",
    },
]


def _match(key: str, st: Dict[str, Any], counts: Dict[str, int], has_depth: bool) -> Optional[Dict[str, Any]]:
    fin = st.get("financials") or {}
    capital_raise = _count(counts, "유상증자")
    convertibles = _count(counts, "전환사채(CB)", "신주인수권부사채(BW)", "교환사채(EB)")
    structural = _count(counts, "감자", "합병", "분할", "회생·상장폐지")
    distress = _count(counts, "회생·상장폐지", "감자")
    ni = fin.get("net_income")

    if key == "neglected_quality":
        # 재무 양호 + 위험 공시 없음(forensic 깊이 미보유 = 위험 이벤트 0)
        if _healthy(fin) and not has_depth:
            return {"부채비율": fin.get("debt_ratio"), "순이익": ni, "roa": fin.get("roa"),
                    "시총_억": st.get("mktcap_eok")}
    elif key == "smallcap_dilution":
        if capital_raise >= 2 or convertibles >= 2:
            return {"유상증자": capital_raise, "CB_BW": convertibles, "시총_억": st.get("mktcap_eok")}
    elif key == "smallcap_distress":
        if (ni is not None and ni < 0) or distress >= 1:
            return {"순이익": ni, "회생·상폐·감자": distress, "시총_억": st.get("mktcap_eok")}
    elif key == "clean_fin_risky_disc":
        if _healthy(fin) and (capital_raise >= 2 or structural >= 1):
            return {"부채비율": fin.get("debt_ratio"), "순이익": ni,
                    "유상증자": capital_raise, "구조공시": structural}
    return None


def main() -> int:
    if not os.path.exists(CORNER_PATH):
        print(f"[smallcap_corner_filters] 코너 부재: {CORNER_PATH} — Phase 0 먼저. skip")
        return 0
    corner = json.load(open(CORNER_PATH, encoding="utf-8")).get("stocks") or []
    forensic_by_ticker: Dict[str, Dict[str, Any]] = {}
    if os.path.exists(FORENSICS_PATH):
        for s in json.load(open(FORENSICS_PATH, encoding="utf-8")).get("stocks") or []:
            forensic_by_ticker[str(s.get("ticker"))] = s

    groups = []
    for spec in FILTERS:
        members = []
        for st in corner:
            tk = str(st.get("ticker"))
            fr = forensic_by_ticker.get(tk) or {}
            counts = fr.get("counts") or {}
            facts = _match(spec["key"], st, counts, bool(st.get("has_forensic_depth")))
            if facts is None:
                continue
            members.append({"ticker": tk, "name": st.get("name") or "",
                            "market": st.get("market") or "", "facts": facts})
        members.sort(key=lambda m: m.get("facts", {}).get("시총_억") or 0)
        groups.append({**spec, "count": len(members), "tickers": members})

    out = {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "track": "kr_smallcap_corner",
            "universe_n": len(corner),
            "disclaimer": "사실·패턴 필터 — 투자 추천/점수/순위 아님. 기준 투명 동봉. KR 소형주 코너 한정.",
            "rule": "RULE 7 (사실만, 검증 점수 held 2027) / RULE 6 (LLM 0)",
        },
        "filters": groups,
    }
    json.dump(out, open(OUTPUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    summary = " / ".join(f"{g['name']} {g['count']}" for g in groups)
    print(f"[smallcap_corner_filters] 적재 OK | universe {len(corner)} | {summary} | out={OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
