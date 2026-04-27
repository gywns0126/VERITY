"""
Dilution 헬퍼 — 관리자용 → 일반인용 콘텐츠 변환.

verity_constitution.json 의 dilution_rules 섹션을 단일 소스 오브 트루스로 사용.
4개 가드 정책 (검증 워터마크 / 시점 표현 / AI fallback / cross-ref) 모두 통합.

호출 예:
    from api.utils.dilution import dilute, apply_grade_guard, ContentBlocked

    label = dilute("VIX", value=28)
    # → "긴장 온도계 28 (주의 구간)"

    grade = apply_grade_guard("STRONG_BUY", validated=False, channel="public")
    # → "BUY"  (자동 강등)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from api.config import DATA_DIR

_logger = logging.getLogger(__name__)
_CONSTITUTION_PATH = os.path.join(DATA_DIR, "verity_constitution.json")
_rules_cache: Optional[Dict[str, Any]] = None


class ContentBlocked(Exception):
    """검증 워터마크 가드가 콘텐츠 발행을 차단할 때."""


# ─── Constitution 로딩 ────────────────────────────────────────

def load_rules(force_reload: bool = False) -> Dict[str, Any]:
    """dilution_rules 섹션 로드 + 캐시. force_reload=True 면 재로드."""
    global _rules_cache
    if _rules_cache is not None and not force_reload:
        return _rules_cache
    try:
        with open(_CONSTITUTION_PATH, "r", encoding="utf-8") as f:
            const = json.load(f)
        _rules_cache = const.get("dilution_rules") or {}
    except Exception as e:
        _logger.error("dilution rules load failed: %s", e)
        _rules_cache = {}
    return _rules_cache


def _all_term_rules() -> Dict[str, Dict[str, Any]]:
    """카테고리 전체에서 term → rule 평탄화 dict."""
    rules = load_rules()
    cats = rules.get("categories") or {}
    out: Dict[str, Dict[str, Any]] = {}
    for _cat_key, cat in cats.items():
        for r in (cat.get("rules") or []):
            term = r.get("term")
            if term:
                out[term] = r
                # alias 도 같은 rule 가리킴
                for alias in (r.get("aliases") or []):
                    out[alias] = r
    return out


# ─── 공개 변환 함수 ───────────────────────────────────────────

def dilute(term: str, value: Optional[Any] = None, sector: Optional[str] = None) -> str:
    """
    용어/지표를 일반인 친화적 표현으로 변환.

    Args:
        term: 변환 대상 용어 (예: "VIX", "PER", "STRONG_BUY", "부채비율")
        value: 숫자 값 (있으면 임계치 기반 구간 라벨 부여)
        sector: 섹터 컨텍스트 — sector_variants 분기. 부채비율은 "general"|"construction"|"financial"|"aviation_shipping".
                유동비율은 "general"|"retail". None 이면 일반 산업 default.

    Returns:
        일반인용 표현. 룰북에 없으면 원본 term 반환 (fallback).
    """
    if not term:
        return ""
    term_rules = _all_term_rules()
    rule = term_rules.get(term)
    if not rule:
        return f"{term} {value}" if value is not None else term

    # sector-aware 분기 (부채비율·유동비율 등)
    sv = None
    if rule.get("sector_variants"):
        variants = rule["sector_variants"]
        sv = variants.get(sector) if sector else None
        if sv is None:
            sv = variants.get("general") or variants.get("default") or {}

    if sv:
        label = sv.get("label") or rule.get("label_default") or rule.get("label", term)
        thresholds = sv.get("thresholds") or rule.get("thresholds") or []
    else:
        label = rule.get("label") or rule.get("label_default", term)
        thresholds = rule.get("thresholds") or []

    # value 가 있으면 맥락 라벨 추가 (원칙 #2)
    if value is not None:
        value_str = _format_value(value, rule.get("unit"))
        ctx = _match_threshold_label(thresholds, value)
        if ctx:
            return f"{label} {value_str} ({ctx})"
        return f"{label} {value_str}"
    return label


# 자명한 단위(지수형·비율형) 는 출력에 표시 안 함 — 자연스러운 한국어
_INVISIBLE_UNITS = {"지수", "지수형", "비율", "배수"}


def _format_value(value: Any, unit: Optional[str]) -> str:
    """수치 + 단위 자연스러운 한국어 포맷."""
    s = str(value)
    if not unit:
        return s
    if unit in _INVISIBLE_UNITS:
        return s
    # 단위가 이미 값에 포함되어 있으면 중복 회피
    if s.endswith(unit):
        return s
    return f"{s}{unit}"


def _match_threshold_label(thresholds: list, value: Any) -> str:
    """thresholds 리스트에서 value 매칭되는 구간 라벨 반환."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    for t in thresholds:
        lo = t.get("min")
        hi = t.get("max")
        lo_ok = lo is None or v >= lo
        hi_ok = hi is None or v < hi
        if lo_ok and hi_ok:
            return t.get("label", "")
    return ""


