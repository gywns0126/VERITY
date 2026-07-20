"""신선도 SLA 공개 board — data/freshness_sla.json 능동검사를 공개용 화이트리스트로 재발행.

나박 대응 잔여 큐 (2026-07-07): "데이터가 얼마나 신선한가" 를 실측 나이 vs SLA 임계 비교
사실만으로 노출. 판정 로직 = scripts/freshness_shadow_monitor.py 헬퍼 재사용 (단일 산식,
주말 carryover 유효 age 포함 — 이중 구현 drift 방지).

화이트리스트 발행 (유리박스 교훈 — [[project_glassbox_public_contract_2026_06_25]]):
  id / label(한글) / criticality / schedule / cadence(공개용 고정 문구) / age_eff_min
  / max_age_min / status(fresh|stale|closed|discontinued) / last_ts(KST)
제외: file 경로, known_issue, 매니페스트 cadence 원문(내부 워크플로명·정정 remark 포함),
  owner=local 스트림(로컬 레이크 — heartbeat 별도), 비발행 내부 입력(analyst_reports).

status 규칙:
  active_check=false          → discontinued (수집 중단 — 사유는 공개용 cadence 문구로)
  schedule 비활성 구간(주말/장 마감) → closed (휴장 = 무생산 정상, 개장 시 재개 — stale 오탐 방지)
  age_eff <= max_age          → fresh, 초과 → stale
  missing/no_ts/bad_ts        → 발행 제외 (내부 진단은 shadow jsonl 몫)

규율: 사실만 — 점수/랭킹/추천 0 (RULE 7). LLM 0 (RULE 6).
출력: data/freshness_board.json (~6KB) — cron_health_monitor.yml 매시 갱신.
"""
from __future__ import annotations

import glob
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from api.config import DATA_DIR, now_kst  # noqa: E402
from scripts.freshness_shadow_monitor import (  # noqa: E402
    _extract_ts,
    _load_any,
    _parse_ts_kst,
    _schedule_active,
    _weekend_minutes_between,
)

