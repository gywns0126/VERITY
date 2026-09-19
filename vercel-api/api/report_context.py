"""Period-aware report context; arithmetic is not a claim about business causes.

Only published inputs are used. Unknown statement scope and missing citations stay
unknown, and quotes are kept separate from calculated observations.
"""
import math
import re
from datetime import date


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def format_money(value, currency="USD"):
    n = _number(value)
    if n is None:
        return "—"
    currency = currency if re.fullmatch(r"[A-Z]{3}", str(currency)) else "통화 미상"
    if currency == "KRW":
        for scale, unit in [(1e12, "조원"), (1e8, "억원")]:
            if abs(n) >= scale:
                return f"{n / scale:,.2f}{unit}"
        return f"{n:,.0f}원"
    prefix = "$" if currency == "USD" else currency + " "
    for scale, unit in [(1e12, "T"), (1e9, "B"), (1e6, "M")]:
        if abs(n) >= scale:
            return prefix + f"{n / scale:,.2f}{unit}"
    return prefix + f"{n:,.2f}"


def annual_context(row, financials, kr):
    explicit = row.get("currency") or financials.get("currency")
    currency = str(explicit or ("KRW" if kr else "USD")).upper()
    raw_scope = str(row.get("fs_div") or row.get("scope") or "").strip()
    scope = {"CFS": "연결", "OFS": "별도", "consolidated": "연결", "standalone": "별도"}.get(raw_scope, raw_scope)
    kind = str(row.get("period_kind") or "annual_feed")
    start, end = str(row.get("start") or ""), str(row.get("end") or "")
    return {
        "year": int(row["year"]), "currency": currency,
        "currency_basis": "보고 통화 필드" if explicit else "공개 피드 기본 단위",
        "scope": scope or "미수신", "kind": kind, "start": start, "end": end,
        "period": f"{start} ~ {end}" if start and end else f"{row['year']}년 연간 · 시작/종료일 미수신",
        "source_url": row.get("source_url") or row.get("url") or "",
        "filed": row.get("filed") or row.get("filed_at") or "미수신",
        "accession": row.get("accession") or row.get("accn") or "",
    }


def compare_annual(annual, financials, kr):
    """Check comparability before deriving changes. Missing scope is not verified."""
    base = {"usable": False, "reason": "비교할 연간 실적이 2개 연도 미만입니다.", "changes": [], "bridge": None}
    if len(annual) < 2:
        return base
    a, b = annual[-2:]
    ca, cb = annual_context(a, financials, kr), annual_context(b, financials, kr)
    if len({int(r['year']) for r in annual}) != len(annual):
        return {**base, "reason": "같은 연도의 재무가 중복되어 비교를 보류했습니다."}
    if cb["year"] - ca["year"] != 1:
        return {**base, "reason": "연간 실적에 누락 연도가 있어 전년 대비 증감률을 만들지 않았습니다."}
    if ca["currency"] != cb["currency"] or not re.fullmatch(r"[A-Z]{3}", ca["currency"]):
        return {**base, "reason": "보고 통화가 다르거나 불명확하여 연도 간 비교를 보류했습니다."}
    if ca["scope"] != cb["scope"]:
        return {**base, "reason": "연결·별도 기준이 다르거나 한쪽 기준이 누락되어 비교를 보류했습니다."}
    annual_kinds = {"annual_feed", "annual", "reported_year", "FY"}
    if ca["kind"] not in annual_kinds or cb["kind"] not in annual_kinds:
        return {**base, "reason": "연간 표에 다른 기간의 값이 섞여 있어 비교를 보류했습니다."}
    if any(c["start"] or c["end"] for c in (ca, cb)):
        try:
            spans = [(date.fromisoformat(c["start"]), date.fromisoformat(c["end"])) for c in (ca, cb)]
            lengths = [(end - start).days for start, end in spans]
            if not all(330 <= n <= 380 for n in lengths) or abs(lengths[0] - lengths[1]) > 14 or spans[0][1] >= spans[1][0]:
                raise ValueError("incomparable_duration")
        except ValueError:
            return {**base, "reason": "재무 기간의 길이·중복·누락을 확인해야 하므로 비교를 보류했습니다."}
    changes = []
    currency = cb["currency"]
    for key, label in [("revenue", "매출"), ("op", "영업이익"), ("net", "순이익")]:
        old, new = _number(a.get(key)), _number(b.get(key))
        if old is not None and new is not None:
            growth = (new / old - 1) * 100 if old > 0 else None
            changes.append({"metric": key, "label": label, "old": old, "new": new, "growth_pct": growth,
                            "text": f"{label} {format_money(old, currency)} → {format_money(new, currency)}" + (f" ({growth:+.1f}%)" if growth is not None else " (증감률 제외: 전기 0 이하)")})
    bridge = None
    r0, r1, o0, o1 = [_number(v) for v in (a.get("revenue"), b.get("revenue"), a.get("op"), b.get("op"))]
    if all(v is not None for v in (r0, r1, o0, o1)) and r0 > 0 and r1 > 0:
        m0, m1 = o0 / r0, o1 / r1
        bridge = {"old_margin_pct": m0 * 100, "new_margin_pct": m1 * 100,
                  "margin_change_pp": (m1 - m0) * 100,
                  "revenue_effect": (r1 - r0) * m0, "margin_effect": r1 * (m1 - m0),
                  "operating_change": o1 - o0,
                  "formula": "Δ영업이익 = (당기 매출−전기 매출)×전기 영업이익률 + 당기 매출×(당기−전기 영업이익률)",
                  "operands": {"prior_revenue": r0, "current_revenue": r1, "prior_op": o0, "current_op": o1}}
    return {"usable": True, "reason": "", "period": f"{ca['year']} → {cb['year']}", "currency": currency,
            "changes": changes, "bridge": bridge, "scope": cb["scope"],
            "qualification": "발행자료상 연간 비교 · 연결/별도 및 원문 수치 대조 필요" if cb["scope"] == "미수신" else f"{cb['scope']} 연간 비교 · 원문 수치 대조 필요"}


