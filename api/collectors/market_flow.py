"""
수급 분석 모듈
네이버 금융에서 외국인/기관 순매수 데이터 수집
"""
import re
import time
import requests
from typing import Dict

NAVER_SISE_URL = "https://finance.naver.com/item/frgn.naver"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}


def get_investor_flow(ticker: str) -> Dict:
    """
    네이버 금융에서 외국인/기관 순매수 데이터 수집
    반환: foreign_net, institution_net, foreign_ratio, flow_signal, flow_score
    """
    try:
        params = {"code": ticker}
        resp = requests.get(NAVER_SISE_URL, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        html = resp.text

        rows = re.findall(
            r'<td[^>]*class="num"[^>]*>([^<]*)</td>',
            html
        )

        foreign_nets = []
        institution_nets = []

        number_vals = []
        for raw in rows:
            cleaned = raw.strip().replace(",", "").replace("+", "")
            if cleaned and cleaned.lstrip("-").isdigit():
                number_vals.append(int(cleaned))

        foreign_ratio_match = re.search(
            r'외국인한도소진율.*?<td[^>]*>([0-9.]+)%',
            html, re.DOTALL
        )
        foreign_ratio = float(foreign_ratio_match.group(1)) if foreign_ratio_match else 0

        foreign_net = 0
        institution_net = 0
        if len(number_vals) >= 10:
            foreign_net = number_vals[4] if len(number_vals) > 4 else 0
            institution_net = number_vals[5] if len(number_vals) > 5 else 0

        score = 50
        signals = []

        if foreign_net > 0:
            score += 10
            signals.append("외국인 순매수")
        elif foreign_net < 0:
            score -= 10
            signals.append("외국인 순매도")

        if institution_net > 0:
            score += 10
            signals.append("기관 순매수")
        elif institution_net < 0:
            score -= 8
            signals.append("기관 순매도")

        if foreign_net > 0 and institution_net > 0:
            score += 10
            signals.append("외국인+기관 동반매수")

        if foreign_ratio > 50:
            score += 5

        score = max(0, min(100, score))

        time.sleep(0.3)

        return {
            "foreign_net": foreign_net,
            "institution_net": institution_net,
            "foreign_ratio": foreign_ratio,
            "flow_signals": signals,
            "flow_score": score,
        }

    except Exception:
        return {
            "foreign_net": 0,
            "institution_net": 0,
            "foreign_ratio": 0,
            "flow_signals": [],
            "flow_score": 50,
        }
