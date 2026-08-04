#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pool_rotation_report — 운영풀 회전 주간 판정 v0 (보고서만, 집행 없음).

사전등록 = docs/PREREG_POOL_ROTATION_2026_08_04.md (PM 승인 2026-08-04, RULE 7 동결 —
임계 20d/10d/10억/55~70/KR 20/25%/주 5 조정 = 재등록).

R6: 주 1회(토요 KST) 판정, v0 = **판정 보고서만** — 집행은 PM 확인 후 수동 반영
(v1 자동 집행 = v0 4주 관찰 후 별도 승인). `--force` = 요일 무관 수동 판정.

판정 재료 = 전부 기존 산출물 read-only (신규 스코어링 0 — RULE 6/7 정합):
  풀 = data/recommendations.json
  스트릭 = data/history/YYYY-MM-DD.json 일별 스냅샷 재구성 (별도 상태 파일 없음 — 결정론 재현)
  R3 후보 = universe_candidates.json(결정론 퍼널) + smallcap_corner_filters.json(코너 통과분)
  R1 보유 = data/portfolio.json vams.holdings + exec_paper_state.json positions

**결측 ≠ 발동**: display_verdict 는 2026-08-03 부터 존재 — 스트릭 증거 일수가 임계(20d/10d)에
미달하면 퇴출 발동하지 않고 관측 누적 현황만 보고한다. 스트릭 단위 = 스냅샷 일(거래일 근사,
비거래일 run 포함 가능성 명시).

출력 = data/pool_rotation_report.json (최신 판정) + data/pool_rotation_log.jsonl (append trail).
둘 다 daily_analysis_full 의 broad `git add data/` 자동 포함 = RULE 4. publish allowlist
미등재 = 비공개 (오퍼레이터 전용 — RULE 7 자체 산식 노출 아님).
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.config import DATA_DIR, now_kst  # noqa: E402

# ── 등록 상수 (LOCKED — 조정 = 재등록) ──────────────────────────────────────
AVOID_EXIT_DAYS = 20        # R2a 배지 사망
POLLUTION_EXIT_DAYS = 10    # R2b 오염 미복구
LIQUIDITY_EXIT_DAYS = 20    # R2c 유동성 미달 지속
LIQUIDITY_MIN_KRW = 1_000_000_000  # 10억 (E3 정합)
POOL_MIN, POOL_MAX = 55, 70  # R4 정원
KR_FLOOR = 20                # R4 KR 하한
SECTOR_CAP_PCT = 25.0        # R4 단일 GICS 상한
WEEKLY_SWAP_CAP = 5          # R5 주당 교체 상한
HISTORY_LOOKBACK = 40        # 스냅샷 로드 상한 (20d 임계 + 여유)

REPORT_PATH = os.path.join(DATA_DIR, "pool_rotation_report.json")
LOG_PATH = os.path.join(DATA_DIR, "pool_rotation_log.jsonl")


