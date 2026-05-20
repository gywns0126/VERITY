"""LANDEX 스냅샷 전세가율 산식 (_compute_jeonse_ratios) — 단위 테스트.

검증:
  - 전세가율 = 전세 보증금 평당 중앙값 / 매매 평당가 중앙값 (평당 정규화)
  - 월세(monthlyRent>0 → lease_type=='월세')는 분자에서 제외
  - 매매 평당가(분모) 결측 구 → None
  - 전세 표본 < 5 → None
  - raw_payload 노출 전용 계약 (score 미반영) — 산식 자체엔 R 영향 없음 확인

_snapshot.py 는 vercel-api 패키지(하이픈) 안이라 importlib 패키지 shim 로 로드
(tests/test_landex_rone_jeonse.py 와 동일 패턴). 무거운 sibling(ecos/rone/seoul_subway)은 stub.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types

import pytest


def _load_snapshot(monkeypatch):
    """vercel-api/api/landex/_snapshot.py 를 패키지 컨텍스트로 로드.

    필요한 실모듈: _lawd / _methodology / _compute / molit.
    불필요한 sibling(ecos/rone/seoul_subway)은 stub ModuleType.
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    landex_dir = os.path.join(repo_root, "vercel-api", "api", "landex")
    sources_dir = os.path.join(landex_dir, "_sources")

    pkg = "vlx_jeonse_test"
    sources_pkg = f"{pkg}._sources"

    pkg_mod = types.ModuleType(pkg)
    pkg_mod.__path__ = [landex_dir]
    monkeypatch.setitem(sys.modules, pkg, pkg_mod)

    sources_mod = types.ModuleType(sources_pkg)
    sources_mod.__path__ = [sources_dir]
    monkeypatch.setitem(sys.modules, sources_pkg, sources_mod)

    def _real(modname, filename, parent_path):
        spec = importlib.util.spec_from_file_location(
            modname, os.path.join(parent_path, filename)
        )
        mod = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, modname, mod)
        spec.loader.exec_module(mod)
        return mod

    # 실모듈 (의존 순서: _lawd → _methodology → _compute → molit)
    _real(f"{sources_pkg}._lawd", "_lawd.py", sources_dir)
    _real(f"{pkg}._methodology", "_methodology.py", landex_dir)
    _real(f"{pkg}._compute", "_compute.py", landex_dir)
    molit = _real(f"{sources_pkg}.molit", "molit.py", sources_dir)

    # 불필요 sibling stub (_snapshot 가 module-level import 하지만 jeonse 산식엔 무관)
    for name in ("ecos", "rone", "seoul_subway"):
        monkeypatch.setitem(sys.modules, f"{sources_pkg}.{name}", types.ModuleType(f"{sources_pkg}.{name}"))

    snap = _real(f"{pkg}._snapshot", "_snapshot.py", landex_dir)
    return snap, molit


def _rent(deposit_man, area_m2, monthly_man=0):
    """RTMS 전월세 파싱 결과 모양 (deposit_won/monthly_rent_won/lease_type/area_m2)."""
    return {
        "deposit_won": deposit_man * 10_000,
        "monthly_rent_won": monthly_man * 10_000,
        "lease_type": "전세" if monthly_man == 0 else "월세",
        "area_m2": area_m2,
    }


def test_jeonse_ratio_basic(monkeypatch):
    snap, molit = _load_snapshot(monkeypatch)

    # 강남구: 전세 평당 보증금 = 매매 평당가의 60% 가 되도록 구성.
    # 84.97 m² ≈ 25.7평. 평당가 6000(만원 단위 아님 — won/평) 와 직접 비교는 아래에서.
    # deposit_pyeong = deposit_won / (area_m2/3.305785).
    PYEONG = 3.305785
    area = 84.97
    pyeong = area / PYEONG  # ≈ 25.7
    price_pyeong_median = 100_000_000.0  # 분모 (won/평) — 임의
    # 전세 보증금을 deposit_pyeong=60_000_000 이 되도록: deposit_won = 60_000_000 * pyeong
    target_dep_pyeong = 60_000_000.0
    deposit_won = target_dep_pyeong * pyeong
    deposit_man = round(deposit_won / 10_000)

    rents = [_rent(deposit_man, area) for _ in range(8)]  # 동일값 8건 → median 동일
    monkeypatch.setattr(molit, "fetch_apt_rents", lambda gu, yyyymm, timeout=8.0: rents)

    price_medians = {gu: None for gu in snap.SEOUL_25_GU}
    price_medians["강남구"] = price_pyeong_median

    out = snap._compute_jeonse_ratios("2026-04", price_medians)

    gn = out["강남구"]
    assert gn is not None
    assert gn["n_jeonse"] == 8
    assert gn["jeonse_ratio"] == pytest.approx(0.60, abs=0.01)
    # 분모 결측 구는 None
    assert out["서초구"] is None


def test_jeonse_ratio_excludes_wolse(monkeypatch):
    snap, molit = _load_snapshot(monkeypatch)
    PYEONG = 3.305785
    area = 84.97
    pyeong = area / PYEONG

    # 전세 5건(평당 보증금 5천만) + 월세 5건(보증금 작음) → 월세 제외돼야 ratio 가 전세만 반영
    dep_man = round((50_000_000.0 * pyeong) / 10_000)
    jeonse = [_rent(dep_man, area) for _ in range(5)]
    wolse = [_rent(round((5_000_000.0 * pyeong) / 10_000), area, monthly_man=100) for _ in range(5)]
    monkeypatch.setattr(molit, "fetch_apt_rents", lambda gu, yyyymm, timeout=8.0: jeonse + wolse)

    price_medians = {gu: None for gu in snap.SEOUL_25_GU}
    price_medians["강남구"] = 100_000_000.0
    out = snap._compute_jeonse_ratios("2026-04", price_medians)

    gn = out["강남구"]
    assert gn is not None
    assert gn["n_jeonse"] == 5  # 전세만
    assert gn["jeonse_ratio"] == pytest.approx(0.50, abs=0.01)


def test_jeonse_ratio_insufficient_sample(monkeypatch):
    snap, molit = _load_snapshot(monkeypatch)
    # 전세 4건 (<5) → None
    rents = [_rent(50000, 84.97) for _ in range(4)]
    monkeypatch.setattr(molit, "fetch_apt_rents", lambda gu, yyyymm, timeout=8.0: rents)
    price_medians = {gu: None for gu in snap.SEOUL_25_GU}
    price_medians["강남구"] = 100_000_000.0
    out = snap._compute_jeonse_ratios("2026-04", price_medians)
    assert out["강남구"] is None


def test_jeonse_ratio_no_rent_data(monkeypatch):
    snap, molit = _load_snapshot(monkeypatch)
    monkeypatch.setattr(molit, "fetch_apt_rents", lambda gu, yyyymm, timeout=8.0: [])
    price_medians = {gu: 100_000_000.0 for gu in snap.SEOUL_25_GU}
    out = snap._compute_jeonse_ratios("2026-04", price_medians)
    assert all(v is None for v in out.values())
