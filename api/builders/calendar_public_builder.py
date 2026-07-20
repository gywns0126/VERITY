"""
투자 캘린더 public 빌더 (2026-07-12) — 보유 이벤트 데이터를 시간축으로 재배열.

🚨 차별점(RULE 6/7 정합): 범용 '실적 캘린더'(네이버·토스 강자영역) 흉내 X.
  우리 강점 = 공시 포렌식. 각 공시 제목을 포렌식 카테고리(희석/자사주/구조/실적)로 분류해 태그.
  = "이벤트 캘린더 + 사실 판단 레이어". 점수·등급·추천 0 (사실 카테고리 태그만).

입력(read-only, 전부 보유):
  - data/public_disclosure_feed.json  (DART 공시, 최근 14일 window · 제목·날짜·원문URL)
  - data/dividends_kr.json            (배당락 ex_date · 미래일자)
  - data/ipo_watch.json               (IPO 청약/납입 일정 · 미래일자)

출력: data/calendar_public.json  { _meta, events:[{date,type,cat,tag,ticker,name,title,url,market}] }
  · publish-data allowlist 추가 의무 ([[feedback_publish_data_file_list_audit]]).

포워드 갭(정직): 실적발표 예정일·락업해제·투자경고 해제 = 구조화 소스 미보유 → v0 제외.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA = os.path.join(_ROOT, "data")

DISCLOSURE_PATH = os.path.join(_DATA, "public_disclosure_feed.json")
DIVIDENDS_PATH = os.path.join(_DATA, "dividends_kr.json")
IPO_PATH = os.path.join(_DATA, "ipo_watch.json")
NAMES_PATH = os.path.join(_DATA, "kr_stock_names.json")
OUTPUT_PATH = os.path.join(_DATA, "calendar_public.json")


def _now() -> str:
    return datetime.now(KST).isoformat()


def _load(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


# 공시 제목 → 포렌식 카테고리·태그 (사실 분류만, 순서 = 구체 우선).
# cat: dilution(희석) / buyback(자사주 취득·소각=수급+) / supply(자사주 처분=수급-)
#      / capital(자본변동) / structural(구조) / earnings(실적) / governance(지배구조)
_RULES = [
    (r"전환사채", ("dilution", "CB")),
    (r"신주인수권부사채", ("dilution", "BW")),
    (r"교환사채", ("dilution", "EB")),
    (r"유상증자", ("dilution", "유상증자")),
    (r"무상증자", ("capital", "무상증자")),
    (r"자기주식.*소각|자기주식소각", ("buyback", "자사주 소각")),
    (r"자기주식.*처분|자기주식처분", ("supply", "자사주 처분")),
    (r"자기주식.*취득|자기주식취득", ("buyback", "자사주 취득")),
    (r"주식소각", ("buyback", "주식 소각")),
    (r"유상감자", ("capital", "유상감자")),
    (r"무상감자|감자", ("capital", "감자")),
    (r"합병", ("structural", "합병")),
    (r"분할", ("structural", "분할")),
    (r"영업양[수도]|영업의?\s*양수|자산양[수도]", ("structural", "영업양수도")),
    (r"주식교환|주식이전", ("structural", "주식교환")),
    (r"잠정실적|영업.?잠정.?실적|매출액.?영업이익", ("earnings", "잠정실적")),
    (r"현금[·, ]?현물배당|주식배당", ("dividend", "배당결정")),
    (r"최대주주.?변경|경영권", ("governance", "최대주주 변경")),
    (r"소송|가처분", ("governance", "소송")),
    (r"상장폐지|관리종목|거래정지", ("governance", "상장위험")),
]


def _classify(title: str) -> tuple | None:
    t = title or ""
    for pat, cattag in _RULES:
        if re.search(pat, t):
            return cattag
    return None  # 미분류 = 일반공시 → v0 제외(신호 집중)


def _valid_date(s: str) -> str | None:
    m = re.match(r"(\d{4})[-.](\d{2})[-.](\d{2})", str(s or ""))
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def build() -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    names = _load(NAMES_PATH, {}) or {}

    # ── 1) 공시 (포렌식 분류) ──
    disc = _load(DISCLOSURE_PATH, {})
    items = disc.get("items") if isinstance(disc, dict) else disc
    n_disc = 0
    for st in (items if isinstance(items, list) else []):
        tk = str(st.get("ticker") or "")
        nm = st.get("name") or names.get(tk) or tk
        for d in (st.get("disclosures") or []):
            if d.get("is_correction"):
                continue  # 정정공시 = 중복 노이즈 회피
            date = _valid_date(d.get("date"))
            title = str(d.get("title") or "")
            cat = _classify(title)
            if not date or not cat:
                continue
            events.append({
                "date": date, "type": "disclosure", "cat": cat[0], "tag": cat[1],
                "ticker": tk, "name": nm, "title": title,
                "url": d.get("source_url") or "", "market": "KR",
            })
            n_disc += 1

    # ── 2) 배당락 (ex_date, 미래·과거 모두 — 컴포넌트가 월 필터) ──
    div = _load(DIVIDENDS_PATH, {})
    n_div = 0
    if isinstance(div, dict):
        for tk, rows in div.items():
            if not isinstance(rows, list):
                continue
            nm = names.get(tk) or tk
            for r in rows:
                date = _valid_date(r.get("ex_date"))
                if not date:
                    continue
                amt = r.get("confirmed_amount_per_share") or r.get("announced_amount_per_share")
                conf = bool(r.get("is_confirmed"))
                events.append({
                    "date": date, "type": "dividend", "cat": "dividend",
                    "tag": "배당락" + ("" if conf else "(예상)"),
                    "ticker": tk, "name": nm,
                    "title": (f"주당 {int(amt):,}원 " if amt else "") + "배당락",
                    "url": "", "market": "KR",
                })
                n_div += 1

    # ── 3) IPO 청약·납입 (미래일자) ──
    ipo = _load(IPO_PATH, {})
    n_ipo = 0
    for w in (ipo.get("watch") or []):
        nm = w.get("corp_name") or ""
        off = w.get("offering") or {}
        for key, lab in (("subscribe_start", "청약 시작"), ("subscribe_end", "청약 마감"), ("payment_date", "납입")):
            date = _valid_date(off.get(key))
            if not date:
                continue
            events.append({
                "date": date, "type": "ipo", "cat": "ipo", "tag": "IPO " + lab,
                "ticker": "", "name": nm, "title": f"{nm} 공모 {lab}",
                "url": w.get("dart_url") or "", "market": "KR",
            })
            n_ipo += 1

    events.sort(key=lambda e: (e["date"], e["type"]))
    out = {
        "_meta": {
            "generated_at": _now(),
            "source": "DART 공시(포렌식 분류)·배당락·IPO — 보유 데이터 재배열, 신규수집 0",
            "note": "이벤트 = 공개 사실. 포렌식 태그(희석/자사주 등)는 공시 제목 분류일 뿐 점수·추천 아님 (RULE 7). "
                    "실적발표 예정일·락업해제 = 소스 미보유로 미포함.",
            "counts": {"disclosure": n_disc, "dividend": n_div, "ipo": n_ipo, "total": len(events)},
        },
        "events": events,
    }
    return out


def main() -> int:
    out = build()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    c = out["_meta"]["counts"]
    sys.stderr.write(f"[calendar_public] events={c['total']} (공시 {c['disclosure']} / 배당 {c['dividend']} / IPO {c['ipo']})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
