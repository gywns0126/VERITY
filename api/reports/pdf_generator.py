"""
VERITY — PDF 리포트 생성기

portfolio.json의 모든 분석 결과를 종합하여
전문 투자 리포트 PDF를 생성한다.

출력: data/verity_report_daily.pdf (일일)
      data/verity_report_weekly.pdf (주간) 등
"""
from __future__ import annotations

import os
import urllib.request
from typing import Any, Dict, List, Optional

from fpdf import FPDF

from api.config import DATA_DIR, now_kst

_FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
_FONT_PATH = os.path.join(_FONT_DIR, "NanumGothic.ttf")
_FONT_BOLD_PATH = os.path.join(_FONT_DIR, "NanumGothicBold.ttf")
_FONT_URL = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
_FONT_BOLD_URL = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf"


def _ensure_fonts():
    """한글 폰트 다운로드 (없으면)."""
    os.makedirs(_FONT_DIR, exist_ok=True)
    for path, url in [(_FONT_PATH, _FONT_URL), (_FONT_BOLD_PATH, _FONT_BOLD_URL)]:
        if not os.path.exists(path):
            try:
                urllib.request.urlretrieve(url, path)
            except Exception as e:
                print(f"  폰트 다운로드 실패 ({url}): {e}")


def _norm_text(s: Any) -> str:
    if s is None:
        return ""
    t = str(s).replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
    return t.strip()


def _portfolio_updated_str(portfolio: Dict[str, Any]) -> str:
    u = portfolio.get("updated_at") or ""
    if len(u) >= 19:
        return u[:19].replace("T", " ") + " (KST 기준일시는 저장 메타데이터를 따름)"
    return now_kst().strftime("%Y-%m-%d %H:%M:%S")


def _doc_id(portfolio: Dict[str, Any]) -> str:
    u = portfolio.get("updated_at") or now_kst().strftime("%Y-%m-%dT%H:%M:%S")
    d = u[:10].replace("-", "")
    return f"VERITY-DR-{d}"


def _executive_summary_narrative(portfolio: Dict[str, Any]) -> str:
    """제1장 요약 — 수치·AI 한줄을 공문체로 엮음."""
    macro = portfolio.get("macro", {})
    mood = macro.get("market_mood", {})
    report = portfolio.get("daily_report", {})
    brain = portfolio.get("verity_brain", {}) or {}
    mb = brain.get("market_brain") or {}
    ov = brain.get("macro_override")

    parts: List[str] = []
    parts.append(
        "본 절에서는 당일 수집·가공된 시장 지표와 규칙기반·AI 분석 결과를 요약한다. "
        "세부 수치는 후술하는 각 장에서 교차 확인할 수 있다."
    )
    parts.append(
        f"거시 분위기 지표는 {mood.get('label', '중립')} 수준(점수 {mood.get('score', '-')})으로 나타났으며, "
        f"공포지수(VIX)는 {macro.get('vix', {}).get('value', '-')} 부근, 원·달러 환율은 "
        f"{macro.get('usd_krw', {}).get('value', '-')}원 전후로 관측되었다."
    )
    if mb.get("avg_brain_score") is not None:
        parts.append(
            f"종목 단위 자료를 통합한 Verity Brain의 시장 평균 점수는 {mb.get('avg_brain_score')}점이다. "
            f"객관 지표 가중 평균(팩트) {mb.get('avg_fact_score', '-')}점, "
            f"심리 지표 가중 평균 {mb.get('avg_sentiment_score', '-')}점이며, "
            f"양자 괴리를 나타내는 VCI는 {mb.get('avg_vci', 0):+d}로 산출되었다."
        )
    if ov and ov.get("mode"):
        parts.append(
            f"매크로 극단 구간에 해당하여 「{ov.get('label', ov.get('mode'))}」 오버라이드가 적용되었다. "
            f"요지는 다음과 같다. {_norm_text(ov.get('reason') or ov.get('message'))}"
        )
    if report.get("market_summary"):
        parts.append(f"[AI 종합 한줄] {_norm_text(report['market_summary'])}")
    return "\n\n".join(parts)


def _methodology_narrative() -> str:
    return (
        "가. 분석 범위\n"
        "본 보고서는 다음 자료를 입력으로 한다. "
        "(1) 국내외 주가지수·환율·단기·장기 금리 및 원자재 시세, "
        "(2) 미 연준(FRED)·한국은행(ECOS) 등 공개 거시통계 시계열, "
        "(3) 국내 업종·섹터 수익률 및 투자주체 수급, "
        "(4) 뉴스 헤드라인 및 소셜(X) 기반 시장 심리 지표, "
        "(5) 기관 컨센서스·목표가 및 재무제표 공시(DART) 요약, "
        "(6) 기술적 지표·멀티팩터 점수·머신러닝(XGBoost) 확률 예측, "
        "(7) 규칙기반 종합엔진 Verity Brain의 등급·레드플래그, "
        "(8) 생성형 AI(Gemini·선택 시 Claude)의 서술형 해석.\n\n"
        "나. 산출 절차\n"
        "수집 데이터는 먼저 정합성 검사(Deadman's Switch)를 거친 뒤, 종목별로 기술·수급·감성·컨센서스를 결합하고, "
        "Brain 점수 및 등급을 부여한다. 이후 AI 모델이 동일 수치를 참고하여 문장형 요약을 생성한다.\n\n"
        "다. 자료의 한계\n"
        "모든 수치는 파이프라인 실행 시점 기준이며, 장중 실시간 호가와 불일치할 수 있다. "
        "공시·뉴스의 누락·지연 가능성이 있다. 본 문서는 투자자문·증권 매매 권유가 아니며, "
        "손익 책임은 투자자 본인에게 있다."
    )


