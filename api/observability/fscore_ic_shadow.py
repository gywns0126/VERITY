"""fscore_ic_shadow — Piotroski F-Score(+accrual) 관측 shadow trail (Tier B B-3, RULE 7 관측 only).

2026-07-12 신설. SoT 사전등록 = docs/PREREG_FSCORE_ACCRUAL_B3_2026_07_12.md (PM 부분승인 =
  **shadow IC trail only, 공개 노출 보류**).

목적: F-Score 는 이미 Brain quality 를 구동하나 **우리 유니버스 forward 예측력은 검증 0**.
  지금부터 (date, ticker, fscore, accrual) 스냅샷을 누적 → N≥252(~2027중) 도달 시 forward rank-IC/ICIR
  로 검증 (별도 분석). 본 모듈 = **누적만**. brain-input 0, decision 무간섭, 물리 분리 jsonl.

산식 = 동결(PREREG §1) = `wide_scan._piotroski_f_score` 9항목 재사용 (정의 이원화 금지).
  accrual(Sloan) = (NI − CFO) / 총자산. 低=양호.
입력 = dart_fundamentals_kr.json(현재 분기) + dart_quarterly_snapshots.jsonl(Δ, fscore_delta 경유).
출력 = data/observations/fscore_ic_shadow.jsonl (주1 append-only, date-dedupe).
  🔸 관측 trail 은 부분점수(available_n<9)도 available_n 병기해 적재 — "full-9 만 유효"는 **공개 표시**
     규칙(PREREG §4)이지 내부 검증 trail 규칙 아님. IC 분석 단계에서 available_n 로 필터.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FUND_PATH = os.path.join(_ROOT, "data", "dart_fundamentals_kr.json")
OUT_DIR = os.path.join(_ROOT, "data", "observations")
OUT_PATH = os.path.join(OUT_DIR, "fscore_ic_shadow.jsonl")


def _now_kst() -> datetime:
    return datetime.now(KST)


def _already_logged(date_str: str) -> bool:
    """date-dedupe — 같은 날짜 entry 존재 시 재적재 skip (idempotent)."""
    if not os.path.exists(OUT_PATH):
        return False
    try:
        with open(OUT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if f'"date": "{date_str}"' in line or f'"date":"{date_str}"' in line:
                    return True
    except OSError:
        pass
    return False


def _accrual(cfo: Any, ni: Any, assets: Any) -> Optional[float]:
    """Sloan accrual = (NI − CFO) / 총자산. 低=양호. 결측/0분모 = None."""
    try:
        if cfo is None or ni is None or not assets:
            return None
        a = float(assets)
        if a == 0:
            return None
        return round((float(ni) - float(cfo)) / a, 4)
    except (TypeError, ValueError):
        return None


def build_snapshots() -> List[Dict[str, Any]]:
    """dart_fundamentals_kr → 종목별 F-Score(동결 정의) + accrual raw 스냅샷."""
    from api.analyzers.wide_scan import _piotroski_f_score

    try:
        with open(FUND_PATH, "r", encoding="utf-8") as f:
            funds = (json.load(f) or {}).get("fundamentals") or {}
    except (OSError, json.JSONDecodeError):
        return []

    rows: List[Dict[str, Any]] = []
    for tk, fd in funds.items():
        if not isinstance(fd, dict):
            continue
        # 동결 산식 입력 (wide_scan._piotroski_f_score 계약 필드) — 결측은 None 전파(낙관 fallback 금지)
        stock = {
            "ticker": tk,
            "roa": fd.get("roa"),
            "operating_cashflow": fd.get("operating_cashflow"),
            "eps": fd.get("eps"),
            "shares_outstanding": fd.get("shares_outstanding") or fd.get("shares"),
            "gross_margin": fd.get("gross_margin"),
            "current_ratio": fd.get("current_ratio"),
            "debt_ratio": fd.get("debt_ratio"),
            "asset_turnover": fd.get("asset_turnover"),
        }
        fs = _piotroski_f_score(stock)
        score = fs.get("score")
        if score is None:  # available_n<3 = 계산 불가, 적재 제외
            continue
        rows.append({
            "ticker": tk,
            "market": "KR",
            "fscore": score,
            "available_n": fs.get("available_n"),
            "accrual": _accrual(fd.get("operating_cashflow"), fd.get("net_income"), fd.get("total_assets")),
        })
    return rows


def main() -> int:
    date_str = _now_kst().strftime("%Y-%m-%d")
    if _already_logged(date_str):
        print(f"[fscore_ic_shadow] {date_str} 이미 적재 — skip (idempotent)", file=sys.stderr)
        return 0
    rows = build_snapshots()
    if not rows:
        print("[fscore_ic_shadow] 산출 0 — 적재 skip (fundamentals/스냅샷 부재?)", file=sys.stderr)
        return 0
    os.makedirs(OUT_DIR, exist_ok=True)
    full9 = sum(1 for r in rows if r.get("available_n") == 9)
    entry = {
        "date": date_str,
        "generated_at": _now_kst().isoformat(),
        "signal": "fscore_piotroski",
        "n": len(rows),
        "n_full9": full9,
        "note": "관측 only · brain-input 0 · PREREG_FSCORE_ACCRUAL_B3 · forward rank-IC 검증용 누적 (공개 X)",
        "stocks": rows,
    }
    with open(OUT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[fscore_ic_shadow] {date_str} 적재 {len(rows)} 종목 (완전9 {full9}) -> {os.path.relpath(OUT_PATH, _ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
