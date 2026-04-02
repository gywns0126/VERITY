"""
VERITY 글로벌 이벤트 캘린더 + 영향 예측

주요 경제 이벤트(FOMC, CPI, 고용, GDP 등)의 일정을 파악하고
각 이벤트가 한국 시장에 미칠 영향을 예측.
"""
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

RECURRING_EVENTS = [
    {
        "name": "미국 FOMC 금리결정",
        "impact_area": ["금리", "성장주", "환율"],
        "severity": "high",
        "impact": "금리 인상 시 성장주↓ 가치주↑, 동결 시 안도 반등 가능",
        "action": "FOMC 전후 2일간 신규 매수 자제, 발표 후 방향 확인",
    },
    {
        "name": "미국 CPI 발표",
        "impact_area": ["물가", "금리기대", "성장주"],
        "severity": "high",
        "impact": "예상 상회 시 금리 인상 우려로 시장 하락, 하회 시 반등",
        "action": "발표 전 변동성 대비, 인플레 수혜주 vs 피해주 구분",
    },
    {
        "name": "미국 고용지표 발표",
        "impact_area": ["경기", "금리", "환율"],
        "severity": "high",
        "impact": "고용 강세→금리 인상 우려, 약세→경기침체 우려. 양면 리스크",
        "action": "발표일 장 초반 관망, 시장 반응 확인 후 대응",
    },
    {
        "name": "한국은행 금통위",
        "impact_area": ["금리", "은행주", "부동산"],
        "severity": "medium",
        "impact": "금리 인하 시 은행주↓ 부동산↑ 성장주↑, 동결 시 영향 제한적",
        "action": "금리 민감 섹터 비중 조절",
    },
    {
        "name": "미국 GDP 발표",
        "impact_area": ["경기", "전체시장"],
        "severity": "medium",
        "impact": "예상 상회 시 경기 낙관→주식↑, 하회 시 침체 우려",
        "action": "경기 사이클 판단 자료로 활용",
    },
    {
        "name": "옵션만기일 (한국)",
        "impact_area": ["변동성", "지수"],
        "severity": "medium",
        "impact": "프로그램 매매 급증으로 지수 변동성 확대. 종가 변동 주의",
        "action": "만기일 장중 단기 매매 자제",
    },
    {
        "name": "미국 PCE 물가지수",
        "impact_area": ["물가", "금리기대"],
        "severity": "medium",
        "impact": "Fed 선호 인플레 지표. CPI와 유사하나 실질 정책 영향 큼",
        "action": "CPI와 교차 확인, 인플레 추세 판단",
    },
]


def collect_global_events() -> list:
    """향후 14일간 주요 경제 이벤트 수집"""
    events = []

    events.extend(_scrape_investing_calendar())

    if len(events) < 3:
        events.extend(_generate_recurring_schedule())

    events.sort(key=lambda x: x.get("date", "9999"))

    now = datetime.now()
    cutoff = now + timedelta(days=14)
    filtered = []
    for ev in events:
        try:
            d = datetime.strptime(ev["date"][:10], "%Y-%m-%d")
            if now - timedelta(days=1) <= d <= cutoff:
                ev["d_day"] = (d - now).days
                filtered.append(ev)
        except (ValueError, TypeError):
            continue

    seen = set()
    deduped = []
    for ev in filtered:
        key = ev["name"][:10] + ev["date"][:10]
        if key not in seen:
            seen.add(key)
            deduped.append(ev)

    return deduped[:15]


def _scrape_investing_calendar() -> list:
    """네이버 증권 경제캘린더 스크래핑"""
    events = []
    now = datetime.now()

    try:
        url = "https://finance.naver.com/world/worldDayListJson.naver"
        params = {
            "date": now.strftime("%Y%m%d"),
            "page": 1,
        }
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, params=params, headers=headers, timeout=10)

        if resp.status_code == 200:
            try:
                data = resp.json()
                for item in data:
                    name = item.get("title", item.get("nm", ""))
                    date_str = item.get("dt", item.get("date", ""))
                    country = item.get("country", item.get("nation", ""))

                    if not name or not date_str:
                        continue

                    event_entry = _match_event_template(name)
                    event_entry["date"] = _normalize_date(date_str)
                    event_entry["country"] = country
                    events.append(event_entry)
            except Exception:
                pass
    except Exception:
        pass

    if len(events) < 3:
        events.extend(_scrape_naver_eco_calendar())

    return events


def _scrape_naver_eco_calendar() -> list:
    """네이버 증권 해외 증시 경제 일정 페이지 스크래핑 폴백"""
    events = []
    try:
        url = "https://finance.naver.com/world/index"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return events

        soup = BeautifulSoup(resp.text, "html.parser")

        for item in soup.select("li, tr"):
            text = item.get_text(strip=True)
            for kw in ["FOMC", "CPI", "GDP", "고용", "PCE", "금리", "옵션만기"]:
                if kw in text:
                    event_entry = _match_event_template(text)
                    event_entry["date"] = datetime.now().strftime("%Y-%m-%d")
                    events.append(event_entry)
                    break
    except Exception:
        pass

    return events


def _match_event_template(event_text: str) -> dict:
    """이벤트 텍스트를 사전 정의된 템플릿과 매칭"""
    keywords = {
        "FOMC": 0, "금리결정": 0, "금리": 3,
        "CPI": 1, "소비자물가": 1,
        "고용": 2, "비농업": 2, "Nonfarm": 2,
        "금통위": 3,
        "GDP": 4, "국내총생산": 4,
        "옵션만기": 5, "네마녀": 5,
        "PCE": 6,
    }

    for kw, idx in keywords.items():
        if kw.lower() in event_text.lower():
            template = RECURRING_EVENTS[idx].copy()
            template["name"] = event_text[:50] if len(event_text) > 10 else template["name"]
            return template

    return {
        "name": event_text[:50],
        "impact_area": ["시장"],
        "severity": "low",
        "impact": "시장 영향 제한적",
        "action": "동향 모니터링",
    }


def _generate_recurring_schedule() -> list:
    """스크래핑 실패 시 정기 이벤트 기반 폴백 일정 생성"""
    events = []
    now = datetime.now()

    # 매월 둘째/넷째 목요일 근처 = 옵션만기 근사
    for delta in range(14):
        d = now + timedelta(days=delta)
        # 매월 둘째 목요일 (8~14일 범위 목요일) = 옵션만기
        if d.weekday() == 3 and 8 <= d.day <= 14:
            ev = RECURRING_EVENTS[5].copy()
            ev["date"] = d.strftime("%Y-%m-%d")
            events.append(ev)

    return events


def _normalize_date(date_str: str) -> str:
    """다양한 날짜 포맷을 YYYY-MM-DD로 정규화"""
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.now().strftime("%Y-%m-%d")
