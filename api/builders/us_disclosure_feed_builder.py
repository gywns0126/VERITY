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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_PATH = os.path.join(_ROOT, "data", "us_financials", "_summary.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_disclosure_feed.json")

WINDOW_DAYS = 60        # 8-K 산발적 → 윈도우 넉넉히
MAX_PER_TICKER = 5


def _now_kst() -> datetime:
    return datetime.now(KST)


def _title(name: str) -> str:
    return " ".join(w.capitalize() for w in str(name or "").split())


def _universe() -> List[Dict[str, str]]:
    try:
        with open(SUMMARY_PATH, "r", encoding="utf-8") as f:
            rows = (json.load(f) or {}).get("rows") or []
    except (OSError, json.JSONDecodeError):
        rows = []
    out = []
    for r in rows:
        tk = r.get("ticker")
        if tk:
            out.append({"ticker": tk, "name": _title(r.get("entity_name") or tk)})
    return out


def build_feed(window_days: int = WINDOW_DAYS) -> Dict[str, Any]:
    from api.collectors.sec_edgar import get_recent_filings
    from api.intelligence.us_financials import SEC_USER_AGENT

    cutoff = (_now_kst().date() - timedelta(days=window_days)).strftime("%Y-%m-%d")
    items: List[Dict[str, Any]] = []
    total = 0

    for u in _universe():
        tk, name = u["ticker"], u["name"]
        try:
            filings = get_recent_filings(tk, SEC_USER_AGENT, ["8-K"]) or []
        except Exception as e:  # noqa: BLE001
            print(f"[us_disclosure_feed] {tk} 8-K fetch 실패: {e!r}", file=sys.stderr)
            continue
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
        if not discs:
            continue
        discs.sort(key=lambda x: x["date"], reverse=True)
        items.append({
            "ticker": tk,
            "name": name,
            "latest": discs[0]["date"],
            "disclosures": discs,
        })
        total += len(discs)

    items.sort(key=lambda it: it["latest"], reverse=True)
    return {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "source": "SEC EDGAR (8-K 수시공시)",
            "market": "US",
            "count": len(items),
            "disclosure_count": total,
            "window_days": window_days,
            "note": "공시 사실·일정만 — 점수·등급·추천 아님 (RULE 7). 제목은 SEC 원문, 링크는 EDGAR. 15 빅캡.",
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
