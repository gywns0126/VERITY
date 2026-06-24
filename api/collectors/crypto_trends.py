"""코인 검색 관심도 — 리테일 관심 프록시 (Google Trends 관심도 지수).

소셜 영역에서 유일하게 무료 + 명시 republish 라이선스를 가진 신호.
Bitcoin/Ethereum/cryptocurrency 등 키워드의 Google Trends "관심도(interest over time)"를
수집한다. 이 값은 절대 검색량이 아니라 **상대 지수(0~100)** 다 — 100 = 해당 기간/키워드 집합
내 최고점, 0 = 데이터 미미. 키워드 간 값도 같은 스케일(서로 비교 가능)이다.

🚨 RULE 7 (자기 산식 노출 = 가설): 여기서는 **외부 1차 수치만** 적재한다.
   점수·등급·매수신호 0. interest_now / trend_pct 는 Google Trends 가 발표하는 그대로의 상대 지수다.

라이선스 / Attribution:
  Data source: Google Trends. Google 은 Trends 데이터의 republish 를 허용하되
  "Data source: Google Trends" 출처 표기를 의무화한다. 캐싱/표시 시 출처 표기 의무.

🚨 breakage 리스크 (의도적 self-contained):
  - pytrends 는 dormant(2023 마지막 릴리스, 비공식 스크래퍼)라 의존 추가를 피했다.
    requirements.txt 에 추가 의존 없음 — 표준 라이브러리 + requests 만 사용.
  - Google Trends 비공식 endpoint(explore → widget token → multiline)를 직접 호출한다.
    이 endpoint 는 비공식이라 Google 이 언제든 형식을 바꾸거나 rate-limit(HTTP 429)할 수 있다.
  - 따라서 **항상 dict 반환, 절대 raise 하지 않는다**. 깨지면 {"ok": False, "error": "..."}.
    breakage 가 파이프라인 전체를 죽이지 않도록 graceful degrade 가 1순위다.
  - US-IP(GitHub Actions)에서 동작 검증 완료(2026-06-24 실호출).

기존 crypto_macro.py / crypto_defillama.py collector 계약 정합:
  표준 라이브러리 + requests 만, 외부 의존 추가 없음. 항상 dict 반환, 절대 raise 안 함.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

# Google Trends 비공식 endpoint. 무인증, 무료. 출처 표기 의무.
_EXPLORE_URL = "https://trends.google.com/trends/api/explore"
_MULTILINE_URL = "https://trends.google.com/trends/api/widgetdata/multiline"
_WARMUP_URL = "https://trends.google.com/trends/explore"

_TIMEOUT = 15
# 브라우저 UA 권장 — Google 은 봇/스크립트 UA 를 자주 차단한다.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "application/json, text/plain, */*",
}
_ATTRIBUTION = "Google Trends"

# 과다 회피 — 3~5개. 키워드 추가 시 Google rate-limit(429) 리스크 증가.
_DEFAULT_KEYWORDS = ["Bitcoin", "Ethereum", "cryptocurrency"]
_GEO = ""              # 빈 문자열 = 전세계. (US 한정 시 "US")
_TIMEFRAME = "today 3-m"  # 최근 3개월 일별

# Google 응답은 XSSI 방어 프리픽스 )]}', 로 시작 → JSON parse 전 제거.
_XSSI_STRIP = ")]}',\n "


def _clean_json(text: str) -> Any:
    """Google Trends XSSI 프리픽스 제거 후 JSON 파싱."""
    return json.loads(text.lstrip(_XSSI_STRIP))


def _trend_pct(values: List[float]) -> Optional[float]:
    """최근 변화율(%). 최근 7포인트 평균 vs 직전 7포인트 평균.

    데이터가 부족하면 None. 0 으로 나눔 방지.
    """
    if len(values) < 14:
        return None
    recent = values[-7:]
    prior = values[-14:-7]
    prior_avg = sum(prior) / len(prior)
    if prior_avg <= 0:
        return None
    recent_avg = sum(recent) / len(recent)
    return round((recent_avg - prior_avg) / prior_avg * 100, 1)


def collect_crypto_trends(
    keywords: Optional[List[str]] = None,
    geo: str = _GEO,
    timeframe: str = _TIMEFRAME,
) -> Dict[str, Any]:
    """코인 검색 관심도(Google Trends) 수집.

    항상 dict 반환, 절대 raise 안 함. 깨지면 {"ok": False, "error": "..."}.

    interest_now / trend_pct 는 **상대 지수(0~100)** 다. 절대 검색량이 아니라,
    조회 기간/키워드 집합 내 최고점=100 으로 정규화된 값이다. 키워드 간 값은 같은 스케일.

    반환:
      ok            : bool — 키워드 1개라도 데이터가 있으면 True
      source        : str  — "Google Trends" (출처 표기 의무)
      as_of         : str  — 수집 시각(UTC ISO)
      timeframe     : str  — 조회 기간(예: "today 3-m")
      geo           : str  — 지역("" = 전세계)
      keywords      : list — [{term, interest_now(0~100), trend_pct, timeframe}]
      실패 시         : {"ok": False, "error": "<짧은 사유>"}
    """
    kws = keywords or list(_DEFAULT_KEYWORDS)
    as_of = datetime.now(timezone.utc).isoformat()

    try:
        s = requests.Session()
        s.headers.update(_HEADERS)

        # Step 0: 워밍업 요청 — Google 은 NID 쿠키 없는 API 호출을 자주 차단(429/400).
        try:
            s.get(
                _WARMUP_URL,
                params={"q": kws[0], "geo": geo},
                timeout=_TIMEOUT,
            )
        except Exception:  # noqa: BLE001 — 쿠키 워밍업 실패해도 본 호출 시도
            pass

        # Step 1: explore → 위젯 + token 발급
        explore_req = {
            "comparisonItem": [
                {"keyword": k, "geo": geo, "time": timeframe} for k in kws
            ],
            "category": 0,
            "property": "",
        }
        er = s.get(
            _EXPLORE_URL,
            params={"hl": "en-US", "tz": "0", "req": json.dumps(explore_req)},
            timeout=_TIMEOUT,
        )
        if er.status_code == 429:
            return {"ok": False, "error": "google_trends_rate_limited_429"}
        er.raise_for_status()
        explore = _clean_json(er.text)

        widgets = explore.get("widgets", []) or []
        ts_widget = next(
            (w for w in widgets if w.get("id") == "TIMESERIES"), None
        )
        if not ts_widget or not ts_widget.get("token"):
            return {"ok": False, "error": "no_timeseries_widget"}

        token = ts_widget["token"]
        ml_req = ts_widget.get("request")
        if not ml_req:
            return {"ok": False, "error": "no_widget_request"}

        # Step 2: multiline → 실제 관심도 시계열
        mr = s.get(
            _MULTILINE_URL,
            params={
                "hl": "en-US",
                "tz": "0",
                "req": json.dumps(ml_req),
                "token": token,
            },
            timeout=_TIMEOUT,
        )
        if mr.status_code == 429:
            return {"ok": False, "error": "google_trends_rate_limited_429"}
        mr.raise_for_status()
        ml = _clean_json(mr.text)

        timeline = (ml.get("default") or {}).get("timelineData") or []
        if not timeline:
            return {"ok": False, "error": "empty_timeline"}

        out_keywords: List[Dict[str, Any]] = []
        for i, term in enumerate(kws):
            # 각 포인트의 value 는 키워드 순서대로의 배열. hasData 로 결측 구분.
            series: List[float] = []
            for p in timeline:
                vals = p.get("value") or []
                has = p.get("hasData") or [True] * len(kws)
                if i < len(vals) and (i >= len(has) or has[i]):
                    try:
                        series.append(float(vals[i]))
                    except (TypeError, ValueError):
                        continue
            if not series:
                out_keywords.append({
                    "term": term,
                    "interest_now": None,
                    "trend_pct": None,
                    "timeframe": timeframe,
                })
                continue
            out_keywords.append({
                "term": term,
                "interest_now": round(series[-1]),  # 0~100 상대 지수, 최신 포인트
                "trend_pct": _trend_pct(series),     # 최근 7d 평균 vs 직전 7d (%)
                "timeframe": timeframe,
            })

        ok = any(k["interest_now"] is not None for k in out_keywords)
        if not ok:
            return {"ok": False, "error": "no_keyword_data"}

        return {
            "ok": True,
            "source": _ATTRIBUTION,
            "as_of": as_of,
            "timeframe": timeframe,
            "geo": geo,
            "keywords": out_keywords,
            "points": len(timeline),
        }
    except Exception as e:  # noqa: BLE001 — 최종 안전망: 절대 raise 안 함(breakage graceful)
        return {"ok": False, "error": str(e)[:120]}
