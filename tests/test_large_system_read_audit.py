from scripts.audit.large_system_read_audit import is_sensitive, ranges_cover


def test_ranges_require_full_contiguous_coverage():
    assert ranges_cover([[1, 50], [51, 100]], 100)
    assert ranges_cover([[51, 100], [1, 75]], 100)
    assert not ranges_cover([[1, 49], [51, 100]], 100)
    assert not ranges_cover([[2, 100]], 100)


def test_sensitive_paths_are_not_hash_targets():
    assert is_sensitive(".env")
    assert is_sensitive("operator-web/.env.local")
    assert is_sensitive("깃허브 복구 키.txt")
    assert not is_sensitive("api/config.py")


def test_local_rules_do_not_restore_retired_project_claims():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    body = "\n".join(p.read_text(encoding="utf-8") for p in (root / ".cursor/rules").glob("*.mdc"))
    assert "raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json" not in body
    assert "#B5FF19" not in body
    assert "Python 3.9+" not in body