def _macro_environment_narrative(macro: Dict[str, Any]) -> str:
    lines: List[str] = []
    mood = macro.get("market_mood", {})
    lines.append(
        f"당일 관측된 시장 분위기 지표는 {mood.get('label', '중립')}(점수 {mood.get('score', '-')})이다. "
        f"이는 환율·금리·해외 지수·원자재 변동을 종합한 내부 스코어링 결과이다."
    )
    lines.append(
        f"VIX {macro.get('vix', {}).get('value', '-')}, "
        f"원/달러 {macro.get('usd_krw', {}).get('value', '-')}원, "
        f"WTI {macro.get('wti_oil', {}).get('value', '-')}달러, "
        f"금 현물 기준가 {macro.get('gold', {}).get('value', '-')}달러 수준에서 거래되었다."
    )
    sp = macro.get("sp500", {}) or {}
    ndx = macro.get("nasdaq", {}) or {}
    lines.append(
        f"미국 S&P500 전일 대비 {sp.get('change_pct', 0):+.2f}%, "
        f"나스닥 {ndx.get('change_pct', 0):+.2f}%로 집계되었다."
    )
    ysp = macro.get("yield_spread", {}) or {}
    if ysp.get("value") is not None:
        lines.append(
            f"장단기 금리 스프레드(10년-2년)는 {ysp.get('value')}%p이며, "
            f"내부 신호는 「{_norm_text(ysp.get('signal'))}」로 분류되었다."
        )
    fred = macro.get("fred") or {}
    dgs = fred.get("dgs10") or {}
    if dgs.get("value") is not None:
        lines.append(
            f"미국 10년 만기 국채 수익률(FRED DGS10)은 {dgs.get('value')}% "
            f"(관측일 {dgs.get('date', '-')})이다."
        )
    cpi = fred.get("core_cpi") or {}
    if cpi.get("yoy_pct") is not None:
        lines.append(f"미국 근원 CPI 전년동월 대비 {cpi.get('yoy_pct')}% 수준이다.")
    m2 = fred.get("m2") or {}
    if m2.get("yoy_pct") is not None:
        lines.append(f"미국 M2 통화량 전년 대비 증가율은 약 {m2.get('yoy_pct')}%이다.")
    ecos = macro.get("ecos") or {}
    kr = ecos.get("korea_policy_rate") or {}
    if kr.get("value") is not None:
        lines.append(f"한국은행 기준금리는 {kr.get('value')}%({kr.get('date', '-')})로 확인되었다.")
    diags = macro.get("macro_diagnosis") or []
    if diags:
        lines.append("자동 매크로 진단 요지는 다음과 같다.")
        for d in diags[:10]:
            tx = _norm_text(d.get("text"))
            if tx:
                lines.append(f"· {tx}")
    micro = macro.get("micro_signals") or []
    for sig in micro[:2]:
        label = sig.get("label", "")
        data = sig.get("data") or []
        if label and data:
            bits = [f"{x.get('name', '?')} ({x.get('change_pct', 0):+.2f}%)" for x in data[:3]]
            lines.append(f"{label}: " + ", ".join(bits))
    return "\n\n".join(lines)


def _capital_flow_narrative(cf: Dict[str, Any]) -> str:
    if not cf:
        return ""
    comm = cf.get("commodities") or {}
    bond = cf.get("bonds") or {}
    eq = cf.get("equities") or {}
    lines = [
        "원자재·채권(달러)·주식 3섹터 상대 강도를 일간 변동률로 비교하여 자금 쏠림 방향을 추정하였다.",
        f"원자재 군 점수 {comm.get('score', '-')}(당일 변동률 합성 {comm.get('change_pct', '-')}%), "
        f"채권·달러 군 {bond.get('score', '-')}({bond.get('change_pct', '-')}%), "
        f"주식 군 {eq.get('score', '-')}({eq.get('change_pct', '-')}%).",
        f"추정 자금 이동 방향 코드: {cf.get('flow_direction', '-')}.",
        f"해석: {_norm_text(cf.get('interpretation'))}",
    ]
    adj = cf.get("ecos_adjustments")
    if adj:
        lines.append("ECOS/FRED 보정 로그: " + "; ".join(str(x) for x in adj))
    return "\n\n".join(lines)


def _commodity_impact_narrative(portfolio: Dict[str, Any]) -> str:
    scout = portfolio.get("commodity_impact") or {}
    if not scout:
        return ""
    lines = [
        "주요 종목과 원자재 가격의 상관·마진 민감도를 스카우팅한 결과는 다음과 같다.",
    ]
    hi = scout.get("high_correlation") or []
    if hi:
        lines.append("고상관 종목(요약): " + ", ".join(str(x.get("name", x)) for x in hi[:8]))
    alerts = scout.get("commodity_mom_alerts") or []
    if alerts:
        lines.append("전월 대비 급변 알림: " + "; ".join(str(a) for a in alerts[:5]))
    nar = scout.get("narrative_summary") or scout.get("summary")
    if nar:
        lines.append(_norm_text(nar))
    return "\n\n".join(lines)


def _x_sentiment_narrative(portfolio: Dict[str, Any]) -> str:
    x = portfolio.get("x_sentiment") or {}
    if not x:
        return ""
    return (
        f"X(트위터) 샘플 기반 시장 심리 점수는 {x.get('score', '-')}점이며, "
        f"수집 건수는 {x.get('tweet_count', '-')}건이다. "
        f"요지: {_norm_text(x.get('summary') or x.get('headline'))}"
    )


