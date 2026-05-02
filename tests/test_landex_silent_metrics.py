"""LANDEX silent 메트릭 — 단위 테스트 (5 cases).

D3 silent 측정 (scripts/landex_meta_validation.py) 검증:
  1. Spearman rank IC + p-value 정확성 (강한 상관 + 약한 상관)
  2. RMSE + market_volatility (z-score 정규화)
  3. Direction Accuracy (방향성 적중)
  4. Quintile Spread Q5-Q1 (분위 간 평균 차이)
  5. _compute_silent_metrics + jsonl append + 운영 verdict 무영향 (silent 보장)
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# scripts/ 는 패키지가 아니라 importlib 로 모듈 로드
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "landex_meta_validation.py"
_spec = importlib.util.spec_from_file_location("landex_mv", str(_SCRIPT_PATH))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


class TestSilentMetrics:
    def test_spearman_rank_ic_strong_vs_weak(self):
        # case 1 — 강한 양의 상관 (rho ≈ 1)
        scores = list(range(25))
        returns = [x * 0.5 + 1 for x in scores]  # 완전 양의 선형
        rho, pval = _mod._spearman_rank_ic(scores, returns)
        assert rho == pytest.approx(1.0, abs=0.001)
        assert pval is not None and pval < 0.01

        # 약한 상관 (random noise)
        import random
        rng = random.Random(0)
        scores2 = [rng.gauss(0, 1) for _ in range(25)]
        returns2 = [rng.gauss(0, 1) for _ in range(25)]  # 독립
        rho2, pval2 = _mod._spearman_rank_ic(scores2, returns2)
        assert rho2 is not None
        assert abs(rho2) < 0.5  # 약한 상관 (n=25 noise 한계)

        # None 처리 — valid n < 3 이면 (None, None) 반환
        rho3, p3 = _mod._spearman_rank_ic([1, 2, None], [1, 2, 3])
        assert rho3 is None and p3 is None  # 1개 제외 후 n=2 < 3
        rho4, _ = _mod._spearman_rank_ic([None, None], [1, 2])
        assert rho4 is None

    def test_rmse_normalized(self):
        # case 2 — z-score 정규화 후 RMSE
        scores = [1.0, 2.0, 3.0, 4.0, 5.0]
        returns = [1.0, 2.0, 3.0, 4.0, 5.0]  # 완전 일치
        rmse, vol = _mod._rmse(scores, returns)
        assert rmse == pytest.approx(0.0, abs=0.001)
        assert vol is not None and vol > 0

        # 완전 반대 (rho=-1) → 정규화 후 RMSE = sqrt(mean((z - (-z))²)) = sqrt(4*var)/std
        scores_rev = [5.0, 4.0, 3.0, 2.0, 1.0]
        rmse_rev, vol_rev = _mod._rmse(scores, scores_rev)
        # 정규화 후 z 와 -z → 차이 2z, RMSE = sqrt(mean(4z²)) = 2 * sqrt(var(z)) = 2
        assert rmse_rev == pytest.approx(2.0, abs=0.01)

        # None 처리
        rmse_n, _ = _mod._rmse([None, None], [1, 2])
        assert rmse_n is None

    def test_direction_accuracy(self):
        # case 3 — 5개 중 4개 방향 일치
        # mean_s = 3, mean_r = 3
        scores = [1, 2, 3, 4, 5]
        returns = [1, 2, 3, 5, 4]  # idx 3,4 swap → 둘 다 mean 위 = 부호 일치
        # (1-3)*(1-3)=+ / (2-3)*(2-3)=+ / (3-3)*(3-3)=0 (0은 무시) / (4-3)*(5-3)=+ / (5-3)*(4-3)=+
        # 4 correct / 4 nonzero = 100%
        acc = _mod._direction_accuracy(scores, returns)
        assert acc == pytest.approx(1.0, abs=0.01)

        # 완전 반대
        returns_rev = [5, 4, 3, 2, 1]
        acc_rev = _mod._direction_accuracy(scores, returns_rev)
        assert acc_rev == pytest.approx(0.0, abs=0.01)

    def test_quintile_spread(self):
        # case 4 — Q5 (top 5) - Q1 (bottom 5)
        # n=25, q_size=5
        scores = list(range(25))
        returns = list(range(25))  # 완전 양의 상관
        # Q1 = scores 0~4 → returns 0~4, 평균=2
        # Q5 = scores 20~24 → returns 20~24, 평균=22
        # spread = 22 - 2 = 20
        spread = _mod._quintile_spread(scores, returns, q_size=5)
        assert spread == pytest.approx(20.0, abs=0.01)

        # n 부족
        spread_short = _mod._quintile_spread([1, 2, 3], [1, 2, 3], q_size=5)
        assert spread_short is None

    def test_compute_silent_metrics_and_jsonl(self, tmp_path):
        # case 5 — 통합: silent 메트릭 산출 + jsonl append + 운영 verdict 무영향
        import random
        rng = random.Random(42)
        pairs = []
        for i in range(25):
            score = 50 + rng.gauss(0, 10)
            ret = 0.5 * (score - 50) / 10 + rng.gauss(0, 0.5)
            pairs.append((score, ret))

        # operational_verdict 는 단순 호환 기록 — silent 처리 영향 X
        record = _mod._compute_silent_metrics(pairs, operational_verdict="ready")

        # 구조 검증
        assert "timestamp" in record
        assert record["horizon_weeks"] == _mod.SILENT_HORIZON_WEEKS
        assert record["n_districts"] == 25
        assert record["current_operational_verdict"] == "ready"

        m = record["metrics"]
        assert m["spearman_rank_ic"] is not None
        assert m["rmse"] is not None
        assert m["direction_accuracy"] is not None
        assert m["quintile_spread_pct"] is not None
        # mock SNR ≈ 1 (signal slope 0.5 / noise std 0.5) → spearman 0.3~0.6 기대
        assert m["spearman_rank_ic"] > 0.2

        thr = record["thresholds_evaluated"]
        assert "p0_passed_count" in thr
        assert "would_pass_with_3_of_4" in thr
        assert thr["p0_passed_count"] >= 0  # silent — 게이팅 영향 X

        # jsonl append (tmp_path 사용 — 운영 jsonl 미터치)
        log_path = tmp_path / "silent_metrics.jsonl"
        _mod._append_silent_metrics_jsonl(record, path=log_path)
        assert log_path.exists()
        line = log_path.read_text(encoding="utf-8").strip().splitlines()[0]
        loaded = json.loads(line)
        assert loaded["n_districts"] == 25
        assert loaded["current_operational_verdict"] == "ready"

        # forward_returns=None 케이스 (실 cron 초기 상태)
        pairs_no_ret = [(p[0], None) for p in pairs]
        record_no_ret = _mod._compute_silent_metrics(pairs_no_ret, operational_verdict="ready")
        # 모든 메트릭 None, p0_passed_count = 0
        assert record_no_ret["thresholds_evaluated"]["p0_passed_count"] == 0
        assert record_no_ret["thresholds_evaluated"]["would_pass_with_3_of_4"] is False
        assert record_no_ret["current_operational_verdict"] == "ready"  # 운영 verdict 호환 그대로
