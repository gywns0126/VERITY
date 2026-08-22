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


MANIFEST_CHECK = os.path.join(ROOT, "scripts", "audit", "build_data_manifest.py")


def test_manifest_three_way():
    """산출물 대장 ↔ 발행 목록 ↔ 무시규칙 3자 대조 (구조 제안 ①).

    C3(계약·SLA 없는 발행물)은 경고라 종료 코드에 반영되지 않는다 — 경성 위반만 실패로 본다.
    """
    r = subprocess.run([sys.executable, MANIFEST_CHECK, "--check"],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, f"대장 3자 대조 위반:\n{r.stdout[-2000:]}"


PANEL = os.path.join(ROOT, "data", "metadata", "kr_fundamental_panel.jsonl")
PANEL_HEALTH = os.path.join(ROOT, "data", "metadata", "kr_fundamental_panel_health.json")


def test_panel_quarter_end_is_calendar_quarter_full_scan():
    """quarter_end 전수 검사 — 계약 검증기는 600행 표본이라 저빈도 오염을 놓친다.

    실측 2026-08-22: 수집일이 quarter_end 로 유입된 201행이 8/12 패널에 남아 있었다
    (72,505 중 0.28%). 빌더 가드가 월("06")만 보고 일을 안 봐서 2026-06-07/15/22/28 이
    통과했다. 표본 600 이면 검출 확률 ~82% — 즉 놓칠 수 있었다. 분모를 전부 본다.
    """
    import json as _json
    if not os.path.exists(PANEL):
        return  # 패널 미생성 환경(CI 경량) — 검증기와 동일하게 스킵
    ok = {"03-31", "06-30", "09-30", "12-31"}
    bad, total = [], 0
    with open(PANEL, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            total += 1
            qe = _json.loads(line)["quarter_end"]
            if len(qe) != 10 or qe[5:] not in ok:
                if len(bad) < 5:
                    bad.append(qe)
    assert total > 0, "패널이 비었다"
    assert not bad, f"달력분기말 아닌 quarter_end (전수 {total}행 중): {bad}"


def test_panel_health_reports_non_calendar_fiscal_exclusion():
    """비12월 결산 제외를 health 가 개수+종목으로 신고하는가 (조용한 손실 차단).

    상류 3a001e283 이 결산월 기준 quarter_end 를 정확히 기록하기 시작한 순간
    패널은 그 13종목을 통째로 잃었다. 신고가 없으면 아무도 모른다.
    """
    import json as _json
    if not os.path.exists(PANEL_HEALTH):
        return
    h = _json.load(open(PANEL_HEALTH, encoding="utf-8"))
    ex = h.get("excluded_non_calendar_fiscal")
    assert isinstance(ex, dict), "health 에 excluded_non_calendar_fiscal 신고가 없다"
    for k in ("rows", "tickers", "ticker_list", "reason"):
        assert k in ex, f"신고 항목 누락: {k}"
    assert len(ex["ticker_list"]) == ex["tickers"], "종목 수와 목록 길이 불일치"
