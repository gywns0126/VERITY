"""
수급 분석 모듈 v2 (Sprint 3)
- 5일치 외국인/기관 순매수 추이 수집
- 연속 매수/매도 일수 계산
- 금액 규모별 가중 점수
"""
import re
import time
import requests
from typing import Dict, List

NAVER_SISE_URL = "https://finance.naver.com/item/frgn.naver"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}


def _parse_flow_table(html: str) -> List[Dict]:
    """네이버 금융 수급 테이블에서 최근 5일 데이터 파싱"""
    rows = re.findall(
        r'<td[^>]*class="num"[^>]*>([^<]*)</td>',
        html
    )
    number_vals = []
    for raw in rows:
        cleaned = raw.strip().replace(",", "").replace("+", "")
        if cleaned and cleaned.lstrip("-").isdigit():
            number_vals.append(int(cleaned))
    return number_vals


def _count_consecutive(values: List[int], positive: bool) -> int:
    """연속 양수(또는 음수) 일수 계산"""
    count = 0
    for v in values:
        if (positive and v > 0) or (not positive and v < 0):
            count += 1
        else:
            break
    return count


def get_investor_flow(ticker: str) -> Dict:
    """
    네이버 금융에서 외국인/기관 순매수 데이터 수집 (강화)
    반환: 금액, 연속일수, 5일 합산, 외국인 비율, 점수, 시그널
    """
    try:
        params = {"code": ticker}
        resp = requests.get(NAVER_SISE_URL, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        html = resp.text

        number_vals = _parse_flow_table(html)

        foreign_ratio_match = re.search(
            r'외국인한도소진율.*?<td[^>]*>([0-9.]+)%',
            html, re.DOTALL
        )
        foreign_ratio = float(foreign_ratio_match.group(1)) if foreign_ratio_match else 0

        foreign_net = number_vals[4] if len(number_vals) > 4 else 0
        institution_net = number_vals[5] if len(number_vals) > 5 else 0

        foreign_5d = [number_vals[i] for i in range(4, min(len(number_vals), 54), 10)][:5]
        institution_5d = [number_vals[i] for i in range(5, min(len(number_vals), 55), 10)][:5]

        foreign_5d_sum = sum(foreign_5d) if foreign_5d else 0
        institution_5d_sum = sum(institution_5d) if institution_5d else 0

        foreign_consec_buy = _count_consecutive(foreign_5d, positive=True)
        foreign_consec_sell = _count_consecutive(foreign_5d, positive=False)
        inst_consec_buy = _count_consecutive(institution_5d, positive=True)
        inst_consec_sell = _count_consecutive(institution_5d, positive=False)

        score = 50
        signals = []

        if foreign_net > 0:
            score += 8
            signals.append(f"외국인 순매수({foreign_net:+,}주)")
        elif foreign_net < 0:
            score -= 8
            signals.append(f"외국인 순매도({foreign_net:+,}주)")

        if institution_net > 0:
            score += 8
            signals.append(f"기관 순매수({institution_net:+,}주)")
        elif institution_net < 0:
            score -= 6
            signals.append(f"기관 순매도({institution_net:+,}주)")

        if foreign_net > 0 and institution_net > 0:
            score += 8
            signals.append("외국인+기관 동반매수")

        if foreign_consec_buy >= 3:
            score += 6
            signals.append(f"외국인 {foreign_consec_buy}일 연속매수")
        elif foreign_consec_sell >= 3:
            score -= 6
            signals.append(f"외국인 {foreign_consec_sell}일 연속매도")

        if inst_consec_buy >= 3:
            score += 5
            signals.append(f"기관 {inst_consec_buy}일 연속매수")
        elif inst_consec_sell >= 3:
            score -= 5
            signals.append(f"기관 {inst_consec_sell}일 연속매도")

        if foreign_5d_sum > 0 and institution_5d_sum > 0:
            score += 5
            signals.append("5일 수급 양호")

        if foreign_ratio > 50:
            score += 3

        score = max(0, min(100, score))

        time.sleep(0.3)

        return {
            "foreign_net": foreign_net,
            "institution_net": institution_net,
            "foreign_5d_sum": foreign_5d_sum,
            "institution_5d_sum": institution_5d_sum,
            "foreign_consec_buy": foreign_consec_buy,
            "foreign_consec_sell": foreign_consec_sell,
            "inst_consec_buy": inst_consec_buy,
            "inst_consec_sell": inst_consec_sell,
            "foreign_ratio": foreign_ratio,
            "flow_signals": signals,
            "flow_score": score,
        }

    except Exception:
        return {
            "foreign_net": 0, "institution_net": 0,
            "foreign_5d_sum": 0, "institution_5d_sum": 0,
            "foreign_consec_buy": 0, "foreign_consec_sell": 0,
            "inst_consec_buy": 0, "inst_consec_sell": 0,
            "foreign_ratio": 0, "flow_signals": [], "flow_score": 50,
        }
