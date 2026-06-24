"""미장(US) 소형주 코너 특화 필터 — 골든구스 미장 트랙 (Phase 5).

KR smallcap_corner_filters_builder 의 미장 대응. 코너 유니버스(us_smallcap_corner.json) ×
8-K forensics(us_disclosure_forensics.json) 를 조인해 사실/패턴 필터를 만든다. 점수/랭킹 0.

KR 4필터 대응 + 미장 특화 1필터(accounting_red_flag = restatement/auditor change — KR DART 엔
없는 SEC 8-K 고유 신호 = 차별). _healthy: KR 부채비율<100% → US debt_to_equity<1.0.

입력(read-only): data/us_smallcap_corner.json + data/us_disclosure_forensics.json
출력: data/us_smallcap_corner_filters.json

규율: 점수/랭킹 0, 사실/패턴만(RULE 7). LLM 0(RULE 6). 임계 투명 동봉. 점수=held(2027).
"""
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORNER_PATH = os.path.join(_ROOT, "data", "us_smallcap_corner.json")
FORENSICS_PATH = os.path.join(_ROOT, "data", "us_disclosure_forensics.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_smallcap_corner_filters.json")

KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    return datetime.now(KST)


def _c(counts: Dict[str, int], *keys: str) -> int:
    return sum(int(counts.get(k, 0) or 0) for k in keys)


def _healthy(fin: Dict[str, Any]) -> bool:
    """재무 양호 코어 = debt_to_equity<1.0 AND net_margin_pct>0 (KR 부채비율<100 대응)."""
    de = fin.get("debt_to_equity")
    nm = fin.get("net_margin_pct")
    return de is not None and de < 1.0 and (nm or 0) > 0


FILTERS = [
    {
        "key": "neglected_quality",
        "name": "방치된 우량 미장 소형주",
        "badge": "방치·우량",
        "why": "재무는 멀쩡하고 위험 공시(8-K)도 없는데 시총이 작아 sell-side 가 안 보는 회사.",
        "criteria_text": "시총 $50M~$5B · D/E 1.0 미만 · 순이익률 > 0 · 최근 2년 위험 8-K 없음",
    },
    {
        "key": "smallcap_dilution",
        "name": "소형주 희석 경계",
        "badge": "희석",
        "why": "소형주 최대 독소 = 지분 희석. 8-K Item 3.02(비등록 주식발행) 반복은 기존 주주 희석 신호.",
        "criteria_text": "최근 2년 8-K dilution(Item 3.02) 2건+",
    },
    {
        "key": "smallcap_distress",
        "name": "소형주 부실 신호",
        "badge": "부실",
        "why": "적자 또는 파산·상폐·채무가속 8-K 는 소형주 상폐 위험의 직접 신호.",
        "criteria_text": "순이익률 < 0 또는 파산(1.03)·상폐(3.01)·채무가속(2.04) 8-K 보유",
    },
    {
        "key": "clean_fin_risky_disc",
        "name": "재무 양호 · 공시 적신호",
        "badge": "교차",
        "why": "실적은 멀쩡한데 희석·구조 8-K 가 잦은 소형주 — 재무 화면만 보면 안 보인다.",
        "criteria_text": "D/E 1.0 미만 · 순이익률 > 0 · (dilution 2건+ 또는 M&A/권리변경 8-K)",
    },
    {
        "key": "accounting_red_flag",
        "name": "회계 적신호 (미장 특화)",
        "badge": "회계",
        "why": "재무제표 재작성(4.02)·회계법인 교체(4.01)는 미국 소형주 회계 부정의 강력한 선행 신호 — KR 엔 없는 SEC 8-K 고유.",
        "criteria_text": "최근 2년 재무재작성(Item 4.02) 또는 회계법인 교체(Item 4.01) 8-K 보유",
    },
]


def _match(key: str, st: Dict[str, Any], counts: Dict[str, int]) -> Optional[Dict[str, Any]]:
    fin = st.get("financials") or {}
    mc = st.get("mktcap_musd")
    dilution = _c(counts, "dilution")
    distress = _c(counts, "bankruptcy", "delisting_risk", "debt_default")
    structural = _c(counts, "mna", "rights_modification", "control_change")
    accounting = _c(counts, "restatement", "auditor_change")
    nm = fin.get("net_margin_pct")

    if key == "neglected_quality":
        if _healthy(fin) and not counts:  # 위험 8-K 신호 0
            return {"debt_to_equity": fin.get("debt_to_equity"), "net_margin_pct": nm,
                    "roe_pct": fin.get("roe_pct"), "mktcap_musd": mc}
    elif key == "smallcap_dilution":
        if dilution >= 2:
            return {"dilution_8k": dilution, "mktcap_musd": mc}
    elif key == "smallcap_distress":
        if (nm is not None and nm < 0) or distress >= 1:
            return {"net_margin_pct": nm, "distress_8k": distress, "mktcap_musd": mc}
    elif key == "clean_fin_risky_disc":
        if _healthy(fin) and (dilution >= 2 or structural >= 1):
            return {"debt_to_equity": fin.get("debt_to_equity"), "net_margin_pct": nm,
                    "dilution_8k": dilution, "structural_8k": structural}
    elif key == "accounting_red_flag":
        if accounting >= 1:
            return {"restatement": _c(counts, "restatement"),
                    "auditor_change": _c(counts, "auditor_change"), "mktcap_musd": mc}
    return None


def main() -> int:
    if not os.path.exists(CORNER_PATH):
        print(f"[us_corner_filters] 코너 부재: {CORNER_PATH} — us_smallcap_corner_builder 먼저. skip")
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
            counts = (forensic_by_ticker.get(tk) or {}).get("counts") or {}
            facts = _match(spec["key"], st, counts)
            if facts is None:
                continue
            members.append({"ticker": tk, "name": st.get("name") or "",
                            "market": "US", "facts": facts})
        members.sort(key=lambda m: m.get("facts", {}).get("mktcap_musd") or 0)
        groups.append({**spec, "count": len(members), "tickers": members})

    out = {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "track": "us_smallcap_corner",
            "universe_n": len(corner),
            "forensic_n": len(forensic_by_ticker),
            "disclaimer": "사실·패턴 필터 — 투자 추천/점수/순위 아님. 기준 투명 동봉. 미장 소형주 코너 한정. "
                          "8-K item 사실 기반(dilution=Item 3.02 unregistered만).",
            "rule": "RULE 7 (사실만, 검증 점수 held 2027) / RULE 6 (LLM 0)",
        },
        "filters": groups,
    }
    json.dump(out, open(OUTPUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    summary = " / ".join(f"{g['name']} {g['count']}" for g in groups)
    print(f"[us_corner_filters] 적재 OK | universe {len(corner)} | {summary} | out={OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
