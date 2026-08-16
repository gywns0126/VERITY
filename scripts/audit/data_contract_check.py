# -*- coding: utf-8 -*-
"""data_contract_check — 데이터 계약 검증기 (구조 재검증 2026-08-16 후 시행).

왜: 하중을 싣는 데이터 의미론(무수정 종가·PIT +45일·dy 지급자 한정)이 빌더 독스트링에만
있으면 소비자는 읽지 않고 가정한다 — 8/16 무수정 종가 사고가 실증. 계약 파일이 의미론의
SoT 사본을 들고, 이 검증기가 실물과의 정합을 기계로 잰다.

검사: data/contracts/*.contract.json 전수 →
  jsonl 패널 = 표본(머리 300 + 꼬리 300) 필수 필드·형식·부호 검증
  json 산출물 = _meta 필수 키 + score_system.is_operational=false
파일 부재 = 경고(레이크·타 환경 허용), 계약 위반 = exit 1.
산출: data/metadata/data_contract_report.json (자기신고, RULE 12)
사용: python3 scripts/audit/data_contract_check.py  (pytest 래퍼 = tests/test_data_contracts.py)
"""
from __future__ import annotations

import glob
import json
import numbers
import os
import re
import sys
from collections import deque
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONTRACTS_DIR = os.path.join(ROOT, "data", "contracts")
REPORT = os.path.join(ROOT, "data", "metadata", "data_contract_report.json")
SAMPLE_N = 300

issues: list[str] = []
warns: list[str] = []


def _sample_rows(path: str) -> list[dict]:
    head: list[dict] = []
    tail: deque = deque(maxlen=SAMPLE_N)
    with open(path, encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                issues.append(f"{os.path.basename(path)}: line {i+1} JSON 파싱 실패")
                continue
            if len(head) < SAMPLE_N:
                head.append(row)
            else:
                tail.append(row)
    return head + list(tail)


def _check_jsonl(contract: dict, path: str) -> dict:
    name = os.path.basename(path)
    rules = contract.get("validation_rules", {})
    nullable = set(rules.get("nullable", []))
    regexes = {k: re.compile(v) for k, v in rules.get("field_regex", {}).items()}
    non_neg = set(rules.get("non_negative", []))
    required = list(contract.get("required_fields", {}))

    rows = _sample_rows(path)
    if not rows:
        issues.append(f"{name}: 표본 0행 — 빈 파일?")
        return {"sampled": 0}

    bad_missing: dict[str, int] = {}
    bad_fmt: dict[str, int] = {}
    bad_neg: dict[str, int] = {}
    for row in rows:
        for k in required:
            v = row.get(k, "__ABSENT__")
            if v == "__ABSENT__" or v is None:
                if k not in nullable:
                    bad_missing[k] = bad_missing.get(k, 0) + 1
                continue
            rx = regexes.get(k)
            if rx and not rx.match(str(v)):
                bad_fmt[k] = bad_fmt.get(k, 0) + 1
            if k in non_neg and isinstance(v, numbers.Number) and v < 0:
                bad_neg[k] = bad_neg.get(k, 0) + 1
    for k, n in bad_missing.items():
        issues.append(f"{name}: 필수 필드 '{k}' 부재 {n}/{len(rows)}행")
    for k, n in bad_fmt.items():
        issues.append(f"{name}: '{k}' 형식 위반 {n}/{len(rows)}행 (규칙 {regexes[k].pattern})")
    for k, n in bad_neg.items():
        issues.append(f"{name}: '{k}' 음수 {n}/{len(rows)}행 (non_negative 규칙)")
    return {"sampled": len(rows),
            "violations": sum(bad_missing.values()) + sum(bad_fmt.values()) + sum(bad_neg.values())}


def _check_artifact(contract: dict, path: str) -> dict:
    name = os.path.basename(path)
    try:
        obj = json.load(open(path, encoding="utf-8"))
    except ValueError as e:
        issues.append(f"{name}: JSON 파싱 실패 {e}")
        return {}
    meta = obj.get("_meta", {})
    missing = [k for k in contract.get("required_meta_keys", []) if k not in meta]
    if missing:
        issues.append(f"{name}: _meta 필수 키 부재 {missing}")
    if contract.get("validation_rules", {}).get("score_system_is_operational_must_be_false"):
        ss = meta.get("score_system")
        op = ss.get("is_operational") if isinstance(ss, dict) else None
        if op is not False and not (isinstance(ss, str) and "비운영" in ss):
            issues.append(f"{name}: score_system 비운영 자기신고 부재/훼손 (is_operational={op!r})")
    return {"meta_keys": len(meta), "missing": len(missing)}


def main() -> int:
    contracts = sorted(glob.glob(os.path.join(CONTRACTS_DIR, "*.contract.json")))
    if not contracts:
        print("계약 0건 — data/contracts/*.contract.json 부재")
        return 1
    stats: dict[str, dict] = {}
    for cpath in contracts:
        contract = json.load(open(cpath, encoding="utf-8"))
        target = os.path.join(ROOT, contract["file"])
        cname = os.path.basename(cpath)
        if not os.path.exists(target):
            warns.append(f"{cname}: 대상 파일 부재 ({contract['file']}) — 이 환경엔 없음, 스킵")
            stats[cname] = {"skipped": True}
            continue
        if contract.get("format", "jsonl").startswith("json ") or contract.get("format") == "json (jsonl 아님)":
            stats[cname] = _check_artifact(contract, target)
        else:
            stats[cname] = _check_jsonl(contract, target)

    print("═" * 60)
    print(f"데이터 계약 검증 — 계약 {len(contracts)}건")
    for cname, st in stats.items():
        print(f"  {cname}: {st}")
    for w in warns:
        print(f"  ⚠ {w}")
    if issues:
        print(f"\n🚨 위반 {len(issues)}:")
        for i in issues:
            print(f"  ✗ {i}")
    else:
        print("\n위반 0 — 계약 정합 ✓")

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    json.dump({"_meta": {"artifact": "data_contract_report",
                         "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                         "contracts": len(contracts)},
               "stats": stats, "issues": issues, "warns": warns},
              open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
