"""
VERITY Brain 통합 감사 리포트 → PDF 생성기 (1회용 스크립트).

출력: data/verity_brain_audit_report.pdf
폰트: api/reports/fonts/NanumGothic{,Bold}.ttf
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import List, Tuple

from fpdf import FPDF

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_FONT_DIR = os.path.join(_ROOT, "api", "reports", "fonts")
_FONT_REG = os.path.join(_FONT_DIR, "NanumGothic.ttf")
_FONT_BOLD = os.path.join(_FONT_DIR, "NanumGothicBold.ttf")
_OUT_PATH = os.path.join(_ROOT, "data", "verity_brain_audit_report.pdf")


# 색상 팔레트 (다크 테마 기반)
BG = (10, 10, 10)
CARD_BG = (20, 20, 20)
TEXT = (240, 240, 240)
MUTED = (140, 140, 140)
ACCENT = (181, 255, 25)        # VERITY green
CRIT = (255, 77, 77)
WARN = (255, 214, 0)
INFO = (96, 165, 250)
NORMAL = (34, 197, 94)
BORDER = (40, 40, 40)


class AuditPDF(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.add_font("Nanum", "", _FONT_REG, uni=True)
        self.add_font("Nanum", "B", _FONT_BOLD, uni=True)
        self.set_auto_page_break(auto=True, margin=18)

    def header(self):
        self.set_fill_color(*BG)
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*CARD_BG)
        self.rect(0, 0, 210, 16, "F")
        self.set_draw_color(*BORDER)
        self.line(0, 16, 210, 16)

        self.set_font("Nanum", "B", 9)
        self.set_text_color(*ACCENT)
        self.set_xy(10, 4)
        self.cell(100, 4, "VERITY TERMINAL — Brain Audit", ln=False)

        self.set_font("Nanum", "", 7)
        self.set_text_color(*MUTED)
        self.set_xy(10, 9.5)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M KST")
        self.cell(100, 4, ts, ln=False)

        self.set_xy(140, 6.5)
        self.set_font("Nanum", "B", 8)
        self.set_text_color(*TEXT)
        self.cell(60, 4, "Brain System Integration Audit", ln=False, align="R")

    def footer(self):
        self.set_y(-12)
        self.set_font("Nanum", "", 7)
        self.set_text_color(*MUTED)
        self.cell(0, 4, f"VERITY Brain Audit · Page {self.page_no()}", align="C")

    # ── 빌딩 블록 ──────────────────────────────────────────
    def chapter_title(self, num: str, title: str, color: Tuple[int, int, int] = ACCENT):
        self.ln(4)
        self.set_font("Nanum", "B", 14)
        self.set_text_color(*color)
        self.cell(8, 8, num, ln=False)
        self.set_text_color(*TEXT)
        self.cell(0, 8, title, ln=True)
        self.set_draw_color(*color)
        self.set_line_width(0.4)
        y = self.get_y()
        self.line(10, y + 1, 200, y + 1)
        self.ln(4)

    def issue_card(
        self,
        ident: str,
        title: str,
        problem: str,
        scenario: str,
        location: str,
        fix: str,
        accent: Tuple[int, int, int],
    ):
        # 카드 배경
        x0 = self.get_x()
        y0 = self.get_y()
        self.set_fill_color(*CARD_BG)
        self.set_draw_color(*accent)
        self.set_line_width(0.2)

        # 임시로 높이 계산 후 박스 그리기 (단순 추정)
        self.set_font("Nanum", "B", 10)
        self.set_text_color(*accent)
        self.cell(20, 6, ident, ln=False)
        self.set_text_color(*TEXT)
        self.cell(0, 6, title, ln=True)
        self.ln(1)

        self._field("문제", problem)
        self._field("발생 시나리오", scenario)
        self._field("수정 위치", location, mono=True)
        self._field("수정 방법", fix, mono=False)
        self.ln(3)

        # 아래 보더
        y_now = self.get_y()
        self.set_draw_color(*BORDER)
        self.line(10, y_now - 1, 200, y_now - 1)
        self.ln(3)

    def _field(self, label: str, content: str, mono: bool = False):
        self.set_font("Nanum", "B", 8)
        self.set_text_color(*MUTED)
        self.cell(28, 5, f"{label}:", ln=False)
        self.set_font("Nanum", "", 9)
        self.set_text_color(*TEXT)
        # 긴 텍스트 multi_cell
        x = self.get_x()
        y = self.get_y()
        self.multi_cell(170, 4.8, content)
        self.ln(0.5)

    def normal_table(self, headers: List[str], rows: List[List[str]], col_widths: List[float]):
        self.set_font("Nanum", "B", 8)
        self.set_text_color(*ACCENT)
        self.set_fill_color(*CARD_BG)
        for h, w in zip(headers, col_widths):
            self.cell(w, 6, h, border=0, fill=True)
        self.ln(6)

        self.set_font("Nanum", "", 8)
        self.set_text_color(*TEXT)
        for row in rows:
            for v, w in zip(row, col_widths):
                self.cell(w, 5.5, str(v), border=0)
            self.ln(5.5)

    def bullet(self, text: str, color: Tuple[int, int, int] = TEXT, indent: float = 5):
        self.set_x(10 + indent)
        self.set_font("Nanum", "", 9)
        self.set_text_color(*color)
        self.cell(3, 5, "·", ln=False)
        self.multi_cell(0, 5, text)

    def kv_block(self, items: List[Tuple[str, str, Tuple[int, int, int]]]):
        for label, value, color in items:
            self.set_font("Nanum", "B", 9)
            self.set_text_color(*MUTED)
            self.cell(60, 6, label, ln=False)
            self.set_font("Nanum", "B", 11)
            self.set_text_color(*color)
            self.cell(0, 6, value, ln=True)


# ── 데이터 ────────────────────────────────────────────────────

CRIT_ITEMS = [
    {
        "id": "1-A",
        "title": "_detect_bubble_signals → 종목 등급 미반영",
        "problem": (
            "constitution.json:577~581에 cape_bubble_mode(CAPE>30 시 신규 매수 보수적·포지션 축소)가 정의되어 있으나 "
            "코드는 result['market_brain']['bubble_warning']에 정보만 기록한다. "
            "detect_macro_override(verity_brain.py:1385~1537)에 CAPE 체크 코드 부재."
        ),
        "scenario": (
            "CAPE 35 + VIX 11 + F&G 88 동시 발생, 종목 W는 fact 90/sent 30이라 STRONG_BUY 유지. "
            "사용자는 카드 한 줄 경고만 보고 W를 매수 진입한다."
        ),
        "location": "verity_brain.py:1385~1537 (detect_macro_override) / 2204~2207",
        "fix": (
            "detect_macro_override 끝에 다음 추가: "
            "cape = fred.get('cape', {}).get('value'); "
            "if cape and float(cape) > 30: _add({'mode':'cape_bubble', 'max_grade':'WATCH', ...})"
        ),
    },
    {
        "id": "1-B",
        "title": "quadrant.unfavored 섹터 강등 미구현",
        "problem": (
            "constitution.json:281~327에 분면별 favored/unfavored 섹터 명시(스태그플레이션 → 성장주 unfavored)되어 있으나 "
            "verity_brain.py에서 unfavored가 사용되는 라인은 단 1곳(L1248), 단순 dict 출력용."
        ),
        "scenario": (
            "growth_down_inflation_up(스태그플레이션) 진입, 종목 Z는 unfavored=성장주. "
            "constitution은 회피 권고이지만 코드는 fact 가중치 0.85만 변경하므로 fact 좋으면 STRONG_BUY 유지."
        ),
        "location": "verity_brain.py:1663~1777 (analyze_stock) 또는 신규 함수",
        "fix": (
            "analyze_stock 후반에 quadrant.unfavored 섹터 매칭 시 brain_score -= 5 + grade 1단계 강등 보정 추가."
        ),
    },
    {
        "id": "1-C",
        "title": "Sentiment 4소스 de-correlation 부재 — 밈 종목 부풀림",
        "problem": (
            "social_sentiment 자체가 news+naver+reddit+stocktwits의 가중 합산(sentiment_engine.py:75~80)인데, "
            "_compute_sentiment_score(verity_brain.py:770~785)가 이를 다시 7개 소스 중 하나로 가산. "
            "상관 보정·cluster cap 코드 0건."
        ),
        "scenario": (
            "X(0.18) + Reddit·Naver(social_sentiment 0.09 내부 0.6 비중) + News(0.25)가 밈 종목에서 동시 90+ → "
            "market_mood/consensus 50 중립이라도 sentiment_score 70+ 도달. VCI 0 부근 정렬되어 경고 미발화."
        ),
        "location": "verity_brain.py:770~797 (_compute_sentiment_score)",
        "fix": (
            "_detect_bubble_signals의 group cap 패턴 차용 — retail sentiment 그룹(x_sentiment + social_sentiment)에 "
            "합산 cap(예: 그룹 기여 ≤ 0.20) 적용."
        ),
    },
    {
        "id": "1-D",
        "title": "strategy_evolver 누적 드리프트 cap 부재",
        "problem": (
            "STRATEGY_MAX_WEIGHT_DELTA=0.05는 단건 제한만 적용. validate_proposal(strategy_evolver.py:404~427)에 "
            "cumulative drift / consecutive direction 검사 코드 0건. 같은 방향 10회 누적 시 ±0.5 이동 가능."
        ),
        "scenario": (
            "Claude가 momentum bias로 10회 연속 'momentum: +0.05' 제안 → validator 매번 통과 → "
            "momentum 0.10 → 0.60 누적 → quality/volatility/mean_reversion이 squeeze."
        ),
        "location": "strategy_evolver.py:394~435 (validate_proposal), config.py",
        "fix": (
            "STRATEGY_MAX_CUMULATIVE_DRIFT=0.20 도입. validate_proposal에서 versions[0].pre_change_snapshot과 비교해 "
            "같은 키의 절대 변화량이 임계 초과면 거부."
        ),
    },
    {
        "id": "1-E",
        "title": "strategy_evolver 적중률 시간 윈도우 명시 부재",
        "problem": (
            "auto_approve_threshold.hit_rate_pct: 80(strategy_evolver.py:127)이 cumulative_stats.hit_rate_pct를 참조 — "
            "시간 무한 누적. rolling_window=8은 버전 인덱스 기반(strategy_evolver.py:650~656)으로 시간 무관."
        ),
        "scenario": (
            "1월 강세장에 5건 제안 모두 hit, hit_rate 80% 도달 → 자동 승인 활성. "
            "3월 약세장에서도 cumulative 80% 유지 → 강세장 패턴 가중치가 약세장에 그대로 적용."
        ),
        "location": "strategy_evolver.py:724~770 (_check_auto_approve_transition), cumulative_stats 스키마",
        "fix": (
            "versions[]를 applied_at 기준 최근 60일 필터 후 hit_rate 재계산. "
            "자동 승인 조건에 시간 윈도우 명시 추가."
        ),
    },
]

WARN_ITEMS = [
    {
        "id": "2-A",
        "title": "수집기 dict 내부 None → 종목 단위 silent data loss",
        "problem": (
            "safe_collect는 result==None만 default로 폴백. dict 내부 None은 통과. "
            "_compute_fact_score(verity_brain.py:550~552)에서 None * weight → TypeError → "
            "analyze_stock outer try(verity_brain.py:2082~2097)에서 catch → brain_score=0, grade=WATCH 폴백."
        ),
        "scenario": (
            "DART 수집기 부분 실패로 dart_financials.gross_profit_margin=None 반환 → analyze_stock 폴백 → "
            "정상 fact 70+ 종목이 brain_score=0으로 표시됨."
        ),
        "location": "verity_brain.py:493~600 (_compute_fact_score) 또는 safe_collect.py",
        "fix": (
            "_safe_float(이미 추가됨, verity_brain.py:57~67)를 모든 component get에 적용. "
            "또는 components dict 빌드 시 None을 50으로 normalize."
        ),
    },
    {
        "id": "2-B",
        "title": "Deadman switch 핵심/비핵심 동등 가중치",
        "problem": (
            "validate_deadman_switch(api/health.py:521)가 len(failed_apis) >= 3 단순 카운트. "
            "telegram(알림) + kipris(특허) + public_data(무역통계) 동시 다운만으로 abort. krx_open_api만 optional."
        ),
        "scenario": (
            "관세청 점검 + KIPRIS 점검 + 텔레그램 토큰 만료가 같은 날 발생 → deadman 발동 → "
            "핵심 분석 가능한데 전 파이프라인 중단."
        ),
        "location": "api/health.py:499~551 (validate_deadman_switch)",
        "fix": (
            "API별 가중치 부여(핵심 1.0, 비핵심 0.3). score >= 3 또는 핵심 다운 >= 임계 시 abort."
        ),
    },
    {
        "id": "2-C",
        "title": "gs_bonus cap 명시 부재",
        "problem": (
            "_compute_group_structure_bonus(verity_brain.py:1542~1568)가 vci_bonus(±10), candle_bonus(±10), "
            "inst_bonus(0~3)와 달리 명시적 cap 없음. 현재는 산술 구조상 ±5 한정이지만 향후 가산 조건 추가 시 "
            "무한 누적 가능."
        ),
        "scenario": (
            "기획자가 향후 NAV discount 외 외국인 지분율 추가 → 합산 +8/+10까지 가능 → "
            "STRONG_BUY 임계 75 도달이 너무 쉬워짐."
        ),
        "location": "verity_brain.py:1568",
        "fix": "return round(min(5.0, max(-3.0, bonus)), 2) 명시 cap 추가.",
    },
    {
        "id": "2-D",
        "title": "contrarian_upgrade / market_structure / quadrant audit 필드 부재",
        "problem": (
            "analyze_stock의 contrarian_upgrade(verity_brain.py:1740~1752)가 grade 한 단계 상향 시 별도 boolean 필드 "
            "없이 grade만 변경. _apply_market_structure_override(L1971~1985)도 사유는 reasoning 문자열 prefix만."
        ),
        "scenario": (
            "어제 BUY → 오늘 WATCH 강등된 종목 사유 추적 시 bond_penalty/cboe_downgrade는 dict 필드로 가능하나 "
            "contrarian/만기 강등은 reasoning 정규식 파싱 필요. postmortem.py가 misleading_factor 잘못 지목할 위험."
        ),
        "location": "verity_brain.py:1740~1752, 1971~1985",
        "fix": (
            "stock['overrides_applied'] = [] 리스트 부착, 각 단계 적용 시 'contrarian_upgrade', "
            "'expiry_downgrade' 등 append 기록."
        ),
    },
    {
        "id": "2-E",
        "title": "strategy_evolver 음수/이상치 weight 차단 부재",
        "problem": (
            "validate_proposal이 변경량(abs(v - current[k]) > 0.05)만 체크. "
            "새 weight 자체의 범위(0 <= v <= 0.5) 검증 0건."
        ),
        "scenario": (
            "Claude가 'consensus 노이즈 많다'고 판단해 -0.04 제안(현재 0.04 → 0.0 또는 -0.01) → "
            "validator 통과 → fact_score에서 consensus 마이너스 기여."
        ),
        "location": "strategy_evolver.py:404~427",
        "fix": "for k, v in fact_changes.items(): if not (0 <= v <= 0.5): return False, ...",
    },
    {
        "id": "2-F",
        "title": "fact_score 가중치 합 1.0 자동 정규화 부재",
        "problem": (
            "validator는 abs(total - 1.0) > 0.01 통과(strategy_evolver.py:407~409). 자동 정규화 없음. "
            "_compute_sentiment_score(verity_brain.py:786~797)는 런타임 정규화하나 _compute_fact_score(L539~552)는 "
            "그대로 합산."
        ),
        "scenario": (
            "100회 제안 누적 후 합 0.992 → fact_score 평균 0.8% 시스템 편향 → "
            "등급 경계(BUY 60) 부근 종목들의 등급 전환에 영향."
        ),
        "location": "strategy_evolver.py:469~527 (apply_proposal)",
        "fix": (
            "_save_constitution 호출 직전에 fact/sentiment weight를 {k: v / sum(weights.values())}로 정규화."
        ),
    },
]

LOGIC_ITEMS = [
    {
        "id": "3-A",
        "title": "fact 0.7 / sent 0.3 가중치 비율의 실증 근거 부재",
        "problem": (
            "default = bw.get('default', {'fact': 0.70, 'sentiment': 0.30})(verity_brain.py:1651) — 하드코딩 폴백. "
            "constitution.json:389~411 분면별 0.65~0.85 분포 정의는 정성적 설명만. "
            "IC, Sharpe 비교, 백테스트 실증 데이터 검증 흔적은 코드 직접 확인 필요."
        ),
        "scenario": "검증 부재 — 0.65/0.35 또는 0.75/0.25가 더 우수할 가능성 미입증.",
        "location": "verity_brain.py:1651, constitution.json:389~411",
        "fix": (
            "data/strategy_registry.json의 versions[].backtest_after 분석 + 대안 가중치 백테스트 비교 실험. "
            "결과를 docs/ 또는 constitution notes에 명시."
        ),
    },
    {
        "id": "3-B",
        "title": "red_flag_penalty 점수+등급 이중 적용 의도성",
        "problem": (
            "red_flag_penalty = min(downgrade_count × 5, 20)(verity_brain.py:1720)로 점수 차감 + L1729~1730에서 "
            "_downgrade(grade, count) 등급 강등. 같은 downgrade_count가 두 차원 동시 트리거. 코드 주석/문서 부재."
        ),
        "scenario": (
            "base raw=70, downgrade_count=2 → penalty -10 → raw=60(BUY) → _downgrade(BUY, 2)=CAUTION. "
            "점수상 BUY 후보가 CAUTION으로 2단계 강등."
        ),
        "location": "verity_brain.py:1720, 1727~1730",
        "fix": (
            "추가 확인 필요 — 설계 의도가 (a) 보수성 강화 의도 (b) 둘 중 하나만 의도된 버그인지 검증. "
            "backtester로 점수만 차감 vs 등급만 강등 시나리오 비교 권고."
        ),
    },
    {
        "id": "3-C",
        "title": "brain_score 100 cap으로 인한 강도 차이 손실",
        "problem": (
            "이론적 raw 최대 = 70+30+5+5+10+3 = 123. _clip(0, 100)(verity_brain.py:1724)로 잘림. "
            "raw 100과 raw 123 종목이 brain_score=100 동률."
        ),
        "scenario": (
            "STRONG_BUY 후보 5종목 모두 brain_score=100 → top_picks 정렬(verity_brain.py:2104) 안정 정렬 미보장 → "
            "매일 다른 종목이 1위로 표시 가능."
        ),
        "location": "verity_brain.py:1724, 2104",
        "fix": (
            "100 초과를 별도 필드(raw_brain_score)로 보존. top_picks 정렬에 raw_brain_score 우선 적용 검토."
        ),
    },
    {
        "id": "3-D",
        "title": "postmortem 7일/10건 표본 statistical power",
        "problem": (
            "generate_postmortem(days=7)(api/main.py:3260)에서 7일 윈도우, failures[:10](postmortem.py:91)으로 "
            "최대 10건. 이 작은 표본의 misleading_factors 카운트가 strategy_evolver의 입력(L180~191)."
        ),
        "scenario": (
            "장중 폭락일 BUY 4건 -3% 하락. 4건 모두 'sentiment' 라벨 → 다음 strategy_evolution이 sentiment "
            "가중치 -0.05 제안 → 단기 노이즈가 누적 가중치에 영향."
        ),
        "location": "api/main.py:3260, postmortem.py:91",
        "fix": (
            "7/14/30일 윈도우별 misleading_factor 분포 비교. 표본 >= 30 도달 시점까지의 시간 측정. "
            "통계적 유의성 검정(p-value) 도입 검토."
        ),
    },
]

NORMAL_ITEMS = [
    ("brain_score 음수 가드", "verity_brain.py:53~54, 1724", "_clip(0, 100)"),
    ("NaN/inf 3중 방어", "verity_brain.py:580, 788, 1722", "fact/sent/raw 모두"),
    ("vci_bonus cap", "verity_brain.py:1685~1689", "±10 명시"),
    ("candle_bonus cap", "verity_brain.py:380~381", "±10 명시"),
    ("inst_bonus cap", "verity_brain.py:1715~1718", "0~3 분기"),
    ("_detect_bubble_signals 그룹 cap", "verity_brain.py:386~452", "시장 레벨 group A~D 분리"),
    ("auto_avoid 차단 (CRIT-1 fix)", "verity_brain.py:1740", "not has_critical 가드"),
    ("bond_regime 등급 보존 (CRIT-2 fix)", "verity_brain.py:1335~1338, 1351~1354", "_cap_grade 적용"),
    ("safe_collect 폴백", "api/utils/safe_collect.py:35, 48", "result==None 처리"),
    ("XGBoost 피처 정규화", "xgb_predictor.py:75~114, 172, 180", "트리 자연 정규화 + Pipeline scaler"),
    ("XGBoost-collectors 분리", "xgb_predictor.py:300~325", "current_features는 폴백 전용"),
    ("postmortem→strategy_evolver 루프", "main.py:3256~3287, evolver:180~191", "닫힌 루프"),
    ("rollback_strategy 실제 복원 (CRIT-9 fix)", "strategy_evolver.py:544~593", "pre_change_snapshot 적용"),
    ("_save_constitution 원자적 + 백업", "strategy_evolver.py:64~98", "tmp+replace + .bak + 아카이브"),
    ("sentiment_score 런타임 정규화", "verity_brain.py:786~797", "norm = 1.0 / w_sum"),
]

SCORE_BREAKDOWN = [
    ("Core formula safety", "85", NORMAL),
    ("Input signal quality", "60", WARN),
    ("Override chain consistency", "70", INFO),
    ("Self-learning safety", "50", CRIT),
    ("Audit & traceability", "70", INFO),
]


# ── 빌드 ────────────────────────────────────────────────────

def build():
    pdf = AuditPDF()

    # ── Cover ──
    pdf.add_page()
    pdf.ln(20)
    pdf.set_font("Nanum", "B", 24)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 14, "VERITY Brain", ln=True, align="C")
    pdf.set_font("Nanum", "B", 18)
    pdf.set_text_color(*TEXT)
    pdf.cell(0, 10, "통합 감사 리포트", ln=True, align="C")
    pdf.ln(6)
    pdf.set_font("Nanum", "", 11)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, datetime.now().strftime("%Y-%m-%d"), ln=True, align="C")

    pdf.ln(20)
    pdf.set_fill_color(*CARD_BG)
    pdf.set_draw_color(*BORDER)
    pdf.rect(20, pdf.get_y(), 170, 80, "DF")
    pdf.set_xy(28, pdf.get_y() + 8)
    pdf.set_font("Nanum", "B", 11)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 7, "검수 대상", ln=True)
    pdf.set_x(28)
    pdf.set_font("Nanum", "", 10)
    pdf.set_text_color(*TEXT)
    pdf.multi_cell(154, 6, (
        "verity_brain.py · multi_factor.py · claude_analyst.py · strategy_evolver.py · "
        "postmortem.py · verity_constitution.json · 관련 collectors/main.py 호출 경로"
    ))

    pdf.ln(2)
    pdf.set_x(28)
    pdf.set_font("Nanum", "B", 11)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 7, "검수 영역", ln=True)
    pdf.set_x(28)
    pdf.set_font("Nanum", "", 10)
    pdf.set_text_color(*TEXT)
    pdf.multi_cell(154, 6, (
        "1) brain_score 공식 (가중치·cap·음수가드·등급 분포)\n"
        "2) 수집기 → brain 입력 (None 전파·deadman·sentiment 상관·XGB 정규화)\n"
        "3) 시장 구조 오버라이드 체인 (만기·CBOE·panic·quadrant·red_flag·bubble)\n"
        "4) strategy_evolver (자동 승인·드리프트·정규화·학습 루프)"
    ))

    # ── 점수 카드 ──
    pdf.ln(8)
    pdf.set_x(20)
    pdf.set_fill_color(*CARD_BG)
    pdf.set_draw_color(*ACCENT)
    pdf.set_line_width(0.6)
    pdf.rect(20, pdf.get_y(), 170, 30, "DF")
    pdf.set_xy(28, pdf.get_y() + 4)
    pdf.set_font("Nanum", "B", 11)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, "Brain 판단 신뢰도 종합 점수", ln=True)
    pdf.set_x(28)
    pdf.set_font("Nanum", "B", 30)
    pdf.set_text_color(*ACCENT)
    pdf.cell(70, 14, "67 / 100", ln=False)
    pdf.set_font("Nanum", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.set_xy(110, pdf.get_y() + 4)
    pdf.multi_cell(75, 5, (
        "치명 5건 · 구조 6건\n로직 4건 · 정상 15건"
    ))

    # ── Chapter 1: 치명적 결함 ──
    pdf.add_page()
    pdf.chapter_title("1.", "치명적 결함 (즉시 수정)", CRIT)
    for it in CRIT_ITEMS:
        pdf.issue_card(
            it["id"], it["title"], it["problem"], it["scenario"],
            it["location"], it["fix"], CRIT,
        )

    # ── Chapter 2: 구조적 취약점 ──
    pdf.add_page()
    pdf.chapter_title("2.", "구조적 취약점 (스프린트 내 수정)", WARN)
    for it in WARN_ITEMS:
        pdf.issue_card(
            it["id"], it["title"], it["problem"], it["scenario"],
            it["location"], it["fix"], WARN,
        )

    # ── Chapter 3: 로직 타당성 의심 ──
    pdf.add_page()
    pdf.chapter_title("3.", "로직 타당성 의심 항목 (검증 필요)", INFO)
    for it in LOGIC_ITEMS:
        pdf.issue_card(
            it["id"], it["title"], it["problem"], it["scenario"],
            it["location"], it["fix"], INFO,
        )

    # ── Chapter 4: 정상 확인 항목 ──
    pdf.add_page()
    pdf.chapter_title("4.", "정상 확인 항목", NORMAL)
    pdf.normal_table(
        headers=["항목", "코드 위치", "검증 결과"],
        rows=[[r[0], r[1], r[2]] for r in NORMAL_ITEMS],
        col_widths=[68, 72, 50],
    )

    # ── Chapter 5: 종합 평가 ──
    pdf.add_page()
    pdf.chapter_title("5.", "종합 평가", ACCENT)

    pdf.set_font("Nanum", "B", 11)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 7, "영역별 점수 분해", ln=True)
    pdf.ln(2)
    pdf.kv_block([(label, f"{score} / 100", color) for label, score, color in SCORE_BREAKDOWN])

    pdf.ln(4)
    pdf.set_font("Nanum", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 5, "가중 평균 = (85+60+70+50+70) / 5 = 67 / 100")

    pdf.ln(6)
    pdf.set_font("Nanum", "B", 12)
    pdf.set_text_color(*CRIT)
    pdf.cell(0, 8, "가장 시급한 단일 수정 사항", ln=True)
    pdf.set_font("Nanum", "B", 11)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 7, "1-D. strategy_evolver 누적 드리프트 cap 도입", ln=True)
    pdf.ln(2)
    pdf.set_font("Nanum", "", 10)
    pdf.set_text_color(*TEXT)
    reasons = [
        "자기학습 시스템이 무한히 한 방향으로 표류 가능 — 단건 ±0.05 제한만으로는 10회 누적 ±0.5 가능",
        "표류한 가중치는 시스템 전체 출력에 영구 영향 — fact_score 모든 종목에 적용",
        "자동 승인 전환 후엔 사람 개입 없이 누적 — admin 명령(CRIT-10) 통제 외부에서 진행",
        "롤백도 1회 직전 스냅샷만 복원 — 중간 누적 표류는 복원 불가",
        "수정 비용 낮음 — validate_proposal에 ~10줄 추가 + 환경변수 1개로 즉시 적용",
    ]
    for r in reasons:
        pdf.bullet(r)

    pdf.ln(4)
    pdf.set_font("Nanum", "B", 10)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, "수정 코드", ln=True)
    pdf.set_font("Nanum", "", 9)
    pdf.set_text_color(*TEXT)
    code = (
        "# config.py\n"
        "STRATEGY_MAX_CUMULATIVE_DRIFT = _env_float(\n"
        "    \"STRATEGY_MAX_CUMULATIVE_DRIFT\", 0.20\n"
        ")\n\n"
        "# strategy_evolver.py validate_proposal 내부, fact_changes 루프 직후\n"
        "initial_w = (registry[\"versions\"][0]\n"
        "             .get(\"pre_change_snapshot\", {})\n"
        "             .get(\"fact_score_weights\", {}))\n"
        "for k, new_v in fact_changes.items():\n"
        "    if k in initial_w and abs(new_v - initial_w[k]) > STRATEGY_MAX_CUMULATIVE_DRIFT:\n"
        "        return False, (\n"
        "            f\"{k} 누적 드리프트 {abs(new_v - initial_w[k]):.3f} \"\n"
        "            f\"> {STRATEGY_MAX_CUMULATIVE_DRIFT}\"\n"
        "        )\n"
    )
    pdf.set_fill_color(*CARD_BG)
    y0 = pdf.get_y()
    pdf.multi_cell(0, 4.6, code, fill=True)

    # ── 마지막 페이지 검수 메타 ──
    pdf.ln(8)
    pdf.set_draw_color(*BORDER)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Nanum", "", 8)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 4.5, (
        "본 리포트는 정적 코드 분석에 기반하며 외부 API 실호출 없이 생성됨. "
        "CRIT-1 ~ CRIT-17, WARN-1 ~ WARN-24 등 SESSION 1~7에서 발견·수정된 이슈와는 별도 트랙으로, "
        "Brain 시스템 핵심 판단 로직의 신뢰도를 평가한다. "
        "추측 기반 판단은 배제했으며 불확실 항목은 '추가 확인 필요' 또는 '코드 직접 확인 필요'로 명시했다."
    ))

    os.makedirs(os.path.dirname(_OUT_PATH), exist_ok=True)
    pdf.output(_OUT_PATH)
    print(f"PDF 생성: {_OUT_PATH}")
    print(f"크기: {os.path.getsize(_OUT_PATH):,} bytes")


if __name__ == "__main__":
    build()