MANIFEST = os.path.join(DATA_DIR, "freshness_sla.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "freshness_board.json")

# 비발행 내부 입력 — 사이트 표면에 대응물이 없어 board 노출 무가치 (다운스트림이 별도 등재)
EXCLUDE_IDS = {"analyst_reports"}

# 공개용 고정 문구 — 매니페스트 cadence 원문은 내부 워크플로명·정정 remark 를 포함하므로
# 재발행하지 않고 여기서 고정. 미등재 id = label 에 id 그대로, cadence 생략 (내부문구 유출 0).
PUBLIC_LABELS = {
    "crypto": ("크립토 시세·파생", "30분 목표"),
    "etf_flow": ("ETF 자금 흐름", "거래일 1회"),
    "macro_snapshot": ("매크로 스냅샷", "1~2시간 주기"),
    "news_flash": ("뉴스 플래시", "평일 15~30분"),
    "price_pulse": ("실시간 가격 펄스", "장중 1분"),
    "ai_synthesis": ("AI 종합 브리핑", "매일 1회"),
    "stock_report_public": ("KR 종목 리포트", "매일 1회"),
    "dart_catalyst_alerts": ("DART 공시 알림", "30분 증분"),
    "factor_ic_history": ("팩터 IC 검증 트레일", "매일 1회"),
    "dart_fundamentals_kr": ("KR 재무 원장 (DART)", "주 1회"),
    "dart_quarterly_snapshots": ("KR 분기 스냅샷 원장", "주 1회"),
    "dart_quarterly_public": ("KR 분기 추이", "주 1회"),
    "us_analyst_consensus": ("US 애널리스트 컨센서스", "수집 중단 — 재배포 권리 검토 중"),
    "us_financials": ("US 재무 (SEC EDGAR)", "월 1회"),
    "us_stock_report_public": ("US 종목 리포트", "월 1회"),
    "us_smallcap_report": ("US 소형주 리포트", "월 1회"),
    "us_insider_trades": ("US 내부자 거래 (Form 4)", "매일 1회"),
    "us_major_holdings": ("US 대량보유 (13D/G)", "주 3회"),
    "us_smart_money_13f": ("US 스마트머니 (13F)", "월 1회"),
    "sec_8k_cache": ("SEC 8-K 공시", "매일 1회"),
    "bonds_etfs": ("채권·ETF 시장", "평일 2회"),
    "penny_watchlist": ("저가주 워치리스트", "매일 1회"),
    "trade_analysis": ("거래 분석 원장", "평일 1회"),
    "equity_research": ("산업 테마 리서치", "주 1회"),
    "macro_themes": ("매크로 테마 브리프", "주 1회"),
    "eps_estimates": ("EPS 추정 스냅샷", "매일 1회"),
    "ipo_watch": ("IPO 워치", "주 1회"),
    "new_listings": ("신규 상장", "주 1회"),
    "broker_guide": ("증권사 가이드", "월 1회"),
    "dividends_kr": ("KR 배당", "매일 1회"),
    "market_warnings": ("KRX 시장경보", "매일 1회"),
}

_CRIT_ORDER = {"P0": 0, "P1": 1, "P2": 2}


def _latest_ts_for_glob(pattern: str, ts_field):
    """glob 스트림(crypto_* 등) — 매칭 파일 전체에서 최신 ts 1개."""
    best = None
    for path in glob.glob(os.path.join(DATA_DIR, pattern)):
        obj = _load_any(path)
        ts = _extract_ts(obj, ts_field)
        t = _parse_ts_kst(ts) if ts else None
        if t and (best is None or t > best):
            best = t
    return best


def build_board() -> dict:
    now = now_kst()
    manifest = _load_any(MANIFEST) or {}
    rows = []
    skipped = []
    for s in manifest.get("streams", []):
        sid = s.get("id", "")
        if s.get("owner") == "local" or sid in EXCLUDE_IDS:
            continue
        label, cadence = PUBLIC_LABELS.get(sid, (sid, None))
        sched = s.get("schedule", "always")
        row = {
            "id": sid,
            "label": label,
            "criticality": s.get("criticality"),
            "schedule": sched,
        }
        if cadence:
            row["cadence"] = cadence

        if s.get("active_check") is False:
            row["status"] = "discontinued"  # 수집 중단(은퇴·권리검토 등) — 주말 휴장과 구분
            rows.append(row)
            continue

        f = s.get("file", "")
        if "*" in f:
            t = _latest_ts_for_glob(f, s.get("ts_field"))
        else:
            path = os.path.join(DATA_DIR, f)
            obj = _load_any(path) if os.path.exists(path) else None
            ts = _extract_ts(obj, s.get("ts_field")) if obj is not None else None
            t = _parse_ts_kst(ts) if ts else None
        if t is None:
            skipped.append(sid)  # 내부 진단 = shadow jsonl 몫, 공개 board 미발행
            continue

        age_min = (now - t).total_seconds() / 60
        age_eff = age_min
        if sched in ("weekday", "market_hours"):
            age_eff = age_min - _weekend_minutes_between(t, now)
        maxm = s.get("max_age_minutes")
        row["age_eff_min"] = round(age_eff, 1)
        row["max_age_min"] = maxm
        row["last_ts"] = t.isoformat()
        if not _schedule_active(sched, now):
            row["status"] = "closed"  # 주말/장 마감 무생산 = 정상(개장 시 재개). stale 오탐 방지
        else:
            row["status"] = "stale" if (maxm and age_eff > maxm) else "fresh"
        rows.append(row)

    rows.sort(key=lambda r: (_CRIT_ORDER.get(r.get("criticality"), 9), r["id"]))
    summary = {
        "fresh": sum(1 for r in rows if r["status"] == "fresh"),
        "stale": sum(1 for r in rows if r["status"] == "stale"),
        "closed": sum(1 for r in rows if r["status"] == "closed"),          # 휴장(장 마감 정상)
        "discontinued": sum(1 for r in rows if r["status"] == "discontinued"),  # 수집 중단
    }
    for crit in ("P0", "P1", "P2"):
        crit_rows = [r for r in rows if r.get("criticality") == crit]
        n_fresh = sum(1 for r in crit_rows if r["status"] == "fresh")
        n_closed = sum(1 for r in crit_rows if r["status"] == "closed")
        n_disc = sum(1 for r in crit_rows if r["status"] == "discontinued")
        # active = 지금 생산돼야 하는 스트림(휴장·중단 제외) → 신선도 비율 분모(주말 오해 방지)
        summary[crit.lower()] = {
            "total": len(crit_rows),
            "fresh": n_fresh,
            "closed": n_closed,
            "active": len(crit_rows) - n_closed - n_disc,
        }
    return {
        "_meta": {
            "generated_at": now.isoformat(),
            "count": len(rows),
            "source": "freshness_sla 매니페스트 매시 능동검사 (실측 나이 vs SLA 임계)",
            "note": "상태 = 마지막 갱신 시각 실측 비교 사실만. 주말·장 마감 무생산 구간은 "
                    "유효 나이에서 제외하며 closed(휴장, 정상)로 표시. 수집 중단은 discontinued. 점수·예측 아님.",
        },
        "summary": summary,
        "streams": rows,
        "_skipped_count": len(skipped),
    }


def main() -> int:
    board = build_board()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(board, f, ensure_ascii=False, indent=1)
    print(f"[freshness-board] streams={board['_meta']['count']} "
          f"summary={board['summary']} skipped={board['_skipped_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