def _stock_detail_block(stock: Dict[str, Any]) -> str:
    """종목별 서술형 근거 (잘리지 않게)."""
    name = stock.get("name", "?")
    ticker = stock.get("ticker", "")
    rec = stock.get("recommendation", "-")
    conf = stock.get("confidence", "")
    parts = [f"【{name} ({ticker})】 최종 권고: {rec}" + (f", 신뢰도 {conf}" if conf else "")]
    vb = stock.get("verity_brain") or {}
    if vb.get("reasoning"):
        parts.append(f"· Brain 판단 근거: {_norm_text(vb['reasoning'])}")
    if stock.get("ai_verdict"):
        parts.append(f"· Gemini 의견: {_norm_text(stock['ai_verdict'])}")
    ca = stock.get("claude_analysis") or {}
    if ca.get("verdict"):
        parts.append(f"· Claude 검증: {_norm_text(ca['verdict'])}")
    if ca.get("vci_analysis"):
        parts.append(f"· VCI 해석(Claude): {_norm_text(ca['vci_analysis'])}")
    if ca.get("conviction_note"):
        parts.append(f"· 확신도 메모: {_norm_text(ca['conviction_note'])}")
    hr = ca.get("hidden_risks") or []
    if hr:
        parts.append("· 잠재 리스크: " + "; ".join(_norm_text(h) for h in hr[:5]))
    if stock.get("gold_insight"):
        parts.append(f"· 강점 요인: {_norm_text(stock['gold_insight'])}")
    if stock.get("silver_insight"):
        parts.append(f"· 보조 요인: {_norm_text(stock['silver_insight'])}")
    mf = stock.get("multi_factor") or {}
    if mf.get("all_signals"):
        sigs = mf["all_signals"][:6]
        parts.append("· 멀티팩터 시그널: " + ", ".join(_norm_text(s) for s in sigs))
    return "\n".join(parts)


def _conclusion_narrative(portfolio: Dict[str, Any]) -> str:
    report = portfolio.get("daily_report", {})
    briefing = portfolio.get("briefing", {})
    lines = [
        "종합하면, 당일 자료가 시사하는 바는 상기 각 장의 표·서술에 정리되어 있다. "
        "투자 실행 전에는 유동성·슬리피지·세금·공시 일정을 별도 확인할 것을 권고한다.",
    ]
    if briefing.get("headline"):
        lines.append(f"비서 브리핑 요지: {_norm_text(briefing['headline'])}")
    items = briefing.get("action_items") or []
    if items:
        lines.append("권장 액션(자동 생성): " + " / ".join(_norm_text(i) for i in items[:6]))
    if report.get("tomorrow_outlook"):
        lines.append(f"단기 전망(참고): {_norm_text(report['tomorrow_outlook'])}")
    lines.append(
        "면책: 본 보고서는 정보 제공 목적의 자동 산출물이며, 특정 금융상품의 매수·매도를 권유하지 않는다. "
        "법령 및 내부 규정에 따른 투자 한도·적합성 점검은 별도로 수행되어야 한다."
    )
    return "\n\n".join(lines)


def _rec_by_ticker(recs: List[Dict[str, Any]], ticker: Any) -> Optional[Dict[str, Any]]:
    if ticker is None:
        return None
    ts = str(ticker)
    for r in recs:
        if str(r.get("ticker")) == ts:
            return r
    return None


