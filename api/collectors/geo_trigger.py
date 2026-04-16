"""
VERITY 지정학 리스크 트리거 — 대만 지진 감시

USGS FDSN Event API를 사용해 대만 주변(TSMC 팹 집중 지역) M6.0+ 지진을
감지하면 global_events[] 에 critical 이벤트로 추가.

설계 원칙:
- 평상시엔 None 반환 (노이즈 제로)
- 이미 알린 이벤트는 state 파일로 dedup (중복 알림 방지)
- 자유 사용, API 키 불필요
- TSMC 단일 의존성 = 반도체 공급망 single point of failure
  → 1건당 2330.TW / 005930.KS / 000660.KS / NVDA / AAPL / AMD 동시 영향

참고 사례:
  2024-04-03 M7.4 화롄  : TSMC 70%+ 장비 자동정지, 삼전 당일 +1.9%
  1999-09-21 M7.7 지지  : DRAM 현물가 2주만에 2배
  2016-02-06 M6.4 가오슝: TSMC 14nm 웨이퍼 수천장 폐기
"""
import json
import os
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

from api.config import DATA_DIR

_KST = timezone(timedelta(hours=9))

# ── 대만 bounding box (TSMC 팹 모두 포함) ──
# Hsinchu(24.8,121.0) / Taichung(24.1,120.7) / Tainan(23.0,120.2) / Kaohsiung(22.6,120.3)
_TAIWAN_BBOX = {
    "minlatitude": 21.5,
    "maxlatitude": 25.5,
    "minlongitude": 119.5,
    "maxlongitude": 122.5,
}

_MIN_MAGNITUDE = 6.0  # M6.0+ 만 의미있는 공급망 충격
_LOOKBACK_HOURS = 2   # 최근 2시간 내 이벤트

_USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"

_STATE_FILE = os.path.join(DATA_DIR, "geo_trigger_state.json")
_STATE_RETENTION_DAYS = 7  # 7일 지난 event ID는 state에서 제거

# TSMC 가치사슬 — 대만 지진 발생시 동시 재분석 대상
_AFFECTED_TICKERS = [
    "2330.TW",    # TSMC 본체
    "005930.KS",  # 삼성전자 (대체 파운드리 반사이익)
    "000660.KS",  # SK하이닉스 (메모리 타이트닝 수혜)
    "NVDA",       # 엔비디아 (TSMC 최대 고객)
    "AAPL",       # 애플 (A/M 시리즈 전량 TSMC)
    "AMD",        # AMD (전량 TSMC)
    "ASML",       # ASML (EUV 장비 발주 지연 리스크)
    "MU",         # 마이크론 (메모리 공급 타이트닝)
]


def _load_state() -> Dict[str, Any]:
    """dedup 상태 로드. 없으면 빈 dict."""
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"seen_events": {}}


def _save_state(state: Dict[str, Any]) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  ⚠️ geo_trigger state 저장 실패: {e}")


