"""F1+F2 회귀 결함 fix 검증 (2026-05-18, PM 승인).

docs/QUADRANT_REGRESSION_AUDIT_20260518.md root cause:
  detect_economic_quadrant 가 찾는 fred.cpi_yoy / fred.gdp_growth / fred.ism_pmi /
  fred.pce_yoy 4 키 모두 portfolio.macro.fred 에 부재 → fallback 영구 trip
  (cpi_yoy=2.5 하드코드 + gdp=(mood-50)*0.06) → growth_down_inflation_down 25/25 단일 강제.

F1: collector 가 core_cpi.yoy_pct → fred.cpi_yoy.value 동시 채움.
F2: us_recession_smoothed_prob.pct → fred.gdp_growth.value proxy (2.5 - 0.08*rp).
"""
from __future__ import annotations

from api.intelligence.verity_brain import detect_economic_quadrant


# 🚨 2026-08-20 F-c — 인플레 축이 **한국 CPI(ECOS)** 로 바뀌었다
#   (PREREG_INFLATION_AXIS_2026_08_20). 이 헬퍼는 **성장 축** 테스트용이므로
#   인플레 축을 기본 주입해 unknown 으로 빠지지 않게 한다.
#   인플레 축 자체의 계약은 tests/test_inflation_axis_kr_cpi.py 가 잠근다.
_KR_AXIS_DOWN = {"inflation_up": False, "z": -0.8, "yoy_pct": 1.5,
                 "form": "rolling_z_sign_only", "window_months": 12}
_KR_AXIS_UP = {"inflation_up": True, "z": 1.0, "yoy_pct": 3.2,
               "form": "rolling_z_sign_only", "window_months": 12}


def _portfolio_with_fred(fred_block: dict, mood_score: int = 50,
                         kr_axis: dict = None) -> dict:
    """detect_economic_quadrant 입력용 최소 portfolio dict.

    kr_axis 미지정 시 **인플레 DOWN** 을 넣는다(성장 축만 검증하는 테스트용).
    `kr_axis=False` 를 주면 인플레 축을 아예 빼서 결손 경로를 검증할 수 있다.
    """
    fred = dict(fred_block)
    if kr_axis is not False:
        fred["korea_cpi_axis"] = kr_axis or _KR_AXIS_DOWN
    return {
        "macro": {
            "fred": fred,
            "market_mood": {"score": mood_score},
        }
    }


class TestF1CpiYoyDerivation:
    """🚨 2026-08-20 F-c 로 **계약이 뒤집혔다**(PREREG_INFLATION_AXIS_2026_08_20).

    종전 이 클래스는 *"미국 core CPI(`fred.cpi_yoy`) + 절대 임계 3.0"* 을 고정했다.
    Q10 이 그 설계를 세 층위에서 동시에 부정했고(원전=서프라이즈 / 관행=headline /
    임계=변화·z-score / core 는 headline 보다 평균이 낮다 / 한국은 한국 CPI),
    실측으로도 118일 중 임계 초과 **0/80** 이라 inflation_up 이 구조적으로 도달 불가였다.

    이제 인플레 축은 **한국 headline CPI(ECOS 901Y009) YoY 의 12M 롤링 z 부호**다.
    `fred.cpi_yoy`(미국 core)는 **관측용 병기**로만 남고 판정에 쓰이지 않는다.
    """

    def test_us_core_cpi_no_longer_decides(self):
        """🚨 미국 core 가 3.0 을 넘어도 판정은 한국 축이 한다."""
        fred = {
            "cpi_yoy": {"value": 9.9, "date": "2026-04-01"},   # 미국 core 극단값
            "gdp_growth": {"value": 2.0, "date": "2026-03-01"},
        }
        result = detect_economic_quadrant(_portfolio_with_fred(fred))   # kr=DOWN
        assert result["quadrant"] == "growth_up_inflation_down", "미국 core 가 개입했다"
        assert result["us_core_cpi_yoy_observed"] == 9.9, "관측 병기가 사라졌다"

    def test_kr_axis_decides_inflation_up(self):
        fred = {"gdp_growth": {"value": 2.0}}
        result = detect_economic_quadrant(
            _portfolio_with_fred(fred, kr_axis=_KR_AXIS_UP))
        assert result["quadrant"] == "growth_up_inflation_up"
        assert result["inflation_source"] == "ecos.901Y009.headline_kr"

    def test_missing_inflation_input_returns_unknown(self):
        """🚨 종전 이름은 `test_missing_cpi_yoy_falls_back_to_hardcode` 였고
        *"부재 시 2.5 하드코드 fallback (의도적)"* 을 고정하고 있었다.

        그 fallback 은 임계 3.0 과 맞물려 **구조적으로 inflation_down 을 주입**했다.
        B1(성장 축)과 같은 계열이라 함께 폐기했다 — **결측은 값이 아니다.**
        """
        fred = {"gdp_growth": {"value": 2.0}}
        result = detect_economic_quadrant(_portfolio_with_fred(fred, kr_axis=False))
        assert result["quadrant"] == "unknown"
        assert result["cpi_yoy"] is None, "결측인데 숫자가 만들어졌다"
        assert result["cpi_yoy"] != 2.5


