#!/usr/bin/env python3
"""memory_drift_audit — 메모리 ↔ 코드 임계값 일치 자동 검사 (월 1회 cron 권장).

연관:
  - audit BRAIN_SELF_GROWTH P1-5
  - feedback_source_attribution_discipline (출처 명시 의무)
  - 메모리에 기록된 정량 임계값이 실제 코드와 일치하는지 자동 감지
  - drift 발견 시 stderr + (옵션) telegram alert

검사 패턴:
  1. 메모리 본문에서 "임계값 N" 패턴 추출 (e.g., "VAMS_PASS_WIN_RATE 0.55", "AVOID 30")
  2. 해당 코드 위치 검색 (file:line 명시된 메모리)
  3. 코드의 현재 값 vs 메모리의 명시 값 비교
  4. 불일치 시 drift alert

사용:
  python scripts/memory_drift_audit.py                 # console report
  python scripts/memory_drift_audit.py --telegram      # drift 발견 시 push
  python scripts/memory_drift_audit.py --threshold-only
                                                       # 정량 임계만 검사
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
MEMORY_DIR = Path(
    "/Users/macbookpro/.claude/projects/-Users-macbookpro-Desktop--------/memory"
)
LEDGER_PATH = REPO_ROOT / "data" / "metadata" / "memory_drift_audit.jsonl"

# 임계값 패턴 — 메모리 본문에서 자주 등장하는 정량 룰
THRESHOLD_PATTERNS = [
    # config.py 환경변수 형식
    r"`?([A-Z_][A-Z0-9_]+)`?\s*=\s*([0-9.]+)",
    # 사람 가독 형식 (e.g., "VAMS 승률 55%")
    # (정밀도 낮으므로 코드 위치 명시된 항목만 사용)
]

# 코드 file:line 추출
CODE_REF_PATTERN = re.compile(r"`?([a-zA-Z_][\w/]*\.py):(\d+)`?")


def _extract_thresholds(memory_text: str) -> List[Tuple[str, str]]:
    """메모리 본문에서 (변수명, 값) 추출."""
    found = []
    for pattern in THRESHOLD_PATTERNS:
        for m in re.finditer(pattern, memory_text):
            var_name = m.group(1)
            val = m.group(2)
            # config.py 스타일 (대문자 + _) 만 (false positive 회피)
            if var_name.isupper() and "_" in var_name and len(var_name) >= 5:
                found.append((var_name, val))
    return found


def _read_code_value(var_name: str) -> Optional[str]:
    """api/config.py 에서 변수의 현재 값 추출 (단순 grep)."""
    config_path = REPO_ROOT / "api" / "config.py"
    if not config_path.exists():
        return None
    try:
        text = config_path.read_text(encoding="utf-8")
        # 정확한 매칭 패턴: VAR = ... 또는 VAR = _env_*("VAR", DEFAULT)
        m = re.search(rf"^{re.escape(var_name)}\s*=\s*(.+)$", text, re.MULTILINE)
        if not m:
            return None
        # _env_int("X", 30) → "30" 추출
        rhs = m.group(1)
        env_m = re.search(r"_env_\w+\([\"']\w+[\"']\s*,\s*([0-9.\-]+)", rhs)
        if env_m:
            return env_m.group(1)
        # 직접 할당: VAR = 30
        direct_m = re.match(r"\s*([0-9.\-]+)", rhs)
        if direct_m:
            return direct_m.group(1)
        return rhs[:50].strip()
    except Exception:
        return None


def _audit_memory(memory_path: Path) -> List[Dict[str, Any]]:
    """단일 메모리 파일 audit — drift 발견 list 반환."""
    try:
        text = memory_path.read_text(encoding="utf-8")
    except Exception:
        return []
    drifts = []
    thresholds = _extract_thresholds(text)
    for var, mem_val in thresholds:
        code_val = _read_code_value(var)
        if code_val is None:
            continue  # 메모리에만 있고 코드 없음 (참조 정보일 수도)
        # 정량 비교 (float 변환 시도)
        try:
            mem_num = float(mem_val)
            code_num = float(code_val)
            if abs(mem_num - code_num) > 0.001:
                drifts.append({
                    "memory": memory_path.name,
                    "variable": var,
                    "memory_value": mem_val,
                    "code_value": code_val,
                    "diff": round(code_num - mem_num, 4),
                })
        except (ValueError, TypeError):
            # 비-숫자 차이는 별 alert 없음 (단순 문자열 비교 skip)
            if str(mem_val).strip() != str(code_val).strip():
                drifts.append({
                    "memory": memory_path.name,
                    "variable": var,
                    "memory_value": mem_val,
                    "code_value": code_val,
                    "diff": "string_mismatch",
                })
    return drifts


def _log_ledger(drifts: List[Dict[str, Any]], total_memories: int) -> None:
    """audit 결과 ledger 적재 (월 단위 누적)."""
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts_kst": datetime.now().isoformat(),
        "total_memories": total_memories,
        "drift_count": len(drifts),
        "drifts": drifts[:20],  # 너무 큰 list 절단
    }
    with open(LEDGER_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _telegram_alert(drifts: List[Dict[str, Any]]) -> None:
    """drift 발견 시 텔레그램 push (env 있을 때만)."""
    if not drifts:
        return
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from api.notifications.telegram import send_message
        lines = [f"🔔 <b>메모리 drift audit</b>", f"drift {len(drifts)}건 발견:"]
        for d in drifts[:10]:
            lines.append(
                f"  · {d['memory']}: {d['variable']} "
                f"메모리={d['memory_value']} ↔ 코드={d['code_value']}"
            )
        if len(drifts) > 10:
            lines.append(f"  ... +{len(drifts) - 10} 건")
        msg = "\n".join(lines)
        sent = send_message(msg, dedupe=False, bypass_quiet=False)
        sys.stderr.write(f"[memory_drift_audit] telegram sent={sent}\n")
    except Exception as e:
        sys.stderr.write(f"[memory_drift_audit] telegram fail: {e}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="메모리 ↔ 코드 drift 자동 audit")
    parser.add_argument("--telegram", action="store_true", help="drift 발견 시 텔레그램 push")
    parser.add_argument("--threshold-only", action="store_true",
                        help="정량 임계만 검사 (string 차이 무시)")
    args = parser.parse_args()

    if not MEMORY_DIR.exists():
        print(f"[error] MEMORY_DIR 없음: {MEMORY_DIR}", file=sys.stderr)
        return 1

    all_drifts = []
    memory_files = sorted(MEMORY_DIR.glob("*.md"))
    for mf in memory_files:
        if mf.name == "MEMORY.md":
            continue
        drifts = _audit_memory(mf)
        if args.threshold_only:
            drifts = [d for d in drifts if d.get("diff") != "string_mismatch"]
        all_drifts.extend(drifts)

    print(f"=== memory_drift_audit ===")
    print(f"  total memories: {len(memory_files) - 1}")
    print(f"  drifts: {len(all_drifts)}")
    print()
    for d in all_drifts[:20]:
        print(f"  ⚠ {d['memory']}: {d['variable']} "
              f"메모리={d['memory_value']} ↔ 코드={d['code_value']} (diff={d['diff']})")
    if len(all_drifts) > 20:
        print(f"  ... +{len(all_drifts) - 20} 건")

    _log_ledger(all_drifts, len(memory_files) - 1)
    if args.telegram and all_drifts:
        _telegram_alert(all_drifts)

    return 0 if not all_drifts else 1


if __name__ == "__main__":
    sys.exit(main())