# ─── 가드 함수들 ──────────────────────────────────────────────

def apply_grade_guard(grade: str, validated: bool = False, channel: str = "admin") -> str:
    """
    검증 워터마크 가드. 검증 미완료 + public 채널이면 강등.

    Returns: 강등된 등급 (예: STRONG_BUY → BUY)
    """
    if validated or channel == "admin":
        return grade
    if channel in ("public", "instagram"):
        if grade == "STRONG_BUY":
            return "BUY"
        if grade == "STRONG_AVOID":
            return "AVOID"
    return grade


def apply_label_guard(label: str, validated: bool = False, channel: str = "admin") -> str:
    """검증 미완료 + public 시 🔥 같은 강한 신호 라벨 강등."""
    if validated or channel == "admin":
        return label
    if channel in ("public", "instagram"):
        return label.replace("🔥", "🟢")
    return label


def block_ticker_content(stock_name: Optional[str], grade: Optional[str],
                         validated: bool = False, channel: str = "admin") -> None:
    """
    검증 미완료 + instagram 채널에서 종목명+등급 조합 차단.
    feedback_scope: 검증 전 종목 추천 콘텐츠 금지.

    Raises:
        ContentBlocked: 차단 조건 충족 시
    """
    if validated or channel != "instagram":
        return
    if stock_name and grade in ("STRONG_BUY", "BUY", "STRONG_AVOID", "AVOID"):
        raise ContentBlocked(
            f"검증 미완료 — 종목명 + 등급 조합 외부 발행 차단: {stock_name} ({grade})"
        )


def timestamp_label(source: Optional[str], as_of: Optional[str] = None) -> str:
    """매크로 지표 시점 표기. feedback_macro_timestamp_policy 묶음."""
    if not source:
        return ""
    src = source.lower()
    if src == "yfinance":
        return "(실시간 또는 가장 최근 거래일 기준)" if not as_of else f"({as_of} 종가 기준)"
    if src == "fred":
        return f"({as_of} 종가 기준)" if as_of else "(지난 거래일 종가 기준)"
    if src == "ecos":
        return f"({as_of} 발표 기준)" if as_of else "(한국은행 최근 발표 기준)"
    return f"({as_of})" if as_of else ""


def translate_ai_fallback(backend_message: Optional[str]) -> Optional[str]:
    """
    백엔드 AI fallback 메시지 → 일반인용 톤. None 반환 시 섹션 숨김 의미.
    feedback_ai_fallback_sanitization 묶음.
    """
    if not backend_message:
        return None
    msg = str(backend_message).strip()
    if not msg or msg.startswith("_error"):
        return None  # 사용자 노출 절대 금지
    if "AI 분석 일시 불가" in msg:
        return "오늘 분석을 다시 검토 중입니다"
    if "분석 스킵" in msg or "json_parse_failed" in msg:
        return None  # 섹션 숨김
    return msg  # 그 외엔 그대로 (룰에 없는 메시지)


# ─── 유틸 ─────────────────────────────────────────────────────

def get_principles() -> list:
    """6대 원칙 반환 — LLM 프롬프트에 system instruction 으로 주입 가능."""
    return load_rules().get("principles") or []


