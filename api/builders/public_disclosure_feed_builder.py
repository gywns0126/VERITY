"""public_disclosure_feed_builder — 공개 터미널 "공시 속보" 피드 빌더.

배경 (2026-06-17):
  AlphaNest 공개 터미널 1차 슬라이스 = 공시 속보 탭. 기존 수집 자산
  data/dart_catalyst_alerts.jsonl (api/main.py STEP 5.78, dart_catalyst.py 수집,
  운영풀 KR 종목 직전 N일 공시, dedupe by rcept_no) 을 **public-safe JSON** 으로 변환.

  순수 변환 빌더 — 외부 API 호출 0, KIS 0, deploy 0. 입력 jsonl read-only.

RULE 7 (자기 산식 비노출):
  - 공시 제목(report_nm) = DART 원문 그대로 = 사실.
  - 공시 분류(pblntf_label) = DART 공식 분류 = 사실.
  - 정정여부(is_correction) / 제출인(flr_nm) / 접수일 = 사실.
  - 원문 링크 = rcept_no 로 DART 문서 viewer deep-link (정보 신뢰도).
  - 자체 severity 가중치 = **정렬에만 사용, JSON 에 노출하지 않음** (자기 산출 점수).
  - 점수·등급·추천·verdict 0.

feedback_data_collection_verification_mandatory:
  - try/finally + logged stderr 표식. silent skip 금지.
  - 산출 0건이면 직전 snapshot 보존 (덮어쓰기 X).

publish (RULE 4 / feedback_publish_data_file_list_audit):
  - 산출 data/public_disclosure_feed.json 은 publish-data action 파일 목록에 추가 필요.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

# 공시 분류 재사용 (재구현 금지) + '왜 중요한가' 결정론 템플릿. 둘 다 런타임 LLM 0.
from api.builders.disclosure_forensics_builder import _classify
from api.builders.disclosure_why_templates import why_for_kr

KST = timezone(timedelta(hours=9))

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INPUT_PATH = os.path.join(_REPO_ROOT, "data", "dart_catalyst_alerts.jsonl")
OUTPUT_PATH = os.path.join(_REPO_ROOT, "data", "public_disclosure_feed.json")

WINDOW_DAYS = 14            # 피드 노출 기간
MAX_PER_TICKER = 8         # 종목당 공시 최대 노출
DART_VIEWER = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="


def _now_kst() -> datetime:
    return datetime.now(KST)


def _fmt_date(rcept_dt: str) -> str:
    """YYYYMMDD -> YYYY-MM-DD (실패 시 원본)."""
    s = str(rcept_dt or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


def _load_alerts() -> List[Dict[str, Any]]:
    if not os.path.isfile(INPUT_PATH):
        return []
    rows: List[Dict[str, Any]] = []
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def build_feed(window_days: int = WINDOW_DAYS) -> Dict[str, Any]:
    now = _now_kst()
    cutoff = (now - timedelta(days=window_days)).strftime("%Y%m%d")

    alerts = _load_alerts()

    # window 필터 + rcept_no dedupe
    seen: set[str] = set()
    recent: List[Dict[str, Any]] = []
    for a in alerts:
        rcept_no = str(a.get("rcept_no") or "").strip()
        rcept_dt = str(a.get("rcept_dt") or "").strip()
        if not rcept_no or not rcept_dt:
            continue
        if rcept_dt < cutoff:
            continue
        if rcept_no in seen:
            continue
        seen.add(rcept_no)
        recent.append(a)

    # 종목별 그룹
    by_ticker: Dict[str, Dict[str, Any]] = {}
    for a in recent:
        ticker = str(a.get("ticker") or "").strip()
        if not ticker:
            continue
        grp = by_ticker.setdefault(
            ticker,
            {"ticker": ticker, "name": a.get("name") or ticker, "_rows": []},
        )
        grp["_rows"].append(a)

    items: List[Dict[str, Any]] = []
    for ticker, grp in by_ticker.items():
        rows = grp["_rows"]
        # 정렬: 접수일 desc, 동일자면 자체 severity desc (severity 는 노출 X)
        rows.sort(
            key=lambda r: (str(r.get("rcept_dt") or ""), int(r.get("severity") or 0)),
            reverse=True,
        )
        disclosures = []
        for r in rows[:MAX_PER_TICKER]:
            rcept_no = str(r.get("rcept_no") or "").strip()
            # '왜 중요한가' — 카테고리 분류(재사용) → 결정론 dict lookup. LLM 0. 미매핑 = 빈 문자열.
            _is_corr = bool(r.get("is_correction"))
            _cls = _classify(r.get("report_nm") or "")
            _cat = "정정공시" if _is_corr else (_cls["category"] if _cls else None)
            disclosures.append(
                {
                    "title": r.get("report_nm") or "",          # DART 원문 제목 (사실)
                    "label": r.get("pblntf_label") or "",       # DART 분류 (사실)
                    "date": _fmt_date(r.get("rcept_dt")),       # 접수일 (사실)
                    "is_correction": _is_corr,
                    "filer": r.get("flr_nm") or "",             # 제출인 (사실)
                    "source_url": DART_VIEWER + rcept_no,        # 원문 deep-link
                    "why_it_matters": why_for_kr(_cat),          # 결정론 사실 설명 (사실+단계 caveat, 판정 0)
                }
            )
        max_sev = max((int(r.get("severity") or 0) for r in rows), default=0)
        items.append(
            {
                "ticker": ticker,
                "name": grp["name"],
                "latest": disclosures[0]["date"] if disclosures else "",
                "_sev": max_sev,  # 정렬 전용 — 출력 직전 제거 (RULE 7: severity 비노출)
                "disclosures": disclosures,
            }
        )

    # 종목 정렬: 임팩트(severity) 큰 종목 먼저, 동급이면 최근 공시일 desc (품질 우선)
    items.sort(key=lambda it: (it["_sev"], it["latest"]), reverse=True)
    for it in items:
        it.pop("_sev", None)  # RULE 7 — 자체 severity 노출 안 함

    return {
        "_meta": {
            "generated_at": now.isoformat(),
            "source": "DART OpenAPI (전자공시)",
            "window_days": window_days,
            "count": len(items),
            "disclosure_count": len(recent),
            "note": "공시 사실·일정만 — 점수·등급·추천 아님 (RULE 7). 제목은 DART 원문 그대로, 링크는 원문 viewer.",
        },
        "items": items,
    }


def main() -> int:
    ok = False
    try:
        feed = build_feed()
        n_items = len(feed["items"])
        n_disc = feed["_meta"]["disclosure_count"]

        if n_disc == 0:
            # 산출 0건 — 직전 snapshot 보존 (덮어쓰기 X)
            if os.path.isfile(OUTPUT_PATH):
                print(
                    f"[public_disclosure_feed] 0 disclosures in window — "
                    f"기존 snapshot 보존 (no overwrite)",
                    file=sys.stderr,
                )
                ok = True
                return 0
            print(
                "[public_disclosure_feed] 0 disclosures and no existing snapshot — "
                "빈 피드 기록",
                file=sys.stderr,
            )

        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(feed, f, ensure_ascii=False, indent=2)

        print(
            f"[public_disclosure_feed] logged=True · {n_items} 종목 · "
            f"{n_disc} 공시 · -> {os.path.relpath(OUTPUT_PATH, _REPO_ROOT)}",
            file=sys.stderr,
        )
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[public_disclosure_feed] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[public_disclosure_feed] logged=False (실패 또는 미완)", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
