"""Reader-facing facts from period-aligned evidence, without generated narrative."""
from datetime import date
import re
from urllib.parse import urlparse

if __package__:
    from .report_context import format_money, _number
else:
    from report_context import format_money, _number

LABELS = {"annual": "연간", "quarter": "단일 분기", "ytd": "누적"}


def valid_period(row):
    try:
        days = (date.fromisoformat(row["end"]) - date.fromisoformat(row["start"])).days
        kind = row.get("period_kind")
        span_ok = {"annual": 330 <= days <= 380, "quarter": 70 <= days <= 110,
                   "ytd": 150 <= days <= 300}.get(kind, False)
        u = urlparse(row.get("source_url", ""))
        return bool(span_ok and row.get("fs_div") in ("CFS", "OFS", "ENTITY")
                    and re.fullmatch(r"[A-Z]{3}", row.get("currency", ""))
                    and u.scheme == "https" and u.hostname and u.path not in ("", "/"))
    except (ValueError, KeyError, TypeError):
        return False


def period_label(row):
    return f"{row['start']} ~ {row['end']} · {LABELS[row['period_kind']]}"


def comparable(a, b):
    if not valid_period(a) or not valid_period(b):
        return False
    if any(a[k] != b[k] for k in ("currency", "fs_div", "period_kind")):
        return False
    start_delta = (date.fromisoformat(b["start"]) - date.fromisoformat(a["start"])).days
    end_delta = (date.fromisoformat(b["end"]) - date.fromisoformat(a["end"])).days
    return 350 <= start_delta <= 380 and 350 <= end_delta <= 380 and abs(start_delta - end_delta) <= 14


def reader_financials(periods, is_financial=False):
    usable = sorted([r for r in periods if valid_period(r)], key=lambda r: (r["end"], r["start"], r.get("filed", "")))
    # Keep one filing for a complete period. Never join metrics from different filings here.
    unique = {}
    for row in usable:
        unique[(row["start"], row["end"], row["currency"], row["fs_div"])] = row
    usable = list(unique.values())
    income = [r for r in usable if any(_number(r.get(k)) is not None for k in ("revenue", "op", "net"))]
    current = max(income, key=lambda r: (r["end"], r["start"]), default=None)
    prior = next((r for r in reversed(income) if current and comparable(r, current)), None)
    rows, observations = [], []
    if current:
        for key, label in [("revenue", "매출"), ("op", "영업이익"), ("net", "순이익")]:
            value = _number(current.get(key))
            before = _number(prior.get(key)) if prior else None
            change = f"{(value / before - 1) * 100:+.1f}%" if value is not None and before is not None and before > 0 else "미산출"
            rows.append([label, format_money(before, current["currency"]), format_money(value, current["currency"]), change])
        if prior and all(_number(r.get(k)) is not None for r in (prior, current) for k in ("revenue", "op")):
            if prior["revenue"] > 0 and current["revenue"] > 0:
                m0, m1 = prior["op"] / prior["revenue"] * 100, current["op"] / current["revenue"] * 100
                observations.append(f"영업이익률 {m0:.1f}% → {m1:.1f}% ({m1-m0:+.1f}%p). 매출 중 영업이익으로 남은 비율입니다.")
        if not prior:
            observations.append("같은 길이·통화·재무제표 기준의 전년 동기 자료가 없어 증감률을 표시하지 않았습니다.")
    else:
        observations.append("기간·통화·연결/별도·원문을 함께 확인할 수 있는 손익 자료가 아직 없습니다.")

    cash = max([r for r in usable if _number(r.get("ocf")) is not None], key=lambda r: (r["end"], r["start"]), default=None)
    cash_rows, cash_notes = [], []
    if cash:
        ccy = cash["currency"]
        ocf, net, capex = [_number(cash.get(k)) for k in ("ocf", "net", "capex")]
        cash_rows = [["순이익", format_money(net, ccy)], ["영업현금흐름", format_money(ocf, ccy)],
                     ["유형자산 취득 지출", format_money(capex, ccy)]]
        if net is not None:
            cash_notes.append(f"영업현금흐름 − 순이익 = {format_money(ocf-net, ccy)}. 감가상각·운전자본·세금 등 조정이 포함되므로 차이만으로 이익의 질을 단정하지 않습니다.")
        if is_financial:
            cash_notes.append("금융업은 자금 조달·대출이 영업 구조에 포함돼 일반 기업식 FCF 비교에서 제외합니다.")
        elif capex is not None and capex >= 0:
            cash_rows.append(["유형자산 취득 후 현금흐름", format_money(ocf-capex, ccy)])
            cash_notes.append("자체계산: 영업현금흐름 − 유형자산 취득 지출. 무형자산·인수 지출 등이 빠질 수 있어 회사가 정의한 FCF와 다를 수 있습니다.")
        else:
            cash_notes.append("같은 기간의 유형자산 취득 지출이 없어 차감 후 현금흐름을 계산하지 않았습니다. 누락을 0으로 취급하지 않습니다.")
        if current and cash["end"] < current["end"]:
            cash_notes.insert(0, f"현금흐름의 마지막 확인 기간은 {cash['end']}로, 위 손익보다 이전 자료입니다.")
    else:
        cash_notes.append("기간과 원문이 연결된 영업현금흐름이 없어 순이익과 비교하지 않았습니다.")
    result = {"current": current, "prior": prior, "rows": rows, "observations": observations,
            "cash": cash, "cash_rows": cash_rows, "cash_notes": cash_notes,
            "periods": usable, "accepted": len(usable), "received": len(periods)}
    if __package__:
        from .report_visuals import build_visuals
    else:
        from report_visuals import build_visuals
    result["visuals"] = build_visuals(result, is_financial, comparable)
    return result
