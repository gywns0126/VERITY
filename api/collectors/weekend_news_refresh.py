"""주말 뉴스 전용 경량 갱신 — portfolio.json 의 headline 필드만 재수집.

배경(PM 결정 2026-07-05, 옵션 B): daily_analysis_full / rss_scout 는 평일(월-금) cron 이라
주말엔 뉴스가 금요일 밤에 정지 → 사용자가 월요일 아침 장전 갭·장후 반응을 낡은 뉴스로 판단.
뉴스는 주말·장외에도 흐르므로, 전체 분석 파이프라인(장 세션 필요)은 그대로 두고
헤드라인만 몇 시간 간격으로 재수집(비용 최소). 전체 분석·수급·재무는 평일 daily_analysis 담당.

동작: news_headlines.py 의 3 수집기(전부 public RSS, secret 불필요)를 재사용해
portfolio.json 의 headlines / bloomberg_google_headlines / us_headlines 필드만 패치.
포맷 정합 = vams.engine.load_portfolio / save_portfolio (main.py 와 동일 경로).
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from api.vams.engine import load_portfolio, save_portfolio
from api.collectors.news_headlines import (
    collect_headlines,
    collect_bloomberg_google_news_rss,
    collect_us_headlines,
)

KST = timezone(timedelta(hours=9))


def _safe(fn, *args, **kwargs):
    """수집기 하나가 실패해도 나머지·기존 데이터 보존 (빈 리스트 반환)."""
    try:
        return fn(*args, **kwargs) or []
    except Exception as e:  # noqa: BLE001 — 뉴스 수집 실패는 치명 아님, 직전 유지
        print(f"[weekend_news] {getattr(fn, '__name__', fn)} 실패: {e}", file=sys.stderr)
        return []


def main() -> None:
    pf = load_portfolio()

    hl = _safe(collect_headlines, max_items=40)   # main.py 와 동일 볼륨(40)
    if hl:
        pf["headlines"] = hl
    bb = _safe(collect_bloomberg_google_news_rss, max_items=15)
    if bb:
        pf["bloomberg_google_headlines"] = bb
    us = _safe(
        collect_us_headlines,
        kr_headlines=pf.get("headlines", []),
        bloomberg_rss=pf.get("bloomberg_google_headlines", []),
        max_items=20,
    )
    if us:
        pf["us_headlines"] = us

    # 뉴스 전용 갱신 표식 (updated_at 은 price_pulse/분석 소유라 미변경)
    pf["news_refreshed_at"] = datetime.now(KST).isoformat()
    save_portfolio(pf)

    print(
        f"[weekend_news] logged=True · headlines={len(pf.get('headlines', []))} · "
        f"bloomberg={len(pf.get('bloomberg_google_headlines', []))} · "
        f"us={len(pf.get('us_headlines', []))} → portfolio.json",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
