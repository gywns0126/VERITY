"""multibagger_watch — 텐버거 후보 WATCH (로깅 전용, 결정 0).

2026-06-09 신설. PM 결정 B (US 확장 대신 KR 소형주 + 멀티배거). 동결 funnel(품질-가치)이
구조적으로 밀어내는 *초기 텐버거형 KR 소형주*를 별 렌즈로 관측·누적.

원칙:
  - 로깅 전용. 결정/실자본 영향 0. active 결정 운영 = 2026-09 gate (project_multi_bagger_watch 결정 22).
    watch 는 *관측*이라 gate 위배 아님 (decision_logging_separation 정합).
  - 재사용: lynch_classifier.classify_lynch_kr (6분류) + multi_bagger_signals.evaluate_multi_bagger_signals
    (5 신호: revenue_acceleration / operating_leverage / category_leader / industry_s_curve / hold_pnl).
    새 신호 로직 0.
  - "시간이 해자" — 언제 텐버거 후보였나는 backfill 불가. forward-only append.
  - funnel freeze 와 무관 (별 트랙, 결정 직교).

watch list = KR 소형주(floor 위 ~ 대형 아래) 중 Fast Grower OR 신호 1+ triggered (focused).
"""
from __future__ import annotations

import json
import os
from datetime import date as _date
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst
from api.intelligence.lynch_classifier import classify_lynch_kr
from api.analyzers.multi_bagger_signals import (
    detect_hold_pnl_threshold,
    evaluate_multi_bagger_signals,
)

_PATH = os.path.join(DATA_DIR, "metadata", "multibagger_watch.jsonl")
# 보유 축은 **별 파일**. 유니버스 행(시총·Lynch·5신호)과 스키마가 달라 한 파일에 섞으면
# 소비자가 동질 population 을 가정하다 깨진다(실측: 기존 end-to-end 테스트가 즉시 실패).
_HOLD_PATH = os.path.join(DATA_DIR, "metadata", "multibagger_holdings.jsonl")

# 소형주 watch 범위 상한 (텐버거 zone: hard_floor 위 ~ 대형 아래). 관측 범위지 결정 임계 아님 — env 조정 가능.
SMALLCAP_MAX_KRW = int(os.environ.get("MULTIBAGGER_SMALLCAP_MAX_KRW", str(1_000_000_000_000)))  # 1조원


def _is_kr_smallcap(s: Dict[str, Any]) -> bool:
    if (s.get("currency") or "").upper() == "USD":
        return False
    mc = s.get("market_cap")
    try:
        mc = float(mc)
    except (TypeError, ValueError):
        return False
    return 0 < mc < SMALLCAP_MAX_KRW


def build_watch(stocks: List[Dict[str, Any]], as_of: Optional[str] = None) -> List[Dict[str, Any]]:
    """KR 소형주 중 Fast Grower OR 신호 triggered 후보만 watch 레코드 생성 (로깅 전용).

    peers = KR 소형주 모집단 (category_leader/industry_s_curve 섹터 peer 비교용).
    """
    as_of = as_of or now_kst().strftime("%Y-%m-%d")
    smallcaps = [s for s in (stocks or []) if _is_kr_smallcap(s)]
    peers = {"recommendations": smallcaps}  # multi_bagger_signals 섹터 peer context

    out: List[Dict[str, Any]] = []
    for s in smallcaps:
        lynch = classify_lynch_kr(s)
        sigs = evaluate_multi_bagger_signals(s, peers)
        is_fast = lynch.get("class") == "FAST_GROWER"
        alert_count = int(sigs.get("alert_count", 0) or 0)
        if not (is_fast or alert_count > 0):
            continue  # focused watch list — 무신호 소형주 제외
        out.append({
            "watch_date": as_of,
            "ticker": str(s.get("ticker")),
            "name": s.get("name"),
            "market_cap": s.get("market_cap"),
            "sector": s.get("sector"),
            "lynch_class": lynch.get("class"),
            "lynch_data_quality": lynch.get("data_quality"),
            "alert_count": alert_count,
            "signals": {
                # 🚨 2026-08-06 — reason 을 함께 남긴다.
                # 이전엔 {triggered, score} 만 저장해 **죽은 신호와 정상 미발동이 구분되지
                # 않았다**. industry_s_curve(미구현 스텁)·hold_pnl_threshold(입력 구조적 부재)가
                # 29,271건 내내 0회였는데 trail 만으로는 알 수 없어 소스를 읽어야 했다.
                # 산출 함수가 이미 사유를 담고 있다("산업 CAGR 데이터 미수집" 등) — 버리지 않는다.
                k: {"triggered": bool(v.get("triggered")), "score": v.get("score"),
                    "reason": v.get("reason")}
                for k, v in sigs.items() if isinstance(v, dict)
            },
            "spec_version": "watch.v0",
            "note": "로깅 전용 — 결정 0 (active gate 2026-09)",
        })
    return out


