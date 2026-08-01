"""us_investor_portfolios_public_builder — 투자 거장 '인물 축' 포트폴리오 빌더.

2026-07-30 신설 (PM 요청 — "거물 투자자 나열 → 클릭하면 포트폴리오").
기존 us_smart_money_13f 는 **종목 축**("이 종목을 누가 들고 있나")이라 종목 상세에서만 쓰인다.
본 빌더는 같은 13F 원천을 **인물/기관 축**("이 사람이 뭘 들고 있나")으로 뒤집는다.

🚨 RULE 7 = 공시 사실만. 자체 점수·매매신호 0.

🚨🚨 '수익률 랭킹' 을 만들지 않는 이유 (의도적 부재 — 나중에 누가 추가하려 하면 이 주석부터 읽을 것):
  · 13F 는 **분기말 기준 보유를 최대 45일 뒤 제출**. 실측 Berkshire — reportDate 2026-03-31 /
    filingDate 2026-05-15. 즉 조회 시점엔 이미 수개월 전 스냅샷이다.
  · **롱 미국주식만** 담긴다. 숏·채권·현금·비미국·대부분 파생 제외(13F 제도 자체의 범위).
    버핏의 현금비중도, 소로스의 숏도 안 보인다.
  · 따라서 이 데이터로 계산한 어떤 수치도 "그 사람의 수익률" 이 아니다. 그렇게 라벨하면 거짓.
  · 대신 공시로부터 직접 확인되는 사실만 낸다 — 공시 총액, QoQ 총액 변동, 종목별 NEW/증액/감액,
    집중도(상위 N 비중). QoQ 총액 변동은 **주가 변동과 실제 매매가 섞인 값**이라 수익률이 아님을
    필드명(disclosed_value_change_pct)과 caveat 양쪽에 명시한다.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

from api.collectors.sec_13f_collector import (
    MANAGER_PERSON, get_recent_13f_filings, parse_13f_holdings,
    compute_replication_returns, annualize_from_quarters,
)
from api.collectors.investor_profiles import collect_profiles
from api.collectors.cusip_resolver import resolve_cusips
from api.builders.us_smart_money_13f_public_builder import (
    ACTIVE_MANAGERS, TOP_HOLDINGS_PER_FUND, _holdings_with_change,
)
from api.builders.us_insider_trades_public_builder import _now_kst

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_investor_portfolios.json")

# 인물 카드에 노출할 종목 수 (평가액 상위). 전체는 파일 비대 — 공개 blob 크기 bound.
TOP_SHOWN = 25

_CAVEAT = (
    "13F 공시 기반 — 분기말 기준 보유를 최대 45일 뒤 제출(조회 시점엔 수개월 전 스냅샷). "
    "롱 미국주식만 포함되며 숏·채권·현금·비미국·대부분 파생은 제도상 제외된다. "
    "따라서 이 수치는 해당 인물의 수익률이 아니다. "
    "disclosed_value_change_pct = 공시 총액의 분기 대비 변동으로, 주가 변동과 실제 매매가 섞인 값."
)

_RETURN_CAVEAT = (
    "복제 수익률 = 각 분기말 공시 포지션을 다음 분기말까지 그대로 보유했다고 가정한 계산값. "
    "분기 중 매매(공시와 공시 사이의 진입·청산)가 반영되지 않아 실제 운용 성과와 다르다. "
    "숏·현금·채권·비미국·파생은 13F 자체에 없어 제외된다. "
    "두 분기 모두 보유한 종목만 계산 가능하므로 coverage_pct(계산에 포함된 평가액 비중)를 함께 본다."
)


def _concentration(holdings: List[dict], top_n: int = 10) -> float | None:
    """상위 top_n 종목이 공시 총액에서 차지하는 비중(%). 집중형/분산형 구분용 사실값."""
    total = sum(h.get("value_usd") or 0 for h in holdings)
    if total <= 0:
        return None
    top = sum(h.get("value_usd") or 0 for h in holdings[:top_n])
    return round(top / total * 100, 1)


# ── 공시에 보이는 운용 방식 (2026-08-01, PM "개미투자자들로 하여금 이해하기 좋게") ──
#
# 🚨 이것은 **성향 판정이 아니다.** "안정적/공격적" 라벨을 붙이지 않는다.
#   13F 는 미국 상장 롱 주식만 담는다 — 현금·채권·숏·해외자산이 통째로 빠진다.
#   실측 반례(2026-08-01): 워런 버핏의 상위10 집중도는 90.7% 로 16인 중 4위다.
#   집중도로 성향을 판정하면 버핏이 "공격적" 이 된다. 그의 안정성은 대부분 현금·보험
#   플로트에서 오는데 그건 13F 에 안 나오기 때문이다. 그래서 판정 대신 **공시 숫자를
#   말로 옮기기만** 한다. 독자가 스스로 읽는다.
#
# 구간값은 서술 편의를 위한 것이며 점수·순위·매매신호가 아니다(RULE 7 — 자체 산식 노출 시
# 가설 명시. 여기서는 아예 점수를 만들지 않는 쪽을 택했다).
_STYLE_BANDS = (
    (90, "몇 개만 크게", "상위 10종목이 대부분입니다"),
    (60, "소수에 실음", "상위 10종목 비중이 큽니다"),
    (35, "반반", "상위 10종목과 나머지가 비슷합니다"),
    (0,  "잘게 쪼갬", "수백 종목에 나눠 담았습니다"),
)
_LOW_TURNOVER_PCT = 15      # 분기 중 손댄 종목이 이 % 미만 = "거의 안 바꿈"
_HIGH_VOL = 12.0            # 분기 복제 수익률 표준편차가 이 이상 = "기복 큼"
_CASH_CAVEAT_CONC = 85      # 집중도가 이 이상이면 현금·채권 미포함 단서를 함께 노출


def _disclosed_style(conc, moves: int, n: int, rets: list) -> Dict[str, Any]:
    """집중도·회전·변동을 평서문으로. 판정·점수 없음."""
    out: Dict[str, Any] = {"label": None, "detail": None, "badges": [], "cash_caveat": False}
    if conc is None or not n:
        return out
    for lo, label, detail in _STYLE_BANDS:
        if conc >= lo:
            out["label"] = label
            out["detail"] = detail
            break
    # 회전 — holdings_count 가 상한에 걸리면 분모가 잘려 비율이 부풀므로 배지를 달지 않는다.
    if n < TOP_HOLDINGS_PER_FUND and (moves / n * 100) < _LOW_TURNOVER_PCT:
        out["badges"].append("거의 안 바꿈")
    vals = [q.get("return_pct") for q in (rets or []) if q.get("return_pct") is not None]
    if len(vals) >= 3:
        m = sum(vals) / len(vals)
        sd = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
        if sd >= _HIGH_VOL:
            out["badges"].append("기복 큼")
    out["cash_caveat"] = conc >= _CASH_CAVEAT_CONC
    return out


def build() -> Dict[str, Any]:
    investors: List[Dict[str, Any]] = []
    errors: List[str] = []
    # 전기 사실은 거의 안 변하므로 캐시 우선 — 위키 호출 절약 + 실패해도 기존 값 유지.
    try:
        profiles = collect_profiles(list(ACTIVE_MANAGERS.values()))
    except Exception as e:                                     # noqa: BLE001
        errors.append(f"프로필 수집 실패(무시): {type(e).__name__}")
        profiles = {}

    for cik, name in ACTIVE_MANAGERS.items():
        try:
            filings = get_recent_13f_filings(cik, n=2)
            if not filings:
                errors.append(f"{name}: 13F-HR 없음")
                continue
            curr_f = filings[0]
            curr = parse_13f_holdings(curr_f["accession_no"], cik)[:TOP_HOLDINGS_PER_FUND]
            if not curr:
                errors.append(f"{name}: 보유 파싱 0건")
                continue
            prev = []
            if len(filings) > 1:
                prev = parse_13f_holdings(filings[1]["accession_no"], cik)[:TOP_HOLDINGS_PER_FUND]

            rows = _holdings_with_change(curr, prev)
            tickers = resolve_cusips([h["cusip"] for h in rows if h.get("cusip")])
            for h in rows:
                h["ticker"] = tickers.get(h.get("cusip"))

            total_now = sum(h.get("value_usd") or 0 for h in rows)
            total_prev = sum(h.get("value_usd") or 0 for h in prev)
            # 🚨 수익률 아님 — 주가 변동 + 실제 매매가 섞인 '공시 총액' 변동.
            change_pct = (
                round((total_now - total_prev) / total_prev * 100, 2)
                if total_prev > 0 else None
            )

            shown = [
                {
                    "ticker": h.get("ticker"),
                    "cusip": h.get("cusip"),
                    "shares": h.get("shares"),
                    "value_usd": h.get("value_usd"),
                    "weight_pct": (round((h.get("value_usd") or 0) / total_now * 100, 2)
                                   if total_now > 0 else None),
                    "change_type": h.get("change_type"),
                    "value_change_usd": h.get("value_change_usd"),
                }
                for h in rows[:TOP_SHOWN]
            ]

            # CUSIP→ticker 미해석 건수 노출. 실측(2026-07-30 ARK) 113건 중 39건 미해석 —
            # 비상장·ADR·채권성 항목 등. ticker=None 을 침묵시키면 프론트가 빈 칸을 그리므로
            # 건수를 사실로 내보내고 cusip 은 그대로 남겨 링크아웃 가능하게 둔다.
            unresolved = sum(1 for h in rows if not h.get("ticker"))

            # 분기 복제 수익률 — 실제 성과 아님(아래 caveat). 과거 제출본은 캐시라 재조회 없음.
            try:
                rets = compute_replication_returns(cik, quarters=9)
            except Exception as e:                             # noqa: BLE001
                errors.append(f"{name}: 복제수익률 실패 {type(e).__name__}")
                rets = []

            _conc = _concentration(rows, 10)
            _n = len(rows)
            _capped = _n >= TOP_HOLDINGS_PER_FUND
            _moves = sum(1 for h in rows
                         if h.get("change_type") in ("NEW", "INCREASED", "DECREASED"))
            _style = _disclosed_style(_conc, _moves, _n, rets)

            investors.append({
                "cik": cik,
                "institution": name,
                "person": MANAGER_PERSON.get(name),
                # 공시에 보이는 운용 방식 (2026-08-01) — 아래 _disclosed_style 주석 참조.
                "disclosed_style": _style,
                # holdings_count 는 TOP_HOLDINGS_PER_FUND 상한에 걸린다. 상한이면 실제는 더 많다.
                "holdings_capped": _capped,
                "profile": profiles.get(name),
                "quarterly_replication_returns": rets,
                "trailing_4q_replication_pct": annualize_from_quarters(rets),
                "unresolved_ticker_count": unresolved,
                # 🚨 보유 기준일 ≠ 제출일. 둘 다 노출해야 신선도 오독이 안 난다.
                "report_date": curr_f.get("report_date"),
                "filed_at": curr_f.get("filed_at"),
                "prev_report_date": filings[1].get("report_date") if len(filings) > 1 else None,
                "holdings_count": _n,
                "disclosed_value_usd": total_now,
                "prev_disclosed_value_usd": total_prev or None,
                "disclosed_value_change_pct": change_pct,
                "top10_concentration_pct": _conc,
                "new_count": sum(1 for h in rows if h.get("change_type") == "NEW"),
                "increased_count": sum(1 for h in rows if h.get("change_type") == "INCREASED"),
                "decreased_count": sum(1 for h in rows if h.get("change_type") == "DECREASED"),
                "top_holdings": shown,
            })
        except Exception as e:  # noqa: BLE001 — 한 매니저 실패가 전체를 죽이지 않게
            errors.append(f"{name}: {type(e).__name__} {str(e)[:80]}")

    # 정렬 = 공시 총액 내림차순 (수익률 랭킹 아님 — 위 caveat 참조).
    investors.sort(key=lambda x: x.get("disclosed_value_usd") or 0, reverse=True)

    return {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "source": "SEC EDGAR 13F-HR + OpenFIGI CUSIP→ticker",
            "investor_count": len(investors),
            "ranking_basis": "disclosed_value_usd (공시 총액) — 수익률 랭킹 아님",
            "caveat": _CAVEAT,
            "return_caveat": _RETURN_CAVEAT,
            "profile_source": "위키백과 REST summary — 직업 키워드 검증 통과분만(동명이인 가드)",
            "errors": errors,
        },
        "investors": investors,
    }


def main() -> int:
    data = build()
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    tmp = OUTPUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, OUTPUT_PATH)

    m = data["_meta"]
    sys.stderr.write(
        f"[investor_portfolios] {m['investor_count']}명 저장 → {OUTPUT_PATH}\n"
    )
    for e in m["errors"]:
        sys.stderr.write(f"::warning::[investor_portfolios] {e}\n")
    # 전원 실패 = 상류 장애. 부분 실패는 경고만(한 매니저 공시 지연이 전체를 막지 않도록).
    if not data["investors"]:
        sys.stderr.write("::error::[investor_portfolios] 수집 0명 — SEC EDGAR 점검 필요\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
