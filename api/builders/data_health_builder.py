"""데이터-헬스 집계 (관리자 감시 SoT) — 2026-07-12.

텔레그램(개인폰) 대신 관리자 사이트 컴포넌트가 읽을 단일 JSON 으로 데이터 무결 신호를 모은다.
read-only aggregate (판정·수정 0, RULE 7). 입력 파일 결손 = 해당 섹션 null(가짜 0 아님).

입력(로컬 산출물):
  - publish_guard.jsonl   — 발행 가드 HOLD 이벤트(blob_upload.js: 결함본 업로드 차단)
  - publish_verify.json   — 발행 후 실물 검증(P2: 배달 채움율 + CDN age)
  - coverage_report.json  + coverage_history.jsonl — 필드 채움율 + 회귀/차단 추이
  - freshness_board.json  — 신선도 SLA 상태(스트림별 fresh/stale/paused)
출력: data/metadata/data_health.json
상태: red(가드 HOLD 24h / 검증 실패 / P0 stale) > amber(회귀·비P0 stale·CDN age 높음) > green.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_META = os.path.join(_ROOT, "data", "metadata")
_DATA = os.path.join(_ROOT, "data")
OUT = os.path.join(_META, "data_health.json")

CDN_AGE_WARN_S = 120  # plain fetch age 가 이 초 초과 = CDN 스테일 서빙(amber)


def _load_json(path: str) -> Optional[Any]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _tail_jsonl(path: str, n: int = 200) -> List[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()[-n:]
    except OSError:
        return []
    out = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def _parse_ts(s: Any) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def _guard_section(now: datetime) -> Optional[Dict[str, Any]]:
    rows = _tail_jsonl(os.path.join(_META, "publish_guard.jsonl"))
    if not rows:
        return {"held_24h": 0, "recent": []}  # 파일 없음 = HOLD 이력 0 (정상 baseline)
    cutoff = now - timedelta(hours=24)
    recent, held_24h = [], 0
    for r in rows[-30:]:
        ts = _parse_ts(r.get("ts"))
        held = r.get("held") or []
        if ts and ts >= cutoff:
            held_24h += len(held)
        recent.append({"ts": r.get("ts"), "held": [h.get("file") for h in held],
                       "reasons": [h.get("reason") for h in held]})
    return {"held_24h": held_24h, "recent": recent[-8:]}


def _verify_section() -> Optional[Dict[str, Any]]:
    doc = _load_json(os.path.join(_META, "publish_verify.json"))
    if not doc:
        return None
    results = doc.get("results") or []
    max_age = max([r.get("cdn_age_s") or 0 for r in results], default=0)
    return {
        "generated_at": doc.get("generated_at"),
        "ok": doc.get("ok"),
        "failed": doc.get("failed"),
        "max_cdn_age_s": max_age,
        "files": [{"file": r.get("file"), "ok": r.get("ok"), "pct": r.get("pct"),
                   "total": r.get("total"), "cdn_age_s": r.get("cdn_age_s"), "error": r.get("error")}
                  for r in results],
    }


def _coverage_section() -> Optional[Dict[str, Any]]:
    rep = _load_json(os.path.join(_META, "coverage_report.json"))
    if not rep:
        return None
    hist = _tail_jsonl(os.path.join(_META, "coverage_history.jsonl"))
    last = hist[-1] if hist else {}
    core = {}
    for scope, key in (("fields", "facts.PBR"), ("fields", "facts.PER"),
                       ("us_fields", "facts.PBR"), ("us_fields", "facts.PER")):
        v = ((rep.get(scope) or {}).get(key) or {})
        if isinstance(v, dict) and v.get("pct") is not None:
            core[f"{scope}.{key}"] = v["pct"]
    return {
        "generated_at": (rep.get("_meta") or {}).get("generated_at"),
        "kr_total": rep.get("kr_total"),
        "us_total": rep.get("us_total"),
        "core_fill_pct": core,
        "last_run_blocked": bool(last.get("blocked")),
        "last_run_fails": last.get("fails", 0),
        "last_run_warns": last.get("warns", 0),
    }


def _freshness_section() -> Optional[Dict[str, Any]]:
    board = _load_json(os.path.join(_DATA, "freshness_board.json"))
    if not board:
        return None
    streams = board.get("streams") or []
    stale = [s for s in streams if s.get("status") == "stale"]
    stale_p0 = [s for s in stale if s.get("criticality") == "P0"]
    return {
        "generated_at": (board.get("_meta") or {}).get("generated_at"),
        "summary": board.get("summary"),
        "stale_p0": [{"id": s.get("id"), "label": s.get("label"), "age_min": s.get("age_eff_min")} for s in stale_p0],
        "stale_other": [s.get("id") for s in stale if s.get("criticality") != "P0"],
    }


def build() -> Dict[str, Any]:
    now = datetime.now(KST)
    guard = _guard_section(now)
    verify = _verify_section()
    coverage = _coverage_section()
    freshness = _freshness_section()

    reds, ambers = [], []
    if guard and guard.get("held_24h", 0) > 0:
        reds.append(f"발행 가드 HOLD {guard['held_24h']}건(24h)")
    if verify is not None and verify.get("ok") is False:
        reds.append(f"배달 검증 실패 {verify.get('failed')}건")
    if freshness and freshness.get("stale_p0"):
        reds.append(f"P0 stale {len(freshness['stale_p0'])}건")
    if coverage and coverage.get("last_run_blocked"):
        reds.append("커버리지 게이트 차단(직전 run)")
    if coverage and coverage.get("last_run_warns", 0) > 0:
        ambers.append(f"커버리지 회귀 경고 {coverage['last_run_warns']}건")
    if freshness and freshness.get("stale_other"):
        ambers.append(f"비P0 stale {len(freshness['stale_other'])}건")
    if verify is not None and (verify.get("max_cdn_age_s") or 0) > CDN_AGE_WARN_S:
        ambers.append(f"CDN age {verify['max_cdn_age_s']}s > {CDN_AGE_WARN_S}s(스테일 서빙)")

    status = "red" if reds else ("amber" if ambers else "green")
    return {
        "_meta": {"generated_at": now.isoformat(),
                  "source": "data_health_builder — 데이터 무결 신호 집계(판정·수정 0)"},
        "status": status,
        "reasons": reds + ambers,
        "publish_guard": guard,
        "publish_verify": verify,
        "coverage": coverage,
        "freshness": freshness,
    }


def main() -> None:
    os.makedirs(_META, exist_ok=True)
    doc = build()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print(f"[data_health] status={doc['status']} · reasons={doc['reasons'] or '없음'} → {OUT}")


if __name__ == "__main__":
    main()
