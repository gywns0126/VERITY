# -*- coding: utf-8 -*-
"""데이터 계약 회귀 가드 — data_contract_check 를 pytest 로 상설화.

계약 파일 존재 + 실물 정합(exit 0)을 CI/로컬 공통으로 강제한다.
대상 파일이 없는 환경에서는 검증기가 스스로 스킵(경고)하므로 테스트는 항상 실행 가능.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKER = os.path.join(ROOT, "scripts", "audit", "data_contract_check.py")


def test_contract_files_exist():
    cdir = os.path.join(ROOT, "data", "contracts")
    names = sorted(f for f in os.listdir(cdir) if f.endswith(".contract.json"))
    assert "kr_valuation_panel.contract.json" in names
    assert "kr_fundamental_panel.contract.json" in names
    assert "factor_engine_artifact.contract.json" in names


def test_contracts_hold():
    r = subprocess.run([sys.executable, CHECKER], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"계약 위반:\n{r.stdout[-2000:]}"