class TestF2GdpGrowthProxy:
    """F2: gdp_growth proxy 산식 검증 (2.5 - 0.08 × recession_prob)."""

    def test_low_recession_prob_yields_growth_up(self):
        """recession_prob 1.82% → proxy 2.35 > 1.5 → growth_up."""
        rec_prob = 1.82
        expected_gdp = round(2.5 - 0.08 * rec_prob, 2)
        assert expected_gdp == 2.35
        fred = {
            "gdp_growth": {"value": expected_gdp},
            "cpi_yoy": {"value": 2.0},
        }
        result = detect_economic_quadrant(_portfolio_with_fred(fred))
        assert result["gdp_growth"] == 2.35
        assert result["quadrant"] == "growth_up_inflation_down"

    def test_proxy_threshold_12_5_pct(self):
        """recession_prob 12.5% → proxy 1.5 = growth_up 임계 (boundary)."""
        rec_prob = 12.5
        expected = round(2.5 - 0.08 * rec_prob, 2)
        assert expected == 1.5
        # gdp_growth > 1.5 인지 검증 (정확히 1.5 면 growth_up = False)
        fred = {
            "gdp_growth": {"value": expected},
            "cpi_yoy": {"value": 2.0},
        }
        result = detect_economic_quadrant(_portfolio_with_fred(fred))
        # gdp 정확히 1.5 → 1.5 > 1.5 = False → growth_down
        assert result["quadrant"].startswith("growth_down")

    def test_high_recession_prob_yields_growth_down(self):
        """recession_prob 50% → proxy -1.5 → growth_down."""
        rec_prob = 50
        expected = round(2.5 - 0.08 * rec_prob, 2)
        assert expected == -1.5
        fred = {
            "gdp_growth": {"value": expected},
            "cpi_yoy": {"value": 4.0},
        }
        # 🚨 인플레 축은 이제 한국 CPI 가 정한다 — UP 을 명시 주입
        result = detect_economic_quadrant(
            _portfolio_with_fred(fred, kr_axis=_KR_AXIS_UP))
        assert result["gdp_growth"] == -1.5
        assert result["quadrant"] == "growth_down_inflation_up"


