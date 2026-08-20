# -*- coding: utf-8 -*-
"""KR cross-section 관측 적재 계약 — 2026-08-20 신설.

이 trail 은 forward IC 검증용 append-only 라 **틀린 행 한 줄이 영구 오염**이다. 세 계약을 고정한다:

① 입력 신선도 — 이 빌더는 같은 run 의 빌더 산출을 읽는다. 분석이 죽어 그 빌더들이 skip 되면
   '어제 값'이 '오늘 date' 로 적재된다(as-of 거짓). generated_at 이 오늘이 아닌 입력은 컬럼을
   null 로 적고 stale_inputs 로 신고해야 하며, 전부 stale 이면 적재 자체를 하지 않아야 한다
   (그래야 같은 날 뒤 run 이 date-dedupe 에 막히지 않는다).
   근거 사고 = 2026-08-14(금) daily_analysis_full 3연속 실패 → 그 주 행 영구 결손.
② insider_net_365d 병기 — 기존 insider_net 은 elestock 약 2년 롤링 누적이라 창이 아니다.
   기존 컬럼은 연속성 때문에 정의를 유지하고 창 컬럼을 병기한다.
③ 🚨 컬럼별 주기(PM 승인 2026-08-20 옵션 B) — 8주 실측에서 시변 성격이 갈렸다
   (foreign_net ρ 0.240 / insider_net ρ 0.986 / family_pct ρ 1.000·변경 0%).
   flow 주간 · insider·dilution 28일 · family_pct 제외.
   🚨 **키 부재 = 미표집**, **null = 표집했으나 입력 stale**. 이 둘을 섞으면 trail 이 거짓말한다.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.builders import kr_observation_logger as ob  # noqa: E402

TK = "000660"
INSIDER_COLS = ("insider_net", "insider_buy_n", "insider_sell_n",
                "insider_net_365d", "insider_buy_n_365d", "insider_sell_n_365d")


def _meta(day: str):
    return {"_meta": {"generated_at": f"{day}T17:59:51+09:00"}}


def _write(tmp, name, doc):
    p = os.path.join(tmp, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    return p


@pytest.fixture
def env(tmp_path, monkeypatch):
    """입력 3종 + 출력/메타 경로를 tmp 로 격리. day 인자로 각 입력의 as-of 를 조작한다."""
    tmp = str(tmp_path)
    today = ob._now_kst().date()
    monkeypatch.setenv("KR_OBS_FORCE", "1")          # 금요일 게이트 우회
    monkeypatch.setattr(ob, "OUT_DIR", tmp)
    out = os.path.join(tmp, "obs.jsonl")
    monkeypatch.setattr(ob, "OUT_PATH", out)
    monkeypatch.setattr(ob, "META_PATH", os.path.join(tmp, "obs_meta.json"))

    def build(insider_day=None, flow_day=None, forensics_day=None):
        d = today.isoformat()
        monkeypatch.setattr(ob, "INSIDER_PATH", _write(tmp, "insider.json", dict(
            _meta(insider_day or d), stocks=[{
                "ticker": TK, "net_change": 106_615, "buy_n": 533, "sell_n": 26,
                "net_change_365d": 2_120, "buy_n_365d": 9, "sell_n_365d": 3,
            }])))
        monkeypatch.setattr(ob, "FLOW_PATH", _write(tmp, "flow.json", dict(
            _meta(flow_day or d), flows={TK: [{"foreign_net": 1}, {"foreign_net": 104_642, "inst_net": -50}]})))
        monkeypatch.setattr(ob, "FORENSICS_PATH", _write(tmp, "forensics.json", dict(
            _meta(forensics_day or d), stocks=[{"ticker": TK, "counts": {
                "유상증자": 2, "전환사채(CB)": 1, "신주인수권부사채(BW)": 0}}])))
        return out

    def seed(days_ago: int, cols):
        """trail 에 과거 행을 심는다 — 주기 판정 입력."""
        d = (today - datetime.timedelta(days=days_ago)).isoformat()
        row = {"date": d, "ticker": TK}
        row.update({c: 1 for c in cols})
        with open(out, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    build.today, build.yday = today.isoformat(), (today - datetime.timedelta(days=1)).isoformat()
    build.out, build.seed, build.meta = out, seed, os.path.join(tmp, "obs_meta.json")
    return build


def _rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def _today_row(path, today):
    return [r for r in _rows(path) if r["date"] == today][0]


class TestFreshInputs:
    def test_first_run_logs_every_group(self, env):
        out = env()
        assert ob.main() == 0
        r = _rows(out)[0]
        assert r["ticker"] == TK
        assert r["cadence"] == ["dilution", "flow", "insider"]
        assert r["insider_net"] == 106_615          # 약 2년 롤링 누적(정의 유지)
        assert r["insider_net_365d"] == 2_120       # 창 컬럼 병기
        assert r["foreign_net"] == 104_642 and r["inst_net"] == -50
        assert r["dilution_count"] == 3
        assert "stale_inputs" not in r              # 정상 주엔 키 자체가 없다

    def test_family_pct_removed_from_trail(self, env):
        # 🚨 8주간 변경 0% · 원천이 공정위 연 1회 → 시계열에서 제외(PM 승인 B)
        out = env()
        assert ob.main() == 0
        assert "family_pct" not in _rows(out)[0]
        assert "family_pct" in ob.RETIRED_COLS

    def test_date_dedupe(self, env):
        out = env()
        assert ob.main() == 0
        assert ob.main() == 0
        assert len([r for r in _rows(out) if r["date"] == env.today]) == 1


class TestCadence:
    def test_flow_weekly_persistent_groups_gated(self, env):
        # 7일 전 전 그룹 적재됨 → 오늘은 flow 만 표집. 나머지는 **키 부재**(null 아님)
        out = env()
        env.seed(7, list(INSIDER_COLS) + ["dilution_count", "foreign_net", "inst_net"])
        assert ob.main() == 0
        r = _today_row(out, env.today)
        assert r["cadence"] == ["flow"]
        assert r["foreign_net"] == 104_642
        for c in INSIDER_COLS + ("dilution_count",):
            assert c not in r, f"{c} 는 미표집이라 키가 없어야 한다(null 아님)"

    def test_due_after_28_days(self, env):
        out = env()
        env.seed(28, list(INSIDER_COLS) + ["dilution_count", "foreign_net", "inst_net"])
        assert ob.main() == 0
        r = _today_row(out, env.today)
        assert r["cadence"] == ["dilution", "flow", "insider"]
        assert r["insider_net"] == 106_615

    def test_new_column_bootstraps_group(self, env):
        # 🚨 신규 컬럼(insider_net_365d)이 한 번도 안 실렸으면 28일 전이라도 그룹을 표집한다.
        #    없으면 신설 컬럼이 최대 28일 비어 있게 된다.
        out = env()
        env.seed(3, ["insider_net", "insider_buy_n", "insider_sell_n",
                     "dilution_count", "foreign_net", "inst_net"])
        assert ob.main() == 0
        r = _today_row(out, env.today)
        assert "insider" in r["cadence"]
        assert r["insider_net_365d"] == 2_120
        assert "dilution_count" not in r          # dilution 은 3일 전 적재 → 아직 아님

    def test_null_counts_as_sampled_for_cadence_clock(self, env):
        # null(=표집했으나 stale)도 주기 시계는 돈다 — 안 그러면 stale 주마다 재표집한다
        out = env()
        env.seed(3, ["foreign_net", "inst_net"])
        with open(out, "a", encoding="utf-8") as f:
            row = {"date": (ob._now_kst().date() - datetime.timedelta(days=3)).isoformat(),
                   "ticker": TK, "dilution_count": None}
            row.update({c: None for c in INSIDER_COLS})
            f.write(json.dumps(row) + "\n")
        assert ob.main() == 0
        assert _today_row(out, env.today)["cadence"] == ["flow"]


class TestStaleInputs:
    def test_stale_insider_nulls_only_its_columns(self, env):
        out = env(insider_day=env.yday)
        assert ob.main() == 0
        r = _rows(out)[0]
        for c in INSIDER_COLS:
            assert r[c] is None, f"{c} 는 표집했으나 stale → null 이어야 한다(키 부재 아님)"
        assert r["stale_inputs"] == ["insider"]
        # 나머지는 살아 있어야 한다 — 한 소스 stale 이 전체 행을 버리게 하면 결손이 커진다
        assert r["foreign_net"] == 104_642
        assert r["dilution_count"] == 3

    def test_stale_forensics_nulls_dilution(self, env):
        out = env(forensics_day=env.yday)
        assert ob.main() == 0
        r = _rows(out)[0]
        assert r["dilution_count"] is None
        assert r["stale_inputs"] == ["forensics"]
        assert r["insider_net_365d"] == 2_120

    def test_all_stale_writes_nothing(self, env):
        # 🚨 핵심 — 빈 행을 남기면 같은 날 뒤 run 이 date-dedupe 에 막혀 진짜 데이터를 잃는다
        out = env(insider_day=env.yday, flow_day=env.yday, forensics_day=env.yday)
        assert ob.main() == 0
        assert _rows(out) == []

    def test_missing_meta_is_stale(self, env):
        # _meta 부재 = as-of 불명 → 신선하다고 가정하지 않는다
        out = env()
        with open(ob.INSIDER_PATH, "w", encoding="utf-8") as f:
            json.dump({"stocks": [{"ticker": TK, "net_change": 1}]}, f)
        assert ob.main() == 0
        assert _rows(out)[0]["stale_inputs"] == ["insider"]


class TestMetaSidecar:
    """🚨 산출물이 자기 입으로 말하게 한다(RULE 12 ②) — jsonl 은 _meta 자리가 없어 사이드카."""

    def test_meta_declares_policy_boundary_and_dead_premise(self, env):
        env()
        assert ob.main() == 0
        m = json.load(open(env.meta, encoding="utf-8"))
        assert m["cadence_policy"]["groups"]["flow"]["days"] == 0
        assert m["cadence_policy"]["groups"]["insider"]["days"] == 28
        # 주기 경계를 신고해야 다음 세션이 행 수를 관측 수로 세지 않는다(RULE 13 ⑤)
        assert m["cadence_change"]["date"] == ob.CADENCE_CHANGE_DATE
        assert "cadence" in m["cadence_change"]["🚨 read_across_boundary"]
        # 키 부재 vs null 의미가 파일 안에 있어야 한다
        assert "미표집" in m["key_semantics"]["키 부재"]
        assert "stale" in m["key_semantics"]["null"]
        # 폐기된 등록 근거를 산출물이 스스로 신고한다
        assert "§7-1" in m["🚨 등록 상태"] and "§7-3" in m["🚨 등록 상태"]
        # 주기 근거 수치가 실측이라는 것과 측정 창이 남아야 한다
        assert m["column_nature_measured_2026_06_21__2026_08_07"]["foreign_net"]["weekly_rank_rho"] == 0.240
        assert m["retired_columns"]["family_pct"]


class TestPowerSelfReport:
    """🚨 §7-1 이 폐기한 것은 표본 수 게이트이고, 폐기 사유는 **기본 출력이 '더 모아라'** 인 것이었다.

    그래서 이 신고의 출력은 "얼마나 모았나" 가 아니라 **"지금 무엇이 판정 가능한가"** 여야 한다.
    k 가 안 오르는 칸은 더 모을 일이 아니라 설계를 바꾸거나 확증 없이 갈 일이다.
    """

    def test_k_and_evidence_class_reported_per_horizon(self, env):
        env()
        assert ob.main() == 0
        blk = json.load(open(env.meta, encoding="utf-8"))["🚨 판정 가능성 자기신고 (§7-3 (7)·(8))"]
        # 지평은 §7-3 (8) — 가격류 1~20일 / 이벤트·가치류 1~12개월
        assert blk["flow.fwd5d"]["horizon_days"] == 5
        assert blk["insider.fwd1m"]["horizon_days"] == 30
        # 첫 관측 1회 = span 0 → 어떤 지평도 판정 불가여야 한다
        for key, v in blk.items():
            if isinstance(v, dict) and "k" in v:
                assert v["k"] == 0 and v["evidence_class"] == "판정 불가(설계상)"

    def test_evidence_class_thresholds(self):
        # §7-3 (7) 외부검증 채택 임계 — k<3 판정 불가 · k<10 exploratory · 이상 confirmatory
        assert ob._evidence_class(0) == "판정 불가(설계상)"
        assert ob._evidence_class(2) == "판정 불가(설계상)"
        assert ob._evidence_class(3) == "exploratory"
        assert ob._evidence_class(9) == "exploratory"
        assert ob._evidence_class(10) == "confirmatory"

    def test_k_uses_span_not_row_count(self, env):
        # 🚨 겹침 관측 수를 n 으로 쓰면 검정력 관문 자체가 오염된다(t 부풀림 2.3~2.5배 실측).
        #    같은 날 여러 행이 있어도 k 는 오르지 않아야 한다.
        env()
        for _ in range(5):
            env.seed(3, ["foreign_net"])            # 3일 전 날짜로 5행(=관측 1회)
        assert ob.main() == 0
        blk = json.load(open(env.meta, encoding="utf-8"))["🚨 판정 가능성 자기신고 (§7-3 (7)·(8))"]
        assert blk["observed_dates"] == 2, "같은 날 5행 + 오늘 1행 = 관측 2회(행 6개 아님)"
        assert blk["span_days"] == 3
        assert blk["flow.fwd5d"]["k"] == 0, "span 3일 < 지평 5일 → 독립관측 0"
