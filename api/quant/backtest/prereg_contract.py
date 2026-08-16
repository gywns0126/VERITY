# -*- coding: utf-8 -*-
"""prereg_contract — 사전등록 산출물이 **스스로 신고해야 하는 것**.

2026-08-15 신설. 하루에 같은 실패가 세 번 났고 원인이 하나였다 —
**한 세션이 아는 것이 다음 세션으로 넘어가지 않는다.**

```
252 게이트 폐기   대화에만 존재      → 다음 세션이 죽은 전제를 하루 종일 인용
검정력 계산       8/9~8/10 하다 소멸  → 3일 만에 규율 퇴화, 아무도 눈치 못 챔
C3 ≠ 운영 점수    코드에만 암묵       → 운영과 무관한 점수를 6개월치라 믿고 검정
```

기억·습관·체크리스트로는 안 막힌다. **산출물이 자기 입으로 말하게** 해야 한다
([[feedback_verify_by_load_bearing_not_surprise]] 의 "숨기면 결국 안 돌린다" 와 같은 원리).

이 모듈은 두 가지를 강제한다:
  ① `score_system`  — 어떤 점수를 쟀는지 + **그게 운영에 쓰이는 것인지**
  ② `min_detectable` — |t|=3 을 만드는 효과 크기. 이게 현실 범위 밖이면 그 등록은 무의미하다

`tests/test_prereg_artifact_contract.py` 가 신규 산출물에 대해 이 계약을 검사한다.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Sequence

# 🚨 운영이 실제로 쓰는 점수 (2026-08-15 grep 실측)
#    · safety_pct(안심점수 6축) → VAMS 게이트 `safety_pct >= GATE_BOTTOM_PCT` (8/12 컷오버)
#    · fact_score / sentiment_score / VCI → Brain 판단·사이트 노출
#    C3(ep bp dy opm roa vol fs8 illiq nearhigh) 는 **백테스트 전용**이며 운영 경로에 없다.
OPERATIONAL_SCORES = frozenset({"safety_pct", "fact_score", "sentiment_score", "vci"})
BACKTEST_ONLY_SCORES = frozenset({"C3", "c3", "safety_full", "formula_rebuild"})


def declare_score_system(name: str, axes: Sequence[str], note: str = "") -> Dict[str, Any]:
    """이 등록이 어떤 점수를 쟀는지, 그게 운영에 쓰이는지 산출물에 명시한다.

    🚨 `is_operational=False` 면 결과를 운영 판단으로 옮겨 읽으면 안 된다.
       2026-08-13~15 등록 9건이 전부 C3(백테스트 전용)를 쟀는데 그 사실이 어디에도
       적혀 있지 않아, 다음 세션이 "우리 점수는 검증됐다" 로 오독할 수 있었다.
    """
    op = name in OPERATIONAL_SCORES
    d: Dict[str, Any] = {
        "name": name,
        "axes": list(axes),
        "is_operational": op,
        "note": note or ("운영 경로에서 사용" if op
                         else "🚨 백테스트 전용 — 운영은 이 점수를 쓰지 않는다"),
    }
    if not op:
        d["do_not_read_as"] = ("이 결과를 '우리 시스템이 검증됐다' 로 읽지 말 것. "
                               f"운영 점수는 {sorted(OPERATIONAL_SCORES)} 이다")
    return d


def detectable_floor(mean_pct: Optional[float], t: Optional[float],
                     t_target: float = 3.0) -> Optional[float]:
    """|t| = t_target 을 만드는 효과 크기. SE = |mean/t| 에서 역산."""
    if mean_pct is None or not t:
        return None
    return round(abs(mean_pct / t) * t_target, 4)


# ── 🚨 도메인 상한표 (2026-08-16 확정, PM 승인) ─────────────────────────────
# 왜 상수인가: 옛 `plausible_max` 는 **호출자 인자**였다. 통과하고 싶으면 상한을 올리면
# 그만이라 검출하한 관문 전체가 자유 변수 하나에 걸려 있었다. 등록자가 고르지 못하게 한다.
#
# 값의 근거 = 문헌 추정이 아니라 **우리 자체 302 IC 셀 + 종목-월 201,169 관측**
# (docs/GATE_DESIGN_2026_08_16.md §5-B·§5-C):
#   · IC 0.10  = 확증 판정 12셀의 검출하한 최대 0.0944 바로 위(진짜 양성 미차단)
#                + 확증 0 인 트랙(겹침감사 60셀) 97% 반려
#   · IC 경고 0.05 = 확증 중앙 하한 0.0365 의 약 1.4배
#   · 수익률 1.5%/월 = #368·#371(판정 불가) 반려 / #367·#370(판정력 있음) 통과로 보정.
#                     코너 N=1,274 의 검출하한 1.51%p 와도 일치
# 표에 없는 도메인을 쓰려면 상한을 **사전에** 등록하고 근거를 적는다 (PM 승인 대상).
DOMAIN_CEILINGS: Dict[str, Dict[str, float]] = {
    "ic":      {"reject": 0.10, "warn": 0.05},    # 횡단면 IC (상관계수 단위)
    "return":  {"reject": 1.5, "warn": 0.9},      # 월간 수익 차 (%/월)
    "winrate": {"reject": 10.0, "warn": 5.0},     # 승률 차 (%p)
}

# 관측 독립성 등급 (Perplexity Q1 채택 + 자체 두 트랙 실측 정합)
K_REJECT, K_CONFIRMATORY = 3, 10

PURPOSES = frozenset({"hypothesis_test", "execution_check"})


def declare_observations(k_independent: Optional[int], purpose: str,
                         horizon: str = "", note: str = "") -> Dict[str, Any]:
    """독립 관측 수와 **이 등록의 목적**을 신고한다 (§7-3 (2)·(7) 기계화).

    purpose:
      hypothesis_test — 가설 검정. k 관문과 검출하한 관문을 모두 받는다.
      execution_check — 집행 현실성·비용·위험 확인. 관문 면제, 대신 "검정 아님" 라벨 강제.
                        (2026-08 등록 5건이 포트폴리오-월 검정으로 드리프트한 자리)
    """
    if purpose not in PURPOSES:
        raise ValueError(f"purpose 는 {sorted(PURPOSES)} 중 하나여야 한다: {purpose!r}")
    d: Dict[str, Any] = {"purpose": purpose, "k_independent": k_independent,
                         "horizon": horizon, "note": note}
    if purpose == "execution_check":
        d["evidence_class"] = "not_a_test"
        d["do_not_read_as"] = "집행 확인이다. 가설 검정 결과로 인용하지 말 것"
        return d
    if k_independent is None:
        d["evidence_class"] = "unestimable"
        d["verdict"] = "🚨 반려 — 독립 관측 수 미신고"
    elif k_independent < K_REJECT:
        d["evidence_class"] = "unestimable"
        d["verdict"] = f"🚨 반려 — k={k_independent} < {K_REJECT} (설계상 판정 불가)"
    elif k_independent < K_CONFIRMATORY:
        d["evidence_class"] = "exploratory"
        d["verdict"] = f"탐색적 — k={k_independent} < {K_CONFIRMATORY}. 임계를 넘어도 확증 아님"
    else:
        d["evidence_class"] = "confirmatory_eligible"
        d["verdict"] = f"확증 가능 — k={k_independent}"
    return d


def declare_power(results: Dict[str, Any], domain: Optional[str] = None,
                  unit: str = "%/월", plausible_max: Optional[float] = None) -> Dict[str, Any]:
    """원장 전체의 검정력을 신고한다. **판정력 없는 등록은 등록 자체가 무의미하다.**

    Args:
        results: {검정명: {"mean_pct":…, "nw": {"t":…}}} 형태
        domain: DOMAIN_CEILINGS 의 키 ("ic" | "return" | "winrate"). 상한을 여기서 읽는다.
        plausible_max: 표에 없는 도메인용 예외. 쓰면 `ceiling_source="ad_hoc"` 로 표시돼
                       계약 검사에서 근거 문서를 요구한다.
    """
    if domain is not None:
        if domain not in DOMAIN_CEILINGS:
            raise ValueError(f"미등록 도메인 {domain!r} — DOMAIN_CEILINGS 에 추가하고 근거를 적을 것")
        ceil = DOMAIN_CEILINGS[domain]["reject"]
        warn_at = DOMAIN_CEILINGS[domain]["warn"]
        source = f"DOMAIN_CEILINGS[{domain}]"
    elif plausible_max is not None:
        ceil, warn_at, source = plausible_max, plausible_max / 2, "ad_hoc"
    else:
        raise ValueError("domain 또는 plausible_max 중 하나는 필요하다")
    floors: Dict[str, Optional[float]] = {}
    missing_se: list = []
    for k, v in (results or {}).items():
        t = (v.get("nw") or {}).get("t") if isinstance(v, dict) else None
        m = v.get("mean_pct") if isinstance(v, dict) else None
        if m is not None and not t:
            missing_se.append(k)          # 🚨 효과만 있고 t/SE 가 없다 = 판정 불가 상태
        floors[k] = detectable_floor(m, t)
    vals = [f for f in floors.values() if f is not None]
    med = sorted(vals)[len(vals) // 2] if vals else None
    incapable = [k for k, f in floors.items() if f is not None and f > ceil]
    warned = [k for k, f in floors.items() if f is not None and warn_at < f <= ceil]
    if missing_se:
        verdict = ("🚨 판정 불가 — 효과 크기만 있고 SE/t 가 없다. "
                   f"신고 누락 {len(missing_se)}건: {missing_se[:5]}")
    elif med is not None and med > ceil:
        verdict = ("🚨 판정 불가 — 검출하한이 현실적 효과 범위를 넘는다. "
                   "이 등록의 '무유의' 는 세상에 대한 정보가 아니라 자의 눈금 문제다")
    elif incapable:
        verdict = "경계 — 일부 검정만 판정력이 있다"
    elif warned:
        verdict = "판정력 있음 (경고 구간 포함)"
    else:
        verdict = "판정력 있음"
    return {
        "unit": unit,
        "t_target": 3.0,
        "domain": domain,
        "ceiling_source": source,
        "plausible_max": ceil,
        "warn_at": warn_at,
        "per_test_floor": floors,
        "median_floor": med,
        "incapable_tests": incapable,
        "warned_tests": warned,
        "missing_se_tests": missing_se,
        "verdict": verdict,
    }


def contract(score: Dict[str, Any], power: Dict[str, Any],
             observations: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """산출물 `_meta` 에 넣을 계약 블록.

    v2 (2026-08-16) = `observations` 추가. 없으면 계약 검사에서 반려된다
    (§7-3 (2)·(7) — 목적과 독립 관측 수를 안 적으면 판정할 수 없다).
    """
    out: Dict[str, Any] = {"score_system": score, "min_detectable": power,
                           "contract_version": "2026-08-16"}
    if observations is not None:
        out["observations"] = observations
    return out


def contract_violations(meta: Dict[str, Any]) -> list:
    """산출물 `_meta` 를 읽어 계약 위반 목록을 낸다 (테스트·CI 공용 단일 판정기).

    🚨 옛 검사는 **필드 존재**만 봤다. 등록서가 스스로 "🚨 판정 불가" 라고 적어도
       통과했다 — 신고는 강제하고 반려는 강제하지 않는 게이트였다. 여기서 닫는다.
    """
    v: list = []
    if "score_system" not in meta:
        v.append("_meta.score_system 없음 — 어떤 점수를 쟀는지, 운영에 쓰이는지 신고할 것")
    p = meta.get("min_detectable")
    if not isinstance(p, dict):
        v.append("_meta.min_detectable 없음 — |t|=3 검출하한 신고할 것")
    else:
        if str(p.get("verdict", "")).startswith("🚨"):
            v.append(f"검출하한 관문 반려 — {p.get('verdict')}")
        if p.get("ceiling_source") == "ad_hoc" and not p.get("ceiling_rationale"):
            v.append("상한을 표 밖에서 썼다 — ceiling_rationale 에 근거 문서를 적을 것")
    o = meta.get("observations")
    if not isinstance(o, dict):
        v.append("_meta.observations 없음 — purpose·k_independent 신고할 것 (§7-3 (2)(7))")
    elif str(o.get("verdict", "")).startswith("🚨"):
        v.append(f"독립 관측 관문 반려 — {o.get('verdict')}")
    return v