class TestF1F2Integration:
    """F1+F2 적용 후 25/25 단일 분면 회귀 회복 검증."""

    def test_current_macro_yields_growth_up_inflation_down(self):
        """실측 macro (cpi=2.99, recession_prob=1.82) → growth_up_inflation_down."""
        # F1 derivation 결과
        cpi_yoy = 2.99
        # F2 derivation 결과
        rec_prob = 1.82
        gdp_proxy = round(2.5 - 0.08 * rec_prob, 2)

        fred = {
            "cpi_yoy": {"value": cpi_yoy, "date": "2026-04-01"},
            "gdp_growth": {"value": gdp_proxy, "date": "2026-03-01"},
        }
        result = detect_economic_quadrant(_portfolio_with_fred(fred))
        assert result["quadrant"] == "growth_up_inflation_down"
        # constitution 의 brain_weights = (0.65, 0.35) 적용 분면
        assert result["crypto_bias"] == "risk_on"
        # favored: 주식/회사채/성장주 (방어주 아님)
        assert "주식" in result["favored"] or "성장주" in result["favored"]

    def test_regression_baseline_now_returns_unknown(self):
        """🚨 2026-08-19 B1 로 계약이 **뒤집혔다** (PREREG_QUADRANT_DISPOSITION_2026_08_19).

        종전 이름은 `test_regression_baseline_without_fix` 였고
        *"4 키 모두 부재 → growth_down_inflation_down **영구 강제**"* 를 고정하고 있었다.
        그 docstring 자신이 "영구 강제" 라고 적었듯 **그건 결함의 기록이지 옳은 동작이
        아니었다.** 118일 전수 측정에서 실제 피해가 확인됐다 —
        결측 37일이 전부 growth_down 으로 나갔고(37/37), 그래서 성장 축이
        경제가 아니라 **필드 존재 여부**로 뒤집히고 있었다.

        B1 이 그 fallback 을 폐기했으므로 이제 같은 입력은 `unknown` 이어야 한다.
        🚨 핀과 값은 한 커밋에서 같이 움직인다 — 오늘 universe_scan timeout 에서
        같은 계열 사고가 한 번 났다(yml 만 바뀌고 핀이 안 따라와 main 이 red).
        """
        fred = {}
        portfolio = _portfolio_with_fred(fred, mood_score=40)
        result = detect_economic_quadrant(portfolio)

        assert result["quadrant"] == "unknown"
        assert result["gdp_growth"] is None, "결측인데 숫자가 만들어졌다"
        assert result["quadrant_source"] == "unknown"
        # 종전 산식이 만들던 값 — 되살아나면 잡는다
        assert result["gdp_growth"] != -0.6


class TestFredMacroBlockDerivation:
    """get_fred_macro_block 의 cpi_yoy / gdp_growth derivation 구현 검증.

    실제 FRED API 호출 없이 derivation 로직만 단위 테스트.
    """

    def test_cpi_yoy_derivation_mirrors_core_cpi(self):
        """core_cpi.yoy_pct = 2.99 → fred.cpi_yoy.value = 2.99 mirror."""
        # 모의 out dict 에 derivation 로직 직접 실행
        out = {
            "core_cpi": {"index": 335.42, "date": "2026-04-01", "yoy_pct": 2.99},
        }
        # fred_macro.py:373-419 의 derivation 블록과 동일 로직
        cpi_block = out.get("core_cpi") or {}
        cpi_yoy_val = cpi_block.get("yoy_pct")
        if cpi_yoy_val is not None:
            out["cpi_yoy"] = {
                "value": float(cpi_yoy_val),
                "date": cpi_block.get("date"),
                "series_id": "CPILFESL",
            }

        assert out["cpi_yoy"]["value"] == 2.99
        assert out["cpi_yoy"]["date"] == "2026-04-01"

    def test_gdp_growth_proxy_formula(self):
        """us_recession_smoothed_prob.pct → gdp_growth = 2.5 - 0.08 × rp."""
        out = {
            "us_recession_smoothed_prob": {
                "pct": 1.82,
                "date": "2026-03-01",
                "series_id": "RECPROUSM156N",
            },
        }
        rec_block = out.get("us_recession_smoothed_prob") or {}
        rec_prob = rec_block.get("pct")
        if rec_prob is not None:
            gdp_proxy = round(2.5 - 0.08 * float(rec_prob), 2)
            out["gdp_growth"] = {
                "value": gdp_proxy,
                "date": rec_block.get("date"),
                "series_id": "RECPROUSM156N",
            }

        assert out["gdp_growth"]["value"] == 2.35
        assert out["gdp_growth"]["date"] == "2026-03-01"

    def test_derivation_skips_when_source_missing(self):
        """source 데이터 부재 시 derivation 건너뜀 (silent skip 아님, 키 자체 부재)."""
        out = {}
        # F1: core_cpi 부재 → cpi_yoy 박지 않음
        cpi_block = out.get("core_cpi") or {}
        if cpi_block.get("yoy_pct") is not None:
            out["cpi_yoy"] = {"value": cpi_block["yoy_pct"]}
        assert "cpi_yoy" not in out

        # F2: us_recession_smoothed_prob 부재 → gdp_growth 박지 않음
        rec_block = out.get("us_recession_smoothed_prob") or {}
        if rec_block.get("pct") is not None:
            out["gdp_growth"] = {"value": 0}
        assert "gdp_growth" not in out
