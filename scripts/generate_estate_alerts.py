#!/usr/bin/env python3
"""ESTATE 자동 알림 생성 — LANDEX 스냅샷 + R-ONE 시계열 변화 분석 → estate_alerts INSERT.

LANDEX snapshot 직후 호출 (GH Actions workflow 의 두 번째 step).

감지 룰:
  1. 미분양 급증 — 전월 대비 +50% 또는 +50호↑      → category=anomaly, severity=high
  2. 미분양 소진 — 전월 대비 -50% 또는 -50호↑      → category=anomaly, severity=mid (긍정)
  3. LANDEX 등급 변동 — 전월 스냅샷 대비 tier10 변경 → category=anomaly, severity=mid
  4. 주간 매매지수 급변 — 4주 누적 ±2% 이상         → category=anomaly, severity=mid
  5. R 점수 변동 (거시) — 전월 대비 ±10 이상          → category=regulation, severity=high

각 알림은 dedup — title 동일 + 같은 month/gu 면 추가 INSERT 안 함.
estate_alerts.user_id NULL → 모든 인증 사용자 공개.

사용:
    python3 scripts/generate_estate_alerts.py 2026-04 [--prev 2026-03]

memory:feedback_macro_timestamp_policy — body 끝에 as_of 명시.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests

ROOT = Path(__file__).resolve().parent.parent

# .env 로드
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# rone 어댑터 importlib 로드 (sys.path 충돌 회피)
SD = ROOT / "vercel-api" / "api" / "landex" / "_sources"
pkg = types.ModuleType("vsrc"); pkg.__path__ = [str(SD)]
sys.modules["vsrc"] = pkg

def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"vsrc.{name}", str(SD / f"{name}.py"))
    mod = importlib.util.module_from_spec(spec); sys.modules[f"vsrc.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod

_load("_lawd")
rone = _load("rone")

KST = timezone(timedelta(hours=9))


def _now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _supabase_url() -> str:
    return (os.environ.get("SUPABASE_URL") or "").rstrip("/")


def _service_key() -> str:
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""


def _prev_month(month: str) -> str:
    """'2026-04' → '2026-03'."""
    y, m = month.split("-")
    yi, mi = int(y), int(m)
    if mi == 1:
        return f"{yi - 1}-12"
    return f"{yi}-{mi - 1:02d}"


# ─────────────────────────────────────────────────────────
# Snapshot 비교 (LANDEX 등급 변동)
# ─────────────────────────────────────────────────────────

def fetch_snapshots(month: str, preset: str = "balanced") -> list[dict]:
    """estate_landex_snapshots 의 25구 행."""
    url = _supabase_url()
    sk = _service_key()
    if not url or not sk:
        return []
    r = requests.get(
        f"{url}/rest/v1/estate_landex_snapshots",
        headers={"apikey": sk, "Authorization": f"Bearer {sk}"},
        params={
            "select": "gu,landex,tier10,r_score,raw_payload",
            "month": f"eq.{month}",
            "preset": f"eq.{preset}",
        },
        timeout=10,
    )
    if r.status_code != 200:
        return []
    return r.json() or []


# ─────────────────────────────────────────────────────────
# 알림 생성 룰
# ─────────────────────────────────────────────────────────

def _alert(category: str, severity: str, title: str, body: str,
           gu: Optional[str] = None, occurred_at: Optional[str] = None) -> dict:
    return {
        "user_id": None,  # 공개
        "category": category,
        "severity": severity,
        "title": title,
        "body": body,
        "gu": gu,
        "source_url": None,
        "occurred_at": occurred_at or _now_iso(),
    }


def detect_unsold_anomalies(month: str) -> list[dict]:
    """R-ONE 미분양 12개월 시계열 분석 → 급증/소진 감지."""
    alerts: list[dict] = []
    series_25 = rone.fetch_monthly_unsold_seoul_25(months=12)
    for gu, payload in series_25.items():
        if not payload:
            continue
        s = payload.get("series") or []
        if len(s) < 2:
            continue
        prev = s[-2]["unsold"]
        curr = s[-1]["unsold"]
        as_of = payload.get("as_of") or s[-1].get("month") or month

        delta = curr - prev
        ratio = (delta / prev * 100) if prev > 0 else (100.0 if curr > 0 else 0.0)

        if curr >= 50 and (delta >= 50 or ratio >= 50):
            alerts.append(_alert(
                category="anomaly", severity="high",
                title=f"{gu} 미분양 급증 — {prev}호 → {curr}호 (+{delta}호, {ratio:+.0f}%)",
                body=(f"R-ONE (월) 미분양 통계: 전월 {prev}호 → 이번 {curr}호 (+{delta}호).\n"
                      f"공급 부담 신호 — 분양시장 둔화 가능성 모니터링 필요.\n"
                      f"as_of {as_of}"),
                gu=gu,
            ))
        elif prev >= 50 and (delta <= -50 or ratio <= -50):
            alerts.append(_alert(
                category="anomaly", severity="mid",
                title=f"{gu} 미분양 소진 — {prev}호 → {curr}호 ({delta}호, {ratio:+.0f}%)",
                body=(f"R-ONE (월) 미분양 통계: 전월 {prev}호 → 이번 {curr}호 ({delta}호).\n"
                      f"공급 흡수 진행 — 분양시장 회복 시그널.\n"
                      f"as_of {as_of}"),
                gu=gu,
            ))
    return alerts


def detect_landex_tier_changes(month: str, prev_month: str) -> list[dict]:
    """전월 스냅샷 vs 이번 달 — tier10 등급 변경 감지."""
    alerts: list[dict] = []
    curr_rows = fetch_snapshots(month)
    prev_rows = fetch_snapshots(prev_month)
    if not curr_rows or not prev_rows:
        return alerts

    prev_map = {r["gu"]: r for r in prev_rows}
    for r in curr_rows:
        gu = r.get("gu")
        prev = prev_map.get(gu)
        if not prev:
            continue
        prev_tier = prev.get("tier10")
        curr_tier = r.get("tier10")
        if not prev_tier or not curr_tier or prev_tier == curr_tier:
            continue
        prev_landex = prev.get("landex") or 0
        curr_landex = r.get("landex") or 0
        # 상승/하락 방향
        direction = "상승" if curr_landex > prev_landex else "하락"
        sev = "high" if abs(curr_landex - prev_landex) >= 10 else "mid"
        alerts.append(_alert(
            category="anomaly", severity=sev,
            title=f"{gu} LANDEX 등급 {direction} — {prev_tier} → {curr_tier} ({prev_landex:.0f} → {curr_landex:.0f})",
            body=(f"{prev_month} {prev_tier}({prev_landex:.0f}) 에서 "
                  f"{month} {curr_tier}({curr_landex:.0f}) 로 변경.\n"
                  f"snapshot 기준 (V/D/S/C/R 종합 가중평균)."),
            gu=gu,
        ))
    return alerts


def detect_weekly_index_swings(month: str) -> list[dict]:
    """R-ONE 주간 매매지수 12주 누적 변화 ±2% 이상 — 강세/약세 시그널."""
    alerts: list[dict] = []
    series_25 = rone.fetch_weekly_index_seoul_25(weeks=12)
    for gu, payload in series_25.items():
        if not payload:
            continue
        s = payload.get("series") or []
        if len(s) < 4:
            continue
        first = s[0]["index"]
        last = s[-1]["index"]
        if first <= 0:
            continue
        change_pct = (last - first) / first * 100
        as_of = payload.get("as_of") or month
        if abs(change_pct) < 2.0:
            continue  # 노이즈 영역
        if change_pct > 0:
            alerts.append(_alert(
                category="anomaly", severity="mid",
                title=f"{gu} 12주 가격지수 강세 — {change_pct:+.2f}%",
                body=(f"R-ONE 주간 매매가격지수 12주 누적 {change_pct:+.2f}%.\n"
                      f"가속도 모멘텀 진입 — D 점수 상승 견인.\n"
                      f"as_of {as_of}"),
                gu=gu,
            ))
        else:
            alerts.append(_alert(
                category="anomaly", severity="mid",
                title=f"{gu} 12주 가격지수 약세 — {change_pct:+.2f}%",
                body=(f"R-ONE 주간 매매가격지수 12주 누적 {change_pct:+.2f}%.\n"
                      f"조정 진행 중 — V 점수 가산점 메리트.\n"
                      f"as_of {as_of}"),
                gu=gu,
            ))
    return alerts


def detect_macro_rate_change(month: str, prev_month: str) -> list[dict]:
    """R 점수 (거시 기준금리) 전월 대비 ±10 이상 변동."""
    alerts: list[dict] = []
    curr_rows = fetch_snapshots(month)
    prev_rows = fetch_snapshots(prev_month)
    if not curr_rows or not prev_rows:
        return alerts
    # R 점수는 모든 구 동일 — 첫 행만 비교
    curr_r = (curr_rows[0] or {}).get("r_score")
    prev_r = (prev_rows[0] or {}).get("r_score")
    if curr_r is None or prev_r is None:
        return alerts
    delta = curr_r - prev_r
    if abs(delta) < 10:
        return alerts
    direction = "완화" if delta > 0 else "긴축"
    alerts.append(_alert(
        category="regulation", severity="high",
        title=f"거시 R 점수 {direction} — {prev_r:.0f} → {curr_r:.0f} ({delta:+.1f})",
        body=(f"ECOS 기준금리 환경 변동: 전월 R={prev_r:.0f} → 이번 R={curr_r:.0f}.\n"
              f"전 25구 동시 영향 — 부동산 매수심리·DSR 부담 변화 신호."),
        gu=None,
    ))
    return alerts


# ─────────────────────────────────────────────────────────
# Dedup + INSERT
# ─────────────────────────────────────────────────────────

def fetch_recent_alerts_titles(days: int = 35) -> set[str]:
    """최근 N일 알림 title 집합 (중복 제거용)."""
    url = _supabase_url(); sk = _service_key()
    if not url or not sk:
        return set()
    since = (datetime.now(KST) - timedelta(days=days)).isoformat(timespec="seconds")
    r = requests.get(
        f"{url}/rest/v1/estate_alerts",
        headers={"apikey": sk, "Authorization": f"Bearer {sk}"},
        params={"select": "title", "occurred_at": f"gte.{since}", "limit": "500"},
        timeout=10,
    )
    if r.status_code != 200:
        return set()
    return {row.get("title", "") for row in r.json() or []}


def insert_alerts(alerts: list[dict]) -> int:
    """estate_alerts 에 batch INSERT. dedup 후 신규만."""
    if not alerts:
        return 0
    url = _supabase_url(); sk = _service_key()
    if not url or not sk:
        print("[alerts] SUPABASE service_role 미설정 — INSERT 스킵")
        return 0

    existing = fetch_recent_alerts_titles()
    new_alerts = [a for a in alerts if a["title"] not in existing]
    if not new_alerts:
        print("[alerts] 신규 알림 없음 (모두 dedup)")
        return 0

    r = requests.post(
        f"{url}/rest/v1/estate_alerts",
        headers={
            "apikey": sk, "Authorization": f"Bearer {sk}",
            "Content-Type": "application/json", "Prefer": "return=minimal",
        },
        data=json.dumps(new_alerts, ensure_ascii=False).encode("utf-8"),
        timeout=15,
    )
    if r.status_code not in (200, 201, 204):
        print(f"[alerts] INSERT 실패: HTTP {r.status_code} body={r.text[:200]}")
        return 0
    return len(new_alerts)


# ─────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("month", help="대상 월 YYYY-MM")
    ap.add_argument("--prev", help="비교 기준 월 YYYY-MM (기본: 자동 -1개월)")
    ap.add_argument("--dry", action="store_true", help="INSERT 안 하고 출력만")
    args = ap.parse_args()

    month = args.month
    prev = args.prev or _prev_month(month)
    print(f"[alerts] 대상 month={month}, 비교 prev={prev}\n")

    all_alerts: list[dict] = []

    print("[1/4] 미분양 급증/소진 감지...")
    a1 = detect_unsold_anomalies(month)
    print(f"   감지: {len(a1)}건")
    all_alerts.extend(a1)

    print("[2/4] LANDEX 등급 변동 감지...")
    a2 = detect_landex_tier_changes(month, prev)
    print(f"   감지: {len(a2)}건")
    all_alerts.extend(a2)

    print("[3/4] 주간 매매지수 ±2% 강·약세 감지...")
    a3 = detect_weekly_index_swings(month)
    print(f"   감지: {len(a3)}건")
    all_alerts.extend(a3)

    print("[4/4] 거시 R 점수 ±10 변동 감지...")
    a4 = detect_macro_rate_change(month, prev)
    print(f"   감지: {len(a4)}건")
    all_alerts.extend(a4)

    print(f"\n총 알림 후보: {len(all_alerts)}건")

    # severity 분포
    from collections import Counter
    sev_c = Counter(a["severity"] for a in all_alerts)
    cat_c = Counter(a["category"] for a in all_alerts)
    print(f"  severity: {dict(sev_c)}")
    print(f"  category: {dict(cat_c)}")

    # high 알림 미리 보기
    print("\nhigh 알림 미리보기:")
    for a in all_alerts:
        if a["severity"] == "high":
            print(f"  [{a['gu'] or '거시'}] {a['title']}")

    if args.dry:
        print("\n[--dry] INSERT 스킵.")
        return

    inserted = insert_alerts(all_alerts)
    print(f"\n[alerts] Supabase INSERT 완료: {inserted}건 (dedup 후)")


if __name__ == "__main__":
    main()
