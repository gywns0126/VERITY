"""공통 pytest fixture — DATA_DIR 격리 + 환경변수 초기화."""
import os
import sys
import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


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

    for k in list(os.environ.keys()):
        if k.startswith("AUTO_TRADE_"):
            monkeypatch.delenv(k, raising=False)

    yield data_dir
