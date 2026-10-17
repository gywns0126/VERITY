"""데이터-헬스 집계 (관리자 감시 SoT) — 2026-07-12.

텔레그램(개인폰) 대신 관리자 사이트 컴포넌트가 읽을 단일 JSON 으로 데이터 무결 신호를 모은다.
read-only aggregate (판정·수정 0, RULE 7). 입력 파일 결손 = 해당 섹션 null(가짜 0 아님).

입력(로컬 산출물):
  - publish_guard.jsonl   — 발행 가드 HOLD 이벤트(blob_upload.js: 결함본 업로드 차단)
  - publish_verify.json   — 발행 후 실물 검증(P2: 배달 채움율 + 배달 시각)
  - coverage_report.json  + coverage_history.jsonl — 필드 채움율 + 회귀/차단 추이
  - freshness_board.json  — 신선도 SLA 상태(스트림별 fresh/stale/paused)
출력: data/metadata/data_health.json
상태: red(가드 HOLD 24h / 검증 실패 / P0 stale) > amber(증거 결손·지연·회귀) > green.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from scripts.publish_verify import GUARD

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_META = os.path.join(_ROOT, "data", "metadata")
_DATA = os.path.join(_ROOT, "data")
OUT = os.path.join(_META, "data_health.json")
# Hourly monitor tolerates two missed slots. Daily coverage allows the weekend gap.
_EVIDENCE_MAX_AGE_H = {"publish_verify": 3, "freshness": 3, "coverage": 96}
_EXPECTED_VERIFY_FILES = set(GUARD) | {"_verity_data_push_recency"}

def _load_json(path: str) -> Optional[Any]:
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
            return doc if isinstance(doc, dict) else None
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
            row = json.loads(ln)
            if isinstance(row, dict):
                out.append(row)
        except ValueError:
            continue
    return out


def _parse_ts(s: Any) -> Optional[datetime]:
    if not s:
        return None
    try:
        ts = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return ts if ts.tzinfo is not None else None
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
    if not isinstance(results, list) or any(not isinstance(r, dict) for r in results):
        return None
    max_age = max([r["cdn_age_s"] for r in results
                   if isinstance(r.get("cdn_age_s"), (int, float))], default=0)
    return {
        "generated_at": doc.get("generated_at"),
        "ok": doc.get("ok"),
        "failed": doc.get("failed"),
        "checked": doc.get("checked"),
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
        "last_run_at": last.get("ts"),
    }


def _freshness_section() -> Optional[Dict[str, Any]]:
    board = _load_json(os.path.join(_DATA, "freshness_board.json"))
    if not board:
        return None
    streams = board.get("streams") or []
    if not isinstance(streams, list) or any(not isinstance(s, dict) for s in streams):
        return None
    if any(s.get("status") not in ("fresh", "stale", "closed", "discontinued") for s in streams):
        return None
    stale = [s for s in streams if s.get("status") == "stale"]
    stale_p0 = [s for s in stale if s.get("criticality") == "P0"]
    return {
        "generated_at": (board.get("_meta") or {}).get("generated_at"),
        "summary": board.get("summary"),
        "stream_count": len(streams),
        "skipped_count": board.get("_skipped_count", 0),
        "stale_p0": [{"id": s.get("id"), "label": s.get("label"), "age_min": s.get("age_eff_min")} for s in stale_p0],
        "stale_other": [s.get("id") for s in stale if s.get("criticality") != "P0"],
    }


def _evidence_status(section: Optional[dict], now: datetime, max_age_h: int) -> dict:
    stamp = section.get("generated_at") if section else None
    ts = _parse_ts(stamp)
    result = {"generated_at": stamp, "max_age_h": max_age_h, "age_h": None}
    if not section or ts is None:
        return {**result, "status": "missing" if not section else "invalid_timestamp"}
    age = (now - ts).total_seconds() / 3600
    status = "future" if age < -5 / 60 else ("stale" if age > max_age_h else "fresh")
    return {**result, "age_h": round(age, 3), "status": status}


def build() -> Dict[str, Any]:
    now = datetime.now(KST)
    guard = _guard_section(now)
    verify = _verify_section()
    coverage = _coverage_section()
    freshness = _freshness_section()

    reds, ambers = [], []
    sections = {"publish_verify": verify, "coverage": coverage, "freshness": freshness}
    evidence = {name: _evidence_status(section, now, _EVIDENCE_MAX_AGE_H[name])
                for name, section in sections.items()}
    for name, item in evidence.items():
        if item["status"] != "fresh":
            ambers.append(f"감시 근거 {name}: {item['status']}")
    if verify and (not isinstance(verify.get("ok"), bool)
                   or verify.get("checked") != len(_EXPECTED_VERIFY_FILES)
                   or len(verify.get("files", [])) != len(_EXPECTED_VERIFY_FILES)
                   or {r.get("file") for r in verify.get("files", [])} != _EXPECTED_VERIFY_FILES):
        ambers.append("배달 검증 결과 누락·불완전")
    if verify and any(r.get("ok") is not True for r in verify.get("files", [])):
        reds.append("배달 개별 검증 실패·미확인")
    if coverage and (not coverage.get("kr_total") or not coverage.get("us_total")
                     or not coverage.get("core_fill_pct")):
        ambers.append("커버리지 측정 분모·결과 누락")
    if coverage:
        history = _evidence_status({"generated_at": coverage.get("last_run_at")}, now,
                                   _EVIDENCE_MAX_AGE_H["coverage"])
        if history["status"] != "fresh":
            ambers.append(f"커버리지 실행 이력: {history['status']}")
    if freshness and (not freshness.get("stream_count") or freshness.get("skipped_count")):
        ambers.append("신선도 감시 대상 누락·미측정")
    if guard and guard.get("held_24h", 0) > 0:
        reds.append(f"발행 가드 HOLD {guard['held_24h']}건(24h)")
    if verify is not None and (verify.get("ok") is False
                              or (isinstance(verify.get("failed"), int) and verify["failed"] > 0)):
        reds.append(f"배달 검증 실패 {verify.get('failed')}건")
    if freshness and freshness.get("stale_p0"):
        reds.append(f"P0 stale {len(freshness['stale_p0'])}건")
    if coverage and coverage.get("last_run_blocked"):
        reds.append("커버리지 게이트 차단(직전 run)")
    if coverage and coverage.get("last_run_warns", 0) > 0:
        ambers.append(f"커버리지 회귀 경고 {coverage['last_run_warns']}건")
    if freshness and freshness.get("stale_other"):
        ambers.append(f"비P0 stale {len(freshness['stale_other'])}건")
    status = "red" if reds else ("amber" if ambers else "green")
    return {
        "_meta": {"generated_at": now.isoformat(),
                  "source": "data_health_builder — 데이터 무결 신호 집계(판정·수정 0)"},
        "status": status,
        "reasons": reds + ambers,
        "evidence": evidence,
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
