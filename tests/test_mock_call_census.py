"""mock 호출 census — prod 전환 시 늘어날 유료 실호출 건수 측정 도구.

2026-07-27. daily_realtime / daily_analysis 에 VERITY_MODE 가 없어 기본값 dev 로 도는데,
prod 로 켰을 때의 비용 델타를 알 방법이 없었음. 기존 logger.info 는 루트 로거 WARNING
레벨이라 GH Actions 로그에서 억제됨(실측 INFO 라인 0건) → 집계 + 종료 시 출력.
"""
import api.config as config
import api.mocks as mocks


def _reset():
    mocks._MOCK_CENSUS.clear()


def test_dev_mode_counts_every_mocked_call(monkeypatch):
    _reset()
    monkeypatch.setattr(config, "VERITY_MODE", "dev")

    @mocks.mockable("gemini.stock_analysis")
    def _f():
        raise AssertionError("dev 에서 실호출되면 안 됨")

    _f(); _f(); _f()
    assert mocks.mock_call_census() == {"gemini.stock_analysis": 3}


def test_prod_mode_records_nothing_and_calls_real(monkeypatch):
    _reset()
    monkeypatch.setattr(config, "VERITY_MODE", "prod")
    hits = []

    @mocks.mockable("gemini.stock_analysis")
    def _f():
        hits.append(1)
        return "real"

    assert _f() == "real"
    assert hits == [1]
    assert mocks.mock_call_census() == {}     # prod = 측정 대상 아님


def test_staging_counts_only_mocked_keys(monkeypatch):
    _reset()
    monkeypatch.setattr(config, "VERITY_MODE", "staging")
    monkeypatch.setattr(config, "VERITY_STAGING_REAL_KEYS", frozenset({"gemini.daily_report"}))
    real = []

    @mocks.mockable("gemini.daily_report")
    def _allowed():
        real.append(1)
        return "real"

    @mocks.mockable("claude.deep")
    def _blocked():
        raise AssertionError("allowlist 밖은 실호출되면 안 됨")

    _allowed(); _blocked(); _blocked()
    assert real == [1]
    assert mocks.mock_call_census() == {"claude.deep": 2}


def test_census_print_is_silent_in_prod(monkeypatch, capsys):
    _reset()
    mocks._MOCK_CENSUS["claude.deep"] = 5
    monkeypatch.setattr(config, "VERITY_MODE", "prod")
    mocks._print_mock_census()
    assert capsys.readouterr().out == ""


def test_census_print_lists_keys_desc(monkeypatch, capsys):
    _reset()
    monkeypatch.setattr(config, "VERITY_MODE", "dev")
    mocks._MOCK_CENSUS.update({"claude.deep": 2, "gemini.stock_analysis": 9})
    mocks._print_mock_census()
    out = capsys.readouterr().out
    assert "MOCK CENSUS" in out and "11건" in out
    assert out.index("gemini.stock_analysis") < out.index("claude.deep")   # 내림차순


def test_empty_census_prints_nothing(monkeypatch, capsys):
    _reset()
    monkeypatch.setattr(config, "VERITY_MODE", "dev")
    mocks._print_mock_census()
    assert capsys.readouterr().out == ""
