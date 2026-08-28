# -*- coding: utf-8 -*-
"""measurement_audit — 측정 오염 자동 검출 6종 (2026-08-05 신설 · 08-06~07 확장).

배경: 2026-08-04~05 감사에서 확정 결함이 다수 나왔는데, **전부 "조용히 죽어서 아무도
몰랐던" 종류**였다 — 하트비트 30일, event_study 38일, 유령 매도 3주, 통화 오류(당시 진행 중).
사람이 478개 모듈을 훑는 방식은 끝나지 않고, 코드가 바뀌면 다시 0부터다.

그래서 그날 결함을 실제로 잡아낸 **세 가지 대조**를 상시 검사로 고정한다. 셋 다 그날
검출력이 실증됐다(각 검사 docstring 에 실측 인용).

  A. 원장 정합  — 보유 재생으로 유령 매도·수량 불일치 검출 → 유령 58건을 잡은 방법
  B. 키 커버리지 — 채점 모듈이 읽는 stock 키를 실 레코드와 대조 → 죽은 경로 9종을 잡은 방법
  C. 단위 스케일 — 같은 종목의 가격 계열 필드 비율 이상 검출 → 통화 오류를 잡은 방법

2026-08-06 확장 — 8/6 하루에 잡은 결함 3종이 **A~C 로는 전부 안 잡히는 부류**였다.
공통점은 "규칙이 국면을 가르지 못한다"였고, 손으로 찾은 방법이 매번 같아서 코드로 옮겼다.

  D. 규칙 판별력  — 매크로 등급 규칙의 발동률. 상시(≥90%)·미발동(≤5%) 검출 + cap 0일 집계
  E. 플래그 커버리지 — red_flag 규칙 중 실제로 발동한 적 없는 것 검출 (코드 정의 vs 관측)
  F. 입력 상수성  — 규칙 입력이 전 종목 **동일값**인가. 존재하는데 다 같으면 측정이 아니라
     상위 공백이다. 8/7 실측: credit_rate·current_ratio 가 19/19 전부 0.0

그리고 **baseline** 을 도입했다. 8/6 에 price_scale 이 통화 혼재를 매일 신고하고 있었는데
아무도 읽지 않은 것이 드러났다 — 매일 FAIL 인 경보는 경보가 아니다. 알려진 미해결분은
KNOWN 으로 내리고, **초과분만 FAIL** 로 올린다. 즉 FAIL = 오늘 새로 생겼다는 뜻이다.

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

# 검사 D — 발동률 판정 대역.
# 🚨 90 인 이유(실측 근거): 최초 구현에서 95 로 뒀더니 `cape_bubble` 94.3% 가 **바로 아래로
#   빠져나갔다**. 그 규칙은 임계 30 이 실측 범위(39.9~42.8) 밖이라 사실상 상수였고, 87일 내내
#   BUY 등급을 막고 있던 장본인이다. 검사가 잡으라고 만든 결함을 검사가 놓친 것이다.
#   90 = 10일 중 9일 발동 → 반대 국면 표본이 10%뿐이라 발동/미발동 비교가 성립하지 않는다.
#   85~90 은 아직 판정하지 않고 watch 로 올려 눈에는 띄게 한다(조용한 통과 금지).
_ALWAYS_ON_PCT = 90.0
_NEVER_ON_PCT = 5.0
_WATCH_PCT = 85.0

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


def audit_guard_inputs() -> Dict[str, Any]:
    """G. 가드 입력 부재 — 가드가 읽는 필드가 실제로 채워져 있는가. (2026-08-11 신설)

    실증(2026-08-11): `check_position_size` 의 포트폴리오 가드 3종이 보유에서
    `sector` / `beta` / `multi_factor.quant_factors` 를 읽는데 **셋 다 0/11 이었다.**
    execute_buy 가 저장한 적이 없다. 결과: 전 보유가 섹터 "Unknown" 으로 뭉쳐 후보 섹터
    노출이 항상 0 → 섹터 35% 상한 무발동. 베타는 전부 기본 1.0 → 상한 1.5 무발동.
    팩터 쏠림은 전부 0% → 무발동. **5/17 리셋 이후 매수 22건이 전부 무가드로 통과했고
    에러도 로그도 0 이었다.**

    A~F 로는 안 잡힌다 — 원장은 정합하고, 키 커버리지는 채점 모듈만 보고, 값이 이상한
    게 아니라 **아예 없다**. "가드가 존재한다"와 "가드가 작동한다"는 다른 명제다.
    """
    try:
        pf = _load(os.path.join(DATA_DIR, "portfolio.json"), {}) or {}
        hs = ((pf.get("vams") or {}).get("holdings")) or []
        if not hs:
            return {"ok": None, "skipped": "보유 0건"}
        specs = (
            ("sector", "섹터 35% 상한", lambda h: h.get("sector")),
            ("beta", "포트폴리오 베타 1.5 상한", lambda h: h.get("beta")),
            ("quant_factors", "팩터 쏠림 차단",
             lambda h: (h.get("multi_factor") or {}).get("quant_factors")),
        )
        dead = []
        cov = {}
        for key, guard, get in specs:
            n = sum(1 for h in hs if get(h))
            cov[key] = {"filled": n, "total": len(hs), "guard": guard}
            if n == 0:
                dead.append({"field": key, "guard": guard, "filled": 0, "total": len(hs)})
        # 게이트 컷오버 입력 생존 (2026-08-12, PR #357) — 추천 풀의 safety_pct 부착률.
        # 0 이면 신 게이트가 전원 폴백(구 55) = 컷오버가 조용히 무효화된 상태다.
        gate_cov = None
        try:
            recs = _load(os.path.join(DATA_DIR, "recommendations.json"), []) or []
            if isinstance(recs, dict):
                recs = recs.get("recommendations") or []
            scored = [r for r in recs if isinstance(r, dict) and r.get("safety_score") is not None]
            if scored:
                with_pct = sum(1 for r in scored if r.get("safety_pct") is not None)
                gate_cov = {"with_pct": with_pct, "scored": len(scored),
                            "ok": with_pct > 0}
                if with_pct == 0:
                    dead.append({"field": "safety_pct", "guard": "게이트 컷오버(하위20% 컷)",
                                 "filled": 0, "total": len(scored)})
        except Exception:  # noqa: BLE001
            pass
        return {
            "ok": not dead,
            "holdings_checked": len(hs),
            "coverage": cov,
            "gate_pct_coverage": gate_cov,
            "dead_guards": dead,
            "detail": (f"입력 전무한 가드 {len(dead)}종 — 코드에 존재하나 한 번도 발동할 수 없다: "
                       + ", ".join(f"{d['guard']}({d['field']})" for d in dead)
                       if dead else "가드 입력 정합"),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": None, "skipped": f"{type(e).__name__}: {e}"[:120]}


def audit_exit_paths() -> Dict[str, Any]:
    """H. 출구 경로 0 — 이익을 확정할 방법이 하나도 없는 보유가 있는가. (2026-08-11 신설)

    실증(2026-08-11): `trailing_active` 가 부분매도 **체결 블록 안에서만** 켜졌다.
    수량이 모자라 skip 되면 그 줄에 도달하지 않고, check_stop_loss 는 exit_targets 를
    가진 보유에 이 플래그를 요구한다 → **1주 포지션은 이익 확정 경로가 0개**였다
    (target_1·2 는 floor 로 0주, target_3 은 플래그 미활성, 기간손절은 return≤0 조건).
    출구가 −20% 손절뿐이라 100% 올라도 되돌릴 때까지 들고 있었다. 실측 6/11 이 사다리
    일부/전부 불능이었고 NEM 은 2R 을 넘겼는데도 미활성이었다.

    fix(#351) 이후에도 **분할 자체의 불가는 남는다**(고가주). 재발과 잔존을 같이 센다.
    """
    try:
        import math
        pf = _load(os.path.join(DATA_DIR, "portfolio.json"), {}) or {}
        hs = ((pf.get("vams") or {}).get("holdings")) or []
        if not hs:
            return {"ok": None, "skipped": "보유 0건"}
        no_exit, ladder_broken = [], []
        for h in hs:
            et = h.get("exit_targets") or {}
            if not et:
                continue          # 사다리 없는 보유는 highest>buy 로 트레일링이 열린다
            q = float(h.get("quantity") or 0)
            ret = float(h.get("return_pct") or 0)
            splittable = {tid: math.floor(q * float((et.get(tid) or {}).get("exit_pct") or 0) / 100)
                          for tid in ("target_1", "target_2")}
            if any(v < 1 for v in splittable.values()):
                ladder_broken.append({"name": h.get("name"), "qty": q,
                                      "splittable": splittable})
            # 이익 중인데 트레일링 미활성 + 분할 불가 = 확정 경로 0
            #   (기간손절은 return≤0 에서만 발동하므로 이익 구간의 출구가 아니다)
            if ret > 0 and not h.get("trailing_active") and all(
                    v < 1 for v in splittable.values()):
                t2 = (et.get("target_2") or {}).get("price")
                cur = float(h.get("current_price") or 0)
                no_exit.append({"name": h.get("name"), "qty": q, "return_pct": ret,
                                "past_target_2": bool(t2 and cur >= t2)})
        return {
            "ok": not no_exit,
            "holdings_checked": len(hs),
            "no_profit_exit": no_exit,
            "ladder_broken": ladder_broken,
            "detail": (f"이익 확정 경로 0인 보유 {len(no_exit)}건 — 출구가 손절뿐이다"
                       + (f" (사다리 불능 {len(ladder_broken)}건 별도)" if ladder_broken else "")
                       if no_exit else
                       f"확정 경로 정합 (사다리 불능 {len(ladder_broken)}건 — 고가주 잔존분)"),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": None, "skipped": f"{type(e).__name__}: {e}"[:120]}


def audit_as_of_staleness() -> Dict[str, Any]:
    """I. as_of 노후 — 발행물의 관측일이 수집일보다 얼마나 뒤처졌는가. (2026-08-11 신설)

    실증(2026-08-11): `bonddata._ecos_fetch_point` 가 ECOS 에 10행만 요청했다. ECOS 는
    오름차순이라 30일 창에서 돌아온 것은 **가장 오래된 10건**이고 rows[-1] 은 약
    10영업일 전 값이었다. 발행 AA- 4.576(as_of 20260727) ↔ ECOS 실제 4.476(20260810).
    국고채 커브도 같은 함수를 타서 전 만기 동반 노후(최대 12bp)였다.

    🚨 탐지가 **as_of 하나에 달려 있었다.** 회사채엔 as_of 가 있어 15일 전인 게 눈에
    걸렸고, 국고채 커브엔 as_of 자체가 없어 영구 미탐지였다. 그래서 이 검사는
    **as_of 부재도 결함으로 센다** — 없으면 노후를 구조적으로 확인할 수 없다.
    """
    try:
        from datetime import date

        def _d(v) -> Optional[date]:
            t = re.sub(r"[^0-9]", "", str(v or ""))[:8]
            try:
                return date(int(t[:4]), int(t[4:6]), int(t[6:8])) if len(t) == 8 else None
            except ValueError:
                return None

        # (파일, 축 경로, 허용 노후일) — 일별 갱신 계열만. 분기 공시는 대상 아님.
        # 🚨 경로는 **실 스키마 확인 후** 고정했다(2026-08-11). 추정 경로를 쓰면 값이
        #   멀쩡해도 영구 'missing' 을 신고해 검사 자체가 잡음이 된다.
        #   회사채 관측일의 실제 키는 `date` 다(`grades_as_of` 는 수집기 내부 이름).
        specs = [
            ("bonds.json", ("kr_corp_spreads", "date"), 5),
            ("bonds.json", ("yield_curves", "kr", "curve_as_of"), 5),
        ]
        stale, missing, absent = [], [], []
        for fname, path, limit in specs:
            doc = _load(os.path.join(DATA_DIR, fname), {}) or {}
            # 🚨 파일 부재와 'as_of 없음' 은 다른 조건이다. 전자는 이 검사의 대상이 아니라
            #   skip 이다 — 무관한 파일이 없다고 측정 감사가 FAIL 하면 경보가 잡음이 된다
            #   (기존 테스트가 이 구분 누락을 잡았다).
            if not doc:
                absent.append(f"{fname}:부재")
                continue
            node: Any = doc
            for k in path[:-1]:
                node = (node or {}).get(k) if isinstance(node, dict) else None
            val = (node or {}).get(path[-1]) if isinstance(node, dict) else None
            axis = f"{fname}:{'.'.join(path)}"
            if not val:
                missing.append(axis)
                continue
            obs = _d(val)
            coll = _d((doc.get("updated_at") or doc.get("collected_at")))
            if not obs or not coll:
                missing.append(axis)
                continue
            lag = (coll - obs).days
            if lag > limit:
                stale.append({"axis": axis, "as_of": str(obs), "collected": str(coll),
                              "lag_days": lag, "limit": limit})
        bad = stale or missing
        if len(absent) == len(specs):
            return {"ok": None, "skipped": f"대상 파일 부재: {','.join(absent)}"[:120]}
        return {
            "ok": not bad,
            "axes_checked": len(specs) - len(absent),
            "stale_axes": stale,
            "missing_as_of": missing,
            "absent_sources": absent,
            "detail": (f"노후 {len(stale)}축 · as_of 부재 {len(missing)}축 — "
                       "as_of 가 없으면 노후를 구조적으로 확인할 수 없다"
                       if bad else "관측일 정합"),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": None, "skipped": f"{type(e).__name__}: {e}"[:120]}


def audit_rule_discrimination() -> Dict[str, Any]:
    """검사 D — 규칙이 국면을 **가르고 있는지** 발동률로 검증 (2026-08-06 신설).

    배경: 8/6 하루에 같은 부류 결함을 세 번 잡았는데 **셋 다 A~C 검사가 못 잡는 종류**였다.
      · 금리 방패 임계 4.50% = 실측 분포 중앙값 4.48% → 분포 한가운데라 판별력 0(AUC→0.5)
      · CAPE 임계 30 = 실측 범위 39.9~42.8 **밖** → 조건부 규칙이 아니라 상수. 87일 내내 발동
      · 결과: 등급 cap 이 0개인 날 = 0/87. BUY 등급이 구조적으로 영구 0
    셋 다 손으로 찾았고 방법이 매번 같았다 — **발동률을 히스토리로 재고 임계를 분포와 대조**.
    그 방법을 코드로 옮긴다.

    판정: 발동률 ≥95% 또는 ≤5% = 국면을 구분하지 못함 = 정보량 0.
      상시 발동은 "항상 방어 중"처럼 보이지만 실제로는 **규칙이 없는 것과 같다** —
      켜지고 꺼지지 않으면 그 규칙이 옳은지 검증할 표본 자체가 생기지 않는다.

    🚨 판정만 한다. 임계를 고치지 않는다(RULE 7 — 조정은 사전등록 대상).
    """
    try:
        import glob as _glob
        files = sorted(_glob.glob(os.path.join(DATA_DIR, "history", "20??-??-??.json")))
        if len(files) < 30:
            return {"ok": None, "skipped": f"히스토리 {len(files)}일 < 30 — 발동률 판정 보류"}

        fired: Dict[str, int] = {}
        capped: Dict[str, int] = {}
        no_cap_days = 0
        n = 0
        for p in files:
            snap = _load(p, None)
            if not isinstance(snap, dict):
                continue
            ov = (snap.get("verity_brain") or {}).get("macro_override")
            if isinstance(ov, list):
                ov = ov[0] if ov else None
            if not isinstance(ov, dict):
                continue
            n += 1
            sigs = [{"mode": ov.get("mode"), "max_grade": ov.get("max_grade")}]
            sigs += [s for s in (ov.get("secondary_signals") or []) if isinstance(s, dict)]
            day_caps = 0
            for s in sigs:
                m = s.get("mode")
                if not m:
                    continue
                fired[m] = fired.get(m, 0) + 1
                if s.get("max_grade") in ("WATCH", "CAUTION", "AVOID"):
                    capped[m] = capped.get(m, 0) + 1
                    day_caps += 1
            if day_caps == 0:
                no_cap_days += 1
        if not n:
            return {"ok": None, "skipped": "스냅샷에 macro_override 없음"}

        degenerate: List[Dict[str, Any]] = []
        watch: List[Dict[str, Any]] = []
        for m, c in sorted(fired.items(), key=lambda kv: -kv[1]):
            rate = round(c / n * 100, 1)
            if not capped.get(m):
                continue                      # 등급에 영향 없는 관측 규칙은 대상 아님
            if rate >= _ALWAYS_ON_PCT or rate <= _NEVER_ON_PCT:
                degenerate.append({
                    "rule": m, "fired_days": c, "activation_pct": rate,
                    "verdict": ("상시 발동 — 국면 구분 불가(정보량 0)" if rate >= _ALWAYS_ON_PCT
                                else "거의 미발동 — 표본 부족으로 검증 불가"),
                })
            elif rate >= _WATCH_PCT:
                watch.append({"rule": m, "fired_days": c, "activation_pct": rate,
                              "verdict": "경계 — 반대 국면 표본이 얇다"})

        return {
            "ok": not degenerate and no_cap_days > 0,
            "snapshots": n,
            "cap_rules_checked": len(capped),
            "degenerate_rules": degenerate,
            "watch_rules": watch,
            "bands": {"always_on_pct": _ALWAYS_ON_PCT, "never_on_pct": _NEVER_ON_PCT,
                      "watch_pct": _WATCH_PCT},
            "days_without_any_cap": no_cap_days,
            "days_without_any_cap_pct": round(no_cap_days / n * 100, 1),
            "detail": (
                (f"상시/미발동 등급 규칙 {len(degenerate)}종 — " +
                 ", ".join(f"{d['rule']}({d['activation_pct']}%)" for d in degenerate) + ". ")
                if degenerate else "") +
            (f"🚨 등급 cap 이 0개인 날 = 0/{n}일 — 최상위 등급이 구조적으로 불가능하다"
             if no_cap_days == 0 else f"cap 없는 날 {no_cap_days}/{n}일"),
            "note": "임계 조정은 사전등록 대상(RULE 7). 본 검사는 판정만 한다.",
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": None, "skipped": f"{type(e).__name__}: {e}"[:120]}


# ── 알려진 미해결 항목 baseline ──────────────────────────────────────
# 🚨 2026-08-06 — 매일 FAIL 이면 아무도 읽지 않는다. 실제로 그렇게 됐다: price_scale 이
#   통화 혼재 3건을 매일 신고하고 있었는데 8/6 까지 아무도 보지 않았다(영구 FAIL 에 묻힘).
#   경보가 의미를 가지려면 **FAIL = 새로 생겼다** 여야 한다. 알려진 미해결분은 여기에
#   고정하고 status 를 KNOWN 으로 내린다. 값이 커지면 즉시 FAIL 로 복귀한다.
#   해소 시 이 baseline 을 낮추는 것이 완료 조건이다(태스크 #19/#20).
_KNOWN_BASELINE = {
    # 8/13 cross-run stale portfolio 로 티쓰리 중복 청산 1건이 추가됐다. 원인은
    # engine 의 ledger 대조 fail-closed 가드로 차단하고, 감사 원문은 보존한다.
    "ledger_integrity": {"phantom_sells": 59},      # 8/28 확인 누적 과거분. 초과 = 재발
    "key_coverage": {"dead_keys": 10},              # 태스크 #20
    # 🚨 2026-08-07 — 3 → 0 하향. 통화 마이그레이션(#300) 적용 후 실 cron 에서 불일치
    #   0건 확인(price_scale ok=True). baseline 을 낮추는 것이 해소의 정의다 —
    #   내려두지 않으면 재발해도 KNOWN 으로 묻힌다.
    "price_scale": {"scale_mismatches": 0},
    # 검사 D — 8/6 에 제거한 cape_bubble(93.1%)이 87일 히스토리 창에서 빠질 때까지
    #   degenerate 1종 + cap 0일이 남는다. 그동안 매일 FAIL·알림이 가면 "알림 0건이 정상"
    #   원칙이 깨진다. 현 상태를 기준선으로 두고 **늘어날 때만** 알린다.
    #   창에서 빠지면 자동으로 0 이 되므로 그때 이 항목을 제거한다.
    "rule_discrimination": {"degenerate_rules": 2},
    # 검사 E — 미발동 red_flag 규칙. 배선 결함과 희소 사건이 섞여 있어 전수 분류 전까지
    # 기준선으로 둔다. 늘어나면(=규칙이 새로 죽으면) 즉시 FAIL.
    "flag_coverage": {"never_fired": 13},
    # 검사 F — 상위 API 가 빈 값을 0 으로 주는 입력 2종(credit_rate·current_ratio).
    #   우리가 고칠 수 없다(KIS 응답). 늘어나면 = 다른 입력도 죽었다는 뜻이므로 FAIL.
    "input_constancy": {"constant_inputs": 2},
    # 검사 H — 고가주는 포지션 상한 안에서 3단 분할이 성립하지 않는다(Alphabet 4주 =
    #   2,022,247원 > max_per_stock 200만). 미해결로 기록됐다(PREREG_SMALL_QTY_EXIT §2-4).
    #   이익 확정 경로 0(no_profit_exit)은 baseline 0 — 하나라도 나오면 신규 발생이다.
    "exit_paths": {"no_profit_exit": 0},
}


def _exceeds_baseline(name: str, chk: Dict[str, Any]) -> Optional[bool]:
    """알려진 baseline 초과 여부. True=신규 발생, False=알려진 범위, None=판정 불가."""
    base = _KNOWN_BASELINE.get(name)
    if not base or chk.get("ok") is not False:
        return None
    for field, limit in base.items():
        v = chk.get(field)
        if isinstance(v, list):
            v = len(v)
        if not isinstance(v, (int, float)):
            return None
        if v > limit:
            return True
    return False


def run(root: str = ".") -> Dict[str, Any]:
    checks = {
        "ledger_integrity": audit_ledger(),
        "key_coverage": audit_key_coverage(root),
        "price_scale": audit_price_scale(),
        "rule_discrimination": audit_rule_discrimination(),
        "flag_coverage": audit_flag_coverage(root),
        "input_constancy": audit_input_constancy(),
        # 2026-08-11 신설 — 그날 손으로 찾은 결함 3종의 검출 방법을 상시화
        "guard_inputs": audit_guard_inputs(),
        "exit_paths": audit_exit_paths(),
        "as_of_staleness": audit_as_of_staleness(),
    }
    # baseline 대조 — 알려진 미해결분은 KNOWN, 초과분만 FAIL
    known: List[str] = []
    for k, v in checks.items():
        ex = _exceeds_baseline(k, v)
        if ex is False:
            v["baseline"] = _KNOWN_BASELINE.get(k)
            v["status"] = "KNOWN"
            known.append(k)
        elif ex is True:
            v["status"] = "REGRESSION"

    fails = [k for k, v in checks.items() if v.get("ok") is False and k not in known]
    skips = [k for k, v in checks.items() if v.get("ok") is None]
    out = {
        "as_of": now_kst().isoformat(timespec="seconds"),
        "version": "measurement_audit_v4",
        "status": ("FAIL" if fails else
                   ("KNOWN" if known else ("PARTIAL" if skips else "OK"))),
        "failing": fails,
        "known_unresolved": known,
        "skipped": skips,
        "checks": checks,
        "note": ("측정 오염 자동 검출 — 8/5 감사가 잡아낸 3대조 + 8/6 신설 규칙 판별력 검사. "
                 "점수 입력 0(관측 전용). status FAIL = **알려진 baseline 초과 = 신규 발생**. "
                 "KNOWN = 미해결분이 알려진 범위 안(태스크 #19/#20). 매일 FAIL 이면 아무도 "
                 "읽지 않는다는 8/6 학습 반영."),
    }
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT_PATH)
    os.makedirs(os.path.dirname(TRAIL_PATH), exist_ok=True)
    with open(TRAIL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"as_of": out["as_of"], "status": out["status"],
                            "failing": out["failing"],
                            "phantom_sells": checks["ledger_integrity"].get("phantom_sells"),
                            "dead_keys": len(checks["key_coverage"].get("dead_keys") or []),
                            "scale_mismatches": len(checks["price_scale"].get("scale_mismatches") or []),
                            "degenerate_rules": len(
                                checks["rule_discrimination"].get("degenerate_rules") or []),
                            "days_without_cap_pct":
                                checks["rule_discrimination"].get("days_without_any_cap_pct"),
                            "flags_never_fired": len(
                                checks["flag_coverage"].get("never_fired") or []),
                            "constant_inputs": len(
                                checks["input_constancy"].get("constant_inputs") or []),
                            "dead_guards": len(checks["guard_inputs"].get("dead_guards") or []),
                            "no_profit_exit": len(checks["exit_paths"].get("no_profit_exit") or []),
                            "stale_axes": len(checks["as_of_staleness"].get("stale_axes") or []),
                            }, ensure_ascii=False) + "\n")
    return out


def _flag_rule_prefixes(root: str = ".") -> List[str]:
    """red_flags.py 의 `_make_flag(f"...")` 리터럴에서 규칙 식별 접두어를 추출.

    코드가 실제로 정의한 규칙 목록 = 이 접두어 집합. 관측과 대조해 죽은 규칙을 찾는다.
    """
    path = os.path.join(root, "api", "intelligence", "factors", "red_flags.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError:
        return []
    out: List[str] = []
    for lit in re.findall(r'_make_flag\(\s*f?"([^"]{4,80})', src):
        head = lit.split("{")[0].strip()
        if len(head) >= 4:
            out.append(head)
    # 중복 제거 + 긴 것 우선 (짧은 접두어가 긴 규칙을 삼키는 것 방지)
    return sorted(set(out), key=len, reverse=True)


def audit_flag_coverage(root: str = ".") -> Dict[str, Any]:
    """검사 E — red_flag 규칙이 **실제로 발동하는가** (2026-08-06 신설).

    검사 D 가 매크로 등급 규칙을 봤다면 이건 종목 레벨 red_flag 층이다.
    코드에 정의된 규칙과 히스토리에서 실제 발동한 규칙을 대조한다.

      · 0회 발동  = 죽은 규칙 — 입력이 항상 결손이거나 임계가 도달 불가
      · 상시 발동 = 판별력 없음 (검사 D 와 같은 논리)

    실측(2026-08-06): 코드 31곳 정의 vs 관측 21종 발동 — 10종 안팎이 죽어 있다.
    태스크 #20(죽은 채점 키 10종)과 같은 부류가 red_flag 층에도 있다는 뜻이다.
    """
    try:
        import glob as _glob
        prefixes = _flag_rule_prefixes(root)
        if not prefixes:
            return {"ok": None, "skipped": "red_flags.py 파싱 실패"}

        files = sorted(_glob.glob(os.path.join(DATA_DIR, "history", "20??-??-??.json")))
        if len(files) < 30:
            return {"ok": None, "skipped": f"히스토리 {len(files)}일 < 30 — 판정 보류"}

        hits: Dict[str, int] = {p: 0 for p in prefixes}
        rows = 0
        for p in files:
            snap = _load(p, None)
            if not isinstance(snap, dict):
                continue
            for rec in (snap.get("recommendations") or []):
                rf = ((rec.get("verity_brain") or {}).get("red_flags")) or {}
                if not rf:
                    continue
                rows += 1
                for t in list(rf.get("auto_avoid") or []) + list(rf.get("downgrade") or []):
                    s = str(t)
                    # 긴 접두어 우선 매칭 — 하나만 귀속시킨다(짧은 규칙의 오탐 방지)
                    for pref in prefixes:
                        if s.startswith(pref):
                            hits[pref] += 1
                            break
        if not rows:
            return {"ok": None, "skipped": "히스토리에 red_flags 기록 없음"}

        never = [{"rule": p, "fired": 0} for p in prefixes if hits[p] == 0]
        always = [{"rule": p, "fired": hits[p], "pct": round(hits[p] / rows * 100, 1)}
                  for p in prefixes if hits[p] and hits[p] / rows * 100 >= _ALWAYS_ON_PCT]
        return {
            "ok": not never and not always,
            "rules_defined": len(prefixes),
            "rules_fired": sum(1 for p in prefixes if hits[p]),
            "stock_days": rows,
            "never_fired": never,
            "always_fired": always,
            "detail": (f"정의 {len(prefixes)}종 중 발동 {sum(1 for p in prefixes if hits[p])}종 · "
                       f"미발동 {len(never)}종"
                       + (f" · 상시 발동 {len(always)}종" if always else "")
                       + ". 🚨 미발동 ≠ 고장 — 입력 결손(배선 문제)인지 원래 드문 사건인지 "
                         "확인해야 한다. 검사 B(죽은 키)와 교차 대조할 것."),
            "note": ("미발동 규칙은 **확인 대상**이지 판정이 아니다. 계속기업 불확실성·"
                     "불성실공시 같은 규칙은 107일 0건이 정상일 수 있다. 반면 입력 필드가 "
                     "항상 결손이면 배선 결함이다. 임계 조정은 사전등록 대상(RULE 7)."),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": None, "skipped": f"{type(e).__name__}: {e}"[:120]}



# 검사 F — 입력 필드 상수값 대역. 전 종목 동일값(특히 0)은 데이터가 아니라 **상위 공백**이다.
_CONST_MIN_RECORDS = 10     # 이보다 적으면 우연히 같을 수 있다

# 검사 F 대상 — 규칙 판정에 실제로 쓰이는 중첩 입력. (라벨, 경로)
_RULE_INPUTS = [
    ("kis_credit_balance.credit_rate", ("kis_credit_balance", "credit_rate")),
    ("kis_financial_ratio.current_ratio", ("kis_financial_ratio", "current_ratio")),
    ("kis_financial_ratio.roe", ("kis_financial_ratio", "roe")),
    ("kis_financial_ratio.debt_ratio", ("kis_financial_ratio", "debt_ratio")),
    ("kis_short_sale.avg_short_ratio_5d", ("kis_short_sale", "avg_short_ratio_5d")),
    ("short_interest.short_pct", ("short_interest", "short_pct")),
    ("options_flow.put_call_ratio", ("options_flow", "put_call_ratio")),
    ("options_flow.avg_iv", ("options_flow", "avg_iv")),
    ("insider_sentiment.mspr", ("insider_sentiment", "mspr")),
]


def _dig(rec: Dict[str, Any], path: tuple) -> Any:
    cur: Any = rec
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def audit_input_constancy() -> Dict[str, Any]:
    """검사 F — 규칙 입력이 전 종목 **동일값**인가 (2026-08-07 신설).

    배경: 8/7 C-1 감사에서 `credit_rate` 와 `current_ratio` 가 19/19 종목 **전부 0.0** 인
    것이 드러났다. 존재하긴 하는데 전부 같은 값이면 그건 측정이 아니라 상위 공백이다.
    그리고 falsy 라서 `x or 기본값` 류 코드에서 결측으로 뭉개져 더 안 보인다 —
    같은 날 hold_pnl 에서 보유 0일이 None 으로 무너진 것과 동일 함정.

    판정: 값이 존재하는 레코드가 10건 이상인데 **고유값이 1개** = 상위 공백 의심.
      · 그 값이 0 이면 특히 강한 신호(대부분의 API 가 빈 값을 0 으로 준다).
      · 결측(None)은 여기서 세지 않는다 — 검사 B 소관이다.

    🚨 판정만 한다. 임계·규칙을 고치지 않는다(RULE 7).
    """
    try:
        recs = _load(os.path.join(DATA_DIR, "recommendations.json"), [])
        if not recs:
            return {"ok": None, "skipped": "recommendations.json 없음"}
        const, varying = [], 0
        for label, path in _RULE_INPUTS:
            vals = [_dig(r, path) for r in recs]
            present = [v for v in vals if isinstance(v, (int, float))]
            if len(present) < _CONST_MIN_RECORDS:
                continue                       # 표본 부족 — 판정 보류
            uniq = set(present)
            if len(uniq) == 1:
                only = next(iter(uniq))
                const.append({"input": label, "n_present": len(present),
                              "constant_value": only,
                              "severity": "high" if only == 0 else "medium"})
            else:
                varying += 1
        return {
            "ok": not const,
            "inputs_checked": len(_RULE_INPUTS),
            "varying": varying,
            "constant_inputs": const,
            "detail": (f"전 종목 동일값 입력 {len(const)}종 — " +
                       ", ".join(f"{c['input']}={c['constant_value']}" for c in const) +
                       ". 측정이 아니라 상위 공백 의심(규칙이 영원히 발동 못 한다)."
                       if const else "입력 값 분산 정상"),
            "note": "결측(None)은 검사 B 소관. 여기는 '존재하는데 전부 같은 값'만 본다.",
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": None, "skipped": f"{type(e).__name__}: {e}"[:120]}
