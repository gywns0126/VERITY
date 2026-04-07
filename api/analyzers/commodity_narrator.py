"""
원자재 급변 × 추적 종목 — 비서 톤 한 줄 서술 (Gemini 1회 호출, 실패 시 템플릿).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from api.analyzers.gemini_analyst import init_gemini
from api.config import GEMINI_MODEL
from api.collectors.CommodityScout import save_commodity_impact


def _stock_lookup(
    candidates: List[Dict[str, Any]],
    holdings: Optional[List[Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    m: Dict[str, Dict[str, Any]] = {
        str(s.get("ticker", "")).zfill(6): s for s in candidates
    }
    for h in holdings or []:
        t = str(h.get("ticker", "")).zfill(6)
        if t and t not in m:
            m[t] = {
                "ticker": h.get("ticker"),
                "name": h.get("name", t),
                "operating_margin": h.get("operating_margin", 0),
                "consensus": {},
            }
    return m


def _linked_for_commodity(
    scout: Dict[str, Any],
    commodity_ticker: str,
    rec_by: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_t = scout.get("by_ticker") or {}
    out: List[Dict[str, Any]] = []
    for tid, block in by_t.items():
        pr = (block or {}).get("primary") or {}
        if pr.get("commodity_ticker") != commodity_ticker:
            continue
        st = rec_by.get(tid, {})
        name = st.get("name") or tid
        cons = st.get("consensus") or {}
        out.append(
            {
                "ticker": tid,
                "name": name,
                "spread_regime": pr.get("spread_regime"),
                "correlation_60d": pr.get("correlation_60d"),
                "margin_safety_score": pr.get("margin_safety_score"),
                "pricing_power": pr.get("pricing_power"),
                "stock_20d_pct": pr.get("stock_20d_pct"),
                "commodity_20d_pct": pr.get("commodity_20d_pct"),
                "operating_margin": st.get("operating_margin"),
                "upside_pct": cons.get("upside_pct"),
            }
        )
    out.sort(key=lambda x: abs(float(x.get("correlation_60d") or 0)), reverse=True)
    return out[:5]


def _template_line(ev: Dict[str, Any]) -> str:
    ct = ev.get("commodity_ticker", "?")
    pct = ev.get("vs_prior_month_avg_pct")
    linked = ev.get("linked") or []
    pct_s = f"{float(pct):+.1f}%" if pct is not None else "?%"

    if not linked:
        return (
            f"사장님, {ct} 전월 평균 대비 {pct_s} — "
            f"추적 유니버스에 직접 매핑된 종목은 없음. 섹터 원가만 체크."
        )

    s = linked[0]
    name = s.get("name", "?")
    regime = s.get("spread_regime") or "중립"
    r = s.get("correlation_60d")
    ms = s.get("margin_safety_score")
    r_s = f"{float(r):.2f}" if r is not None else "n/a"
    ms_s = f"{float(ms):.0f}" if ms is not None else "n/a"
    opm = s.get("operating_margin")
    up = s.get("upside_pct")
    opm_s = f"영업이익률 {float(opm):.1f}%" if opm is not None else "영업이익률 데이터 없음"
    up_s = ""
    if up is not None:
        up_s = f", 목표가 여력 {float(up):+.1f}%"

    if regime == "마진 스프레드 확대":
        tail = "원가 약세·주가 강세라 마진 스프레드 확대 구간으로 본다."
    elif regime == "동반 상승":
        tail = "원가·주가 동반 상승 — 판가 전이가 붙는지 컨센·실적으로만 판단."
    elif regime == "비용 압박":
        tail = "원가 상승에 주가는 못 따라감 — 마진 압박, 방어 점검."
    elif regime == "최악의 상황":
        tail = "원가 급등·주가 급락 겹침 — 최악 국면, 손절·비중부터."
    else:
        tail = "국면 중립에 가깝다 — 숫자만 보고 과매수만 피하자."

    extra = ""
    if len(linked) > 1:
        extra = f" 외 {len(linked) - 1}종 동일 원자재 연동."

    return (
        f"사장님, {ct} 전월 대비 {pct_s}. '{name}' {opm_s}{up_s}. "
        f"60일 r {r_s}, 마진안심 {ms_s} — {tail}{extra}"
    )


def _gemini_briefs(events: List[Dict[str, Any]]) -> Optional[List[str]]:
    if not events:
        return None
    try:
        client = init_gemini()
    except Exception:
        return None

    slim = []
    for ev in events:
        slim.append(
            {
                "commodity_ticker": ev["commodity_ticker"],
                "vs_prior_month_avg_pct": ev["vs_prior_month_avg_pct"],
                "linked": [
                    {
                        "name": x.get("name"),
                        "spread_regime": x.get("spread_regime"),
                        "correlation_60d": x.get("correlation_60d"),
                        "margin_safety_score": x.get("margin_safety_score"),
                        "pricing_power": x.get("pricing_power"),
                        "stock_20d_pct": x.get("stock_20d_pct"),
                        "commodity_20d_pct": x.get("commodity_20d_pct"),
                        "operating_margin": x.get("operating_margin"),
                        "upside_pct": x.get("upside_pct"),
                    }
                    for x in (ev.get("linked") or [])[:4]
                ],
            }
        )

    prompt = f"""너는 15년 차 한국 펀드매니저다. 사장님께 텔레그램으로 짧게 보고한다.
