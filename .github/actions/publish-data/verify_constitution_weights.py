#!/usr/bin/env python3
"""발행 전 게이트 — 헌법 `fact_score.weights` 불변식 검사. 위반 = **발행 정지**.

## 왜 발행을 막나 (R2, 2026-08-18)

`PREREG_BASELINE_V1_LITERATURE` §7-C 의 되돌림 조건 R2 를 "되돌릴지 판단" 이 아니라
**발행 정지**로 격상했다. 가중 합이 1.0 이 아니면 그 점수는 되돌림을 검토할 대상이 아니라
**애초에 의미가 없다.** 의미 없는 점수를 내보낸 뒤에 되돌리는 것은 순서가 틀렸다.

🚨 그리고 이 결함은 **혼자서는 절대 안 보인다.** `api/intelligence/factors/fact.py:523` 이
    if w_sum > 0 and abs(w_sum - 1.0) > 0.01:
        for k in list(w.keys()): w[k] = w[k] / w_sum
로 **조용히 재정규화**한다. 그 정규화 자체는 정당한 안전장치지만(2026-05-16 P0 fix,
IC=DEAD 시 합이 0.6 으로 떨어져 brain max 46 이던 결함), 부작용으로 **헌법이 깨져도
점수가 그럴듯하게 나온다.** 런타임은 자기를 고치고, 아무도 원인을 못 본다.
그래서 검사를 런타임이 아니라 **원본(verity_constitution.json)** 에 건다.

## 검사 내용

1. `fact_score.weights` 합 = 1.0 (±1e-6)
2. 키 집합 = 베이스라인 v1.0 문헌 4축 정확히 일치
3. 개별 가중이 음수·0 이 아님

2번이 걸리면 산식이 바뀐 것이다. **그건 RULE 7 사전등록 + PM 승인 대상**이고, 승인된
변경이라면 이 파일의 `EXPECTED_AXES` 도 같은 커밋에서 갱신되어야 한다 — 가드를 손대야
바꿀 수 있게 하는 것이 의도다(조용한 drift 차단).
"""
from __future__ import annotations

import json
import sys

# 베이스라인 v1.0 (PREREG_BASELINE_V1_LITERATURE_2026_08_16, PM 승인)
# 🚨 변경 = RULE 7 사전등록 + PM 승인 후에만. 같은 커밋에서 여기도 갱신할 것.
EXPECTED_AXES = {"graham_value", "canslim_growth", "quant_quality", "quant_volatility"}
TOLERANCE = 1e-6


def main(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as f:
            const = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"🚨 발행 정지 — 헌법을 읽을 수 없다: {e}", file=sys.stderr)
        return 1

    w = (const.get("fact_score") or {}).get("weights")
    if not isinstance(w, dict) or not w:
        print("🚨 발행 정지 — fact_score.weights 가 없거나 비었다", file=sys.stderr)
        return 1

    fails = []
    total = sum(v for v in w.values() if isinstance(v, (int, float)))
    if abs(total - 1.0) > TOLERANCE:
        fails.append(f"가중 합 {total!r} ≠ 1.0 (허용 ±{TOLERANCE})")

    keys = set(w)
    if keys != EXPECTED_AXES:
        missing, extra = EXPECTED_AXES - keys, keys - EXPECTED_AXES
        fails.append(f"축 집합 불일치 — 누락 {sorted(missing)} · 추가 {sorted(extra)}")

    bad = {k: v for k, v in w.items() if not isinstance(v, (int, float)) or v <= 0}
    if bad:
        fails.append(f"가중이 양수가 아니다: {bad}")

    if fails:
        print("🚨 발행 정지 — 헌법 가중 불변식 위반 (R2, §7-C)", file=sys.stderr)
        for f_ in fails:
            print(f"   · {f_}", file=sys.stderr)
        print("   fact.py 는 이걸 조용히 재정규화하므로 산출물만 보면 정상으로 보인다.",
              file=sys.stderr)
        print("   승인된 산식 변경이라면 EXPECTED_AXES 를 같은 커밋에서 갱신할 것.",
              file=sys.stderr)
        return 1

    print(f"verify_constitution_weights: 4축 합 {total:.6f} · 키 일치 ✓")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: verify_constitution_weights.py <path/to/verity_constitution.json>")
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