class VerityPDF(FPDF):
    """VERITY 디자인 시스템 적용 PDF."""

    BG = (0, 0, 0)
    CARD_BG = (17, 17, 17)
    BORDER = (34, 34, 34)
    ACCENT = (181, 255, 25)
    WHITE = (255, 255, 255)
    GRAY = (153, 153, 153)
    DARK_GRAY = (102, 102, 102)
    GREEN = (34, 197, 94)
    RED = (239, 68, 68)
    BLUE = (96, 165, 250)
    PURPLE = (167, 139, 250)
    YELLOW = (255, 214, 0)
    ORANGE = (245, 158, 11)

    GRADE_COLORS = {
        "STRONG_BUY": (34, 197, 94),
        "BUY": (181, 255, 25),
        "WATCH": (255, 214, 0),
        "CAUTION": (245, 158, 11),
        "AVOID": (239, 68, 68),
    }
    GRADE_LABELS = {
        "STRONG_BUY": "강력매수",
        "BUY": "매수",
        "WATCH": "관망",
        "CAUTION": "주의",
        "AVOID": "회피",
    }

    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        _ensure_fonts()
        if os.path.exists(_FONT_PATH):
            self.add_font("Nanum", "", _FONT_PATH, uni=True)
        if os.path.exists(_FONT_BOLD_PATH):
            self.add_font("Nanum", "B", _FONT_BOLD_PATH, uni=True)
        self._font_name = "Nanum" if os.path.exists(_FONT_PATH) else "Helvetica"
        self.set_auto_page_break(auto=True, margin=15)

    def _set_font(self, style: str = "", size: int = 10):
        self.set_font(self._font_name, style, size)

    def header(self):
        self.set_fill_color(*self.BG)
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*self.CARD_BG)
        self.rect(0, 0, 210, 18, "F")
        self.set_draw_color(*self.BORDER)
        self.line(0, 18, 210, 18)

        self._set_font("B", 9)
        self.set_text_color(*self.ACCENT)
        self.set_xy(10, 5)
        self.cell(0, 4, "VERITY TERMINAL", ln=False)

        self._set_font("", 7)
        self.set_text_color(*self.DARK_GRAY)
        self.set_xy(10, 10)
        self.cell(0, 4, f"AI 자산 보안 비서  |  {now_kst().strftime('%Y-%m-%d %H:%M KST')}", ln=False)

        self._set_font("", 7)
        self.set_text_color(*self.GRAY)
        self.set_xy(160, 5)
        self.cell(0, 4, f"p.{self.page_no()}", ln=False, align="R")
        self.set_y(22)

    def footer(self):
        self.set_y(-14)
        self._set_font("", 5)
        self.set_text_color(*self.DARK_GRAY)
        self.cell(0, 4, "본 문서는 자동생성 참고자료이며 법적·회계적 효력을 가지지 않습니다.", align="C")
        self.set_y(-9)
        self.cell(0, 4, "VERITY AI | 투자 결과에 대한 책임은 투자자 본인에게 있습니다.", align="C")

    def chapter_title(self, num: int, title: str):
        if self.get_y() > 248:
            self.add_page()
        self._set_font("B", 12)
        self.set_text_color(*self.WHITE)
        self.set_x(12)
        self.cell(0, 8, f"제{num}장  {title}")
        self.ln(1)
        self.set_draw_color(*self.BORDER)
        y = self.get_y()
        self.line(12, y, 198, y)
        self.ln(5)

    def subsection_title(self, title: str):
        if self.get_y() > 262:
            self.add_page()
        self._set_font("B", 10)
        self.set_text_color(*self.ACCENT)
        self.set_x(15)
        self.cell(0, 6, title)
        self.ln(4)

    def narrative_paragraphs(self, text: str, size: int = 9):
        t = _norm_text(text)
        if not t:
            return
        self._set_font("", size)
        self.set_text_color(204, 204, 204)
        for block in t.split("\n\n"):
            b = block.strip()
            if not b:
                continue
            if self.get_y() > 275:
                self.add_page()
            self.set_x(15)
            self.multi_cell(180, 5, b)
            self.ln(3)

    def section_title(self, icon: str, title: str, color: tuple = None):
        """섹션 헤더."""
        if self.get_y() > 260:
            self.add_page()
        c = color or self.ACCENT
        self.set_draw_color(*c)
        self.set_fill_color(c[0], c[1], c[2])
        y = self.get_y()
        self.rect(10, y, 2, 6, "F")
        self._set_font("B", 11)
        self.set_text_color(*c)
        self.set_xy(15, y - 0.5)
        self.cell(0, 7, f"{icon}  {title}")
        self.ln(10)

    def card_start(self):
        """카드 배경 시작."""
        self._card_y = self.get_y()

    def card_end(self):
        """카드 배경 끝."""
        y_end = self.get_y()
        self.set_fill_color(*self.CARD_BG)
        self.set_draw_color(*self.BORDER)
        self.rect(10, self._card_y - 2, 190, y_end - self._card_y + 4, "D")

    def metric_row(self, items: List[Dict[str, Any]]):
        """지표 행 (라벨 + 값 쌍)."""
        col_w = 180 / max(len(items), 1)
        x0 = 15
        y0 = self.get_y()

        for item in items:
            self.set_fill_color(10, 10, 10)
            self.rect(x0, y0, col_w - 2, 14, "F")

            self._set_font("", 7)
            self.set_text_color(*self.DARK_GRAY)
            self.set_xy(x0 + 3, y0 + 1)
            self.cell(col_w - 6, 5, str(item.get("label", "")))

            color = item.get("color", self.WHITE)
            self._set_font("B", 10)
            self.set_text_color(*color)
            self.set_xy(x0 + 3, y0 + 6)
            self.cell(col_w - 6, 7, str(item.get("value", "")))

            x0 += col_w

        self.set_y(y0 + 17)

    def text_block(self, text: str, color: tuple = None):
        """본문 텍스트 블록."""
        c = color or (204, 204, 204)
        self._set_font("", 9)
        self.set_text_color(*c)
        self.set_x(15)
        self.multi_cell(180, 5, text)
        self.ln(2)

    def stock_row(self, rank: int, name: str, ticker: str, score: int, grade: str, extra: str = ""):
        """종목 한 줄."""
        gc = self.GRADE_COLORS.get(grade, self.GRAY)
        gl = self.GRADE_LABELS.get(grade, grade)
        y = self.get_y()

        if y > 275:
            self.add_page()
            y = self.get_y()

        self.set_fill_color(*self.CARD_BG)
        self.rect(15, y, 180, 8, "F")

        self._set_font("B", 8)
        self.set_text_color(*gc)
        self.set_xy(17, y + 1)
        self.cell(8, 6, str(rank))

        self._set_font("B", 9)
        self.set_text_color(*self.WHITE)
        self.set_xy(25, y + 1)
        self.cell(60, 6, name)

        self._set_font("", 7)
        self.set_text_color(*self.DARK_GRAY)
        self.set_xy(85, y + 1)
        self.cell(25, 6, str(ticker))

        self._set_font("B", 10)
        self.set_text_color(*gc)
        self.set_xy(115, y + 1)
        self.cell(15, 6, str(score), align="R")

        self._set_font("", 8)
        self.set_xy(135, y + 1)
        self.cell(20, 6, gl)

        if extra:
            self._set_font("", 7)
            self.set_text_color(*self.GRAY)
            self.set_xy(158, y + 1)
            self.cell(35, 6, extra, align="R")

        self.set_y(y + 9)

    def divider(self):
        y = self.get_y()
        self.set_draw_color(*self.BORDER)
        self.line(15, y, 195, y)
        self.ln(3)

    def bar_chart(self, items: List[Dict[str, Any]], max_val: float = None):
        """간단한 수평 바 차트."""
        mv = max_val or max((abs(i.get("value", 0)) for i in items), default=1)
        for item in items:
            y = self.get_y()
            if y > 278:
                self.add_page()
                y = self.get_y()

            self._set_font("", 7)
            self.set_text_color(*self.GRAY)
            self.set_xy(15, y)
            self.cell(35, 5, str(item.get("label", "")), align="R")

            bar_w = min(abs(item.get("value", 0)) / mv * 100, 100)
            c = item.get("color", self.GREEN)
            self.set_fill_color(*c)
            self.rect(53, y + 0.5, bar_w, 4, "F")

            self._set_font("B", 8)
            self.set_text_color(*c)
            self.set_xy(155, y)
            v = item.get("value", 0)
            self.cell(20, 5, f"{'+' if v >= 0 else ''}{v:.1f}%", align="R")

            self.set_y(y + 6)

        self.ln(2)