def business_profile(record, stock, source_cell):
    text = str(record.get("text") or "").strip()
    source = source_cell(record)
    if text and isinstance(source, dict) and source["text"] == "원문 열기":
        paragraphs = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
        product_paragraph = next((p for p in paragraphs if re.search(r"사업별|주요 제품|주요 서비스|제품을|제품과|생산[ㆍ·, ]*판매하며", p)), None)
        selected = product_paragraph or next((p for p in paragraphs if any(w in p for w in ("생산", "판매", "제공", "운영", "manufactur", "services"))), paragraphs[0])
        # Contiguous excerpt only; never stitch separate clauses into a new claim.
        short = selected[:220]
        if len(selected) > 220:
            ends = [m.end() for m in re.finditer(r"[.!?](?:\s|$)|다\.", short)]
            if ends and ends[-1] >= 80:
                short = short[:ends[-1]].rstrip()
            short += " …"
        return {"available": True, "summary": short, "text": text, "source": source,
                "label": f"{record.get('fiscal_year') or '기준연도 미수신'} · {record.get('report') or '사업 설명'} · 원문 발췌",
                "filed_at": str(record.get("filed_at") or "미수신"), "truncated": bool(record.get("truncated"))}
    sector = str(stock.get("business") or stock.get("gics_ko") or "업종 미수신")
    return {"available": False, "summary": f"업종 분류: {sector}. 이 리포트에 제품·사업부 설명 원문이 연결되지 않았습니다.",
            "text": "", "source": None, "label": "업종 분류는 수익 구조 설명의 대체물이 아닙니다."}


def first_page(profile, comparison, issues):
    cards = [{"title": "어떤 사업을 하나", "observation": profile["summary"],
              "question": profile["label"], "refs": "B1" if profile["available"] else "R", "source": profile["source"]}]
    if comparison["usable"] and comparison["changes"]:
        changes = comparison["changes"]
        op = next((r for r in changes if r["metric"] == "op"), None)
        revenue = next((r for r in changes if r["metric"] == "revenue"), None)
        title = "최근 실적에서 달라진 점"
        if op and revenue and revenue["new"] > revenue["old"] and op["new"] < op["old"]:
            title = "매출은 늘었지만 영업이익은 줄었습니다"
        cards.append({"title": title, "observation": comparison["period"] + ": " + " · ".join(r["text"] for r in changes[:2]),
                      "question": comparison["qualification"], "refs": "R0 · R1", "source": None})
        bridge = comparison["bridge"]
        if bridge:
            direction = "낮아졌습니다" if bridge["margin_change_pp"] < 0 else "높아졌습니다" if bridge["margin_change_pp"] > 0 else "같습니다"
            observation = f"영업이익률 {bridge['old_margin_pct']:.1f}% → {bridge['new_margin_pct']:.1f}% ({bridge['margin_change_pp']:+.1f}%p). 매출 1원당 남긴 영업이익의 비율이 {direction}"
            question = "가격·판매량·제품 구성·비용·일회성 항목 중 무엇이 설명하는지 사업부 실적과 회사 설명에서 확인하세요. 아래 계산만으로 사업 원인을 단정하지 않습니다."
            refs = "R5"
        else:
            observation, question, refs = "매출과 영업이익이 함께 있어야 이익률 변화를 계산할 수 있습니다.", "누락된 실적과 비교 기간을 원문에서 먼저 확인하세요.", "R0 · R1"
    else:
        cards.append({"title": "최근 실적 비교는 보류합니다", "observation": comparison["reason"] or "비교 가능한 연간 수치가 없습니다.",
                      "question": "누락된 기간과 보고 기준을 확인한 뒤 비교합니다.", "refs": "R0 · R1", "source": None})
        event = next((q for q in issues if q["refs"] == "D1"), None)
        observation = event["observation"] if event else "현재 자료만으로 실적 변화의 원인을 설명할 수 없습니다."
        question = "최신 실적 공시의 재무 기간·보고 통화·연결/별도와 사업 설명을 먼저 확인하세요."
        refs = "D1" if event else "R"
    cards.append({"title": "다음에 확인할 핵심", "observation": observation, "question": question, "refs": refs, "source": None})
    return cards
