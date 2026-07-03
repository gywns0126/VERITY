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
NAVER_TREND_URL = "https://m.stock.naver.com/api/stock/{code}/trend"  # 모바일 JSON 폴백

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://finance.naver.com/",
}

# frgn 데이터 행 = class="tah" 셀 [날짜,종가,전일비,등락률,거래량,기관(5),외국인(6),보유주수(7),소진율(8)]
# 원전 = scripts/kr/flow_observation_logger.py 실검증 파서(2026-06-15). 구 class="num" 파서는
# 매치 0 → 전 종목 flow 0/중립 silent 반환 (2026-07-04 실호출 확정 후 이식).
_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_TAH = re.compile(r'<(?:td|span)[^>]*class="tah[^"]*"[^>]*>(.*?)</(?:td|span)>', re.S)
_DATE = re.compile(r"\d{4}\.\d{2}\.\d{2}")


def _num(s: str) -> int:
    s = re.sub(r"<[^>]+>", "", s).strip().replace(",", "").replace("+", "").replace("%", "")
    try:
        return int(float(s))
    except ValueError:
        return 0


def _parse_flow_table(html: str) -> List[Dict]:
    """frgn 페이지 → 최신순 [{foreign, inst, ratio}] (주 단위, ratio=외국인 소진율 %)."""
    rows: List[Dict] = []
    for tr in _TR.findall(html):
        if not _DATE.search(tr):
            continue
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in _TAH.findall(tr)]
        cells = [c for c in cells if c]
        if len(cells) < 7 or not _DATE.fullmatch(cells[0]):
            continue
        ratio = float(cells[8].replace("%", "")) if len(cells) > 8 and cells[8].endswith("%") else 0.0
        rows.append({"foreign": _num(cells[6]), "inst": _num(cells[5]), "ratio": ratio})
    return rows


def _fetch_trend_mobile(ticker: str) -> List[Dict]:
    """모바일 trend JSON 폴백 (frgn HTML 파스 0행 시) — 최신순. ratio 미제공=0."""
    try:
        r = requests.get(NAVER_TREND_URL.format(code=ticker), params={"pageSize": 10, "page": 1},
                         headers=HEADERS, timeout=10)
        arr = r.json()
    except Exception:
        return []
    if not isinstance(arr, list):
        return []
    return [{"foreign": _num(str(it.get("foreignerPureBuyQuant") or "")),
             "inst": _num(str(it.get("organPureBuyQuant") or "")),
             "ratio": 0.0}
            for it in arr if len(str(it.get("bizdate") or "")) == 8]


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
        resp.encoding = "euc-kr"  # 미설정 시 한글 매칭 전멸 (frgn = EUC-KR)
        flow_rows = _parse_flow_table(resp.text) or _fetch_trend_mobile(ticker)

        # 구 '외국인한도소진율' 상단 라벨 = 페이지에서 소멸 (2026-07-04 실호출) → 행 내 소진율 컬럼 사용
        foreign_ratio = flow_rows[0]["ratio"] if flow_rows else 0.0

        foreign_net = flow_rows[0]["foreign"] if flow_rows else 0
        institution_net = flow_rows[0]["inst"] if flow_rows else 0

        foreign_5d = [r["foreign"] for r in flow_rows[:5]]
        institution_5d = [r["inst"] for r in flow_rows[:5]]

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
