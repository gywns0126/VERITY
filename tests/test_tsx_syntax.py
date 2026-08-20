"""tsx/ts 문법 파손을 CI 에서 잡는다.

## 왜 (2026-08-19 신설)

`PublicGlassboxTab.tsx` 를 편집하면서 툴팁 문자열 안에 **큰따옴표**를 넣었다:

    "… 다만 "몇 개면 충분" 이라는 고정 최소선은 …"

문자열이 그 자리에서 끊겨 `Expected ',', got '몇'` 로 파싱이 죽었다. PM 이 라이브에
붙인 뒤에야 발견됐다.

🚨 **파이썬은 매 편집마다 `ast.parse` 로 막았는데 tsx 는 아무 검사도 없었다.**
회귀 스위트 2,431건이 전부 통과한 상태로 깨진 컴포넌트가 나갔다 — 테스트가 파이썬만
보고 있었기 때문이다. 같은 방어를 프런트에도 건다.

esbuild 는 `node_modules` 에 이미 있다(0.28.1). 없으면 이 테스트는 skip 한다 —
없다고 조용히 통과시키지 않고 사유를 남긴다.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SCAN_DIRS = ("framer-components", "operator-web/app")
_SKIP_PARTS = {"node_modules", ".next", "dist", "build"}


def _targets():
    out = []
    for d in _SCAN_DIRS:
        base = _ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*.tsx"):
            if _SKIP_PARTS & set(p.parts):
                continue
            out.append(p)
    return sorted(out)


def _esbuild_ok() -> bool:
    if not (_ROOT / "node_modules").exists():
        return False
    return shutil.which("npx") is not None


def test_tsx_gate_is_live_in_ci():
    """🚨 CI 에서는 skip 을 허용하지 않는다.

    2026-08-21 발견 — 이 게이트는 신설(8/19) 이래 **CI 에서 한 번도 돈 적이 없었다**.
    러너에 `node_modules` 가 없어 매 run 이 `SKIPPED (esbuild 부재)` 였다. 사유를 남겼으니
    조용한 실패는 아니지만, 실질은 로컬 전용이라 게이트를 만든 목적 자체를 못 채웠다
    (목적 = 로컬에서만 보다가 깨진 컴포넌트를 라이브로 내보낸 사고의 재발 방지).

    그래서 부재를 **CI 에서만 실패로 승격**한다. 로컬은 종전대로 graceful skip —
    node 없이 파이썬만 돌리는 환경을 막을 이유가 없다.
    아래 `test_all_tsx_parses` 의 skipif 는 그대로 두되, CI 에서는 이 계약이 먼저 깨진다.
    """
    if not os.environ.get("CI"):
        pytest.skip("로컬 환경 — 이 계약은 CI 전용")
    assert _esbuild_ok(), (
        "CI 에 node_modules 가 없어 tsx 문법 게이트가 꺼진다. "
        "`.github/workflows/tests.yml` 의 'Install node deps (esbuild)' 단계를 확인할 것")


@pytest.mark.skipif(not _esbuild_ok(), reason="esbuild(node_modules) 부재 — 로컬/CI 환경 확인 필요")
def test_all_tsx_parses():
    """🚨 전수 검사 — 표본이 아니다 (RULE 13). 실패 시 파일명과 esbuild 원문을 남긴다."""
    targets = _targets()
    assert targets, "검사 대상 tsx 가 0건 — 스캔 경로가 잘못됐다"

    broken = []
    for p in targets:
        r = subprocess.run(
            ["npx", "--no-install", "esbuild", str(p), "--outfile=/dev/null",
             "--log-level=warning"],
            capture_output=True, text=True, cwd=str(_ROOT))
        if r.returncode != 0 or r.stderr.strip():
            broken.append(f"{p.relative_to(_ROOT)}\n{r.stderr.strip()[:400]}")

    assert not broken, (
        f"tsx 문법 파손 {len(broken)}/{len(targets)}건:\n\n" + "\n\n".join(broken))
