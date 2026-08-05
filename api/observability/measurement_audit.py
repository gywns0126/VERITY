# -*- coding: utf-8 -*-
"""measurement_audit — 측정 오염 자동 검출 3종 (2026-08-05 신설).

배경: 2026-08-04~05 감사에서 확정 결함이 다수 나왔는데, **전부 "조용히 죽어서 아무도
몰랐던" 종류**였다 — 하트비트 30일, event_study 38일, 유령 매도 3주, 통화 오류(당시 진행 중).
사람이 478개 모듈을 훑는 방식은 끝나지 않고, 코드가 바뀌면 다시 0부터다.

그래서 그날 결함을 실제로 잡아낸 **세 가지 대조**를 상시 검사로 고정한다. 셋 다 그날
검출력이 실증됐다(각 검사 docstring 에 실측 인용).

  A. 원장 정합  — 보유 재생으로 유령 매도·수량 불일치 검출 → 유령 58건을 잡은 방법
  B. 키 커버리지 — 채점 모듈이 읽는 stock 키를 실 레코드와 대조 → 죽은 경로 9종을 잡은 방법
  C. 단위 스케일 — 같은 종목의 가격 계열 필드 비율 이상 검출 → 통화 오류를 잡은 방법

산출: data/measurement_audit.json (+ jsonl append trail)
🚨 이 모듈은 **어떤 점수에도 입력되지 않는다.** 관측·신고 전용 (RULE 7 산식 무변경).
graceful: 입력 결손·예외 시 해당 검사만 skip, 파이프라인 fail 금지.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

OUT_PATH = os.path.join(DATA_DIR, "measurement_audit.json")
TRAIL_PATH = os.path.join(DATA_DIR, "metadata", "measurement_audit_trail.jsonl")

# 검사 C — 가격 계열 필드 비율 임계. 통화 혼재(USD↔KRW)는 1,300배 근처라 10배면 충분히 잡힌다.
SCALE_RATIO_MAX = 10.0

# 검사 B — 채점 판단에 실제로 쓰이는 모듈만 (전 코드베이스가 아니라 채점 경로 한정)
SCORING_MODULES = [
    "api/intelligence/factors/fact.py",
    "api/intelligence/factors/graham.py",
    "api/intelligence/factors/moat.py",
    "api/intelligence/factors/canslim.py",
    "api/intelligence/factors/vci.py",
    "api/intelligence/factors/red_flags.py",
    "api/quant/factors/quality.py",
    "api/analyzers/multi_factor.py",
    "api/intelligence/value_guards.py",
]
_STOCK_GET = re.compile(r'stock\.get\(\s*["\']([a-zA-Z_0-9]+)["\']')

# 검사 B 화이트리스트 — 폴백이 존재해 결측이 무해한 키 (2026-08-05 검증 완료)
#   per/pbr 이 67/67 이라 아래 대체 키는 쓰일 일이 없다.
_BENIGN_MISSING = {"price_to_earnings", "price_to_book"}


def _load(path: str, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def audit_ledger() -> Dict[str, Any]:
    """A. 원장 정합 — 보유 재생으로 유령 매도 검출.

    실증(2026-08-05): 리셋 후 SELL 70건 중 58건이 보유 0 상태 매도였고 −1,396,639원의
    존재하지 않는 손실이 게이트 통계에 들어가 있었다. 버그(dev-mode 오염)는 7/20 에
    수정됐지만 적재된 기록이 남아 계속 집계되던 것을 이 대조가 잡아냈다.
    """
    try:
        from api.vams.engine import load_history
        from api.vams.trade_ledger import reconstruct
        pf = _load(os.path.join(DATA_DIR, "portfolio.json"), {}) or {}
        reset_at = str((((pf.get("vams") or {}).get("reset_meta") or {})
                        .get("reset_at") or ""))[:10] or None
        led = reconstruct(load_history(), since=reset_at)
        n_ph = len(led["phantoms"])
        return {
            "ok": n_ph == 0,
            "episodes": len(led["episodes"]),
            "phantom_sells": n_ph,
            "phantom_pnl": led["phantom_pnl"],
            "window_start": reset_at,
            "detail": (f"보유 0 상태 매도 {n_ph}건 (손익 {led['phantom_pnl']:,.0f}원) — "
                       "집계에서 배제됨. 신규 발생이면 원장 오염 재발"
                       if n_ph else "유령 매도 없음"),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": None, "skipped": f"{type(e).__name__}: {e}"[:120]}


def audit_key_coverage(root: str = ".") -> Dict[str, Any]:
    """B. 키 커버리지 — 채점 모듈이 읽는 stock 키가 실 레코드에 존재하는가.

    실증(2026-08-05): 채점 모듈이 최상위에서 읽는 75키 중 **9개가 0/67** 이었다.
    가장 큰 것은 alpha_combined — 퀀트 alpha 보너스가 항상 0 으로 흘렀다.
    폴백이 있는 키(price_to_earnings 등)는 화이트리스트로 오탐 배제.
    """
    try:
        recs = _load(os.path.join(DATA_DIR, "recommendations.json"), [])
        if not recs:
            return {"ok": None, "skipped": "recommendations.json 없음"}
        wanted: Dict[str, List[str]] = {}
        for rel in SCORING_MODULES:
            p = os.path.join(root, rel)
            if not os.path.exists(p):
                continue
            with open(p, encoding="utf-8") as f:
                for k in set(_STOCK_GET.findall(f.read())):
                    wanted.setdefault(k, []).append(os.path.basename(rel))
        dead, thin = [], []
        for k, mods in wanted.items():
            if k in _BENIGN_MISSING:
                continue
            n = sum(1 for r in recs if r.get(k) is not None)
            if n == 0:
                dead.append({"key": k, "modules": sorted(set(mods))})
            elif n < len(recs) * 0.05:
                thin.append({"key": k, "coverage": f"{n}/{len(recs)}"})
        return {
            "ok": not dead,
            "keys_checked": len(wanted),
            "dead_keys": sorted(dead, key=lambda x: x["key"]),
            "thin_keys": thin[:10],
            "detail": (f"레코드에 한 번도 없는 키 {len(dead)}종 — 해당 채점 축이 조용히 죽어 있다"
                       if dead else "죽은 키 없음"),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": None, "skipped": f"{type(e).__name__}: {e}"[:120]}


def audit_price_scale() -> Dict[str, Any]:
    """C. 단위 스케일 — 같은 보유의 가격 계열 필드끼리 비율이 정상인가.

    실증(2026-08-05): 보유 US 5종 전부 매수가/익절타깃 비율이 1,312~1,340배(=USD/KRW
    환율)였다. `current_price >= target_price` 가 항상 참이 되어 매 run 익절이 발동했다
    (EQT 30회·EXE 20회). 10배 임계면 통화 혼재를 확실히 잡고 정상 변동은 통과한다.
    """
    try:
        pf = _load(os.path.join(DATA_DIR, "portfolio.json"), {}) or {}
        hs = ((pf.get("vams") or {}).get("holdings")) or []
        bad = []
        for h in hs:
            bp = h.get("buy_price") or 0
            if bp <= 0:
                continue
            for label, val in (
                ("target_1", ((h.get("exit_targets") or {}).get("target_1") or {}).get("price")),
                ("stop_price", h.get("stop_price")),
            ):
                if not isinstance(val, (int, float)) or val <= 0:
                    continue
                ratio = bp / val
                if ratio > SCALE_RATIO_MAX or ratio < 1 / SCALE_RATIO_MAX:
                    bad.append({"name": h.get("name"), "ticker": h.get("ticker"),
                                "field": label, "buy_price": round(bp, 2),
                                "value": round(val, 2), "ratio": round(ratio, 1)})
        return {
            "ok": not bad,
            "holdings_checked": len(hs),
            "scale_mismatches": bad,
            "detail": (f"가격 스케일 불일치 {len(bad)}건 — 통화 혼재 의심(비율≈환율이면 확정). "
                       "해당 보유는 부분익절 평가가 skip 된다(fail-closed)"
                       if bad else "스케일 정합"),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": None, "skipped": f"{type(e).__name__}: {e}"[:120]}


def run(root: str = ".") -> Dict[str, Any]:
    checks = {
        "ledger_integrity": audit_ledger(),
        "key_coverage": audit_key_coverage(root),
        "price_scale": audit_price_scale(),
    }
    fails = [k for k, v in checks.items() if v.get("ok") is False]
    skips = [k for k, v in checks.items() if v.get("ok") is None]
    out = {
        "as_of": now_kst().isoformat(timespec="seconds"),
        "version": "measurement_audit_v0",
        "status": "FAIL" if fails else ("PARTIAL" if skips else "OK"),
        "failing": fails,
        "skipped": skips,
        "checks": checks,
        "note": ("측정 오염 자동 검출 — 2026-08-05 감사에서 확정 결함을 실제로 잡아낸 "
                 "세 대조를 상시화. 점수 입력 0(관측 전용)."),
    }
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT_PATH)
    os.makedirs(os.path.dirname(TRAIL_PATH), exist_ok=True)
    with open(TRAIL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"as_of": out["as_of"], "status": out["status"],
                            "phantom_sells": checks["ledger_integrity"].get("phantom_sells"),
                            "dead_keys": len(checks["key_coverage"].get("dead_keys") or []),
                            "scale_mismatches": len(checks["price_scale"].get("scale_mismatches") or []),
                            }, ensure_ascii=False) + "\n")
    return out
