#!/usr/bin/env python3
"""LANDEX 25구 풀 스냅샷 실행 wrapper.

ROOT 와 vercel-api 의 api/ 가 충돌해서 `python -m api.landex._snapshot` 직접 호출
어려움 (ROOT/api 가 regular package). 이 wrapper 가 .env 로드 + sys.path 보정 +
api.landex._snapshot 의 compute_snapshot/save_snapshot 직접 호출.

사용:
    python3 scripts/run_landex_snapshot.py 2026-04 [--preset balanced]
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 1) .env 로드 (큰따옴표 제거)
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)

# 2) sys.path 에 vercel-api 추가 — api.landex 모듈 경로
VERCEL_API = ROOT / "vercel-api"

# ROOT/api 가 이미 regular package 라 vercel-api/api 를 동일 namespace 로 못 씀.
# 우회: vercel-api 의 api 디렉터리를 직접 importlib 로 로드.
import importlib.util
import types

api_pkg = types.ModuleType("vapi"); api_pkg.__path__ = [str(VERCEL_API / "api")]
sys.modules["vapi"] = api_pkg

landex_pkg = types.ModuleType("vapi.landex"); landex_pkg.__path__ = [str(VERCEL_API / "api" / "landex")]
sys.modules["vapi.landex"] = landex_pkg

sources_pkg = types.ModuleType("vapi.landex._sources")
sources_pkg.__path__ = [str(VERCEL_API / "api" / "landex" / "_sources")]
sys.modules["vapi.landex._sources"] = sources_pkg


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# 의존 순서대로 로드 (relative import 풀어서 절대 모듈명으로 등록)
SD = VERCEL_API / "api" / "landex" / "_sources"
LD = VERCEL_API / "api" / "landex"

_load("vapi.landex._sources._lawd",        SD / "_lawd.py")
_load("vapi.landex._sources.molit",        SD / "molit.py")
_load("vapi.landex._sources.ecos",         SD / "ecos.py")
_load("vapi.landex._sources.seoul_subway", SD / "seoul_subway.py")
_load("vapi.landex._sources.rone",         SD / "rone.py")
_load("vapi.landex._methodology",          LD / "_methodology.py")
_load("vapi.landex._compute",              LD / "_compute.py")

# _snapshot.py 안의 import (`from . import _methodology as M`, `from ._sources import ...`)
# 가 relative 라 그대로는 import 안 됨. 코드 읽어서 절대명으로 바꾼 버전 메모리 로드.
snapshot_src = (LD / "_snapshot.py").read_text()
snapshot_src = snapshot_src.replace("from . import _methodology as M", "from vapi.landex import _methodology as M")
snapshot_src = snapshot_src.replace("from ._compute import", "from vapi.landex._compute import")
snapshot_src = snapshot_src.replace("from ._sources._lawd import", "from vapi.landex._sources._lawd import")
snapshot_src = snapshot_src.replace("from ._sources import", "from vapi.landex._sources import")

snap_module = types.ModuleType("vapi.landex._snapshot")
snap_module.__file__ = str(LD / "_snapshot.py")
sys.modules["vapi.landex._snapshot"] = snap_module
exec(compile(snapshot_src, str(LD / "_snapshot.py"), "exec"), snap_module.__dict__)


# 3) 실행
def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/run_landex_snapshot.py YYYY-MM [--preset balanced|growth|value]")
        sys.exit(1)
    month = sys.argv[1]
    preset = "balanced"
    if "--preset" in sys.argv:
        idx = sys.argv.index("--preset")
        if idx + 1 < len(sys.argv):
            preset = sys.argv[idx + 1]

    print(f"\n=== LANDEX 풀 스냅샷 ===")
    print(f"month={month} preset={preset}")
    print(f"REB_API_KEY 존재: {bool(os.environ.get('REB_API_KEY'))}")
    print(f"ECOS_API_KEY 존재: {bool(os.environ.get('ECOS_API_KEY'))}")
    print(f"PUBLIC_DATA_API_KEY 존재: {bool(os.environ.get('PUBLIC_DATA_API_KEY'))}")
    print(f"SEOUL_SUBWAY_API_KEY 존재: {bool(os.environ.get('SEOUL_SUBWAY_API_KEY'))}")
    print(f"SUPABASE_URL 존재: {bool(os.environ.get('SUPABASE_URL'))}")
    print(f"SUPABASE_SERVICE_ROLE_KEY 존재: {bool(os.environ.get('SUPABASE_SERVICE_ROLE_KEY'))}")
    print()

    t0 = time.time()
    rows = snap_module.compute_snapshot(month, preset=preset)
    elapsed = time.time() - t0
    print(f"\n[wrapper] 스냅샷 생성 완료: {len(rows)}구, {elapsed:.1f}초")

    # 요약 통계
    by_source = {"v": {}, "d": {}, "s": {}}
    for r in rows:
        rp = r.get("raw_payload", {})
        for axis, key in [("v", "v_source"), ("d", "d_source"), ("s", "s_source")]:
            src = rp.get(key, "missing")
            by_source[axis][src] = by_source[axis].get(src, 0) + 1
    print(f"\n  V source 분포: {by_source['v']}")
    print(f"  D source 분포: {by_source['d']}")
    print(f"  S source 분포: {by_source['s']}")

    # 상위 5개 / 하위 5개
    sorted_rows = sorted(rows, key=lambda x: x.get("landex") or 0, reverse=True)
    print(f"\n  LANDEX 상위 5:")
    for r in sorted_rows[:5]:
        print(f"    {r['gu']:6s} V={r['v_score']} D={r['d_score']} S={r['s_score']} "
              f"C={r['c_score']} R={r['r_score']} → {r['landex']} ({r['tier10']})")
    print(f"\n  LANDEX 하위 5:")
    for r in sorted_rows[-5:]:
        print(f"    {r['gu']:6s} V={r['v_score']} D={r['d_score']} S={r['s_score']} "
              f"C={r['c_score']} R={r['r_score']} → {r['landex']} ({r['tier10']})")

    # Supabase 저장
    saved = snap_module.save_snapshot(rows)
    print(f"\n  Supabase upsert: {'성공 ✓' if saved else '실패 또는 service_role 미설정'}")


if __name__ == "__main__":
    main()