def _load(path: str, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _is_kr(tk: str) -> bool:
    return bool(re.fullmatch(r"\d{6}", str(tk or "")))


def _polluted(rec: Dict[str, Any]) -> bool:
    """R2b 오염 판정 — name 오염(콤마 마커) ∨ 펀더멘털 0-채움 게이트(quality 미적용) 발동."""
    if "," in str(rec.get("name") or ""):
        return True
    mf = rec.get("multi_factor")
    return isinstance(mf, dict) and "quality_data_missing" in json.dumps(mf, ensure_ascii=False)


def load_history_days(hist_dir: str, lookback: int = HISTORY_LOOKBACK
                      ) -> List[Tuple[str, Dict[str, Dict[str, Any]]]]:
    """일별 스냅샷 → [(date, {ticker: slim_rec})] 오름차순. display_verdict 있는 날만."""
    days = []
    for path in sorted(glob.glob(os.path.join(hist_dir, "20??-??-??.json")))[-lookback:]:
        date = os.path.basename(path)[:-5]
        snap = _load(path, None)
        if not isinstance(snap, dict):
            continue
        recs = snap.get("recommendations") or []
        by_tk = {}
        for r in recs:
            dv = r.get("display_verdict")
            if not isinstance(dv, dict):
                continue
            by_tk[str(r.get("ticker"))] = {
                "final": dv.get("final"), "name": r.get("name"),
                "trading_value": r.get("trading_value"), "polluted": _polluted(r),
            }
        if by_tk:  # display_verdict 가동 run 만 (2026-08-03~)
            days.append((date, by_tk))
    return days


def compute_streaks(days: List[Tuple[str, Dict[str, Dict[str, Any]]]]
                    ) -> Dict[str, Dict[str, Any]]:
    """최신일 기준 역방향 연속 스트릭 — AVOID·오염, KR 유동성 미달 연속일."""
    out: Dict[str, Dict[str, Any]] = {}
    if not days:
        return out
    latest = days[-1][1]
    for tk in latest:
        avoid = pollution = lowliq = 0
        avoid_run = pollution_run = lowliq_run = True
        for _, snap in reversed(days):
            r = snap.get(tk)
            if r is None:
                break  # 풀 이탈 지점 — 스트릭 단절
            if avoid_run and r.get("final") == "AVOID":
                avoid += 1
            else:
                avoid_run = False
            if pollution_run and r.get("polluted"):
                pollution += 1
            else:
                pollution_run = False
            tv = r.get("trading_value")
            if lowliq_run and _is_kr(tk) and isinstance(tv, (int, float)) and tv < LIQUIDITY_MIN_KRW:
                lowliq += 1
            else:
                lowliq_run = False
        out[tk] = {"avoid_streak": avoid, "pollution_streak": pollution,
                   "lowliq_streak": lowliq, "evidence_days": sum(1 for _, s in days if tk in s)}
    return out


def _held_tickers(portfolio: Dict[str, Any], paper_state: Dict[str, Any]) -> set:
    held = set()
    for h in ((portfolio.get("vams") or {}).get("holdings") or []):
        tk = str(h.get("ticker") or "").strip()
        if tk:
            held.add(tk)
    held.update(str(t) for t in (paper_state.get("positions") or {}).keys())
    return held


def _entry_gate_ok(item: Dict[str, Any], mapping: Dict[str, str]) -> bool:
    """R3 진입 게이트 — 재무 커버리지(DART corp 매핑) ∧ E3 유동성 ∧ 오염 0."""
    tk = str(item.get("ticker") or "")
    if "," in str(item.get("name") or ""):
        return False
    if _is_kr(tk):
        if tk not in mapping:
            return False
        tv = item.get("trading_value")
        if not isinstance(tv, (int, float)) or tv < LIQUIDITY_MIN_KRW:
            return False
    return True


def build_report(pool: List[Dict[str, Any]], days, portfolio: Dict[str, Any],
                 paper_state: Dict[str, Any], universe: List[Dict[str, Any]],
                 smallcap_filters: List[Dict[str, Any]], mapping: Dict[str, str]
                 ) -> Dict[str, Any]:
    held = _held_tickers(portfolio, paper_state)
    streaks = compute_streaks(days)
    pool_tks = [str(r.get("ticker")) for r in pool]
    kr_tks = [t for t in pool_tks if _is_kr(t)]
    n_days = len(days)

    # ── R4 구성 ──
    sector_n: Dict[str, int] = {}
    for r in pool:
        s = str(r.get("sector") or "Unknown")
        sector_n[s] = sector_n.get(s, 0) + 1
    sector_over = {s: round(n / len(pool) * 100, 1) for s, n in sector_n.items()
                   if len(pool) and n / len(pool) * 100 > SECTOR_CAP_PCT}

    # ── R2 퇴출 판정 (증거 일수 임계 도달분만 — 결측 ≠ 발동) ──
    exits, watch_streaks = [], []
    for tk, st in sorted(streaks.items(), key=lambda kv: -kv[1]["avoid_streak"]):
        if tk not in pool_tks:
            continue
        reason = None
        if st["avoid_streak"] >= AVOID_EXIT_DAYS:
            reason = f"R2a 배지 AVOID {st['avoid_streak']}일 연속"
        elif st["pollution_streak"] >= POLLUTION_EXIT_DAYS:
            reason = f"R2b 오염 {st['pollution_streak']}일 미복구"
        elif st["lowliq_streak"] >= LIQUIDITY_EXIT_DAYS:
            reason = f"R2c 거래대금 10억 미만 {st['lowliq_streak']}일"
        if reason:
            if tk in held:
                watch_streaks.append({"ticker": tk, "note": f"{reason} — R1 보유 예외(퇴출 금지)",
                                      **st})
            else:
                exits.append({"ticker": tk, "reason": reason, **st})
        elif st["avoid_streak"] >= 5 or st["pollution_streak"] >= 3 or st["lowliq_streak"] >= 10:
            watch_streaks.append({"ticker": tk, **st})
    exits = exits[:WEEKLY_SWAP_CAP]

    # ── R3 진입 후보 (KR 가중 — KR 하한 미달 시 KR 만 제안) ──
    in_pool = set(pool_tks)
    kr_deficit = max(0, KR_FLOOR - len(kr_tks))
    seen = set()
    candidates = []
    for src, items in (("funnel", universe), ("smallcap", [
            t for f in smallcap_filters for t in (f.get("tickers") or [])])):
        for it in items:
            tk = str(it.get("ticker") or "")
            if not tk or tk in in_pool or tk in seen:
                continue
            if kr_deficit > 0 and not _is_kr(tk):
                continue  # KR 가중: 하한 미달 동안 KR 후보만
            if not _entry_gate_ok(it, mapping):
                continue
            seen.add(tk)
            candidates.append({"ticker": tk, "name": it.get("name"), "source": src,
                               "trading_value": it.get("trading_value")})
    # R5: 주당 교체 ≤ 5종목 — v0 는 제안 자체를 상한으로 캡 (퇴출·진입 각각 ≤5,
    # 실제 조합 적용은 PM 몫). 정원 55~70 밴드 내 순증도 허용되므로 진입은 독립 캡.
    entries = candidates[:WEEKLY_SWAP_CAP]

    # 후보 공급 진단 — KR 결손 해소 속도의 병목 가시화 (2026-08-04 실측: 퍼널 25종 중
    # 풀 밖 KR 1 · 소형주 코너는 거래대금 필드 부재로 E3 게이트 통과 구조적 불가)
    _sc_items = [t for f in smallcap_filters for t in (f.get("tickers") or [])]
    supply = {
        "funnel_total": len(universe),
        "funnel_kr_out_of_pool": sum(1 for c in universe
                                     if _is_kr(str(c.get("ticker"))) and str(c.get("ticker")) not in in_pool),
        "smallcap_total": len(_sc_items),
        "smallcap_liquidity_field_missing": bool(_sc_items) and not any(
            isinstance(t.get("trading_value"), (int, float)) for t in _sc_items),
    }

    pool_size_note = None
    if len(pool) < POOL_MIN:
        pool_size_note = f"정원 미달 {len(pool)} < {POOL_MIN}"
    elif len(pool) > POOL_MAX:
        pool_size_note = f"정원 초과 {len(pool)} > {POOL_MAX}"

    return {
        "as_of": now_kst().isoformat(timespec="seconds"),
        "version": "v0 (PREREG_POOL_ROTATION_2026_08_04 — 보고서만, 집행 없음)",
        "evidence_days": n_days,
        "evidence_note": ("display_verdict 가동(2026-08-03~) 이후 스냅샷 일 기준 — "
                          f"퇴출 임계(20d/10d) 대비 증거 {n_days}일. 미달 임계는 발동하지 않음"),
        "pool": {"size": len(pool), "kr": len(kr_tks), "kr_floor": KR_FLOOR,
                 "kr_deficit": kr_deficit, "size_note": pool_size_note,
                 "sector_over_cap": sector_over},
        "r1_held": sorted(held),
        "r1_held_out_of_pool": sorted(t for t in held if t not in in_pool),
        "exits": exits,
        "entries": entries,
        "watch_streaks": watch_streaks[:15],
        "candidate_supply": supply,
        "swap_cap": WEEKLY_SWAP_CAP,
        "action": "PM 확인 후 수동 반영 (v0). 4주 관찰 후 v1 자동 집행 별도 승인",
    }


def main() -> int:
    force = "--force" in sys.argv
    # R6: 토요일(KST) 정기 판정. 그 외 요일 = no-op (파이프라인 무부하).
    if not force and now_kst().weekday() != 5:
        print("[pool_rotation] 토요 정기 판정 아님 — skip (--force 로 수동 판정)")
        return 0
    pool = _load(os.path.join(DATA_DIR, "recommendations.json"), [])
    if not pool:
        print("[pool_rotation] recommendations.json 없음 — skip")
        return 0
    days = load_history_days(os.path.join(DATA_DIR, "history"))
    portfolio = _load(os.path.join(DATA_DIR, "portfolio.json"), {})
    paper_state = _load(os.path.join(DATA_DIR, "exec_paper_state.json"), {})
    universe = (_load(os.path.join(DATA_DIR, "universe_candidates.json"), {}) or {}).get("candidates") or []
    scf = (_load(os.path.join(DATA_DIR, "smallcap_corner_filters.json"), {}) or {}).get("filters") or []
    mapping = _load(os.path.join(DATA_DIR, "mapping.json"), {})

    report = build_report(pool, days, portfolio, paper_state, universe, scf, mapping)
    tmp = REPORT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    os.replace(tmp, REPORT_PATH)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"date": report["as_of"][:10], "evidence_days": report["evidence_days"],
                            "pool_size": report["pool"]["size"], "kr": report["pool"]["kr"],
                            "exits": [e["ticker"] for e in report["exits"]],
                            "entries": [e["ticker"] for e in report["entries"]],
                            "held_out_of_pool": report["r1_held_out_of_pool"]},
                           ensure_ascii=False) + "\n")
    print(f"[pool_rotation] 판정 완료 — 풀 {report['pool']['size']} (KR {report['pool']['kr']}"
          f"/{KR_FLOOR}) · 퇴출 {len(report['exits'])} · 진입 제안 {len(report['entries'])}"
          f" · 증거 {report['evidence_days']}일")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
