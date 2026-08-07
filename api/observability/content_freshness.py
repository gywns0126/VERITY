#!/usr/bin/env python3
"""내용 신선도 — 파일이 아니라 **안에 든 데이터의 기준일자**를 잰다.

PM 지시 2026-08-07 "전체 파이프라인 검사하는 크론을 만들어서 상시 돌게하여 시스템
신선도 체크". 조사해보니 상시 검사(freshness_board, cron_health_monitor.yml 매시)는
이미 있었다. 진짜 갭은 주기가 아니라 **측정 축**이었다.

발단 사고 (국민연금 직원수, 2026-08-07):
  · 보드 판정 = last_ts 2026-07-08, age 29.7일 < SLA 35일 → **"fresh"**
  · 실제 = 파일 안의 데이터는 2026년 5월분. 7/15 수집이 timeout 으로 죽어 6월분을 놓쳤다.
  → 보드는 **파일이 언제 써졌는지**만 본다. 5월 데이터를 매일 다시 써도 영원히 fresh 다.
    파이프라인이 "돌긴 도는데 낡은 값을 재발행" 하는 상태를 구조적으로 못 잡는다.

이 모듈이 그 두 번째 축을 담당한다. 파일 신선도(기존)와 내용 신선도(여기)는 **직교**다:
  · 파일 fresh + 내용 fresh  = 정상
  · 파일 stale + 내용 fresh  = 수집이 멈춤(기존 축이 이미 잡음)
  · 파일 fresh + 내용 stale  = 🚨 낡은 값 재발행 — 종전엔 안 보이던 사각지대
  · 둘 다 stale              = 명백한 중단

🚨 오탐 방지 설계 — **opt-in**. SLA 항목에 `max_content_age_minutes` 가 있고 기준일자를
   확신을 갖고 뽑아낸 스트림만 판정한다. 나머지는 `unknown` 으로 두고 기존 판정을 그대로
   쓴다. 스트림이 100개 가까이 되는데 추측으로 임계를 걸면 경고가 무뎌져(alert fatigue)
   진짜 사고를 놓친다 — 신선도 감시가 스스로 무력해지는 가장 흔한 실패 방식이다.
"""
from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

KST = timezone(timedelta(hours=9))

# 기준일자가 담기는 흔한 키. 순서 = 신뢰도 (앞일수록 명시적).
_DATE_KEYS = (
    "data_ym_latest", "data_date", "as_of", "as_of_date", "base_date",
    "trade_date", "기준일", "기준월", "report_date",
)

_YM = re.compile(r"^(\d{4})(\d{2})$")
_YMD = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_YMD_COMPACT = re.compile(r"^(\d{4})(\d{2})(\d{2})$")


def _from_ym(v: str) -> Optional[datetime]:
    """YYYYMM → 그 달의 **말일 23:59**. 월 단위 데이터의 실질 기준 시점.

    말일을 쓰는 이유: 202606 자료는 6월 한 달을 담으므로 6/1 보다 6/30 이 실질 기준이다.
    1일로 잡으면 월간 자료가 항상 한 달 더 낡아 보여 임계가 왜곡된다.
    """
    m = _YM.match(v)
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    if not (1900 <= y <= 2999 and 1 <= mo <= 12):
        return None
    return datetime(y, mo, calendar.monthrange(y, mo)[1], 23, 59, tzinfo=KST)


def parse_content_date(v: Any) -> Optional[datetime]:
    """문자열/숫자에서 기준일자 파싱. 해석 불가면 None (= 판정 안 함)."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    m = _YMD.match(s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 23, 59, tzinfo=KST)
        except ValueError:
            return None
    m = _YMD_COMPACT.match(s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 23, 59, tzinfo=KST)
        except ValueError:
            return None
    return _from_ym(s)


def extract_content_ts(obj: Any, field: Optional[str] = None) -> Optional[datetime]:
    """데이터 객체에서 기준일자를 뽑는다.

    탐색 범위는 **최상위와 _meta 만** — 깊이 파고들면 종목별 필드 같은 무관한 날짜를
    주워 엉뚱한 판정을 낸다. SLA 가 `content_field` 로 지정하면 그것만 본다.
    """
    if not isinstance(obj, dict):
        return None
    if field:
        for scope in (obj, obj.get("_meta") if isinstance(obj.get("_meta"), dict) else {}):
            if isinstance(scope, dict) and field in scope:
                return parse_content_date(scope[field])
        return None
    meta = obj.get("_meta") if isinstance(obj.get("_meta"), dict) else {}
    for scope in (meta, obj):
        for k in _DATE_KEYS:
            if k in scope:
                t = parse_content_date(scope[k])
                if t:
                    return t
    return None


def content_status(content_ts: Optional[datetime], max_age_min: Optional[float],
                   now: Optional[datetime] = None) -> tuple:
    """(status, age_min). 임계 미지정이거나 기준일자 부재면 ('unknown', age|None).

    🚨 미래 일자는 stale 이 아니라 unknown 으로 둔다 — 소스 오기/타임존 착오일 뿐인데
    stale 로 올리면 잘못된 방향의 경보가 된다.
    """
    if content_ts is None:
        return "unknown", None
    now = now or datetime.now(KST)
    age = (now - content_ts).total_seconds() / 60
    if age < 0:
        return "unknown", round(age, 1)
    if not max_age_min:
        return "unknown", round(age, 1)
    return ("stale" if age > max_age_min else "fresh"), round(age, 1)