def build_dictionary_for_prompt(max_items_per_category: int = 12) -> str:
    """
    룰북 → LLM 프롬프트용 변환 사전 텍스트.
    note-only 항목 + 임계 항목 모두 포함하여 LLM이 일관된 톤으로 변환할 수 있게 한다.

    Returns:
        멀티라인 텍스트 — system_instruction 또는 user_prompt 에 주입.
    """
    rules = load_rules()
    cats = rules.get("categories") or {}
    out_lines = ["[일반인 변환 사전 — 이 표현 외에 임의 단어 사용 금지]"]
    for _key, cat in cats.items():
        # ESTATE 부동산은 daily 리포트에 안 쓰임 — 제외
        if _key == "real_estate":
            continue
        out_lines.append(f"\n# {cat.get('name')}")
        for r in (cat.get("rules") or [])[:max_items_per_category]:
            term = r.get("term")
            if not term:
                continue
            label = r.get("label") or r.get("label_default")
            line = f"- {term} → {label}"
            if r.get("note"):
                line += f" (메모: {r['note']})"
            elif r.get("thresholds"):
                # 첫·마지막 구간만 압축 표시
                thr = r["thresholds"]
                if len(thr) >= 2:
                    first = thr[0].get("label", "")
                    last = thr[-1].get("label", "")
                    line += f" (구간: {first} ~ {last})"
            out_lines.append(line)
    out_lines.append("\n[규칙]")
    out_lines.append("- 위 표에 없는 전문 용어는 괄호로 풀어서 설명")
    out_lines.append("- 같은 개념의 다중 라벨 (변동성·VIX·베타) 동시 사용 금지 — 1차 라벨만")
    out_lines.append("- 수익 보장 표현 금지 ('반드시 오릅니다', '확실히 좋습니다' 등)")
    return "\n".join(out_lines)


def get_forbidden_phrases() -> list:
    """절대 사용 금지 표현 (LLM 프롬프트 negative constraint)."""
    return load_rules().get("forbidden") or []


def scenario_label(role: str = "primary", validated: bool = False,
                   backtest_samples: int = 0) -> str:
    """
    시나리오 라벨링. 검증 미완료 시 '주요/대안/극단', 검증 후 확률 표기 허용.

    Args:
        role: 'primary' | 'alternative' | 'tail'
        validated: 검증 정책 통과 여부
        backtest_samples: 백테스트 누적 샘플 수
    """
    rules = load_rules()
    guard = (rules.get("guards") or {}).get("scenario_labeling") or {}
    defaults = guard.get("default_labels") or {
        "primary": "주요 시나리오",
        "alternative": "대안 시나리오",
        "tail": "극단 시나리오",
    }
    return defaults.get(role, defaults["primary"])


def can_show_probability(validated: bool, backtest_samples: int = 0) -> bool:
    """확률 표기 가능 여부. 검증 미완료 또는 샘플 부족 시 False."""
    return validated and backtest_samples >= 200


# ─── Cross-reference 자동 검출 ────────────────────────────

# 같은 개념의 다중 라벨 — 한 글에 동시 등장 시 1차 라벨만 사용
_CROSS_REF_GROUPS = [
    {
        "concept": "변동성·불안",
        "primary": "VIX",
        "aliases": ["변동성", "σ", "volatility", "베타", "β", "beta"],
    },
    {
        "concept": "주가 대비 가격",
        "primary": "PER",
        "aliases": ["비싼지 싼지", "이익 대비 가격", "PSR", "EV/EBITDA"],
    },
]


def detect_cross_ref_conflicts(text: str) -> list:
    """
    텍스트에서 같은 개념의 다중 라벨이 동시 등장하는지 검출.

    Returns:
        [{"concept": str, "primary": str, "found_aliases": [str]}, ...]
    """
    out = []
    if not text:
        return out
    for grp in _CROSS_REF_GROUPS:
        primary = grp["primary"]
        primary_in = primary in text
        found = [a for a in grp["aliases"] if a in text]
        if primary_in and found:
            out.append({
                "concept": grp["concept"],
                "primary": primary,
                "found_aliases": found,
                "advice": f"'{primary}' 와 {found} 가 동시 등장. 1차 라벨만 사용 권장.",
            })
    return out