def log_watch(records: List[Dict[str, Any]], path: Optional[str] = None) -> int:
    """watch 레코드 append (forward-only). 실패해도 caller 진행 (부수효과)."""
    if not records:
        return 0
    target = path or _PATH
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(records)


def _hold_days(buy_date: Any, as_of: str) -> Optional[int]:
    """매수일 → 보유 일수. 파싱 실패 시 None (0 으로 만들지 않는다)."""
    try:
        b = _date.fromisoformat(str(buy_date)[:10])
        a = _date.fromisoformat(as_of)
    except (TypeError, ValueError):
        return None
    d = (a - b).days
    return d if d >= 0 else None


def build_holding_flowers(portfolio: Optional[Dict[str, Any]] = None,
                          as_of: Optional[str] = None) -> List[Dict[str, Any]]:
    """보유 종목에 대한 hold_pnl_threshold 평가 (2026-08-06 PM 승인 — 소비자 이전).

    사인 조사 결과: Lynch "꽃을 뽑지 마라"는 **보유 포지션** 규칙인데 유일한 호출자가
    **미보유 유니버스 스캔**이었다(hold_days 0/29,271 → 구조상 발동 불가). 대상을 옮긴다.

    ⚠️ 옮겨도 당분간 0 이 정상이다 — 임계가 보유 180일인데 VAMS 리셋(2026-05-17) 이후
    최장 보유가 42일(2026-08-07 기준)이다. **2026-11-13 이전 발동은 구조적으로 불가.**
    그때까지의 0 은 "미충족"이지 "고장"이 아니며, reason 이 그 둘을 구분해 기록한다.

    나머지 4신호는 평가하지 않는다 — 보유 레코드는 포지션 정보이지 종목 펀더멘털이
    아니라서(매출성장률·섹터 peer 부재) 평가하면 전부 결손으로 나온다.
    """
    as_of = as_of or now_kst().strftime("%Y-%m-%d")
    if portfolio is None:
        try:
            with open(os.path.join(DATA_DIR, "portfolio.json"), encoding="utf-8") as f:
                portfolio = json.load(f)
        except (OSError, json.JSONDecodeError):
            return []
    holdings = ((portfolio.get("vams") or {}).get("holdings")) or []

    out: List[Dict[str, Any]] = []
    for h in holdings:
        days = _hold_days(h.get("buy_date"), as_of)
        sig = detect_hold_pnl_threshold({
            "hold_days": days,
            "return_pct": h.get("return_pct"),
        })
        out.append({
            "watch_date": as_of,
            "source": "holding",          # 파일이 분리돼 있지만 병합 분석 시를 위해 명시
            "ticker": str(h.get("ticker")),
            "name": h.get("name"),
            "hold_days": days,
            "return_pct": h.get("return_pct"),
            "signals": {"hold_pnl_threshold": {
                "triggered": bool(sig.get("triggered")),
                "score": sig.get("score"),
                "reason": sig.get("reason"),
            }},
            "alert_count": 1 if sig.get("triggered") else 0,
            "spec_version": "watch.v0",
            "note": "로깅 전용 — 결정 0 (active gate 2026-09)",
        })
    return out


def run_watch(stocks: List[Dict[str, Any]], path: Optional[str] = None,
              portfolio: Optional[Dict[str, Any]] = None,
              hold_path: Optional[str] = None) -> int:
    """build + log 일괄 (wide_scan 등 caller 진입점). 반환 = 로깅된 행 수.

    유니버스 스캔(KR 소형주 텐버거 후보) + 보유 종목 hold_pnl 평가 두 축을 함께 기록한다.
    보유 축 실패가 유니버스 축을 죽이지 않는다.
    """
    n = log_watch(build_watch(stocks), path=path)
    try:
        n += log_watch(build_holding_flowers(portfolio), path=hold_path or _HOLD_PATH)
    except Exception as e:  # noqa: BLE001 — 관측 실패가 funnel 을 죽이지 않는다
        import sys as _sys
        print(f"[multibagger_watch] 보유 축 skip: {type(e).__name__}: {e}", file=_sys.stderr)
    return n
