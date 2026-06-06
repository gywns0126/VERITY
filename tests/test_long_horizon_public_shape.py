"""
long_horizon_public._render_pdf 리스트 항목 shape 내성 회귀 테스트.

2026-06-06 사고: 월간 public 리포트가 narrative 생성(out=430)은 성공했으나 PDF 렌더에서
AttributeError: 'str' object has no attribute 'get' (line 279). 원인 = LLM 이 next.events /
sectors.winners·losers 를 dict({description}/{label,reason}) 대신 str 리스트로 반환했는데
렌더러가 dict 로 가정. review.key_events 는 str 처리하면서 여기만 dict 가정 = 불일치.
이 렌더러는 월간/주간/분기/반기/연간 public 전부 공유.

게이트: events / winners / losers 가 str 리스트여도 AttributeError 없이 렌더.
"""
import pytest

from api.reports import long_horizon_public as L


def _content(string_shape: bool):
    if string_shape:
        winners, losers = ["삼성전자", "SK하이닉스"], ["LG화학"]
        events = ["반도체 업황 점검", "FOMC"]
    else:
        winners = [{"label": "삼성전자", "reason": "메모리"}]
        losers = [{"label": "LG화학", "reason": "수요 둔화"}]
        events = [{"description": "FOMC"}]
    return {
        "metadata": {"period": "monthly", "date_range": {"start": "2026-05-01", "end": "2026-05-31"},
                     "validated": False, "watermark": "예비"},
        "cover": "표지",
        "sections": {
            "review": {"summary": "요약", "key_events": ["사건1"]},
            "sectors": {"winners": winners, "losers": losers},
            "next": {"events": events, "positive_scenario": "긍정",
                     "negative_scenario": "부정", "biggest_factor": "변수"},
            "judgment": {"icon_label": "관망", "reasoning": "근거", "big_picture": "큰그림"},
            "self_assessment": "자기평가",
        },
    }


@pytest.mark.parametrize("string_shape", [True, False])
def test_render_pdf_tolerates_list_item_shapes(tmp_path, monkeypatch, string_shape):
    # 부산물 격리: DATA_DIR 을 tmp 로
    monkeypatch.setattr(L, "DATA_DIR", str(tmp_path))
    try:
        L._render_pdf(_content(string_shape), "Monthly")
    except AttributeError as e:
        pytest.fail(f"shape 회귀 (str 리스트 미허용): {e}")
    except Exception:
        # 폰트/IO 등 환경 의존 예외는 본 테스트 범위 밖 (shape crash 만 검증)
        pass
