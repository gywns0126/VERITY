# -*- coding: utf-8 -*-
"""스위트가 운영 `data/` 에 쓰지 못하게 한다 — 2026-08-17 실측 사고에서 도출.

## 무슨 일이 있었나

`conftest._isolate_data_dir` 는 `cfg.DATA_DIR` 을 tmp 로 갈아끼운다. 그런데 일부 모듈이
**import 시점에** `os.path.join(DATA_DIR, ...)` 로 자기 모듈 상수를 만들어 두면 그 뒤의
패치가 닿지 않는다. 그래서 격리 픽스처가 있는데도 스위트가 운영 원장에 실제로 append 했다:

| 원장 | 유출량 | 픽스처 지문 |
|---|---|---|
| `data/telegram_volume.jsonl` | origin/main 2,991행 중 **84행** | "동일 본문"·"야간 routine 알림" |
| `data/metadata/rule_change_log.jsonl` | 스위트 1회당 **+6행** | 동일 fx_hedge_regime 이벤트가 같은 초에 6번 |
| `data/metadata/backtest_gap.jsonl` | 스위트 1회당 **+5행** | 005930 진입가 70000.0/80000.0 · 슬리피지 0.0 |

`telegram_volume.jsonl` 소비처에 오퍼레이터 콕핏(`cockpit_aggregate.py`)과 `novelty.py` 가
있어 **관측 표면이 오염**됐다. 6/03·8/16·8/17 에 걸쳐 남아 있었다.

## 이 파일이 하는 것

개별 모듈을 손으로 나열하지 않는다 — **`api/` 를 기계적으로 훑어** 모듈 상수가 `DATA_DIR`
기반 경로로 굳어진 자리를 전부 찾고, 테스트 중 그 상수가 **운영 `data/` 밖**을 가리키는지
확인한다. 새 모듈이 같은 실수를 해도 여기서 걸린다 (분모를 먼저 세는 형태 · RULE 13).
"""
from __future__ import annotations

import ast
import importlib
import os

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REAL_DATA = os.path.realpath(os.path.join(_REPO, "data"))

# 쓰기 계열만 본다 — 읽기 전용 캐시/맵은 오염원이 아니다.
_WRITE_SUFFIX = (".jsonl", ".log")


def _module_path_constants():
    """`api/` 전수에서 `NAME = os.path.join(DATA_DIR, ..., "*.jsonl")` 꼴을 수집.

    반환 = [(모듈경로, 상수명)]. AST 로 읽으므로 import 부작용이 없다.
    """
    found = []
    for root, _dirs, files in os.walk(os.path.join(_REPO, "api")):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(root, fn)
            try:
                tree = ast.parse(open(p, encoding="utf-8").read())
            except (OSError, SyntaxError):
                continue
            for node in tree.body:                      # 모듈 최상위만
                if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                    continue
                tgt = node.targets[0]
                if not isinstance(tgt, ast.Name):
                    continue
                src = ast.dump(node.value)
                if "DATA_DIR" not in src:
                    continue
                lits = [n.value for n in ast.walk(node.value)
                        if isinstance(n, ast.Constant) and isinstance(n.value, str)]
                if not any(str(v).endswith(_WRITE_SUFFIX) for v in lits):
                    continue
                mod = os.path.relpath(p, _REPO)[:-3].replace(os.sep, ".")
                found.append((mod, tgt.id))
    return sorted(set(found))


def test_write_path_constants_are_enumerable():
    """분모 자기신고 — 대상이 0이면 탐지 정규식 자체를 의심해야 한다."""
    consts = _module_path_constants()
    assert consts, "DATA_DIR 기반 쓰기 경로 상수를 하나도 못 찾음 — AST 탐지를 의심할 것"
    # 8/17 실측 3건(fx_hedge_regime·stoploss_watch·backtest_gap)이 최소선.
    assert len(consts) >= 3, f"탐지 {len(consts)}건 — 8/17 실측 3건 대비 급감"


def test_production_pointing_constants_do_not_grow():
    """운영 경로를 가리키는 쓰기 상수 **개수**를 추적한다 (전부 0 으로 만들지는 않는다).

    🚨 전수 격리는 실측으로 기각했다 (2026-08-17). 65건을 일괄 패치해보니 두 곳이 깨졌다:
      ① `regime_prediction.REGIME_PATH` 는 `prediction_trail` 상수의 **별칭**이라 한쪽만
         갈리면 두 모듈이 같은 파일을 봐야 하는 불변이 깨진다
         (`test_scorer_separate_from_cross_section`). 별칭 관계는 AST 로 알 수 없다.
      ② telegram 은 `DATA_DIR` 이 아니라 `__file__` 로 경로를 만들어 탐지에서 아예 빠진다.
      ③ 대부분은 테스트 중 실행되지 않아 실제 오염을 만들지 않는다.

    그래서 하드 게이트는 아래 `test_known_offenders_are_isolated`(실측으로 확인된 자리) +
    스위트 전후 해시 실측이 담당하고, 여기서는 모집단 크기만 본다 — 늘어나면 새 원장이
    생긴 것이므로 실제로 쓰는지 확인이 필요하다. 실측 기준선 = 2026-08-17 · 탐지 67 · 지목 65.
    """
    offenders = []
    for mod, name in _module_path_constants():
        try:
            m = importlib.import_module(mod)
        except Exception:                                # noqa: BLE001 — import 불가 모듈은 범위 밖
            continue
        val = getattr(m, name, None)
        if not isinstance(val, str):
            continue
        if os.path.realpath(val).startswith(_REAL_DATA):
            offenders.append(f"{mod}.{name} → {val}")
    assert len(offenders) <= 70, (
        "운영 경로 지목 쓰기 상수 "
        f"{len(offenders)}건 — 8/17 기준선 65 대비 증가. 새 자리가 스위트 중 실제로 쓰이는지"
        " 해시로 실측하고, 쓴다면 conftest `_isolate_data_dir` 목록에 추가할 것:\n  "
        + "\n  ".join(offenders[-8:])
        + "\n  → tests/conftest.py `_isolate_data_dir` 에 monkeypatch 를 추가할 것.")


@pytest.mark.parametrize("mod,name", [
    ("api.vams.fx_hedge_regime", "RULE_LOG_PATH"),
    ("api.observability.stoploss_watch", "RULE_LOG_PATH"),
    ("api.metadata.backtest_gap", "_PATH"),
    ("api.notifications.telegram", "_VOLUME_LEDGER_PATH"),
])
def test_known_offenders_are_isolated(mod, name):
    """8/17 에 실제로 유출한 4자리를 이름으로 고정한다 (AST 탐지가 놓쳐도 여기서 잡힌다)."""
    m = importlib.import_module(mod)
    val = getattr(m, name)
    assert not os.path.realpath(val).startswith(_REAL_DATA), (
        f"{mod}.{name} 가 운영 경로({val}) — 8/17 유출 재발")
