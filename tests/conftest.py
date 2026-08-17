"""공통 pytest fixture — DATA_DIR 격리 + 환경변수 초기화."""
import ast
import functools
import importlib
import os
import sys
import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_WRITE_SUFFIX = (".jsonl", ".log")


@functools.lru_cache(maxsize=1)
def _data_write_constants():
    """`api/` 전수에서 `NAME = os.path.join(DATA_DIR, ..., "*.jsonl|log")` 꼴 수집.

    반환 = ((모듈, 상수명, data/ 기준 상대경로), ...). AST 라 import 부작용이 없고,
    lru_cache 로 세션당 1회만 훑는다. `test_no_production_data_writes` 가 같은 탐지를
    쓰며 누락을 검증한다 — 한쪽만 고치면 그 테스트가 실패한다.
    """
    out = []
    for root, _dirs, files in os.walk(os.path.join(_REPO_ROOT, "api")):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(root, fn)
            try:
                tree = ast.parse(open(p, encoding="utf-8").read())
            except (OSError, SyntaxError):
                continue
            for node in tree.body:                       # 모듈 최상위 대입만
                if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                    continue
                tgt = node.targets[0]
                if not isinstance(tgt, ast.Name) or "DATA_DIR" not in ast.dump(node.value):
                    continue
                lits = [n.value for n in ast.walk(node.value)
                        if isinstance(n, ast.Constant) and isinstance(n.value, str)]
                tail = [v for v in lits if str(v).endswith(_WRITE_SUFFIX)]
                if not tail:
                    continue
                # DATA_DIR 뒤에 붙은 리터럴만 이어 상대경로를 만든다 (예: metadata/x.jsonl)
                rel = os.path.join(*[v for v in lits if not v.startswith("/")]) if lits else tail[0]
                mod = os.path.relpath(p, _REPO_ROOT)[:-3].replace(os.sep, ".")
                out.append((mod, tgt.id, rel))
    return tuple(sorted(set(out)))


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    """각 테스트마다 DATA_DIR을 tmp로 바꿔서 실제 data/를 건드리지 않게."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VERITY_MODE", "dev")

    import api.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(cfg, "PORTFOLIO_PATH", str(data_dir / "portfolio.json"))
    monkeypatch.setattr(cfg, "RECOMMENDATIONS_PATH", str(data_dir / "recommendations.json"))
    monkeypatch.setattr(cfg, "HISTORY_PATH", str(data_dir / "history.json"))

    import api.trading.auto_trader as at
    monkeypatch.setattr(at, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(at, "_KILLSWITCH_PATH", str(data_dir / ".auto_trade_paused"))
    monkeypatch.setattr(at, "_HISTORY_PATH", str(data_dir / "auto_trade_history.json"))

    import api.trading.mock_kis_broker as mb
    monkeypatch.setattr(mb, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(mb, "_MOCK_LOG_PATH", str(data_dir / "mock_orders.log"))
    monkeypatch.setattr(mb, "_MOCK_STATE_PATH", str(data_dir / "mock_broker_state.json"))

    import api.notifications.timing_signal_watcher as tw
    monkeypatch.setattr(tw, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(tw, "_STATE_PATH", str(data_dir / ".timing_state.json"))

    # 🚨 2026-08-17 — 이 픽스처가 `cfg.DATA_DIR` 을 갈아도 **모듈이 import 시점에 자기 상수로
    #   복사**해 가면 안 먹힌다. 그래서 스위트가 운영 원장에 실제로 append 했다:
    #     rule_change_log.jsonl  +6행/회 (동일 fx_hedge_regime 이벤트, 전부 같은 초)
    #     backtest_gap.jsonl     +5행/회 (005930 진입가 70000.0/80000.0 · 슬리피지 0.0)
    #     telegram_volume.jsonl  origin/main 2,991행 중 84행이 픽스처 (6/03·8/16·8/17)
    #   소비처에 오퍼레이터 콕핏·novelty 가 있어 관측 표면이 오염됐다.
    #
    #   🚨 **일괄 패치는 기각했다** (2026-08-17 실측). AST 목록 65건을 한꺼번에 갈아끼웠더니
    #   두 곳이 깨졌다: ① `regime_prediction.REGIME_PATH` 는 `prediction_trail` 상수의
    #   **별칭**이라 한쪽만 갈리면 `test_scorer_separate_from_cross_section` 의 동일성 불변이
    #   깨진다 ② telegram 은 `DATA_DIR` 이 아니라 `__file__` 로 경로를 만들어 탐지에서 빠진다.
    #   → 판정 기준을 "경로 상수가 운영을 가리키는가"(65건, 대부분 무해)에서
    #     **"스위트가 실제로 쓰는가"**(7건)로 좁힌다. 실측으로 확인된 자리만 격리한다.
    #   전체 65건 목록은 `test_no_production_data_writes` 가 개수로 추적한다(증가 시 신고).
    metadata_dir = data_dir / "metadata"
    for _mod, _attr, _rel in (
        ("api.vams.fx_hedge_regime", "RULE_LOG_PATH", "metadata/rule_change_log.jsonl"),
        ("api.observability.stoploss_watch", "RULE_LOG_PATH", "metadata/rule_change_log.jsonl"),
        ("api.metadata.backtest_gap", "_PATH", "metadata/backtest_gap.jsonl"),
        ("api.notifications.telegram", "_VOLUME_LEDGER_PATH", "telegram_volume.jsonl"),
        ("api.builders.crypto_collect_builder", "ORDERBOOK_SLIPPAGE_PATH",
         "upbit_orderbook_slippage.jsonl"),
        ("api.builders.crypto_regime_synthesis", "TRAIL_PATH", "crypto_regime_trail.jsonl"),
        ("api.intelligence.multibagger_watch", "_HOLD_PATH", "metadata/multibagger_holdings.jsonl"),
        # 8번째 — jsonl 전수(3,596종)로 넓히고서야 드러났다. 표본을 80종으로 잡았을 때는
        # 안 보였다. LLM 비용 장부라 오염되면 비용 회계가 틀어진다 (RULE 13 분모).
        ("api.metadata.llm_cost", "_PATH", "metadata/llm_cost.jsonl"),
    ):
        try:
            _m = importlib.import_module(_mod)
        except Exception:                                # noqa: BLE001 — import 불가 모듈은 범위 밖
            continue
        if isinstance(getattr(_m, _attr, None), str):
            monkeypatch.setattr(_m, _attr, str(data_dir / _rel))
    # 🚨 디렉터리를 미리 만들지 않는다 — 쓰는 코드가 스스로 `makedirs(exist_ok=True)` 하고,
    #   여기서 만들면 `test_cockpit_aggregate.mock_ledger_dir` 의 `mkdir()`(exist_ok 없음)이
    #   FileExistsError 로 터진다 (2026-08-17 실측, 내가 낸 회귀).

    for k in list(os.environ.keys()):
        if k.startswith("AUTO_TRADE_"):
            monkeypatch.delenv(k, raising=False)

    yield data_dir
