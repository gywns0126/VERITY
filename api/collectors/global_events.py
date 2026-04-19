"""
VERITY 글로벌 이벤트 캘린더 (FRED Releases API + 공식 스케줄 기반)

소스 구성:
1) FRED Releases API — CPI/NFP/PCE/GDP/PPI/Retail/Jobless Claims/Housing
2) 공식 스케줄 하드코딩 — FOMC / ECB / BOJ / 한국은행 금통위 / Quad Witching
3) 달력 규칙 기반 동적 계산 — ISM 제조업 PMI / ISM 서비스 PMI /
   Michigan 소비자심리 / Conference Board 소비자신뢰 / 한국 옵션만기

모든 이벤트는 severity/impact/action/impact_area 를 부여해 UI에서 바로 사용 가능.
"""
import os
import calendar
import requests
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

try:
    from api.config import FRED_API_KEY  # type: ignore
except Exception:  # pragma: no cover
    FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

_FRED_BASE = "https://api.stlouisfed.org/fred"
_KST = timezone(timedelta(hours=9))
_TIMEOUT = 10

# ──────────────────────────────────────────────────────────────
# FRED Release ID → 이벤트 템플릿
# 검증: https://fred.stlouisfed.org/releases
# ──────────────────────────────────────────────────────────────
FRED_RELEASES: Dict[int, Dict[str, Any]] = {
    10: {
        "name": "미국 CPI 발표",
        "severity": "high",
        "impact_area": ["물가", "금리기대", "성장주"],
        "impact": "예상 상회 시 금리 인상 우려로 시장 하락, 하회 시 반등",
        "action": "발표 전 변동성 대비, 인플레 수혜주 vs 피해주 구분",
    },
    50: {
        "name": "미국 고용지표 (NFP)",
        "severity": "high",
        "impact_area": ["경기", "금리", "환율"],
        "impact": "고용 강세→금리 인상 우려, 약세→경기침체 우려. 양면 리스크",
        "action": "발표일 장 초반 관망, 시장 반응 확인 후 대응",
    },
    21: {
        "name": "미국 PCE 물가지수",
        "severity": "high",
        "impact_area": ["물가", "금리기대"],
        "impact": "Fed 선호 인플레 지표. CPI와 유사하나 실질 정책 영향 큼",
        "action": "CPI와 교차 확인, 인플레 추세 판단",
    },
    53: {
        "name": "미국 GDP 발표",
        "severity": "medium",
        "impact_area": ["경기", "전체시장"],
        "impact": "예상 상회 시 경기 낙관→주식↑, 하회 시 침체 우려",
        "action": "경기 사이클 판단 자료로 활용",
    },
    46: {
        "name": "미국 PPI 발표",
        "severity": "medium",
        "impact_area": ["물가", "기업마진"],
        "impact": "생산자 물가. CPI 선행지표. 기업 마진 압박 신호",
        "action": "CPI 발표 전 힌트로 활용",
    },
    9: {
        "name": "미국 소매판매",
        "severity": "medium",
        "impact_area": ["소비", "경기"],
        "impact": "미국 소비 강도 지표. 전체 GDP 70%가 소비",
        "action": "소비재 섹터 판단 자료",
    },
    180: {
        "name": "미국 주간 실업수당 청구",
        "severity": "medium",
        "impact_area": ["경기", "고용"],
        "impact": "NFP 선행지표. 급증 시 경기침체 우려, 급감 시 고용 견조",
        "action": "4주 이동평균 추세로 판단. 단기 노이즈 무시",
    },
    27: {
        "name": "미국 주택착공",
        "severity": "low",
        "impact_area": ["부동산", "금리민감"],
        "impact": "금리 민감 섹터. 건설주/가전주/목재주에 영향",
        "action": "주택 관련 섹터 비중 점검",
    },
    291: {
        "name": "미국 기존주택판매",
        "severity": "low",
        "impact_area": ["부동산", "소비"],
        "impact": "미국 주택시장 수요 온도계. 모기지 금리 민감",
        "action": "금리 사이클 전환기 주목",
    },
}

# ──────────────────────────────────────────────────────────────
# 2026년 공식 스케줄 (매년 연초 업데이트 필요)
# ──────────────────────────────────────────────────────────────

# FOMC (Fed) — Day 2 발표일 기준
# https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
_FOMC_SCHEDULE: List[str] = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]

# ECB Governing Council 통화정책회의 — Day 2 발표일 (기자회견일)
# https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html
_ECB_SCHEDULE: List[str] = [
    "2026-01-29", "2026-03-12", "2026-04-30", "2026-06-11",
    "2026-07-23", "2026-09-10", "2026-10-29", "2026-12-17",
]

# BOJ 금융정책결정회합 (MPM) — Day 2 발표일
# https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm
_BOJ_SCHEDULE: List[str] = [
    "2026-01-23", "2026-03-19", "2026-04-28", "2026-06-16",
    "2026-07-31", "2026-09-18", "2026-10-30", "2026-12-18",
]

