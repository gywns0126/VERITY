"""
Brain 진화 이력 자동 추적.

git log 의 commit 메시지를 분석해 portfolio["brain_evolution_log"] 갱신.
AdminDashboard (Framer 코드 컴포넌트) 가 이를 fetch 해서 카드로 표시.

대상 commit prefix:
  - feat(brain):  / fix(brain):     → 룰 이식 / 버그 수정
  - feat(observability): / fix(observability):  → 모니터링/검증 변화
  - feat(reports): / fix(reports):  → 리포트 시스템 변화
  - feat(estate): / fix(estate):    → ESTATE 통합

각 카테고리 색상 / 의미는 AdminDashboard 가 결정.

데이터 모델 (portfolio["brain_evolution_log"]):
[
  {
    "sha": "fd17367",
    "date": "2026-04-28",
    "category": "brain",       # brain / observability / reports / estate
    "kind": "feat" | "fix" | "chore",
    "title": "regime_weight — bond_regime → multi_factor 가중치 동적",
    "subject_full": "feat(brain): regime_weight ...",  # 첫 줄 전체
    "author": "Kim Hyojun",
    "lines_added": 71, "lines_deleted": 6,
  },
  ...
]
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 추적 대상 commit 카테고리 (커밋 메시지 프리픽스)
TRACKED_CATEGORIES = ("brain", "observability", "reports", "estate")
# 추적 대상 kind
TRACKED_KINDS = ("feat", "fix", "perf", "refactor")

_PREFIX_RE = re.compile(
    r"^(?P<kind>feat|fix|perf|refactor|chore|docs|test|ci)"
    r"\((?P<category>[a-z_]+)\):\s*(?P<title>.+)$"
)


def _git(args: List[str], cwd: str) -> str:
    try:
        out = subprocess.check_output(["git"] + args, cwd=cwd, text=True,
                                      stderr=subprocess.DEVNULL, timeout=10)
        return out.strip()
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
        logger.warning("brain_evolution: git command failed: %s", e)
        return ""


def collect_evolution_log(repo_root: str, max_count: int = 30) -> List[Dict[str, Any]]:
    """
    repo_root 의 git log 에서 추적 대상 commit 들을 수집.

    Returns: 최신순 list (최대 max_count 개).
    """
    fmt = "%h\x1f%ad\x1f%an\x1f%s"
    raw = _git([
        "log", f"-n{max_count * 5}",  # 필터링 후 부족할 가능성 대비 5x
        "--date=short",
        f"--pretty=format:{fmt}",
    ], cwd=repo_root)
    if not raw:
        return []

    items: List[Dict[str, Any]] = []
    for line in raw.split("\n"):
        parts = line.split("\x1f")
        if len(parts) < 4:
            continue
        sha, date, author, subject = parts[0], parts[1], parts[2], parts[3]
        m = _PREFIX_RE.match(subject)
        if not m:
            continue
        category = m.group("category")
        kind = m.group("kind")
        if category not in TRACKED_CATEGORIES:
            continue
        if kind not in TRACKED_KINDS:
            continue
        # 통계: lines added/deleted
        stat = _git(["show", "--shortstat", "--pretty=format:", sha], cwd=repo_root)
        added, deleted = _parse_shortstat(stat)
        items.append({
            "sha": sha,
            "date": date,
            "author": author,
            "category": category,
            "kind": kind,
            "title": m.group("title").strip(),
            "subject_full": subject,
            "lines_added": added,
            "lines_deleted": deleted,
        })
        if len(items) >= max_count:
            break

    return items


def _parse_shortstat(stat: str) -> tuple:
    """git --shortstat 출력에서 added/deleted 추출."""
    if not stat:
        return 0, 0
    add_m = re.search(r"(\d+) insertions?\(\+\)", stat)
    del_m = re.search(r"(\d+) deletions?\(-\)", stat)
    return (int(add_m.group(1)) if add_m else 0,
            int(del_m.group(1)) if del_m else 0)


def attach_to_portfolio(portfolio: Dict[str, Any],
                       repo_root: Optional[str] = None,
                       max_count: int = 30) -> Dict[str, Any]:
    """portfolio 에 brain_evolution_log 부착. 외부 호출 진입점.

    Args:
        portfolio: in-place 수정
        repo_root: git repo 경로. None 이면 자동 탐지 (이 파일 위치 기준).
        max_count: 보관할 최대 commit 수.

    Returns: portfolio (in-place + 반환)
    """
    if repo_root is None:
        # api/intelligence/brain_evolution.py → 두 단계 위 = repo root
        here = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.abspath(os.path.join(here, "..", ".."))
    try:
        log = collect_evolution_log(repo_root, max_count=max_count)
        portfolio["brain_evolution_log"] = log
        logger.info("brain_evolution: %d entries", len(log))
    except Exception as e:  # noqa: BLE001
        logger.warning("brain_evolution attach failed: %s", e, exc_info=True)
    return portfolio
