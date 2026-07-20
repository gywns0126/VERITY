"""us_disclosure_feed_builder — 공개 터미널 미장(US) 공시속보 빌더 (SEC 8-K).

2026-06-19 국장/미장 분리. us_financials 유니버스(15 빅캡)의 최근 8-K(수시공시)를
SEC EDGAR submissions 에서 수집 → public-safe JSON. 스키마 = KR public_disclosure_feed.json
동일 → PublicDisclosureFeed 컴포넌트 재사용 (/us/feed 페이지에 feedUrl=이 파일).

🚨 RULE 7 — 공시 사실(폼타입·제목·접수일·원문URL)만. 점수·등급·추천 0.
SEC EDGAR 무료, rate limit 10/s (sec_edgar._throttle 내장). UA = SEC_USER_AGENT.
publish: data/us_disclosure_feed.json (action.yml 등재 필요).
빌더는 네트워크 호출 — daily_analysis_full(일간) 에서 실행. 로컬 테스트는 네트워크 필요.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_PATH = os.path.join(_ROOT, "data", "us_financials", "_summary.json")
COMBINED_PATH = os.path.join(_ROOT, "data", "us_universe_combined.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_disclosure_feed.json")

WINDOW_DAYS = 90        # 8-K 산발적 → 윈도우 넉넉히 (2026-07-17 60→90: 어닝-8-K 주기 ~91일 포괄. 분기초 위치 종목의 직전 8-K 회수 → disclosures 84.7%→~97%. SEC 콜 0 증가=cutoff 필터만)
MAX_PER_TICKER = 5
# 🚨 예산 가드 — 무가드 1,505 SEC 순회가 daily_analysis_full 에서 완주 못 해 2건만 남던 사고(2026-07-09) 방지.
MAX_SECONDS = int(os.environ.get("US_DISCLOSURE_MAX_SECONDS", "1800"))


def _now_kst() -> datetime:
    return datetime.now(KST)


def _title(name: str) -> str:
    return " ".join(w.capitalize() for w in str(name or "").split())


def _name_map() -> Dict[str, str]:
    """ticker→표시명 — combined names(전 US, 소형주 포함) + summary entity_name 병합."""
    out: Dict[str, str] = {}
    try:
        with open(COMBINED_PATH, encoding="utf-8") as f:
            names = (json.load(f) or {}).get("names") or {}
        if isinstance(names, dict):
            for tk, nm in names.items():
                if tk and nm:
                    out[str(tk).upper()] = _title(nm)
    except (OSError, json.JSONDecodeError):
        pass
    try:
        with open(SUMMARY_PATH, encoding="utf-8") as f:
            for r in ((json.load(f) or {}).get("rows") or []):
                tk = r.get("ticker")
                if tk and r.get("entity_name"):
                    out[str(tk).upper()] = _title(r.get("entity_name"))
    except (OSError, json.JSONDecodeError):
        pass
    return out


def _universe() -> List[str]:
    """전체 US 유니버스(combined, 소형주 포함) — 심화 파이프라인 공유 rotation 재사용(rec 우선+페이지 회전).
    부재 시 summary(S&P1500) fallback."""
    try:
        from api.builders.us_insider_trades_public_builder import _ordered_universe
        uni = _ordered_universe()
        if uni:
            return [str(t).upper() for t in uni]
    except Exception:  # noqa: BLE001
        pass
    try:
        with open(SUMMARY_PATH, encoding="utf-8") as f:
            return [str(r["ticker"]).upper() for r in ((json.load(f) or {}).get("rows") or []) if r.get("ticker")]
    except (OSError, json.JSONDecodeError, KeyError):
        return []


def build_feed(window_days: int = WINDOW_DAYS) -> Dict[str, Any]:
    from api.collectors.sec_edgar import get_recent_filings
    from api.intelligence.us_financials import SEC_USER_AGENT

    cutoff = (_now_kst().date() - timedelta(days=window_days)).strftime("%Y-%m-%d")
    names = _name_map()

    # carry-forward — 이전 스냅샷(이번 회전서 안 건드린 종목 보존). 예산 완주 실패해도 누적.
    prev: Dict[str, Dict[str, Any]] = {}
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            for it in ((json.load(f) or {}).get("items") or []):
                if it.get("ticker"):
                    prev[str(it["ticker"]).upper()] = it
    except (OSError, json.JSONDecodeError):
        pass
    merged: Dict[str, Dict[str, Any]] = dict(prev)

    t0 = time.monotonic()
    covered = 0
    for tk in _universe():
        if time.monotonic() - t0 > MAX_SECONDS:
            print(f"[us_disclosure_feed] budget 도달 ({int(time.monotonic()-t0)}s, {covered}종목) — 나머지 carry-forward", file=sys.stderr)
            break
        name = names.get(tk, tk)
        try:
            filings = get_recent_filings(tk, SEC_USER_AGENT, ["8-K"]) or []
        except Exception as e:  # noqa: BLE001
            print(f"[us_disclosure_feed] {tk} 8-K fetch 실패: {e!r}", file=sys.stderr)
            continue
        covered += 1
        discs = []
        for fl in filings:
            d = str(fl.get("filed_date") or "")
            if d and d < cutoff:
                continue
            discs.append({
                "title": (fl.get("description") or "").strip() or "8-K 수시공시",
                "label": "8-K",
                "date": d,
                "is_correction": False,
                "filer": name,
                "source_url": fl.get("url") or "",
            })
            if len(discs) >= MAX_PER_TICKER:
                break
        if discs:
            discs.sort(key=lambda x: x["date"], reverse=True)
            merged[tk] = {"ticker": tk, "name": name, "latest": discs[0]["date"], "disclosures": discs}
        else:
            merged.pop(tk, None)  # 이번 커버됐는데 윈도우 내 8-K 없음 → 오래된 항목 제거(신선도)

    # 윈도우 밖으로 밀린 carry-forward 항목 정리
    items = [it for it in merged.values() if str(it.get("latest", "")) >= cutoff]
    items.sort(key=lambda it: it["latest"], reverse=True)
    total = sum(len(it.get("disclosures") or []) for it in items)
    return {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "source": "SEC EDGAR (8-K 수시공시)",
            "market": "US",
            "count": len(items),
            "disclosure_count": total,
            "window_days": window_days,
            "covered_this_run": covered,
            "note": "공시 사실·일정만 — 점수·등급·추천 아님 (RULE 7). 제목은 SEC 원문, 링크는 EDGAR. "
                    "유니버스=combined(S&P 1500 + Polygon 소형주), 페이지 회전+carry-forward 누적.",
        },
        "items": items,
    }


def main() -> int:
    ok = False
    try:
        feed = build_feed()
        n_items = len(feed["items"])
        n_disc = feed["_meta"]["disclosure_count"]
        if n_items == 0 and os.path.isfile(OUTPUT_PATH):
            print("[us_disclosure_feed] 0 items — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(feed, f, ensure_ascii=False, indent=2)
        print(f"[us_disclosure_feed] logged=True · {n_items} 종목 · {n_disc} 공시 -> "
              f"{os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[us_disclosure_feed] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[us_disclosure_feed] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