# 한국은행 금통위 (BOK)
_BOK_SCHEDULE: List[str] = [
    "2026-01-15", "2026-02-26", "2026-04-09", "2026-05-28",
    "2026-07-09", "2026-08-27", "2026-10-22", "2026-11-26",
]

# 미국 삼중마녀의 날 (Quad Witching) — 분기 셋째 금요일
_QUAD_WITCHING: List[str] = [
    "2026-03-20", "2026-06-19", "2026-09-18", "2026-12-18",
]


def _now_kst() -> datetime:
    return datetime.now(_KST)


# ──────────────────────────────────────────────────────────────
# 달력 규칙 기반 동적 계산 (ISM / Michigan / CB / 한국 옵션만기)
# ──────────────────────────────────────────────────────────────

def _next_business_day(d: date) -> date:
    """주말이면 다음 월요일. (공휴일은 미반영 — 근사)"""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """해당 월의 n번째 특정 요일. weekday: 0=월 … 6=일."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + (n - 1) * 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """해당 월의 마지막 특정 요일."""
    last = date(year, month, calendar.monthrange(year, month)[1])
    offset = (last.weekday() - weekday) % 7
    return last - timedelta(days=offset)


def _monthly_calendar_events() -> List[Dict[str, Any]]:
    """이번달 + 다음달의 ISM/Michigan/CB/옵션만기를 규칙으로 생성."""
    out: List[Dict[str, Any]] = []
    now = _now_kst().date()

    for add in (0, 1):
        y = now.year + ((now.month - 1 + add) // 12)
        m = ((now.month - 1 + add) % 12) + 1

        ism_mfg = _next_business_day(date(y, m, 1))
        out.append({
            "name": "ISM 제조업 PMI",
            "date": ism_mfg.isoformat(),
            "country": "미국",
            "severity": "medium",
            "impact_area": ["경기", "제조업"],
            "impact": "50선 기준. 상회 시 경기 확장, 하회 시 수축. 주식시장 방향성 선행",
            "action": "50선 돌파/이탈 시 경기민감주 비중 조절",
            "source": "ISM",
        })

        ism_svc = _next_business_day(ism_mfg + timedelta(days=1))
        ism_svc = _next_business_day(ism_svc + timedelta(days=1))
        out.append({
            "name": "ISM 서비스 PMI",
            "date": ism_svc.isoformat(),
            "country": "미국",
            "severity": "medium",
            "impact_area": ["경기", "서비스"],
            "impact": "미국 GDP 70%인 서비스업 체감경기. 제조업 PMI와 교차 확인",
            "action": "서비스 견조 시 소프트랜딩 시나리오 우호",
            "source": "ISM",
        })

        fridays = [d for d in (_nth_weekday(y, m, 4, n) for n in range(1, 6))
                   if d.month == m]
        if len(fridays) >= 2:
            out.append({
                "name": "Michigan 소비자심리 예비치",
                "date": fridays[1].isoformat(),
                "country": "미국",
                "severity": "low",
                "impact_area": ["소비심리", "기대인플레"],
                "impact": "미국 소비자 기대 인플레이션 포함. Fed도 주시하는 지표",
                "action": "소비재·리테일 섹터 감정 판단",
                "source": "UMich",
            })

        cb_date = _last_weekday(y, m, 1)  # 마지막 화요일
        out.append({
            "name": "Conference Board 소비자신뢰",
            "date": cb_date.isoformat(),
            "country": "미국",
            "severity": "low",
            "impact_area": ["소비심리", "고용기대"],
            "impact": "Michigan과 교차 검증되는 소비심리. 고용 기대 하위지표 중요",
            "action": "Michigan과 방향 일치 시 신뢰도 상승",
            "source": "Conference Board",
        })

        thursdays = [d for d in (_nth_weekday(y, m, 3, n) for n in range(1, 6))
                     if d.month == m and 8 <= d.day <= 14]
        if thursdays:
            out.append({
                "name": "옵션만기일 (한국)",
                "date": thursdays[0].isoformat(),
                "country": "한국",
                "severity": "medium",
                "impact_area": ["변동성", "지수"],
                "impact": "프로그램 매매 급증으로 지수 변동성 확대. 종가 변동 주의",
                "action": "만기일 장중 단기 매매 자제",
                "source": "KRX",
            })

    return out


# ──────────────────────────────────────────────────────────────
# FRED API 호출
# ──────────────────────────────────────────────────────────────

def _fetch_fred_releases(window_days: int = 30) -> List[Dict[str, Any]]:
    """각 Release ID별 가장 가까운 미래 발표일을 조회."""
    if not FRED_API_KEY:
        return []

    today = date.today()
    end = today + timedelta(days=window_days)
    out: List[Dict[str, Any]] = []

    for rid, template in FRED_RELEASES.items():
        try:
            r = requests.get(
                f"{_FRED_BASE}/release/dates",
                params={
                    "api_key": FRED_API_KEY,
                    "file_type": "json",
                    "release_id": rid,
                    "realtime_start": today.isoformat(),
                    "realtime_end": end.isoformat(),
                    "include_release_dates_with_no_data": "true",
                    "sort_order": "asc",
                    "limit": 10,
                },
                timeout=_TIMEOUT,
            )
            if r.status_code != 200:
                continue
            dates = r.json().get("release_dates", [])
        except Exception:
            continue

        is_weekly = rid == 180
        taken = 0
        for d in dates:
            date_str = (d.get("date") or "")[:10]
            if not date_str or date_str < today.isoformat():
                continue
            ev = dict(template)
            ev["date"] = date_str
            ev["country"] = "미국"
            ev["source"] = "FRED"
            ev["release_id"] = rid
            out.append(ev)
            taken += 1
            if not is_weekly or taken >= 3:
                break

    return out


# ──────────────────────────────────────────────────────────────
# 하드코딩 스케줄 → 이벤트
# ──────────────────────────────────────────────────────────────

def _fixed_schedule_events(
    schedule: List[str],
    template: Dict[str, Any],
) -> List[Dict[str, Any]]:
    today = date.today().isoformat()
    out: List[Dict[str, Any]] = []
    for d in schedule:
        if d >= today:
            ev = dict(template)
            ev["date"] = d
            out.append(ev)
    return out


# ──────────────────────────────────────────────────────────────
# 메인 엔트리
# ──────────────────────────────────────────────────────────────

def collect_global_events() -> List[Dict[str, Any]]:
    """향후 14일(및 직전 3일) 주요 경제 이벤트 수집 + d_day 부여."""
    events: List[Dict[str, Any]] = []

    events.extend(_fetch_fred_releases(window_days=30))

    events.extend(_fixed_schedule_events(_FOMC_SCHEDULE, {
        "name": "미국 FOMC 금리결정",
        "severity": "high",
        "impact_area": ["금리", "성장주", "환율"],
        "impact": "금리 인상 시 성장주↓ 가치주↑, 동결 시 안도 반등 가능",
        "action": "FOMC 전후 2일간 신규 매수 자제, 발표 후 방향 확인",
        "country": "미국",
        "source": "Fed",
    }))

    events.extend(_fixed_schedule_events(_ECB_SCHEDULE, {
        "name": "ECB 통화정책회의",
        "severity": "high",
        "impact_area": ["금리", "유로/달러", "유럽주식"],
        "impact": "유로존 금리결정. 유로/달러 환율 → 한국 수출주·신흥국 자금흐름 파급",
        "action": "발표 후 유로/달러 방향 확인, 수출주 환율 민감도 점검",
        "country": "유럽",
        "source": "ECB",
    }))

    events.extend(_fixed_schedule_events(_BOJ_SCHEDULE, {
        "name": "BOJ 금융정책결정회합",
        "severity": "high",
        "impact_area": ["엔환율", "엔캐리", "반도체", "자동차"],
        "impact": "엔 강세 전환 시 엔캐리 청산 리스크 → 글로벌 자산가격 급변. 한일 수출경쟁 영향",
        "action": "엔/달러 150선 근처면 청산 리스크 경계, 자동차·반도체 수출주 점검",
        "country": "일본",
        "source": "BOJ",
    }))

    events.extend(_fixed_schedule_events(_BOK_SCHEDULE, {
        "name": "한국은행 금통위",
        "severity": "medium",
        "impact_area": ["금리", "은행주", "부동산"],
        "impact": "금리 인하 시 은행주↓ 부동산↑ 성장주↑, 동결 시 영향 제한적",
        "action": "금리 민감 섹터 비중 조절",
        "country": "한국",
        "source": "BOK",
    }))

    events.extend(_fixed_schedule_events(_QUAD_WITCHING, {
        "name": "삼중마녀의 날 (Quad Witching)",
        "severity": "medium",
        "impact_area": ["변동성", "지수"],
        "impact": "주식·지수 선물·개별·지수 옵션 동시 만기. S&P500 거래량·변동성 급증",
        "action": "장 마감 전후 30분 변동성 급등 주의",
        "country": "미국",
        "source": "CBOE",
    }))

    events.extend(_monthly_calendar_events())

    now = _now_kst()
    lower = now - timedelta(days=3)
    upper = now + timedelta(days=14)

    normalized: List[Dict[str, Any]] = []
    for ev in events:
        try:
            d = datetime.strptime(ev["date"][:10], "%Y-%m-%d").replace(tzinfo=_KST)
        except (ValueError, TypeError, KeyError):
            continue
        if not (lower <= d <= upper):
            continue
        ev["d_day"] = (d.date() - now.date()).days
        ev.setdefault("country", "미국")
        normalized.append(ev)

    normalized.sort(key=lambda x: (x.get("date", "9999"), x.get("name", "")))

    seen = set()
    deduped: List[Dict[str, Any]] = []
    for ev in normalized:
        key = (ev.get("name", "")[:20], ev.get("date", "")[:10])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ev)

    return deduped[:30]
