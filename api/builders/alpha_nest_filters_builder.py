"""AlphaNest 공개 필터 빌더 — 공시 forensics × 재무 교차 (사실/패턴, 점수·랭킹 0).

입력 (read-only):
  · data/disclosure_forensics.json   — 위험 공시 이벤트 보유 종목 (유상증자/CB/BW/감자/합병/자기주식/회생 빈도)
  · data/dart_quarterly_snapshots.jsonl — 종목별 재무 (debt_ratio/net_income/roa/gross_margin), 종목당 최신 분기 픽

출력:
  · data/alpha_nest_filters.json — 명명된 필터 그룹 + 종목별 사실. 투명 기준 노출, RULE 7 (추천/점수 아님).

설계 규율:
  · 사실/패턴만 ("이 패턴 있다"), 매수/매도/랭킹 없음 (유사투자자문 + RULE 7 안전선).
  · 임계는 *투명*하게 출력에 동봉 (토스식 "배당 3%+" 처럼 사용자에게 공개되는 필터 기준 — 숨은 검증 점수 아님).
  · LLM 0 (RULE 6).
"""
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FORENSICS_PATH = os.path.join(_ROOT, "data", "disclosure_forensics.json")
FINANCIALS_PATH = os.path.join(_ROOT, "data", "dart_quarterly_snapshots.jsonl")
OUTPUT_PATH = os.path.join(_ROOT, "data", "alpha_nest_filters.json")

KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    return datetime.now(KST)


def _latest_financials() -> Dict[str, Dict[str, Any]]:
    """종목별 최신 분기 재무 (quarter_end 기준)."""
    latest: Dict[str, Dict[str, Any]] = {}
    if not os.path.exists(FINANCIALS_PATH):
        return latest
    with open(FINANCIALS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            tk = str(r.get("ticker") or "").strip()
            if not tk:
                continue
            # 일부 행은 스냅샷 placeholder(quarter_end=수집일, 재무 전부 null) → 실 재무 보유 행만 채택
            if r.get("debt_ratio") is None:
                continue
            qe = str(r.get("quarter_end") or "")
            prev = latest.get(tk)
            if prev is None or qe > str(prev.get("quarter_end") or ""):
                latest[tk] = r
    return latest


def _count(counts: Dict[str, int], *keys: str) -> int:
    return sum(int(counts.get(k, 0) or 0) for k in keys)


# 필터 정의 — 3단 해석(쉬운이름/용어배지/왜중요) + 투명 기준. 전부 사실/패턴.
FILTERS = [
    {
        "key": "dilution_watch",
        "name": "잦은 유상증자",
        "badge": "희석",
        "why": "신주 발행이 잦으면 기존 주주 지분이 그만큼 희석된다.",
        "criteria_text": "최근 공시 유상증자 2건 이상",
    },
    {
        "key": "convertible_overhang",
        "name": "전환사채 빈발",
        "badge": "CB·BW",
        "why": "전환사채·신주인수권부사채는 향후 주식으로 전환될 잠재 물량(오버행)이다.",
        "criteria_text": "전환사채(CB)+신주인수권부사채(BW)+교환사채(EB) 공시 2건 이상",
    },
    {
        "key": "buyback_active",
        "name": "자사주 매입 활발",
        "badge": "자기주식취득",
        "why": "자사주 매입은 주주환원 신호일 수 있다(단 소각 여부는 별도 확인 필요).",
        "criteria_text": "자기주식취득 공시 2건 이상",
    },
    {
        "key": "clean_fin_risky_disc",
        "name": "재무 양호 · 공시 적신호",
        "badge": "교차",
        "why": "실적은 멀쩡한데 희석·구조 공시가 잦은 회사 — 재무 화면만 보면 안 보인다.",
        "criteria_text": "부채비율 100% 미만 · 순이익 > 0 · (유상증자 2건+ 또는 감자/합병/분할 공시 보유)",
    },
    {
        "key": "distress_history",
        "name": "부실 이력 (회생·감자)",
        "badge": "부실",
        "why": "회생절차·상장폐지·감자 공시는 자본 구조 위험의 직접 신호다.",
        "criteria_text": "회생·상장폐지 또는 감자 공시 보유",
    },
]


def _match(filter_key: str, st: Dict[str, Any], fin: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """필터 적합 시 자격 사실(facts) dict 반환, 아니면 None."""
    counts: Dict[str, int] = st.get("counts") or {}
    capital_raise = _count(counts, "유상증자")
    convertibles = _count(counts, "전환사채(CB)", "신주인수권부사채(BW)", "교환사채(EB)")
    buyback = _count(counts, "자기주식취득")
    structural = _count(counts, "감자", "합병", "분할", "회생·상장폐지")
    distress = _count(counts, "회생·상장폐지", "감자")

    debt = fin.get("debt_ratio") if fin else None
    ni = fin.get("net_income") if fin else None

    if filter_key == "dilution_watch":
        if capital_raise >= 2:
            return {"유상증자": capital_raise, "희석성공시_합": st.get("dilution_count")}
    elif filter_key == "convertible_overhang":
        if convertibles >= 2:
            return {"CB_BW_EB": convertibles}
    elif filter_key == "buyback_active":
        if buyback >= 2:
            return {"자기주식취득": buyback}
    elif filter_key == "clean_fin_risky_disc":
        if debt is not None and debt < 100 and (ni or 0) > 0 and (capital_raise >= 2 or structural >= 1):
            return {
                "부채비율": round(float(debt), 1),
                "순이익": ni,
                "유상증자": capital_raise,
                "구조공시": structural,
            }
    elif filter_key == "distress_history":
        if distress >= 1:
            return {"회생·상폐·감자": distress}
    return None


def main() -> int:
    if not os.path.exists(FORENSICS_PATH):
        print(f"[alpha_nest_filters] 입력 부재: {FORENSICS_PATH} — skip")
        return 0
    with open(FORENSICS_PATH, encoding="utf-8") as f:
        forensics = json.load(f)
    stocks: List[Dict[str, Any]] = forensics.get("stocks") or []
    fin_by_ticker = _latest_financials()

    groups = []
    for spec in FILTERS:
        members = []
        for st in stocks:
            tk = str(st.get("ticker") or "").strip()
            facts = _match(spec["key"], st, fin_by_ticker.get(tk))
            if facts is None:
                continue
            members.append({
                "ticker": tk,
                "name": st.get("name") or "",
                "facts": facts,
                "has_financials": tk in fin_by_ticker,
            })
        groups.append({
            **spec,
            "count": len(members),
            "tickers": members,
        })

    out = {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "source": "disclosure_forensics.json × dart_quarterly_snapshots.jsonl",
            "universe": {
                "disclosure_event_flagged": len(stocks),
                "with_financials": sum(1 for st in stocks if str(st.get("ticker") or "") in fin_by_ticker),
            },
            "disclaimer": "사실·패턴 필터 — 투자 추천/점수/순위 아님. 기준은 각 필터에 투명 동봉. 데이터=DART 공시+분기재무.",
            "rule": "RULE 7 (사실만, 검증 점수 비공개) / RULE 6 (LLM 0)",
        },
        "filters": groups,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    summary = " / ".join(f"{g['name']} {g['count']}" for g in groups)
    print(f"[alpha_nest_filters] 적재 OK at={out['_meta']['generated_at']} | {summary} | out={OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