규칙: 한국어. 반말·굵은 말투 OK. "분석 결과" 같은 서론 금지. 입력에 없는 숫자·사실 invent 금지.
각 이벤트당 한 문장(최대 160자). 원자재 티커명은 그대로 써도 됨.

입력(JSON):
{json.dumps(slim, ensure_ascii=False)}

출력은 JSON만:
{{"lines": ["첫 이벤트 한 줄", "둘째 …", …]}}
lines 개수는 이벤트 개수와 동일하게."""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        text = (response.text or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]
        data = json.loads(text)
        lines = data.get("lines")
        if not isinstance(lines, list):
            return None
        out = [str(x).strip() for x in lines if str(x).strip()]
        if len(out) != len(events):
            return None
        return out
    except Exception:
        return None


def enrich_commodity_impact_narratives(
    scout: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    holdings: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    전월 대비 급변 원자재(임계 이상)마다 서술 1줄 생성 → scout에 부착 후 JSON 재저장.
    """
    rows = scout.get("commodity_mom_alerts") or []
    th = float(scout.get("mom_alert_threshold_pct") or 10)
    rec_by = _stock_lookup(candidates, holdings)
    events: List[Dict[str, Any]] = []
    for row in rows[:5]:
        ct = row.get("commodity_ticker")
        pct = row.get("vs_prior_month_avg_pct")
        if ct is None or pct is None:
            continue
        if abs(float(pct)) < th:
            continue
        events.append(
            {
                "commodity_ticker": ct,
                "vs_prior_month_avg_pct": float(pct),
                "linked": _linked_for_commodity(scout, ct, rec_by),
            }
        )
    events = events[:3]

    gemini_lines = _gemini_briefs(events) if events else None
    if gemini_lines is not None and len(gemini_lines) != len(events):
        gemini_lines = None

    mom_narratives: List[Dict[str, Any]] = []
    narrative_lines: List[str] = []
    for i, ev in enumerate(events):
        if gemini_lines and i < len(gemini_lines) and gemini_lines[i]:
            line = gemini_lines[i]
            src = "gemini"
        else:
            line = _template_line(ev)
            src = "template"
        if len(line) > 220:
            line = line[:217] + "…"
        mom_narratives.append(
            {
                "commodity_ticker": ev["commodity_ticker"],
                "line": line,
                "source": src,
            }
        )
        narrative_lines.append(line)

    scout["mom_narratives"] = mom_narratives
    scout["narrative_lines"] = narrative_lines
    save_commodity_impact(scout)
    return scout


def narrative_for_commodity(scout: Dict[str, Any], commodity_ticker: str) -> Optional[str]:
    for item in scout.get("mom_narratives") or []:
        if item.get("commodity_ticker") == commodity_ticker:
            return item.get("line")
    return None
