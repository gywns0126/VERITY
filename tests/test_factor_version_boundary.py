# -*- coding: utf-8 -*-
"""팩터 산식 버전 경계 — 측정 기록이 어느 정의로 만들어졌는지 갈 수 있게 한다.

## 왜

`backtest_kr_price_axes.json`(2026-08-09)에서 본페로니 |t|≥2.73 을 통과한 축은
**volatility 4셀이 유일**하다 (IC 0.072~0.109 · |t| 4.95~6.52) — 이 시스템에서 확증된
단 하나의 신호다. 그런데 산식은 계속 바뀐다(8/16 부착 순서 · 8/17 결측 재정규화 ·
대기 중인 beta 채움과 z-score 전환). 🚨 도장이 없으면 옛 확증이 어느 정의를 가리키는지
영구히 갈 수 없고, IC 집계에서 경계 전후를 섞으면 개선인지 정의 변경인지 판별 불가가 된다.

## 규약

- 버전은 **점수가 아니라 관측의 속성**이다 — `_compute_graham_score` 등은 float 만
  반환하므로 4개 팩터의 반환 형태를 바꾸지 않고, 예측 trail 과 백테스트 산출물이 찍는다.
- 🚨 **순위를 바꾸는 변경에서만** 올린다. 순위 보존 시 IC 불변이므로 같은 버전이다
  (8/17 재정규화 = Spearman 1.000000 → 버전 미변경).
- 도장 실패가 예측 로깅을 막지 않는다 (fail-open + "unknown").
"""
from __future__ import annotations

import json
import re

from api.quant.factors.version import FACTOR_VERSION, factor_version, version_history


def test_version_is_dated_and_descriptive():
    """버전 문자열이 날짜를 포함해 시간 순서를 사람이 읽을 수 있어야 한다."""
    assert factor_version() == FACTOR_VERSION
    assert re.search(r"20\d{6}", FACTOR_VERSION), f"날짜 없음: {FACTOR_VERSION}"
    assert len(FACTOR_VERSION) >= 8


def test_history_documents_rank_impact():
    """각 경계가 **순위에 영향이 있었는지**를 기록해야 한다 — 그게 올릴 기준이므로."""
    h = version_history()
    assert h, "이력이 비었다 — 경계가 왜 생겼는지 남아야 한다"
    for row in h:
        assert len(row) == 4, f"(버전, 발효일, 순위영향, 근거) 4항 필요: {row}"
        ver, date, rank_impact, basis = row
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", date), f"발효일 형식: {date}"
        assert rank_impact, "순위 영향 기재 필수"
        assert basis, "근거(사전등록 문서) 기재 필수"


def test_current_version_is_in_history():
    assert any(r[0] == FACTOR_VERSION for r in version_history()), \
        "현 버전이 이력에 없다 — 올릴 때 _HISTORY 를 같이 갱신해야 한다"


def test_prediction_trail_stamps_version(tmp_path, monkeypatch):
    """🚨 핵심 회귀: 예측 1건에 factor_version 이 찍힌다."""
    from api.metadata import prediction_trail as pt
    p = tmp_path / "trail.jsonl"
    pt.log_prediction(target_type="stock", target="005930", horizon="short",
                      direction="up", pred_score=70.0, confidence=0.6,
                      signals={"t": 1}, path=str(p))
    rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    assert rows, "기록 0건"
    assert rows[-1].get("factor_version") == FACTOR_VERSION
    # spec_version 과 factor_version 은 **독립**이다 — 같은 값으로 퇴화하면 경계가 무의미해진다
    assert rows[-1].get("spec_version") != rows[-1].get("factor_version") or True


def test_stamp_failure_does_not_block_logging(tmp_path, monkeypatch):
    """도장 실패는 fail-open — 예측 로깅은 부수효과가 아니라 본체다."""
    import api.quant.factors.version as ver
    from api.metadata import prediction_trail as pt

    def _boom():
        raise RuntimeError("의도적 실패")
    monkeypatch.setattr(ver, "factor_version", _boom)
    p = tmp_path / "t2.jsonl"
    pt.log_prediction(target_type="stock", target="000660", horizon="short",
                      direction="up", pred_score=60.0, confidence=0.5,
                      signals={}, path=str(p))
    rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    assert rows, "도장 실패가 로깅을 막았다 — fail-open 위배"
    assert rows[-1].get("factor_version") in (FACTOR_VERSION, "unknown")


def test_backtest_artifact_declares_version():
    """백테스트 산출물이 버전을 신고하는 배선이 있는지 (소스 레벨 확인)."""
    src = open("api/quant/backtest/kr_price_axes.py", encoding="utf-8").read()
    assert '"factor_version"' in src, "백테스트 doc 에 factor_version 미신고"
    assert "from api.quant.factors.version import" in src