def generate_daily_pdf(portfolio: Dict[str, Any]) -> str:
    """일일 종합 리포트 PDF (공문체 장·절, 서술형 상세)."""
    pdf = VerityPDF()
    pdf.add_page()

    date_str = now_kst().strftime("%Y년 %m월 %d일")
    report = portfolio.get("daily_report", {}) or {}
    brain = portfolio.get("verity_brain", {}) or {}
    macro_ov = brain.get("macro_override") or {}
    market_brain = brain.get("market_brain", {}) or {}
    macro = portfolio.get("macro", {}) or {}
    fred = macro.get("fred") or {}
    ecos = macro.get("ecos") or {}
    recs: List[Dict[str, Any]] = list(portfolio.get("recommendations", []) or [])

    pdf._set_font("B", 16)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(12)
    pdf.cell(0, 8, "일일 시장·종목 종합 분석 보고서")
    pdf.ln(6)
    pdf._set_font("", 9)
    pdf.set_text_color(*pdf.GRAY)
    pdf.set_x(12)
    pdf.multi_cell(180, 5, "VERITY 자동분석 체계 출력물 (참고용 · 투자자문 또는 매매 권유 아님)")
    pdf.ln(2)
    pdf.set_x(12)
    pdf.cell(0, 5, f"문서번호: {_doc_id(portfolio)}")
    pdf.ln(5)
    pdf.set_x(12)
    pdf.cell(0, 5, f"작성·집계 기준: {_portfolio_updated_str(portfolio)}")
    pdf.ln(5)
    pdf.set_x(12)
    pdf.cell(0, 5, f"보고 일자: {date_str}")
    pdf.ln(8)

    if report.get("market_summary"):
        pdf.set_fill_color(10, 26, 0)
        y = pdf.get_y()
        pdf.rect(10, y, 190, 12)
        pdf._set_font("B", 10)
        pdf.set_text_color(*pdf.ACCENT)
        pdf.set_xy(14, y + 2)
        pdf.multi_cell(182, 4, _norm_text(report["market_summary"]))
        pdf.ln(8)

    if macro_ov.get("mode"):
        mode = str(macro_ov["mode"]).lower()
        c = pdf.RED if mode == "panic" else pdf.BLUE if mode == "yield_defense" else pdf.YELLOW
        pdf.set_fill_color(c[0] // 4, c[1] // 4, c[2] // 4)
        y = pdf.get_y()
        pdf.rect(10, y, 190, 10)
        pdf._set_font("B", 9)
        pdf.set_text_color(*c)
        pdf.set_xy(14, y + 2)
        pdf.multi_cell(
            182,
            4,
            "특이사항(매크로 오버라이드): "
            + _norm_text(str(macro_ov.get("label", "")))
            + " — "
            + _norm_text(macro_ov.get("reason") or macro_ov.get("message")),
        )
        pdf.ln(12)

    pdf.chapter_title(1, "요약")
    pdf.narrative_paragraphs(_executive_summary_narrative(portfolio))

    pdf.chapter_title(2, "분석 범위·방법 및 자료의 한계")
    pdf.narrative_paragraphs(_methodology_narrative())

    pdf.chapter_title(3, "거시경제·금융시장 환경")
    pdf.narrative_paragraphs(_macro_environment_narrative(macro))
    cf = macro.get("capital_flow") or {}
    if cf:
        pdf.subsection_title("3-1. 자금 흐름 추정(3-섹터)")
        pdf.narrative_paragraphs(_capital_flow_narrative(cf))
    cx = _commodity_impact_narrative(portfolio)
    if cx:
        pdf.subsection_title("3-2. 원자재 민감도")
        pdf.narrative_paragraphs(cx)
    xs = _x_sentiment_narrative(portfolio)
    if xs:
        pdf.subsection_title("3-3. 소셜 미디어 시장 심리")
        pdf.narrative_paragraphs(xs)

    pdf.subsection_title("3-4. 주요 지표(표)")
    mood = macro.get("market_mood", {})
    mood_score = mood.get("score", 50)
    mood_c = pdf.GREEN if mood_score >= 60 else pdf.RED if mood_score <= 40 else pdf.YELLOW
    vix_val = macro.get("vix", {}).get("value", 0)
    vix_c = pdf.RED if vix_val and float(vix_val) > 25 else pdf.GREEN
    pdf.metric_row([
        {"label": "시장 분위기", "value": f"{mood.get('label', '-')} ({mood_score}점)", "color": mood_c},
        {"label": "VIX", "value": str(vix_val or "-"), "color": vix_c},
        {"label": "USD/KRW", "value": f"{macro.get('usd_krw', {}).get('value', '-')}원", "color": pdf.WHITE},
        {"label": "FRED DGS10", "value": f"{fred.get('dgs10', {}).get('value', '-')}%", "color": pdf.BLUE},
    ])
    sp_chg = macro.get("sp500", {}).get("change_pct", 0) or 0
    ndx_chg = macro.get("nasdaq", {}).get("change_pct", 0) or 0
    pdf.metric_row([
        {"label": "S&P500", "value": f"{'+' if sp_chg >= 0 else ''}{sp_chg:.2f}%", "color": pdf.GREEN if sp_chg >= 0 else pdf.RED},
        {"label": "NASDAQ", "value": f"{'+' if ndx_chg >= 0 else ''}{ndx_chg:.2f}%", "color": pdf.GREEN if ndx_chg >= 0 else pdf.RED},
        {"label": "금", "value": f"${macro.get('gold', {}).get('value', '-')}", "color": pdf.YELLOW},
        {"label": "WTI", "value": f"${macro.get('wti_oil', {}).get('value', '-')}", "color": pdf.WHITE},
    ])
    kr_rate = ecos.get("korea_policy_rate", {}).get("value")
    kr_10y = fred.get("korea_gov_10y", {}).get("value")
    cpi_v = fred.get("core_cpi", {}).get("yoy_pct")
    m2_v = fred.get("m2", {}).get("yoy_pct")
    extra_items: List[Dict[str, Any]] = []
    if kr_rate:
        extra_items.append({"label": "한국 기준금리", "value": f"{kr_rate}%", "color": pdf.BLUE})
    if kr_10y:
        extra_items.append({"label": "한국 국고10Y", "value": f"{kr_10y}%", "color": pdf.BLUE})
    if cpi_v:
        extra_items.append({"label": "근원 CPI YoY", "value": f"{cpi_v}%", "color": pdf.ORANGE})
    if m2_v:
        extra_items.append({"label": "M2 YoY", "value": f"{m2_v}%", "color": pdf.PURPLE})
    if extra_items:
        pdf.metric_row(extra_items[:4])

    pdf.chapter_title(4, "Verity Brain 종합 판단")
    avg_brain = market_brain.get("avg_brain_score")
    if avg_brain is not None:
        pdf.narrative_paragraphs(
            "Brain 점수는 객관 지표(컨센서스·예측·백테스트·타이밍·원자재·수출 등)에 높은 가중을 두고, "
            "심리 지표(뉴스·X감성·시장분위기·컨센서스 투자의견)를 보조적으로 결합한다. "
            "VCI(Verity Contrarian Index)는 팩트 점수와 심리 점수의 차이로 정의되며, "
            "괴리가 클수록 시장 심리와 기본면의 불일치가 크다고 본다."
        )
        avg_fact = market_brain.get("avg_fact_score", 0)
        avg_sent = market_brain.get("avg_sentiment_score", 0)
        avg_vci = market_brain.get("avg_vci", 0)
        bc = pdf.GREEN if avg_brain >= 65 else pdf.YELLOW if avg_brain >= 45 else pdf.RED
        fc = pdf.GREEN if avg_fact >= 65 else pdf.YELLOW if avg_fact >= 45 else pdf.RED
        sc = pdf.BLUE if avg_sent >= 65 else pdf.YELLOW if avg_sent >= 45 else pdf.RED
        pdf.metric_row([
            {"label": "종합", "value": str(avg_brain), "color": bc},
            {"label": "팩트", "value": str(avg_fact), "color": fc},
            {"label": "심리", "value": str(avg_sent), "color": sc},
            {"label": "VCI", "value": f"{'+' if avg_vci >= 0 else ''}{avg_vci}", "color": pdf.ACCENT if avg_vci > 15 else pdf.RED if avg_vci < -15 else pdf.GRAY},
        ])
        grade_dist = market_brain.get("grade_distribution", {})
        if grade_dist:
            parts = [
                f"{pdf.GRADE_LABELS.get(g, g)} {grade_dist.get(g, 0)}종"
                for g in ["STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"]
                if grade_dist.get(g)
            ]
            pdf.narrative_paragraphs("등급 분포: " + ", ".join(parts))
    else:
        pdf.narrative_paragraphs(
            "당일 산출 JSON에 Brain 시장 집계가 없을 수 있다. 장 마감 full 파이프라인 실행 및 portfolio.json 갱신 여부를 확인한다."
        )

    pdf.chapter_title(5, "생성형 AI 기반 시장 해석 및 전략")
    if report.get("market_analysis"):
        pdf.subsection_title("5-1. 시장 상황 분석")
        pdf.narrative_paragraphs(_norm_text(report["market_analysis"]))
    if report.get("strategy"):
        pdf.subsection_title("5-2. 전략적 시사점")
        pdf.narrative_paragraphs(_norm_text(report["strategy"]))
    if report.get("hot_theme"):
        pdf.subsection_title("5-3. 주목 테마")
        pdf.narrative_paragraphs(_norm_text(report["hot_theme"]))
    if report.get("risk_watch"):
        pdf.subsection_title("5-4. 리스크 및 유의사항")
        pdf.narrative_paragraphs(_norm_text(report["risk_watch"]))
    if report.get("tomorrow_outlook"):
        pdf.subsection_title("5-5. 단기 전망(참고)")
        pdf.narrative_paragraphs(_norm_text(report["tomorrow_outlook"]))

    top_picks = market_brain.get("top_picks", []) or []
    pdf.chapter_title(6, "주요 종목 평가")
    if top_picks:
        pdf.subsection_title("6-1. Brain 탑픽")
        for i, tp in enumerate(top_picks[:10], 1):
            full = _rec_by_ticker(recs, tp.get("ticker"))
            raw_bs = tp.get("brain_score") if tp.get("brain_score") is not None else tp.get("score", 0)
            try:
                bsi = int(round(float(raw_bs)))
            except (TypeError, ValueError):
                bsi = 0
            vci_val = 0
            if full:
                vci_val = (full.get("verity_brain") or {}).get("vci", {}).get("vci", 0) or 0
            extra = f"VCI {'+' if vci_val >= 0 else ''}{vci_val}"
            pdf.stock_row(i, tp.get("name", "?"), str(tp.get("ticker", "")), bsi, tp.get("grade", "WATCH"), extra)
        for tp in top_picks[:6]:
            full = _rec_by_ticker(recs, tp.get("ticker"))
            if full:
                pdf.narrative_paragraphs(_stock_detail_block(full))

    buy_recs = [
        r
        for r in recs
        if r.get("recommendation") == "BUY" or (r.get("verity_brain") or {}).get("grade") in ("STRONG_BUY", "BUY")
    ]
    avoid_recs = [
        r
        for r in recs
        if r.get("recommendation") == "AVOID" or (r.get("verity_brain") or {}).get("grade") in ("CAUTION", "AVOID")
    ]

    if buy_recs:
        pdf.subsection_title("6-2. 매수·적극 관심 종목(표 및 상세 서술)")
        for i, s in enumerate(buy_recs[:15], 1):
            br = s.get("verity_brain", {})
            bs = br.get("brain_score") if br.get("brain_score") is not None else (s.get("multi_factor", {}) or {}).get("multi_score", 0)
            grade = br.get("grade") or s.get("recommendation", "BUY")
            price = s.get("price", 0)
            extra = ""
            try:
                if price:
                    extra = f"{float(price):,.0f}원"
            except (TypeError, ValueError):
                extra = ""
            try:
                bsi = int(round(float(bs)))
            except (TypeError, ValueError):
                bsi = 0
            pdf.stock_row(i, s.get("name", "?"), str(s.get("ticker", "")), bsi, str(grade), extra)
        for s in buy_recs[:8]:
            pdf.narrative_paragraphs(_stock_detail_block(s))

    if avoid_recs:
        pdf.subsection_title("6-3. 주의·회피 권고 종목")
        for i, s in enumerate(avoid_recs[:12], 1):
            br = s.get("verity_brain", {})
            bs = br.get("brain_score") if br.get("brain_score") is not None else (s.get("multi_factor", {}) or {}).get("multi_score", 0)
            grade = br.get("grade") or s.get("recommendation", "AVOID")
            rf = br.get("red_flags", {})
            flags = (rf.get("auto_avoid", []) or []) + (rf.get("downgrade", []) or [])
            extra = ""
            if flags:
                extra = _norm_text(flags[0])[:26] + "..."
            try:
                bsi = int(round(float(bs)))
            except (TypeError, ValueError):
                bsi = 0
            pdf.stock_row(i, s.get("name", "?"), str(s.get("ticker", "")), bsi, str(grade), extra)
        for s in avoid_recs[:5]:
            pdf.narrative_paragraphs(_stock_detail_block(s))

    pdf.chapter_title(7, "섹터·산업 동향")
    sectors = portfolio.get("sectors", []) or []
    if sectors:
        top_s = sorted(sectors, key=lambda s: s.get("change_pct", 0), reverse=True)[:5]
        bottom_s = sorted(sectors, key=lambda s: s.get("change_pct", 0))[:3]
        pdf.bar_chart(
            [{"label": s.get("name", "?"), "value": s.get("change_pct", 0), "color": pdf.GREEN} for s in top_s]
            + [{"label": s.get("name", "?"), "value": s.get("change_pct", 0), "color": pdf.RED} for s in bottom_s]
        )
    rotation = portfolio.get("sector_rotation", {}) or {}
    if rotation.get("cycle_label"):
        pdf.narrative_paragraphs(
            f"경기 국면 분류: {rotation.get('cycle_label')}. {_norm_text(rotation.get('cycle_desc'))}"
        )

    pdf.chapter_title(8, "정보환경·일정")
    headlines = portfolio.get("headlines", []) or []
    if headlines:
        pdf.subsection_title("8-1. 뉴스 헤드라인")
        for h in headlines[:12]:
            if pdf.get_y() > 275:
                pdf.add_page()
            y = pdf.get_y()
            sent = h.get("sentiment", "neutral")
            ic = pdf.GREEN if sent == "positive" else pdf.RED if sent == "negative" else pdf.GRAY
            pdf.set_fill_color(*ic)
            pdf.rect(16, y + 1.5, 2, 2, "F")
            pdf._set_font("", 8)
            pdf.set_text_color(204, 204, 204)
            pdf.set_xy(20, y)
            pdf.multi_cell(175, 4, _norm_text(h.get("title", ""))[:220])
            pdf.ln(1)
    events = portfolio.get("global_events", []) or []
    upcoming = [e for e in events if (e.get("d_day") or 99) <= 14]
    if upcoming:
        pdf.subsection_title("8-2. 다가오는 이벤트(D-14 이내)")
        for e in upcoming[:8]:
            line = f"{_norm_text(e.get('name'))} (D-{e.get('d_day', '?')})."
            imp = _norm_text(e.get("impact"))
            if imp:
                line += " " + imp
            pdf.narrative_paragraphs(line)

    ch_next = 9
    vams = portfolio.get("vams", {}) or {}
    holdings = vams.get("holdings", []) or []
    if holdings:
        pdf.chapter_title(ch_next, "가상 포트폴리오(VAMS) 현황")
        ch_next += 1
        total_return = float(vams.get("total_return_pct", 0) or 0)
        total_asset = float(vams.get("total_asset", 0) or 0)
        cash = float(vams.get("cash", 0) or 0)
        rc = pdf.GREEN if total_return >= 0 else pdf.RED
        pdf.metric_row([
            {"label": "총 자산", "value": f"{total_asset:,.0f}원", "color": pdf.WHITE},
            {"label": "수익률", "value": f"{'+' if total_return >= 0 else ''}{total_return:.2f}%", "color": rc},
            {"label": "현금", "value": f"{cash:,.0f}원", "color": pdf.GRAY},
            {"label": "보유", "value": f"{len(holdings)}종목", "color": pdf.WHITE},
        ])
        for h in holdings:
            if pdf.get_y() > 278:
                pdf.add_page()
            y = pdf.get_y()
            pct = float(h.get("return_pct", 0) or 0)
            c = pdf.GREEN if pct >= 0 else pdf.RED
            pdf._set_font("", 8)
            pdf.set_text_color(*pdf.WHITE)
            pdf.set_xy(16, y)
            pdf.cell(100, 5, f"{h.get('name', '?')} ({h.get('quantity', 0)}주)")
            pdf._set_font("B", 9)
            pdf.set_text_color(*c)
            pdf.set_xy(130, y)
            pdf.cell(50, 5, f"{'+' if pct >= 0 else ''}{pct:.2f}%", align="R")
            pdf.set_y(y + 6)

    pdf.chapter_title(ch_next, "결론·교차검증·브리핑 및 면책")
    briefing = portfolio.get("briefing", {}) or {}
    if briefing.get("headline"):
        pdf.subsection_title("가. 운영 브리핑 요약")
        pdf.narrative_paragraphs(_norm_text(briefing["headline"]))
    acts = briefing.get("action_items") or []
    if acts:
        pdf.subsection_title("나. 권장 조치(자동 생성)")
        pdf.narrative_paragraphs("\n".join(f"· {_norm_text(a)}" for a in acts[:8]))

    cv = portfolio.get("cross_verification", {}) or {}
    disagreements = cv.get("disagreements", []) or []
    if disagreements:
        pdf.subsection_title("다. AI 모델 간 이견(참고)")
        for d in disagreements:
            pdf.narrative_paragraphs(
                f"{d.get('name', '?')} (종목코드 {d.get('ticker', '-')}). "
                f"1차(Gemini) {_norm_text(str(d.get('gemini_rec')))}, 2차(Claude) {_norm_text(str(d.get('claude_rec')))}. "
                f"검토 사유: {_norm_text(d.get('reason'))}"
            )

    pdf.subsection_title("라. 종합 정리 및 면책")
    pdf.narrative_paragraphs(_conclusion_narrative(portfolio))

    output_path = os.path.join(DATA_DIR, "verity_report_daily.pdf")
    pdf.output(output_path)
    return output_path

def generate_periodic_pdf(portfolio: Dict[str, Any], period: str = "weekly") -> Optional[str]:
    """정기 리포트 PDF (주간/월간/분기)."""
    key_map = {
        "weekly": "weekly_report",
        "monthly": "monthly_report",
        "quarterly": "quarterly_report",
    }
    label_map = {"weekly": "주간", "monthly": "월간", "quarterly": "분기"}
    report_key = key_map.get(period)
    if not report_key:
        return None
    pr = portfolio.get(report_key)
    if not pr:
        return None

    label = label_map.get(period, period)
    pdf = VerityPDF()
    pdf.add_page()

    pdf._set_font("B", 16)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(12)
    pdf.cell(0, 8, f"{label} 시장·성과 종합 분석 보고서")
    pdf.ln(5)
    pdf._set_font("", 8)
    pdf.set_text_color(*pdf.GRAY)
    pdf.set_x(12)
    pdf.cell(0, 5, f"문서번호: {_doc_id(portfolio)}-{period}")
    pdf.ln(8)

    date_range = pr.get("_date_range", {})
    if date_range:
        pdf.set_x(12)
        pdf.cell(0, 5, f"분석 기간: {date_range.get('start', '')} ~ {date_range.get('end', '')}")
        pdf.ln(6)

    if pr.get("executive_summary"):
        pdf.set_fill_color(10, 26, 0)
        y = pdf.get_y()
        pdf.rect(10, y, 190, 14, "F")
        pdf._set_font("B", 11)
        pdf.set_text_color(*pdf.ACCENT)
        pdf.set_xy(15, y + 2)
        pdf.multi_cell(180, 5, _norm_text(pr["executive_summary"]))
        pdf.ln(6)

    pdf.chapter_title(1, "요약 및 성과 지표")
    pdf.narrative_paragraphs(
        f"본 보고서는 {label} 구간 동안의 추천 성과·섹터 동향·매크로 전망을 아카이브 스냅샷과 AI 서술로 정리한 것이다. "
        "수치는 동일 기간 내 저장된 portfolio 스냅샷에 기반한다."
    )

    stats = pr.get("_raw_stats", {})
    if stats:
        pdf.subsection_title("1-1. 추천 성과(표)")
        hit_rate = stats.get("hit_rate_pct", 0)
        avg_ret = stats.get("avg_return_pct", 0)
        pdf.metric_row([
            {"label": "BUY 추천", "value": f"{stats.get('total_buy_recs', 0)}건", "color": pdf.WHITE},
            {"label": "적중률", "value": f"{hit_rate}%", "color": pdf.GREEN if hit_rate >= 50 else pdf.RED},
            {"label": "평균 수익률", "value": f"{'+' if avg_ret >= 0 else ''}{avg_ret}%", "color": pdf.GREEN if avg_ret >= 0 else pdf.RED},
        ])

        best = stats.get("best_picks", [])
        if best:
            pdf._set_font("B", 8)
            pdf.set_text_color(*pdf.GREEN)
            pdf.set_x(15)
            pdf.cell(0, 5, "최고 수익 종목")
            pdf.ln(5)
            for s in best[:5]:
                y = pdf.get_y()
                pdf._set_font("", 8)
                pdf.set_text_color(204, 204, 204)
                pdf.set_xy(18, y)
                pdf.cell(80, 5, s.get("name", "?"))
                pct = s.get("return_pct", 0)
                c = pdf.GREEN if pct >= 0 else pdf.RED
                pdf._set_font("B", 9)
                pdf.set_text_color(*c)
                pdf.set_xy(130, y)
                pdf.cell(45, 5, f"{'+' if pct >= 0 else ''}{pct}%", align="R")
                pdf.set_y(y + 6)

    if pr.get("performance_review"):
        pdf.chapter_title(2, "성과 복기(서술)")
        pdf.narrative_paragraphs(_norm_text(pr["performance_review"]))

    if pr.get("sector_analysis"):
        pdf.chapter_title(3, "섹터·산업 동향")
        pdf.narrative_paragraphs(_norm_text(pr["sector_analysis"]))

    if pr.get("meta_insight"):
        pdf.subsection_title("3-1. 메타 인사이트")
        pdf.narrative_paragraphs(_norm_text(pr["meta_insight"]))

    if pr.get("macro_outlook"):
        pdf.chapter_title(4, "매크로 환경 전망")
        pdf.narrative_paragraphs(_norm_text(pr["macro_outlook"]))

    if pr.get("strategy"):
        pdf.chapter_title(5, f"향후 {label} 전략")
        pdf.narrative_paragraphs(_norm_text(pr["strategy"]))

    if pr.get("brain_review"):
        pdf.subsection_title("5-1. 브레인 등급별 평가")
        pdf.narrative_paragraphs(_norm_text(pr["brain_review"]))

    if pr.get("risk_watch"):
        pdf.chapter_title(6, "리스크 및 유의사항")
        pdf.narrative_paragraphs(_norm_text(pr["risk_watch"]))

    pdf.narrative_paragraphs(
        "면책: 본 정기 보고서 역시 자동 생성 참고자료이며, 투자자문이 아니다. "
        "실제 투자는 자기책임 원칙에 따라 판단할 것."
    )

    filename = f"verity_report_{period}.pdf"
    output_path = os.path.join(DATA_DIR, filename)
    pdf.output(output_path)
    return output_path


def generate_all_reports(portfolio: Dict[str, Any]) -> List[str]:
    """일일 + 가용한 정기 리포트 전부 생성."""
    paths = []
    try:
        p = generate_daily_pdf(portfolio)
        paths.append(p)
        print(f"  PDF 생성: {p}")
    except Exception as e:
        print(f"  일일 PDF 실패: {e}")

    for period in ("weekly", "monthly", "quarterly"):
        try:
            p = generate_periodic_pdf(portfolio, period)
            if p:
                paths.append(p)
                print(f"  PDF 생성: {p}")
        except Exception as e:
            print(f"  {period} PDF 실패: {e}")

    return paths
