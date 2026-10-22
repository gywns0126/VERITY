"""Offline tests: synthetic config and transports; never import server.main."""
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


SOURCE = Path(__file__).resolve().parents[1] / "server" / "kis_ws_client.py"


class DisabledWebSocketTests(unittest.TestCase):
    def setUp(self):
        config = ModuleType("server.config")
        for name, value in {
            "KIS_APP_KEY": "synthetic-app",
            "KIS_APP_SECRET": "synthetic-secret",
            "KIS_BASE_URL": "https://kis.invalid",
            "KIS_WS_URL": "wss://kis.invalid",
            "MAX_CANDLE_MINUTES": 240,
            "MAX_SUBS": 20,
        }.items():
            setattr(config, name, value)
        requests = ModuleType("requests")
        requests.post = Mock(side_effect=AssertionError("No real HTTP allowed"))
        websocket = ModuleType("websocket")
        websocket.WebSocketApp = Mock()
        spec = importlib.util.spec_from_file_location("isolated_kis_ws", SOURCE)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"server.config": config,
                                      "requests": requests, "websocket": websocket}):
            spec.loader.exec_module(self.module)
        self.client = self.module.KISWebSocketClient()

    def test_explicit_false_and_invalid_values_disable(self):
        for value in ("0", "false", "off", "no", "", " ", "typo", "2"):
            with self.subTest(value=value), patch.dict(os.environ, {"KIS_WS_ENABLED": value}):
                self.assertFalse(self.module._ws_enabled())

    def test_unset_and_explicit_true_preserve_existing_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(self.module._ws_enabled())
        for value in ("1", "true", "yes", "on", " TRUE "):
            with self.subTest(value=value), patch.dict(os.environ, {"KIS_WS_ENABLED": value}):
                self.assertTrue(self.module._ws_enabled())

    def test_disabled_start_creates_no_thread(self):
        self.client._should_run = True
        with patch.dict(os.environ, {"KIS_WS_ENABLED": "0"}), \
                patch.object(self.module.threading, "Thread") as thread:
            self.client.start()
        thread.assert_not_called()
        self.assertFalse(self.client._should_run)

    def test_disabled_connect_does_not_read_key_or_create_socket(self):
        self.client._should_run = True
        with patch.dict(os.environ, {"KIS_WS_ENABLED": "0"}), \
                patch.object(self.client, "_get_approval_key") as get_key:
            self.client._connect()
        get_key.assert_not_called()
        self.module.websocket.WebSocketApp.assert_not_called()
        self.module.requests.post.assert_not_called()
        self.assertFalse(self.client._should_run)

    def test_disabled_approval_denies_cache_and_force(self):
        self.client._approval_key = "synthetic-cached-approval"
        self.client._approval_key_issued_at = self.module.time.time()
        with patch.dict(os.environ, {"KIS_WS_ENABLED": "0"}), \
                patch.object(self.client, "_load_cached_approval_key") as read_cache, \
                patch.object(self.client, "_save_cached_approval_key") as save_cache:
            for force in (False, True):
                with self.subTest(force=force), self.assertRaisesRegex(RuntimeError, "disabled"):
                    self.client._get_approval_key(force=force)
        read_cache.assert_not_called()
        save_cache.assert_not_called()
        self.module.requests.post.assert_not_called()

    def test_disabled_close_stops_reconnect_without_sleep(self):
        self.client._should_run = True
        with patch.dict(os.environ, {"KIS_WS_ENABLED": "0"}), \
                patch.object(self.module.time, "sleep") as sleep, \
                patch.object(self.client, "_connect") as connect:
            self.client._on_close(None, 1000, "synthetic-close")
        sleep.assert_not_called()
        connect.assert_not_called()
        self.assertFalse(self.client._should_run)

    def test_enabled_connect_retains_fake_transport_flow(self):
        with patch.dict(os.environ, {"KIS_WS_ENABLED": "1"}), \
                patch.object(self.client, "_get_approval_key", return_value="synthetic") as get_key:
            self.client._connect()
        get_key.assert_called_once_with()
        self.module.websocket.WebSocketApp.assert_called_once()
        self.module.websocket.WebSocketApp.return_value.run_forever.assert_called_once_with(
            ping_interval=30, ping_timeout=10)
        self.module.requests.post.assert_not_called()

    def test_enabled_start_retains_thread_flow(self):
        with patch.dict(os.environ, {"KIS_WS_ENABLED": "1"}), \
                patch.object(self.module.threading, "Thread") as thread:
            self.client.start()
        thread.assert_called_once_with(target=self.client._connect, daemon=True)
        thread.return_value.start.assert_called_once_with()
        self.assertTrue(self.client._should_run)


if __name__ == "__main__":
    unittest.main()
