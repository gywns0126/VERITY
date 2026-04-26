"""
GET /api/digest/publish-readiness?digest_id=xxx
GET /api/digest/publish-readiness                  (현재 작성 중인 다이제스트, mock)

Confidence Score + 9종 체크리스트 + 다이버전스 경고 통합 검증.

응답:
{
  "checklist": [{ "id": "recency", "category": "data", "label": "...", "passed": true, "reason": "..." }, ...],
  "divergence_warnings": [...],
  "confidence_score": 75.5,
  "ready_to_publish": false,
  "preview": {...}
}
"""
from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import parse_qs, urlparse

from api.landex._methodology import PUBLISH_CHECKLIST, CONFIDENCE
from api.landex._compute import compute_confidence, detect_divergence


# Mock 다이제스트 검증 결과 — 실 데이터 연결 시 _validate_digest()로 교체
def _mock_check_results():
    """현재 작성 중인 다이제스트의 9종 체크 결과 (시연용 — 일부 미통과)."""
    results = []
    for spec in PUBLISH_CHECKLIST:
        # 시연용 룰: source/divergence/comparison 미통과
        passed = spec["id"] not in ("source", "divergence", "comparison")
        item = {**spec, "passed": passed}
        if not passed:
            reasons = {
                "source": "V/D/S/C/R 중 R 결측 — 한국은행 ECOS 응답 누락",
                "divergence": "LANDEX 상승 + GEI Stage 4 발생했으나 요약문에 경고 미포함",
                "comparison": "구 평균 비교 차트 미생성",
            }
            item["reason"] = reasons.get(spec["id"], "")
        results.append(item)
    return results


def _mock_divergence_warnings():
    return detect_divergence(landex_trend="up", gei_stage=4, volume_trend="down")


def _mock_preview():
    return {
        "title": "서울 부동산 주간 인사이트",
        "period": "2026-04 4주차",
        "summary": "GEI Stage 3 이상 구가 2주 연속 5개 유지. 강남권 과열 신호 지속.",
        "sections": [
            {"heading": "이번주 핵심", "body": "강남권 LANDEX 상위 5구 평균 +4점 상승."},
            {"heading": "주목 흐름", "body": "용산구 신분당선 연장 확정 — 카탈리스트 +12."},
            {"heading": "주의 구간", "body": "도봉·강북구 AVOID 등급 유지."},
        ],
        "public_notes": [
            "본 리포트는 VERITY ESTATE 내부 모델의 희석된 공개판입니다.",
            "개별 구의 정확한 점수·매수 추천은 포함하지 않습니다.",
            "투자 판단의 책임은 본인에게 있습니다.",
        ],
    }


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        # digest_id 무시 — v1 mock
        checks = _mock_check_results()
        warnings = _mock_divergence_warnings()
        confidence, ready = compute_confidence(checks, divergence_warnings=len(warnings))

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")  # 동적 — 캐시 안 함
        self.end_headers()
        body = json.dumps({
            "checklist": checks,
            "divergence_warnings": warnings,
            "confidence_score": confidence,
            "publish_threshold": CONFIDENCE["publish_threshold"],
            "ready_to_publish": ready,
            "preview": _mock_preview(),
        }, ensure_ascii=False).encode("utf-8")
        self.wfile.write(body)
