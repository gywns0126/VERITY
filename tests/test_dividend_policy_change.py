"""
test_dividend_policy_change — 배당 정책 변화 이벤트 분류 단위 검증.

사전등록 spec (docs/dividend_policy_change_spec_v0_2026_06_13.md) 정합:
개시(positive) / 삭감(medium) / 중단(high) / 무변화(none) / 증액(positive) /
baseline 부재(none) / 같은연도 합산 / graceful. 관측 only — scored 미주입.
"""
import api.analyzers.dividend_policy_change as DPC


def _rec(ex_date, confirmed=None, announced=None, dtype="year_end"):
    r = {"ex_date": ex_date, "dividend_type": dtype, "is_confirmed": confirmed is not None}
    if confirmed is not None:
        r["confirmed_amount_per_share"] = confirmed
    if announced is not None:
        r["announced_amount_per_share"] = announced
    return r


def test_initiation():
    """무배당(prev) → 배당(curr) = 개시(positive)."""
    hist = [_rec("2023-12-30", confirmed=0), _rec("2024-12-30", confirmed=500)]
    r = DPC.classify_dividend_history(hist)
    assert r["change_type"] == "initiation"
    assert r["severity"] == "positive"
    assert r["curr_amount"] == 500.0


def test_initiation_from_absent_amount_record():
    """이전 연도 레코드가 amount 결손(=무배당 0 정규화)이어도 개시 인식.
    명시적 무배당 점은 보존(개시 전이 판별 필수)."""
    hist = [_rec("2023-12-30", confirmed=None), _rec("2024-12-30", confirmed=500)]
    r = DPC.classify_dividend_history(hist)
    assert r["change_type"] == "initiation"
    assert r["years_observed"] == 2
    assert r["prev_amount"] == 0.0


def test_cut():
    """직전 대비 절반 이하 감액 = 삭감(medium)."""
    hist = [_rec("2023-12-30", confirmed=1000), _rec("2024-12-30", confirmed=400)]
    r = DPC.classify_dividend_history(hist)
    assert r["change_type"] == "cut"
    assert r["severity"] == "medium"
    assert r["change_pct"] == -60.0


def test_cut_boundary_exact_half():
    """정확히 절반(CUT_RATIO 경계) = 삭감 포함(<=)."""
    hist = [_rec("2023-12-30", confirmed=1000), _rec("2024-12-30", confirmed=500)]
    r = DPC.classify_dividend_history(hist)
    assert r["change_type"] == "cut"


def test_mild_reduction_is_maintained():
    """경계 미만 소폭 감액(예: -30%)은 cut 아님 = 유지."""
    hist = [_rec("2023-12-30", confirmed=1000), _rec("2024-12-30", confirmed=700)]
    r = DPC.classify_dividend_history(hist)
    assert r["change_type"] == "maintained"
    assert r["severity"] == "none"


def test_omission():
    """배당(prev) → 무배당(curr) = 중단(high, distress 동형)."""
    hist = [_rec("2023-12-30", confirmed=800), _rec("2024-12-30", confirmed=0)]
    r = DPC.classify_dividend_history(hist)
    assert r["change_type"] == "omission"
    assert r["severity"] == "high"


def test_raise():
    """직전 대비 50%+ 증액 = 증액(positive)."""
    hist = [_rec("2023-12-30", confirmed=1000), _rec("2024-12-30", confirmed=1600)]
    r = DPC.classify_dividend_history(hist)
    assert r["change_type"] == "raise"
    assert r["severity"] == "positive"
    assert r["change_pct"] == 60.0


def test_maintained_no_change():
    hist = [_rec("2023-12-30", confirmed=1000), _rec("2024-12-30", confirmed=1000)]
    r = DPC.classify_dividend_history(hist)
    assert r["change_type"] == "maintained"
    assert r["change_pct"] == 0.0


def test_no_baseline_single_year():
    """단일 연도 = 비교 불가(none). baseline 부재."""
    r = DPC.classify_dividend_history([_rec("2024-12-30", confirmed=500)])
    assert r["change_type"] == "none"
    assert r["years_observed"] == 1
    assert r["curr_amount"] == 500.0


def test_empty_history_graceful():
    r = DPC.classify_dividend_history([])
    assert r["change_type"] == "none"
    assert r["years_observed"] == 0
    r2 = DPC.classify_dividend_history(None)
    assert r2["change_type"] == "none"


def test_meta_records_excluded():
    """_meta(tier2_decisions) 레코드는 series 에서 제외."""
    hist = [
        {"_meta": "tier2_decisions", "recent_decisions": []},
        _rec("2023-12-30", confirmed=1000),
        _rec("2024-12-30", confirmed=0),
    ]
    r = DPC.classify_dividend_history(hist)
    assert r["change_type"] == "omission"
    assert r["years_observed"] == 2  # _meta 만 제외, 무배당(0) 점은 보존


def test_same_year_records_summed():
    """같은 연도 중간+연말 배당은 합산(연간 총배당)."""
    hist = [
        _rec("2023-12-30", confirmed=1000),
        _rec("2024-06-30", confirmed=300, dtype="interim"),
        _rec("2024-12-30", confirmed=900, dtype="year_end"),
    ]
    r = DPC.classify_dividend_history(hist)
    # 2024 = 300+900 = 1200 vs 2023 = 1000 → +20% = 유지(증액 경계 미만)
    assert r["curr_amount"] == 1200.0
    assert r["change_type"] == "maintained"


def test_announced_fallback_when_no_confirmed():
    """confirmed 없으면 announced 사용."""
    hist = [_rec("2023-12-30", announced=1000), _rec("2024-12-30", announced=300)]
    r = DPC.classify_dividend_history(hist)
    assert r["change_type"] == "cut"


def test_observation_only_no_score_fields():
    """관측 only — score/verdict/risk_flag 류 출력 필드 없음 (RULE 7)."""
    r = DPC.classify_dividend_history(
        [_rec("2023-12-30", confirmed=800), _rec("2024-12-30", confirmed=0)]
    )
    forbidden = {"score", "verdict", "risk_flag", "risk_flags", "auto_avoid", "brain_score"}
    assert not (forbidden & set(r))


def test_scan_wrapper_with_injected_db():
    """scan 래퍼 — 주입 DB 로 종목별 부착. baseline 부재 종목은 제외."""
    db = {
        "005930": [_rec("2023-12-30", confirmed=1000), _rec("2024-12-30", confirmed=400)],  # cut
        "000660": [_rec("2024-12-30", confirmed=500)],  # 단일 연도 = 제외
    }
    stocks = {"005930": {}, "000660": {}, "035720.KS": {}}  # 035720 = DB 없음 → 제외
    out = DPC.scan_dividend_policy_changes(stocks, dividends_db=db)
    assert "005930" in out
    assert out["005930"]["change_type"] == "cut"
    assert "000660" not in out  # baseline 부재
    assert "035720" not in out  # 이력 없음
    assert out["005930"]["ticker"] == "005930"


def test_scan_ticker_suffix_normalized():
    """티커 suffix(.KS) 정규화 후 6자리 매칭."""
    db = {"005930": [_rec("2023-12-30", confirmed=1000), _rec("2024-12-30", confirmed=0)]}
    out = DPC.scan_dividend_policy_changes({"005930.KS": {}}, dividends_db=db)
    assert "005930" in out
    assert out["005930"]["change_type"] == "omission"


def test_scan_graceful_empty():
    assert DPC.scan_dividend_policy_changes({}, dividends_db={}) == {}
