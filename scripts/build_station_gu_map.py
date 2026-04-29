#!/usr/bin/env python3
"""서울 지하철역 → 자치구 매핑 JSON 생성 (VWORLD 지오코딩 활용).

배경:
  vercel-api/api/landex/_sources/seoul_subway.py 의 STATION_TO_GU 가 76개로
  좁아서 강북구·성북구 등 일부 자치구가 C 점수 0 으로 떨어졌음.
  서울 카드 API 의 모든 고유 역명을 VWORLD 지오코딩해서 자동 매핑.

출력:
  vercel-api/api/landex/_sources/station_to_gu.json
    {
      "version": "1.0",
      "generated_at": "2026-04-30T...",
      "source": "vworld_geocode",
      "mapping": { "강남": "강남구", "역삼": "강남구", ... }
    }

seoul_subway.py 는 이 JSON 을 import 하고 hardcoded STATION_TO_GU 위에 merge.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# .env 로드
for line in (ROOT / ".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# vercel-api 의 seoul_subway + vworld 모듈 로드 (importlib 우회)
SD = ROOT / "vercel-api" / "api" / "landex" / "_sources"
pkg = types.ModuleType("vsrc"); pkg.__path__ = [str(SD)]
sys.modules["vsrc"] = pkg


def _load(name):
    spec = importlib.util.spec_from_file_location(f"vsrc.{name}", str(SD / f"{name}.py"))
    mod = importlib.util.module_from_spec(spec); sys.modules[f"vsrc.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


_load("_lawd")
ss = _load("seoul_subway")
vw = _load("vworld")

# 1) 서울 카드 API 에서 고유 역명 수집
print("[1/3] 서울 카드 API 호출…")
rows = ss.fetch_card_stats_recent(start_idx=1, end_idx=1000, timeout=15)
if not rows:
    print("FAIL: 카드 API 응답 없음")
    sys.exit(1)

unique_stations = sorted({r["station"] for r in rows if r.get("station")})
print(f"   고유 역 {len(unique_stations)}개")

# 2) VWORLD 지오코딩
print("\n[2/3] VWORLD 지오코딩…")
SEOUL_GU_NAMES = vw.SEOUL_GU_NAMES

mapping: dict[str, str] = {}
non_seoul: list[str] = []
not_found: list[str] = []

for i, station in enumerate(unique_stations, 1):
    # "서울 {역}역" 으로 검색 — 동명 역(예: 시청·중구) 의 충돌 방지
    addr = f"서울 {station}역"
    g = vw.geocode(addr, timeout=8.0)
    if g is None:
        # 폴백 — "역" 빼고 시도
        g = vw.geocode(f"서울 {station}", timeout=8.0)
    if g is None:
        not_found.append(station)
        if i % 30 == 0:
            print(f"   {i}/{len(unique_stations)} (미매칭 누적 {len(not_found)})")
        continue

    level1 = g.get("level1") or ""
    level2 = g.get("level2") or ""
    if "서울" not in level1:
        non_seoul.append(f"{station}({level1}>{level2})")
        continue
    if level2 in SEOUL_GU_NAMES:
        mapping[station] = level2
    else:
        not_found.append(f"{station}({level2})")

    # 진행 표시 + rate-limit 보호
    if i % 30 == 0:
        print(f"   {i}/{len(unique_stations)} (매핑 {len(mapping)}, 비서울 {len(non_seoul)}, 미매칭 {len(not_found)})")
    time.sleep(0.05)  # VWORLD 일일 30k 한도지만 안전

# 3) 결과 저장
print(f"\n[3/3] 결과 저장…")
print(f"   서울 25구 매핑: {len(mapping)}개")
print(f"   비서울 (분당/인천 등): {len(non_seoul)}")
print(f"   미매칭: {len(not_found)}")

# 25구별 매핑 분포
from collections import Counter
gu_counts = Counter(mapping.values())
print(f"\n   25구별 분포:")
for gu in sorted(SEOUL_GU_NAMES):
    cnt = gu_counts.get(gu, 0)
    flag = "" if cnt > 0 else "  ⚠ 매핑 없음"
    print(f"     {gu:6s}: {cnt:3d}역{flag}")

# JSON 파일 저장
out_path = SD / "station_to_gu.json"
payload = {
    "version": "1.0",
    "generated_at": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
    "source": "vworld_geocode",
    "total_stations_seen": len(unique_stations),
    "mapped_count": len(mapping),
    "non_seoul_count": len(non_seoul),
    "not_found_count": len(not_found),
    "mapping": dict(sorted(mapping.items())),
}
out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
print(f"\n   저장: {out_path}")
print(f"   ({out_path.stat().st_size} bytes)")
