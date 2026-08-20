"""G10(중립 배제) · G9-c(단일 비율) 계약 — PM 승인 2026-08-21 · RULE 7 쿼터 각 1 소모.

되돌림 방지가 목적이다. 두 변경 모두 사전등록
(PREREG_BASELINE_V1_LITERATURE_2026_08_16 §G10·G9-c)에 예상 효과를 결과 보기 전에
선언하고 시행했다.

🚨 이 테스트가 고정하지 **않는** 것 = 점수 값 자체.
   G8(정규화 재설계)이 승인되면 스케일이 재조정되므로 값을 고정하면 그때 막힌다.
   고정 대상은 **구조**(중립이 분모에서 빠지는가 · 분면 가중이 부활했는가)뿐이다.
"""
import json
import os

from api.collectors.news_sentiment import analyze_sentiment
from api.intelligence.verity_brain import _get_brain_weights

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONSTITUTION = os.path.join(ROOT, "data", "verity_constitution.json")


# ── G10 ─────────────────────────────────────────────────────────────────

def test_neutral_headlines_are_excluded_from_denominator():
    """🚨 핵심 계약 — 중립을 늘려도 점수가 희석되지 않아야 한다.

    종전에는 중립이 분모에 포함돼, 사전 미매칭 63.7%가 신호의 3분의 2를 0으로 눌렀다.
    A&F(2004, JF)는 M_hold 를 분모에서 명시 배제한다.
    """
    pos_only = ["삼성전자 영업이익 급등 신고가 돌파"]
    filler = ["오늘 회의가 열렸다고 전해진다 관계자 설명"] * 20   # 사전 미매칭 = 중립
    a = analyze_sentiment(pos_only, lang="kr")["score"]
    b = analyze_sentiment(pos_only + filler, lang="kr")["score"]
    assert a == b, (
        f"중립 20건을 더했더니 점수가 {a} → {b} 로 변했다 — 중립이 분모에 섞여 있다"
    )


def test_all_neutral_returns_exactly_neutral():
    """전부 중립이면 분모가 0 이라 중립값을 돌려줘야 한다 (0 나누기 방지)."""
    out = analyze_sentiment(["오늘 회의가 열렸다고 전해진다"] * 5, lang="kr")
    assert out["score"] == 50
    assert out["neutral"] == 5 and out["positive"] == 0 and out["negative"] == 0


def test_direction_is_preserved():
    """부호가 뒤집히면 안 된다 — 이 변경은 해상도이지 방향 반전이 아니다."""
    up = analyze_sentiment(["급등 신고가 돌파 호실적"], lang="kr")["score"]
    down = analyze_sentiment(["급락 적자 상장폐지 우려"], lang="kr")["score"]
    assert up > 50 > down


def test_counts_still_include_neutral():
    """분모에서만 빼는 것이지 신고에서 빼는 것이 아니다 — 관측은 유지."""
    out = analyze_sentiment(["급등 신고가"] + ["오늘 회의가 열렸다"] * 3, lang="kr")
    assert out["headline_count"] == 4
    assert out["neutral"] == 3, "중립 건수 신고가 사라지면 커버리지를 못 잰다"


# ── G9-c ────────────────────────────────────────────────────────────────

def _bw():
    with open(CONSTITUTION, encoding="utf-8") as f:
        return (json.load(f).get("decision_tree") or {}).get("brain_weights") or {}


def test_quadrant_specific_weights_are_gone():
    """🚨 분면별 가중이 부활하면 여기서 걸린다.

    Q4 회신 — 국면별 조정은 임의 구간 설정이라 롤링 IC 로 재산출하거나
    근거 부족을 인정하고 단일 비율로 되돌려야 한다. 후자를 택했다.
    """
    bw = _bw()
    revived = [k for k in bw if k.startswith("growth_")]
    assert not revived, (
        f"분면별 가중이 부활했다: {revived} — 되돌리려면 사전등록 + RULE 7 쿼터가 필요하다"
    )


def test_all_quadrants_resolve_to_the_same_weights():
    """어떤 분면 이름을 줘도 동일 가중이어야 한다."""
    names = ["growth_up_inflation_down", "growth_up_inflation_up",
             "growth_down_inflation_down", "growth_down_inflation_up",
             "unknown", None]
    got = [tuple(sorted(_get_brain_weights(n).items())) for n in names]
    assert len(set(got)) == 1, f"분면마다 가중이 다르다: {dict(zip(map(str, names), got))}"


def test_removal_is_self_reported():
    """RULE 12 — 제거 사실과 제거분이 헌법에 남아 있어야 한다."""
    bw = _bw()
    note = next((v for k, v in bw.items() if k.startswith("_note") and "G9c" in k), None)
    assert note, "G9-c 제거 기록이 헌법에서 사라졌다"
    assert "0.65" in note and "0.85" in note, "제거된 값이 기록에 남아 있어야 복원이 가능하다"


def test_default_ratio_is_unchanged():
    """🚨 G9-c 는 '분면 매핑 제거'이지 '비율 변경'이 아니다.

    0.7/0.3 도 출처 없는 값이나, Q8 이 '등급 경계·가중을 통계로 유도하는 표준 공식은
    없다'고 답했으므로 현행을 유지한다. 이 값을 바꾸려면 별도 사전등록이 필요하다.
    """
    d = _bw().get("default") or {}
    assert (d.get("fact"), d.get("sentiment")) == (0.7, 0.3)
