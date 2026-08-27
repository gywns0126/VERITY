"""만료된 알파콘솔 세션이 공유 IP 차단으로 번지는 회귀 방지."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "vercel-api" / "api" / "admin.py"


def test_admin_unauthorized_is_observation_only() -> None:
    source = ADMIN.read_text(encoding="utf-8")
    start = source.index("def _sec_note_unauthorized(")
    end = source.index("\n\ndef handle_security", start)
    body = source[start:end]

    assert "security_probe_log" in body
    assert 'rest/v1/blocked_ips' not in body
    assert "_sec_blocked.add" not in body