def _prune_state(state: Dict[str, Any]) -> None:
    """7일 지난 event ID 제거 (무한 성장 방지)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=_STATE_RETENTION_DAYS)
    seen = state.get("seen_events", {})
    pruned = {
        eid: ts for eid, ts in seen.items()
        if _parse_iso(ts) and _parse_iso(ts) > cutoff
    }
    state["seen_events"] = pruned


def _parse_iso(s: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _severity_from_magnitude(mag: float) -> str:
    """규모별 severity 매핑."""
    if mag >= 7.5:
        return "critical"   # 전국 피해 + TSMC 장기 가동중단 가능
    elif mag >= 7.0:
        return "critical"   # 광역 피해 + 장비 점검 필수
    elif mag >= 6.5:
        return "high"       # TSMC 수율 영향 가능
    else:
        return "high"       # M6.0~6.5도 자동 정지 가능


def _build_event_entry(feature: Dict[str, Any]) -> Dict[str, Any]:
    """USGS feature → VERITY global_events 스키마."""
    props = feature.get("properties", {})
    coords = feature.get("geometry", {}).get("coordinates", [None, None, None])
    mag = float(props.get("mag") or 0)
    place = props.get("place") or "대만 인근"
    time_ms = props.get("time", 0)
    dt_utc = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc)
    dt_kst = dt_utc.astimezone(_KST)

    sev = _severity_from_magnitude(mag)
    depth_km = coords[2] if len(coords) >= 3 else None

    return {
        "name": f"대만 M{mag:.1f} 지진 감지 ({place[:30]})",
        "date": dt_kst.strftime("%Y-%m-%d"),
        "datetime_kst": dt_kst.strftime("%Y-%m-%d %H:%M KST"),
        "d_day": 0,
        "impact_area": ["반도체", "공급망", "TSMC", "글로벌"],
        "severity": sev,
        "impact": (
            f"TSMC 팹 자동정지 프로토콜 발동 가능. "
            f"규모 {mag:.1f}는 "
            + ("선단공정 웨이퍼 폐기 + 복구 수일~수주 소요될 수 있음." if mag >= 6.5
               else "단기 가동중단 가능하나 수율 영향 제한적일 가능성.")
        ),
        "action": (
            "TSMC 고객사(NVDA/AAPL/AMD) 즉시 변동성 대비. "
            "삼성전자(005930)·SK하이닉스(000660) 반사이익 포지션 검토. "
            "TSMC 1시간 내 공식 성명 모니터링 필수."
        ),
        "affected_tickers": _AFFECTED_TICKERS,
        "trigger_source": "usgs_taiwan_quake",
        "meta": {
            "magnitude": mag,
            "depth_km": depth_km,
            "place": place,
            "event_id": feature.get("id", ""),
            "usgs_url": props.get("url", ""),
            "occurred_utc": dt_utc.isoformat(),
        },
    }


def check_taiwan_quake_trigger(
    min_magnitude: float = _MIN_MAGNITUDE,
    lookback_hours: int = _LOOKBACK_HOURS,
    timeout: int = 8,
) -> List[Dict[str, Any]]:
    """
    USGS API에서 대만 인근 M6.0+ 지진 조회. 신규 이벤트만 반환.

    평상시: 빈 리스트 반환 (노이즈 제로).
    M6.0+ 발생 시: global_events 스키마의 dict 리스트 반환.
    이미 알린 이벤트는 state 파일로 dedup 처리.
    """
    try:
        since_utc = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        params = {
            "format": "geojson",
            "starttime": since_utc.strftime("%Y-%m-%dT%H:%M:%S"),
            "minmagnitude": min_magnitude,
            **_TAIWAN_BBOX,
            "orderby": "time",
        }
        resp = requests.get(_USGS_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        features = resp.json().get("features", []) or []
    except Exception as e:
        print(f"  ⚠️ USGS 대만 지진 체크 실패: {e}")
        return []

    if not features:
        return []

    state = _load_state()
    _prune_state(state)
    seen = state.setdefault("seen_events", {})

    new_events: List[Dict[str, Any]] = []
    for feat in features:
        eid = feat.get("id")
        if not eid or eid in seen:
            continue
        entry = _build_event_entry(feat)
        new_events.append(entry)
        seen[eid] = datetime.now(timezone.utc).isoformat()

    if new_events:
        _save_state(state)

    return new_events


def format_alert_message(event: Dict[str, Any]) -> str:
    """텔레그램 긴급 알림 포맷."""
    meta = event.get("meta", {})
    mag = meta.get("magnitude", 0)
    depth = meta.get("depth_km")
    depth_str = f"{depth:.0f}km" if isinstance(depth, (int, float)) else "N/A"
    return (
        f"🚨 대만 지진 알림 (VERITY)\n"
        f"규모 M{mag:.1f} / 심도 {depth_str}\n"
        f"위치: {meta.get('place', 'N/A')}\n"
        f"시각: {event.get('datetime_kst', 'N/A')}\n"
        f"\n"
        f"💥 {event.get('impact', '')}\n"
        f"\n"
        f"📌 {event.get('action', '')}\n"
        f"\n"
        f"🔗 {meta.get('usgs_url', '')}"
    )


if __name__ == "__main__":
    import sys
    results = check_taiwan_quake_trigger(min_magnitude=6.0)
    if results:
        for ev in results:
            print(format_alert_message(ev))
            print("---")
    else:
        print("대만 인근 M6.0+ 지진 없음 (최근 2시간). 정상.")
    sys.exit(0)
