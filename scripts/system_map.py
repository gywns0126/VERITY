#!/usr/bin/env python3
"""
system_map.py — VERITY "한눈에 보기" 시스템 맵 generator (실행형, drift 불가).

2026-06-07 신설. 시스템이 1인 사이드로 ~156K 라인까지 커지며 PM 이 전체 규모를
머리로 잡지 못하는 상태 도달 → "검수했나?" 가 아니라 "맵이 자동 갱신되나?" 로 전환.

손으로 그린 다이어그램은 한 달이면 drift 나 거짓말이 되므로 (프로젝트 만성병),
레포를 실제 스캔해 data/system_map.json 을 산출한다. Admin "VERITY 한눈에 보기"
컴포넌트의 단일 입력. 정적 .md 맵은 금지.

산출 6축 (1차 자료 직접 스캔 — agent 추정 없음, RULE 10 정합):
  1. ingest      — 수집기 (KIS / DART / FRED / ECOS / sentiment / macro)
  2. brain       — 두뇌 모듈 (api/intelligence)
  3. automation  — 자동화 워크플로 + cron 스케줄
  4. surface     — 출력 (Framer 컴포넌트, 페이지 그룹별)
  5. data        — 발행 데이터 (git 추적 JSON)
  6. validation  — 검증 N (n_counter.json) + 마일스톤

라이브 헬스: n_counter.json / infra_status.json / 핵심 발행 파일 신선도 읽기.
generated_at = now_kst (tz-aware 의무, datetime.now() 금지).

사용:
  python3 scripts/system_map.py            # data/system_map.json 산출 + 요약 출력
  python3 scripts/system_map.py --dry-run  # 파일 미작성, 요약만 출력
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# now_kst = 프로젝트 단일 tz-aware 시각원 (api/config.py). 독립 실행 대비 fallback.
try:
    from api.config import now_kst  # type: ignore
except Exception:  # pragma: no cover - 독립 실행 경로
    from datetime import datetime, timedelta, timezone

    _KST = timezone(timedelta(hours=9))

    def now_kst():  # type: ignore
        return datetime.now(_KST)

# data/metadata/ = publish-data metadata/ 루프 + OperatorCockpit 컴포넌트 fetch 경로 정합.
# 발행 URL = raw.githubusercontent.com/gywns0126/VERITY-data/main/metadata/system_map.json
OUT_PATH = os.path.join(REPO_ROOT, "data", "metadata", "system_map.json")

# ── git 추적 기준 카운트 (venv/site-packages 노이즈 차단) ───────────────


def _git_files(*patterns: str) -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "ls-files", *patterns],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    return [ln for ln in out.splitlines() if ln.strip()]


def _count_lines(paths: list[str]) -> int:
    total = 0
    for p in paths:
        fp = os.path.join(REPO_ROOT, p)
        try:
            with open(fp, "rb") as f:
                total += sum(1 for _ in f)
        except Exception:
            continue
    return total


def _top_dir(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else "(root)"


# ── 워크플로 cron 스케줄 추출 (정규식 — PyYAML 의존 회피) ───────────────


def _extract_crons(yml_path: str) -> list[str]:
    crons: list[str] = []
    try:
        with open(yml_path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return crons
    # `- cron: "M H * * *"` / `cron: 'M H * * *'` 모두 허용
    for m in re.finditer(r"cron:\s*['\"]?([\d*/,\s-]+?)['\"]?\s*(?:#|$)", text, re.M):
        expr = m.group(1).strip()
        if expr:
            crons.append(expr)
    return crons


# ── 라이브 헬스 (기존 산출물 읽기) ─────────────────────────────────────


def _load_json(rel: str):
    fp = os.path.join(REPO_ROOT, rel)
    if not os.path.exists(fp):
        return None
    try:
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _file_age_hours(rel: str):
    fp = os.path.join(REPO_ROOT, rel)
    if not os.path.exists(fp):
        return None
    mtime = os.path.getmtime(fp)
    age_s = now_kst().timestamp() - mtime
    return round(age_s / 3600, 1)


def _latest_investable():
    """실 투자가능 유니버스 수 = wide_scan_log 최신 c_gate_prep input_n (품질 floor 통과).

    5000 은 cap(상한)이지 실제 수가 아님 — floor(시총·거래대금) 통과 전체가 실 유니버스.
    """
    fp = os.path.join(REPO_ROOT, "data", "wide_scan_log.jsonl")
    if not os.path.exists(fp):
        return None
    latest = None
    try:
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("step") == "c_gate_prep" and rec.get("input_n"):
                    latest = rec["input_n"]  # 최신값으로 갱신
    except Exception:
        return latest
    return latest


# ── 맵 구성 ────────────────────────────────────────────────────────────


def build_map() -> dict:
    py = _git_files("*.py")
    tsx = _git_files("*.tsx")
    jsonf = _git_files("*.json")
    ymlf = _git_files(".github/workflows/*.yml", ".github/workflows/*.yaml")

    # 1. ingest — 수집기 (이름 휴리스틱 + 디렉토리). test 경로는 제외 (noise).
    ingest_keys = (
        "collector", "kis_", "dart", "fred", "ecos", "sentiment",
        "macro", "scrape", "naver", "rss", "scout", "pulse",
    )

    def _is_test(p: str) -> bool:
        return p.startswith("tests/") or "/test" in p or os.path.basename(p).startswith("test_")

    ingest = sorted(
        p for p in py
        if not _is_test(p)
        and any(k in os.path.basename(p).lower() for k in ingest_keys)
    )

    # 2. brain — api/intelligence
    brain = sorted(p for p in py if p.startswith("api/intelligence/"))

    # 3. automation — 워크플로 + cron
    workflows = []
    cron_total = 0
    for w in sorted(ymlf):
        crons = _extract_crons(os.path.join(REPO_ROOT, w))
        cron_total += len(crons)
        workflows.append({
            "name": os.path.basename(w).replace(".yml", "").replace(".yaml", ""),
            "crons": crons,
            "scheduled": bool(crons),
        })

    # 4. surface — Framer 컴포넌트, 페이지 그룹별
    surface_groups: dict[str, int] = {}
    for t in tsx:
        # framer-components/pages/<group>/X.tsx → group, 그 외 → 상위 폴더
        parts = t.split("/")
        if "pages" in parts:
            i = parts.index("pages")
            group = parts[i + 1] if i + 1 < len(parts) - 1 else "(pages-root)"
        else:
            group = "/".join(parts[:-1]) or "(root)"
        surface_groups[group] = surface_groups.get(group, 0) + 1

    # 5. data — 발행 데이터 JSON (git 추적)
    data_json = [p for p in jsonf if p.startswith("data/")]

    # 6. validation — n_counter
    n_counter = _load_json("data/metadata/n_counter.json") or {}

    # python 디렉토리 분포
    py_by_dir: dict[str, int] = {}
    for p in py:
        py_by_dir[_top_dir(p)] = py_by_dir.get(_top_dir(p), 0) + 1

    # ── 라이브 헬스 ──
    infra = _load_json("data/infra_status.json") or {}
    freshness = {
        rel: _file_age_hours(rel)
        for rel in (
            "data/price_pulse.json",
            "data/portfolio.json",
            "data/recommendations.json",
            "data/metadata/n_counter.json",
            "data/infra_status.json",
        )
    }

    _inv = _latest_investable()  # 실 투자가능 유니버스 (floor 통과, 5000 cap 아님)

    return {
        "generated_at": now_kst().isoformat(),
        "generator": "scripts/system_map.py",
        "note": "자동 생성. 손수정 금지 — 값은 레포 실제 스캔 결과 (drift 불가).",
        "scale": {
            "code_lines_tsx_py": _count_lines(py + tsx),
            "python_modules": len(py),
            "tsx_components": len(tsx),
            "json_data_files": len(data_json),
            "json_total_tracked": len(jsonf),
            "workflows": len(workflows),
            "scheduled_workflows": sum(1 for w in workflows if w["scheduled"]),
            "cron_triggers": cron_total,
            "git_tracked_files": len(_git_files()),
        },
        "subsystems": {
            "ingest": {
                "label": "수집",
                "count": len(ingest),
                "modules": ingest,
            },
            "brain": {
                "label": "두뇌",
                "count": len(brain),
                "modules": brain,
            },
            "automation": {
                "label": "자동화",
                "count": len(workflows),
                "scheduled": sum(1 for w in workflows if w["scheduled"]),
                "workflows": workflows,
            },
            "surface": {
                "label": "출력",
                "count": len(tsx),
                "by_group": dict(sorted(surface_groups.items(), key=lambda x: -x[1])),
            },
            "data": {
                "label": "데이터",
                "count": len(data_json),
            },
            "validation": {
                "label": "검증",
                "n_trading_days": n_counter.get("n_trading_days"),
                "n_calendar_days": n_counter.get("n_calendar_days"),
                "next_milestone": n_counter.get("next_milestone"),
                "as_of": n_counter.get("as_of"),
            },
        },
        "python_by_dir": dict(sorted(py_by_dir.items(), key=lambda x: -x[1])),
        # Universe funnel — 품질 floor 기반 (5000 = cap 상한, 목표 아님; floor 통과 전체가 정의).
        # 실 투자가능 = wide_scan c_gate input_n (KR ~1,600 + US ~150 fallback). 5000 도달 불가
        # (KR 상장 ~2,700 + US S&P100 fallback). 산식=가설, N=검증 진행 중.
        "funnel": {
            "investable_real": _inv,
            "cap": 5000,
            "stages": [_inv or 0, 300, 100, 25],
            "labels": ["투자가능(floor)", "정밀", "brain100", "Top 25"],
            "status": (
                "5000=cap(상한)·도달 불가. 실 투자가능 ~%s → 25. US=S&P100 fallback "
                "(universe_us.json 부재). 산식=가설, 검증 N 진행 중." % (_inv or "?")
            ),
        },
        "health": {
            "infra_summary": infra.get("summary"),
            "infra_as_of": infra.get("as_of"),
            "file_age_hours": freshness,
        },
    }


def _print_summary(m: dict) -> None:
    s = m["scale"]
    print("=" * 56)
    print("  VERITY 한눈에 보기 — 시스템 맵")
    print(f"  생성: {m['generated_at']}")
    print("=" * 56)
    print(f"  코드 라인 (tsx+py)   {s['code_lines_tsx_py']:>10,}")
    print(f"  Python 모듈          {s['python_modules']:>10,}")
    print(f"  Framer 컴포넌트       {s['tsx_components']:>10,}")
    print(f"  발행 데이터 JSON      {s['json_data_files']:>10,}")
    print(f"  워크플로 (스케줄/cron) {s['workflows']:>3} ({s['scheduled_workflows']}/{s['cron_triggers']})")
    print(f"  git 추적 파일         {s['git_tracked_files']:>10,}")
    print("-" * 56)
    for key, sub in m["subsystems"].items():
        cnt = sub.get("count", sub.get("n_trading_days", "—"))
        print(f"  [{sub['label']:>4}] {key:<12} {cnt}")
    v = m["subsystems"]["validation"]
    print("-" * 56)
    print(f"  검증 N = {v.get('n_trading_days')} 거래일  "
          f"(다음 마일스톤: {v.get('next_milestone')})")
    print("=" * 56)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="파일 미작성, 요약만")
    args = ap.parse_args()

    m = build_map()
    _print_summary(m)

    if args.dry_run:
        print("[dry-run] data/system_map.json 미작성")
        return 0

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    rel = os.path.relpath(OUT_PATH, REPO_ROOT)
    print(f"[ok] {rel} 작성 ({os.path.getsize(OUT_PATH):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