def normalize_cross_ref(text: str) -> str:
    """
    동일 개념 다중 라벨 정리 — alias 등장 시 첫 등장 후 제거.
    LLM 출력 후처리에 사용.

    예: "VIX 28이고 변동성도 큽니다" → "VIX 28이고 변동성도 큽니다 (※ VIX와 변동성 = 같은 개념)"
    """
    if not text:
        return text
    conflicts = detect_cross_ref_conflicts(text)
    if not conflicts:
        return text
    notes = []
    for c in conflicts:
        notes.append(f"※ '{c['primary']}'과 {c['found_aliases']} 는 같은 개념입니다")
    return text + "\n\n" + "\n".join(notes)


def brain_grade_from_score(score: Optional[float]) -> str:
    """
    Brain Score → 등급 매핑. 룰북의 brain_grades.score_range 사용.
    v2.0 임계: STRONG_BUY 75+ / BUY 60-74 / WATCH 45-59 / CAUTION 30-44 / AVOID 30↓

    Returns:
        등급 문자열. score 가 None 이거나 매칭 안 되면 "WATCH" 기본.
    """
    if score is None:
        return "WATCH"
    rules = load_rules()
    bg = (rules.get("categories") or {}).get("brain_grades", {}).get("rules") or []
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "WATCH"
    for r in bg:
        sr = r.get("score_range") or {}
        lo = sr.get("min")
        hi = sr.get("max")
        lo_ok = lo is None or s >= lo
        hi_ok = hi is None or s <= hi  # max 포함 (v2.0 테이블 기준)
        if lo_ok and hi_ok:
            return r.get("term", "WATCH")
    return "WATCH"


def grade_label(grade: str) -> str:
    """등급 → 일반인 라벨 (룰북에서 동적 로드). 예: BUY → '🟢 좋아 보여요'."""
    rules = load_rules()
    bg = (rules.get("categories") or {}).get("brain_grades", {}).get("rules") or []
    for r in bg:
        if r.get("term") == grade or grade in (r.get("aliases") or []):
            icon = r.get("icon", "")
            label = r.get("label", grade)
            return f"{icon} {label}".strip()
    return grade


def is_validated(vams_data: Optional[Dict[str, Any]] = None) -> bool:
    """
    VAMS 검증 완료 여부. project_validation_plan 메모리 정책.

    환경변수 강제 우선 (수동 override). 없으면 VAMS 데이터 기반 자동 판정:
      - 누적 거래 횟수 >= MIN_TRADES (200)
      - 검증 기간 >= MIN_DAYS (90, 약 3개월)
      - 승률 >= MIN_HIT_RATE (55%)
      - 평균 수익률 >= 0

    Args:
        vams_data: VAMS 누적 통계. None 이면 환경변수만 확인.
    """
    # 1. 환경변수 강제 우선
    env = os.environ.get("VERITY_VAMS_VALIDATED", "").lower()
    if env in ("1", "true", "yes"):
        return True
    if env in ("0", "false", "no"):
        return False

    # 2. VAMS 데이터 기반 자동 판정
    if not isinstance(vams_data, dict):
        return False

    total_trades = vams_data.get("total_trades", 0)
    days_active = vams_data.get("days_active", 0)
    hit_rate = vams_data.get("hit_rate", 0)
    avg_return = vams_data.get("avg_return", 0)

    return (
        total_trades >= 200
        and days_active >= 90
        and hit_rate >= 55
        and avg_return >= 0
    )


def validation_status_summary(vams_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    검증 상태 진단 메타. 리포트 워터마크에 사용.

    Returns:
        {
          "validated": bool,
          "samples": int,
          "days_active": int,
          "hit_rate": float,
          "watermark_label": str  # "검증 진행 중 — 표본 N개 / D일"
        }
    """
    vd = vams_data or {}
    samples = vd.get("total_trades", 0)
    days = vd.get("days_active", 0)
    hit_rate = vd.get("hit_rate", 0)
    validated = is_validated(vd)
    if validated:
        label = "검증 통과 — 통계적 의미 확보"
    else:
        label = f"검증 진행 중 — 표본 {samples}건 / {days}일 (필요: 200건 / 90일 / 승률 55%↑)"
    return {
        "validated": validated,
        "samples": samples,
        "days_active": days,
        "hit_rate": hit_rate,
        "avg_return": vd.get("avg_return", 0),
        "watermark_label": label,
    }
