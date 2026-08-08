#!/usr/bin/env python3
"""
fetch_us_etf_universe.py — 미장 ETF 유니버스 소싱 (Polygon 전 ETF/ETV/ETN active).

배경 (2026-08-08 커버리지 감사): KR ETF 는 KRX etf_bydd_trd 가 그날 상장 전량을 한 번에 주기
때문에 1,160 종 전량 커버인데, US ETF 는 `us_etf_public_builder.CURATED` 손큐레이션 84 종에
머물러 있었다. 같은 질문("ETF 커버리지")에 국장은 전량, 미장은 84 라는 비대칭이었다.
병목은 소스가 아니라 우리 설정이었다 — [[feedback_coverage_check_collector_filter_first]].

소스: Polygon /v3/reference/tickers (보유 키·추가 비용 0). us_universe_combined 의 CS 소싱과
동일 경로·동일 페이징 패턴 (scripts/us/fetch_us_smallcap_universe.py).
  · type=ETF — 일반 ETF (SPY/QQQ/VOO …)
  · type=ETV — 신탁형 상품. 🚨 GLD·SLV·USO 가 여기 있다. ETF 만 받으면 원자재가 통째로 빠진다
    (2026-08-08 실호출 확인).
  · type=ETN — 지수연동증권. KR 검색 유니버스가 ETN 370 종을 따로 세는 것과 짝을 맞춘다.

산출: data/us_etf_universe.json {_meta, tickers, names, type_map}
세이프가드: 1,000 종 미만 수집 시 기존 파일 보존 + exit 1 (Polygon 장애 방어).
  🚨 [[feedback_silent_total_failure_guard]] — 0 건인데 성공 종료 = 신선도 보드 통과. 금지.

usage: python3 scripts/us/fetch_us_etf_universe.py [--max-age-days N]
  --max-age-days N = 기존 파일이 N 일보다 신선하면 재수집 없이 종료(0). 매일 도는 워크플로에
  끼워도 Polygon 호출이 월 1 회로 유지된다. 🚨 파일 mtime 이 아니라 _meta.generated_at 으로
  판정한다 — CI checkout 은 mtime 을 매번 현재로 바꾸므로 mtime 기준 가드는 항상 통과한다.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import timedelta, timezone
from pathlib import Path
from typing import Optional

_KST = timezone(timedelta(hours=9))
_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = _ROOT / "data" / "us_etf_universe.json"
POLY = "https://api.polygon.io/v3/reference/tickers"

# Polygon ticker type → 우리 분류. 순서 = 우선순위(같은 티커 중복 시 앞이 이김).
_TYPES = ("ETF", "ETV", "ETN")

# Polygon 제한 tier ~5 req/min. CS 소싱과 동일 마진.
_PAGE_SLEEP = 13.0
_MAX_PAGES_PER_TYPE = 12
_MIN_TOTAL = 1000


def _get(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "verity-etf-universe"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fetch_type(api_key: str, tk_type: str) -> tuple[dict[str, str], int]:
    """단일 type 의 active 종목 {ticker: name} + 소비한 페이지 수."""
    out: dict[str, str] = {}
    url = (
        f"{POLY}?type={tk_type}&active=true&market=stocks"
        f"&limit=1000&apiKey={api_key}"
    )
    pages = 0
    while url and pages < _MAX_PAGES_PER_TYPE:
        d = _get(url)
        pages += 1
        for r in d.get("results", []):
            tk = str(r.get("ticker", "")).strip().upper().replace(".", "-")
            # CS 소싱과 동일 정규화 — 워런트/우선주 접미 기호가 섞인 티커 배제.
            if tk and tk.replace("-", "").isalnum():
                out[tk] = r.get("name") or ""
        nxt = d.get("next_url")
        url = (nxt + f"&apiKey={api_key}") if nxt else None
        if url:
            time.sleep(_PAGE_SLEEP)
    return out, pages


def _existing_age_days() -> Optional[float]:
    """기존 산출물의 _meta.generated_at 기준 나이(일). 없으면 None."""
    try:
        doc = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        gen = (doc.get("_meta") or {}).get("generated_at")
        if not gen or not doc.get("tickers"):
            return None
        from datetime import datetime
        return (datetime.now(_KST) - datetime.fromisoformat(gen)).total_seconds() / 86400.0
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return None


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:  # noqa: BLE001
        pass
    sys.path.insert(0, str(_ROOT))
    from api.config import now_kst

    max_age = None
    if "--max-age-days" in sys.argv:
        try:
            max_age = float(sys.argv[sys.argv.index("--max-age-days") + 1])
        except (IndexError, ValueError):
            sys.stderr.write("[us_etf_universe] --max-age-days 인자 파싱 실패 — 무시\n")
    if max_age is not None:
        age = _existing_age_days()
        if age is not None and age < max_age:
            print(f"[us_etf_universe] 기존 산출물 {age:.1f}일 < {max_age}일 — 재수집 생략")
            return 0

    key = os.environ.get("POLYGON_API_KEY")
    if not key:
        sys.stderr.write("[us_etf_universe] POLYGON_API_KEY 부재 — 중단\n")
        return 1

    names: dict[str, str] = {}
    type_map: dict[str, str] = {}
    per_type: dict[str, int] = {}
    pages_total = 0

    for tk_type in _TYPES:
        try:
            got, pages = fetch_type(key, tk_type)
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(
                f"[us_etf_universe] {tk_type} fetch 실패: {type(e).__name__}: {e}\n"
            )
            got, pages = {}, 0
        pages_total += pages
        per_type[tk_type] = len(got)
        for tk, nm in got.items():
            if tk in type_map:      # 앞 type 우선 (ETF > ETV > ETN)
                continue
            type_map[tk] = tk_type
            names[tk] = nm
        print(f"[us_etf_universe] {tk_type}: {len(got):,}종 ({pages} page)")
        if tk_type != _TYPES[-1]:
            time.sleep(_PAGE_SLEEP)

    total = len(type_map)
    if total < _MIN_TOTAL:
        sys.stderr.write(
            f"[us_etf_universe] 수집 {total} < {_MIN_TOTAL} — Polygon 장애 의심, 기존 보존(미덮음)\n"
        )
        return 1

    tickers = sorted(type_map)
    doc = {
        "_meta": {
            "generated_at": now_kst().isoformat(),
            "source": "Polygon /v3/reference/tickers (type=ETF|ETV|ETN, active)",
            "count": total,
            "per_type": per_type,
            "pages": pages_total,
            "note": (
                "미국 상장 ETF/ETV/ETN 티커·명칭 사실. 점수·추천 0(RULE 7). "
                "사실 enrich(AUM·보수·구성종목)는 us_etf_public_builder 가 증분 수행."
            ),
        },
        "tickers": tickers,
        "names": names,
        "type_map": type_map,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, OUT_PATH)
    print(f"[us_etf_universe] 저장 {total:,}종 → {OUT_PATH.name} ({per_type})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
