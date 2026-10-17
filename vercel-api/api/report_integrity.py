"""Distinguish received display values from attributable financial evidence.

Legacy formatted values are never promoted into arithmetic inputs. Parsing below
only detects contradictory displayed totals and keeps the received value visible.
"""
import re

if __package__:
    from .report_context import _number
    from .report_reader import valid_period
else:
    from report_context import _number
    from report_reader import valid_period


def displayed_amount(value):
    if isinstance(value, (int, float)):
        return _number(value)
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*(조|억|만)?(?:원)?", str(value or "").replace(",", "").replace("−", "-").strip())
    if not match:
        return None
    return float(match[1]) * {None: 1, "만": 1e4, "억": 1e8, "조": 1e12}[match[2]]


def financial_display(fin):
    """Return a presentation copy; do not change stored or published operands."""
    groups, warnings = [], []
    for group in fin.get("groups", []):
        rows = [dict(r) for r in group.get("rows", [])]
        by_name = {r.get("k"): r for r in rows}
        for row in rows:
            if row.get("status") in ("conflict", "inconsistent", "unverified_zero"):
                warnings.append(f"{row.get('k')}: {row.get('reason') or '수신값의 원천 확인 필요'}")
                if row.get("status") == "unverified_zero":
                    row.update(received_value=row.get("v"), v="확인 필요 (수신값 0)")
        gross, op, sga = (displayed_amount(by_name.get(k, {}).get("v"))
                          for k in ("매출총이익", "영업이익", "판매비와관리비"))
        if sga == 0 and gross is not None and op is not None and abs(gross - op) > 2e8:
            # Rounding of two whole-eok display values cannot explain this gap.
            # Other operating accounts may explain it, so never derive SG&A.
            row = by_name["판매비와관리비"]
            row.update(received_value=row.get("v"), v="확인 필요 (수신값 0)",
                       status="inconsistent", reason="매출총이익·영업이익과의 차이 및 기타 영업항목 대조 필요")
            warnings.append("판매비와관리비 수신값 0은 매출총이익·영업이익과 함께 검산이 필요합니다. 차액을 판관비로 대체하지 않았습니다.")
        elif sga == 0:
            # Agreement of formatted totals is not proof of an original zero.
            # Reviewed statement metrics replace this legacy group separately.
            row = by_name["판매비와관리비"]
            row.update(received_value=row.get("v"), v="확인 필요 (수신값 0)",
                       status="unverified_zero", reason="직접 원문 계정·기간·범위가 연결되지 않은 수집 요약값")
            warnings.append("판매비와관리비 수신값 0의 직접 원문을 확인하지 못했습니다. 합계 일치만으로 실제 판관비 0을 확정하지 않습니다.")
        groups.append({**group, "rows": rows})
    return {**fin, "groups": groups}, warnings


def cash_receipt(fin, reader):
    rows = [r for g in fin.get("groups", []) if g.get("title") == "현금흐름표"
            for r in g.get("rows", []) if r.get("k") in ("영업활동", "영업현금흐름", "영업활동 현금흐름")]
    received = next((r for r in rows if r.get("v") not in (None, "", "—")), None)
    cash = reader.get("cash")
    usable_cash = bool(cash and valid_period(cash) and _number(cash.get("ocf")) is not None)
    shown = displayed_amount(received["v"]) if received else None
    rounded = re.fullmatch(r"[+-]?\d+(?:\.(\d+))?\s*(조|억|만)(?:원)?", str(received["v"]).replace(",", "").strip()) if received else None
    tolerance = ({"만": 1e4, "억": 1e8, "조": 1e12}[rounded[2]] * 10 ** -len(rounded[1] or "") / 2) if rounded else 0
    # The reader may legitimately contain older cash data. It is not provenance
    # for the latest formatted summary, even when the amounts happen to match.
    summary_linked = bool(usable_cash and received
                          and str(fin.get("period")) == str(cash.get("year"))
                          and cash.get("period_kind") == "annual"
                          and fin.get("currency") == cash.get("currency")
                          and fin.get("fs_div") == cash.get("fs_div")
                          and shown is not None and abs(shown - _number(cash.get("ocf"))) <= tolerance)
    if usable_cash and (not received or summary_linked):
        return {"received": True, "period_identified": True, "source_linked": True,
                "primary_value_verified": False, "calculation_ready": True,
                "analysis_usable": _number(cash.get("net")) is not None,
                "reported_period": cash["end"], "summary_linked": summary_linked,
                "status": cash["end"] + (" 기간·원문 연결" if received else " 원값 연결 · 요약값 미수신"), "missing_fields": [],
                "note": "공시 링크 연결은 개별 원문 수치 대조 완료를 뜻하지 않습니다."}
    missing = ["현금흐름 숫자 원값", "시작일·종료일", "통화", "연결·별도", "개별 계정 공시 원문"]
    note = (f"부록 R2에 {fin.get('period') or '기간 미상'}년 영업현금흐름 요약값 {received['v']}을 수신했습니다. "
            "이 값의 기간·통화·연결/별도·개별 계정 원문이 분석용 숫자와 연결되지 않아 순이익 비교를 보류했습니다. "
            "요약값이 없는 상태와는 다릅니다.") if received else "영업현금흐름 숫자와 요약값을 수신하지 못해 순이익과 비교하지 않았습니다."
    if usable_cash:
        note += f" 본문의 {cash['start']}~{cash['end']} 현금흐름은 별도 자료이며 이 요약값의 연결 근거로 사용하지 않았습니다."
    return {"received": bool(received), "received_value": received.get("v") if received else None,
            "reported_period": fin.get("period"), "period_identified": False,
            "source_linked": False, "summary_linked": False, "primary_value_verified": False, "calculation_ready": False,
            "analysis_usable": False, "status": "요약값 수신 · 분석 연결 미완료" if received else "미수신",
            "missing_fields": missing, "note": note}


def valuation_display(facts, notes, calculations):
    values, descriptions, warnings = dict(facts), dict(calculations), []
    for key in ("PBR", "BPS"):
        calc = str(calculations.get(key) or "")
        if key not in facts or not re.search(r"총자산.*부채비율|assets_debt_ratio", calc):
            continue
        values[key] = f"추정 {facts[key]}" if not str(facts[key]).startswith("추정") else facts[key]
        qualification = "역산 자기자본 기준의 추정값 · 지배기업 소유주지분 직접값 미확인"
        if key == "BPS":
            qualification += " · 자기주식 차감 및 주식수 기준일 정합 미확인"
        descriptions[key] = calc + " · " + qualification
        warnings.append(f"{key}는 역산 자기자본으로 계산한 추정값입니다. 지배기업 소유주지분과 주식수 기준을 확인하기 전 확정적인 가치 판단에 사용하지 않습니다.")
    return values, descriptions, warnings


def quarter_missing_fields(row):
    labels = {"start": "시작일", "end": "종료일", "period_kind": "단일 분기·누적 구분",
              "currency": "통화", "fs_div": "연결·별도", "source_url": "공시 원문 URL"}
    return [label for key, label in labels.items() if not row.get(key)]
