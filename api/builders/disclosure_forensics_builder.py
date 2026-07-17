"""disclosure_forensics_builder — 공개 터미널 종목별 공시 이벤트 이력·빈도(상습범 forensics) 빌더.

2026-06-19 신설. 차별기능 정밀검증(3 에이전트 + 1차자료 verify) 결과 = build-now.
  증권사/토스/네이버 = 개별 공시 "오늘 떴다" 속보만. VERITY 차별 = 한 종목이 유상증자/감자/CB/
  정정 같은 주주가치 희석·리스크 이벤트를 **언제 몇 번 반복했나**(누적 빈도·타임라인). 자기 데이터 자산.

입력 = data/dart_catalyst_alerts.jsonl (public_disclosure_feed_builder 와 동일 소스, read-only).
  · 현재 깊이 ~5주(rolling). 2015~ 전체는 scripts/dart_catalyst_backfill.py 백필 후 자동 심화(같은 jsonl append).
출력 = data/disclosure_forensics.json (action.yml publish 등재 필요).

🚨 RULE 7 — report_nm(DART 원문 제목)·접수일·빈도 카운트 = 사실만. 자체 위험점수·등급·판단 0.
  "상습범" 프레이밍은 내부용 — 노출 문구는 "이력·빈도"(중립). pblntf 분류는 DART 공식.
RULE 6 — 런타임 LLM 0. 키워드 분류는 사전 정의(아래 CATEGORIES). 순수 변환(외부호출 0, KIS 0).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INPUT_PATH = os.path.join(_ROOT, "data", "dart_catalyst_alerts.jsonl")
BACKFILL_PATH = os.path.join(_ROOT, "data", "dart_catalyst_backfill.jsonl")  # 2015~ 과거 이력(있으면 심화)
OUTPUT_PATH = os.path.join(_ROOT, "data", "disclosure_forensics.json")

# 주주가치 희석·리스크 이벤트 분류 (report_nm 키워드, 우선순위 순 — 첫 매치 채택). RULE 6 사전 정의.
CATEGORIES: List[Dict[str, Any]] = [
    {"key": "유상증자", "kw": ["유상증자"], "risk": "dilution"},
    {"key": "무상증자", "kw": ["무상증자"], "risk": "neutral"},
    {"key": "전환사채(CB)", "kw": ["전환사채"], "risk": "dilution"},
    {"key": "신주인수권부사채(BW)", "kw": ["신주인수권부사채", "신주인수권"], "risk": "dilution"},
    {"key": "교환사채(EB)", "kw": ["교환사채"], "risk": "dilution"},
    {"key": "감자", "kw": ["감자"], "risk": "risk"},
    {"key": "자기주식취득", "kw": ["자기주식취득", "자기주식 취득", "자기주식취득신탁"], "risk": "favorable"},
    {"key": "자기주식처분", "kw": ["자기주식처분", "자기주식 처분"], "risk": "dilution"},
    {"key": "횡령·배임", "kw": ["횡령", "배임"], "risk": "risk"},
    {"key": "회생·상장폐지", "kw": ["회생절차", "상장폐지", "관리종목", "거래정지", "감사의견"], "risk": "risk"},
    {"key": "불성실공시", "kw": ["불성실공시"], "risk": "risk"},
    {"key": "합병", "kw": ["합병"], "risk": "structural"},
    {"key": "분할", "kw": ["분할"], "risk": "structural"},
    {"key": "영업양수도", "kw": ["영업양수", "영업양도", "자산양수", "자산양도"], "risk": "structural"},
]


def _now_kst() -> datetime:
    return datetime.now(KST)


def _classify(report_nm: str) -> Dict[str, str] | None:
    nm = report_nm or ""
    for c in CATEGORIES:
        if any(k in nm for k in c["kw"]):
            return {"category": c["key"], "risk": c["risk"]}
    return None


def main() -> int:
    ok = False
    try:
        if not os.path.isfile(INPUT_PATH) and not os.path.isfile(BACKFILL_PATH):
            print("[disclosure_forensics] 입력 jsonl 부재 — skip", file=sys.stderr)
            return 0
        rows: List[Dict[str, Any]] = []
        for path in (INPUT_PATH, BACKFILL_PATH):  # rolling 최근 + 2015~ 백필 합산
            if not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        # 종목별 집계 (dedup by rcept_no)
        by_ticker: Dict[str, Dict[str, Any]] = {}
        seen: set = set()
        all_dates: List[str] = []
        for a in rows:
            tk = str(a.get("ticker") or "").strip()
            rc = str(a.get("rcept_no") or "")
            nm = a.get("report_nm") or ""
            if not tk or not rc or rc in seen:
                continue
            is_corr = bool(a.get("is_correction"))
            cls = _classify(nm)
            if not cls and not is_corr:
                continue  # forensics 관련 이벤트만 (일반 공시 제외)
            seen.add(rc)
            dt = str(a.get("rcept_dt") or "")
            date = f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}" if len(dt) == 8 else dt
            if dt:
                all_dates.append(dt)
            cat = "정정공시" if is_corr else cls["category"]
            risk = "correction" if is_corr else cls["risk"]
            slot = by_ticker.setdefault(tk, {
                "ticker": tk, "name": a.get("name") or "", "counts": {}, "events": [],
            })
            slot["counts"][cat] = slot["counts"].get(cat, 0) + 1
            slot["events"].append({
                "date": date,
                "category": cat,
                "risk": risk,
                "title": nm,
                "is_correction": is_corr,
                "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + rc,
            })

        dilution_keys = ("유상증자", "전환사채(CB)", "신주인수권부사채(BW)", "교환사채(EB)", "자기주식처분")
        cutoff_12m = (_now_kst() - timedelta(days=365)).strftime("%Y-%m-%d")
        stocks: List[Dict[str, Any]] = []
        for tk, slot in by_ticker.items():
            slot["events"].sort(key=lambda e: e["date"], reverse=True)
            full_events = slot["events"]  # 캡 전 전체 — 파생 사실 계산용
            slot["total"] = sum(slot["counts"].values())
            # 희석성 이벤트 합 (유상증자/CB/BW/EB/자기주식처분) — 사실 카운트, 점수 아님
            slot["dilution_count"] = sum(slot["counts"].get(k, 0) for k in dilution_keys)
            # ── 파생 포렌식 사실 (체인 깊이) — 순수 카운트/날짜, 판정·점수·추천 0 (RULE 7) ──
            corr_n = slot["counts"].get("정정공시", 0)
            dil_dates = sorted([e["date"] for e in full_events
                                if e["category"] in dilution_keys and e["date"]])
            # 직전(12개월 이전) 희석 이벤트 = baseline 사실. "최근 12개월 N회 (직전 연평균 M회)" 병기용.
            # 🚨 RULE 7 — 두 raw 사실만. "급증/이상" 판정·boolean·점수 0. 독자가 두 숫자 보고 판단.
            prior_dates = [d for d in dil_dates if d < cutoff_12m]
            prior_avg = 0.0
            if prior_dates:
                try:
                    _d0 = datetime.strptime(prior_dates[0][:10], "%Y-%m-%d")
                    _dc = datetime.strptime(cutoff_12m[:10], "%Y-%m-%d")
                    _span_years = max(1.0, (_dc - _d0).days / 365.0)  # 관측 기간(년), 최소 1
                    prior_avg = round(len(prior_dates) / _span_years, 1)
                except (ValueError, TypeError):
                    prior_avg = 0.0
            slot["forensics_flags"] = {
                "correction_count": corr_n,                                    # 정정공시 건수 (공시 신뢰도 사실)
                "correction_pct": round(100.0 * corr_n / slot["total"]) if slot["total"] else 0,
                "dilution_12m": sum(1 for d in dil_dates if d >= cutoff_12m),   # 최근 12개월 희석 횟수
                "dilution_span": (dil_dates[0] + " ~ " + dil_dates[-1]) if len(dil_dates) >= 2 else "",
                "dilution_annual_avg_prior": prior_avg,                         # 직전(12m 이전) 연평균 희석 횟수 (baseline 사실)
                "dilution_history_from": prior_dates[0] if prior_dates else "", # 관측 시작일 (사실, 맥락)
            }
            slot["events"] = full_events[:30]
            stocks.append(slot)
        # 총 이벤트 많은 순 (사실 정렬)
        stocks.sort(key=lambda s: s["total"], reverse=True)

        win_lo = min(all_dates) if all_dates else ""
        win_hi = max(all_dates) if all_dates else ""

        if not stocks and os.path.isfile(OUTPUT_PATH):
            print("[disclosure_forensics] 0 종목 — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0

        out = {
            "_meta": {
                "generated_at": _now_kst().isoformat(),
                "source": "DART 전자공시 (report_nm 사실 분류)",
                "window": {"from": win_lo, "to": win_hi},
                "count": len(stocks),
                "note": "공시 원문 제목 기준 이벤트 이력·빈도(사실) — 자체 위험점수·등급·판단 0 (RULE 7). "
                        "현재 수집창 한정, 2015~ 전체는 백필 후 심화.",
                "categories": [c["key"] for c in CATEGORIES] + ["정정공시"],
            },
            "stocks": stocks,
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[disclosure_forensics] logged=True · {len(stocks)} 종목 · 창 {win_lo}~{win_hi} -> "
              f"{os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[disclosure_forensics] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[disclosure_forensics] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
