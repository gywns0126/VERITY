"""Only isolated function ASTs run; all I/O and threads are synthetic."""
import ast
import __future__
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


SOURCE = Path(__file__).resolve().parents[1] / "server" / "security.py"


class SecurityStartupStatusTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name in ("_refresh_blocklist", "start_security")]
        self.assertEqual(len(functions), 2)
        self.response = SimpleNamespace(status_code=200, json=Mock(return_value=[]))
        self.request = Mock(return_value=self.response)
        self.logger = Mock()
        self.thread = Mock()
        self.ns = {
            "SUPABASE_URL": "https://synthetic.invalid",
            "SUPABASE_KEY": "synthetic-server-key",
            "requests": SimpleNamespace(get=self.request),
            "time": SimpleNamespace(time=lambda: 1),
            "_iso": lambda value: "2026-01-01T00:00:00+00:00",
            "logger": self.logger,
            "threading": SimpleNamespace(Thread=self.thread),
            "_bg_refresher": Mock(),
            "SecurityMiddleware": object(),
            "BLOCK_ENABLED": True,
            "AUTO_BLOCK_THRESHOLD": 3,
            "BLOCK_TTL_SEC": 86400,
            "_sb_headers": lambda: {"apikey": "synthetic-server-key"},
        }
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec",
                     flags=__future__.annotations.compiler_flag), self.ns)

    def test_success_reports_status_without_extra_request(self):
        self.ns["start_security"](Mock())
        self.request.assert_called_once()
        self.response.json.assert_called_once_with()
        self.logger.info.assert_any_call("security Supabase startup read status=%s", 200)
        self.thread.return_value.start.assert_called_once_with()

    def test_auth_failure_reports_only_status_not_response_body(self):
        self.response.status_code = 401
        self.ns["start_security"](Mock())
        self.request.assert_called_once()
        self.response.json.assert_not_called()
        self.logger.info.assert_any_call("security Supabase startup read status=%s", 401)

    def test_missing_configuration_does_not_query(self):
        self.ns["SUPABASE_KEY"] = ""
        self.ns["start_security"](Mock())
        self.request.assert_not_called()
        self.logger.info.assert_any_call("security Supabase startup read status=%s", None)


if __name__ == "__main__":
    unittest.main()
