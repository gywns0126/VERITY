"""분산매도 정황 관측 (Distribution Footprint) — observation ONLY.

⚠️ 관측 ONLY — 점수/등급/결정 wire 0. data/observations/distribution_footprint.jsonl append.

배경 (AlphaNest 유리박스 mandate): 기관·대주주가 개미를 *출구 유동성(exit liquidity)* 으로
분산매도하는 정황을 **공개 사실**로 노출하는 역(방어) 렌즈. "기관 따라사기/다음 수 추론"이
아니다 — 그건 RULE 6(LLM 내러티브) + 거짓(숏/옵션 비공시라 공개정보로 불가) + 법률 저촉.

🚨 데이터 한계 (출력에 항상 병기): 13F = 롱만·45일 지연·숏/옵션/스왑 비공시. 따라서
'지금 무엇을 하는지'는 공개정보로 알 수 없다. 본 관측 = KR 외국인/기관 일별 순매매(KIS) +
대량보유 변동(DART 5%룰) 의 **사실 발자국**. 가설. 점수·추천 0.

플래그 정의 (고정 — 사후 변경 = 신규 사전등록. docs/PREREG_DISTRIBUTION_FOOTPRINT_2026_06_25.md):
  · foreign_net_sell        : flow 외국인 순매도(<0)
  · foreign_consec_sell_Nd  : 외국인 N일 연속 순매도 (N>=3)
  · inst_net_sell           : 기관 순매도(<0)
  · inst_consec_sell_Nd     : 기관 N일 연속 순매도 (N>=3)
  · major_holder_reduction  : DART 대량보유 변동 중 delta_pct_pt <= -1.0 (1%p+ 축소)
  · institution_overhang    : 기관보유율 >= 30% (분산 잠재물량 context — sell 아님)
flag 리스트 + count 만. 등급/순위/verdict 절대 X (RULE 7).
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

OBS_DIR = os.path.join(DATA_DIR, "observations")
OBS_PATH = os.path.join(OBS_DIR, "distribution_footprint.jsonl")

# ── 고정 플래그 임계 (사전등록 docs/PREREG_DISTRIBUTION_FOOTPRINT_2026_06_25.md) ──
MAJOR_HOLDER_CUT_PT = -1.0   # DART 5%룰 변동 중 1%p+ 축소
CONSEC_SELL_MIN = 3          # N일 연속 순매도 (관행 임계)
INST_OVERHANG_PCT = 30.0     # 기관보유율 overhang context

DISCLAIMER = (
    "관측-only·가설. 공개 사실(외국인/기관 순매매·DART 5%룰)만. "
    "13F=롱만·45일지연·숏/옵션 비공시 → '지금 무엇' 불가. 점수·추천 0."
)


def _num(v: Any) -> float:
    try:
        if v is None:
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def compute_distribution_footprint(stock: Dict[str, Any]) -> Dict[str, Any]:
    """단일 종목 분산매도 정황 = 공개 사실 플래그 집합. 점수 0.

    입력 = recommendations 종목 dict (flow / major_shareholder_changes / held_pct_institutions).
    """
    flow = stock.get("flow") or {}
    flags: List[str] = []

    # 외국인/기관 순매도 (KIS 일별, kis_* 우선)
    f_net = _num(flow.get("kis_foreign_net") if flow.get("kis_foreign_net") is not None else flow.get("foreign_net"))
    i_net = _num(flow.get("kis_institution_net") if flow.get("kis_institution_net") is not None else flow.get("institution_net"))
    f_consec = int(_num(flow.get("foreign_consec_sell")))
    i_consec = int(_num(flow.get("inst_consec_sell")))

    if f_net < 0:
        flags.append("foreign_net_sell")
    if f_consec >= CONSEC_SELL_MIN:
        flags.append(f"foreign_consec_sell_{f_consec}d")
    if i_net < 0:
        flags.append("inst_net_sell")
    if i_consec >= CONSEC_SELL_MIN:
        flags.append(f"inst_consec_sell_{i_consec}d")

    # DART 대량보유 변동 — 1%p+ 축소만 (5%룰 공시 = 공개 사실)
    reductions: List[Dict[str, Any]] = []
    for ch in (stock.get("major_shareholder_changes") or []):
        if not isinstance(ch, dict):
            continue
        d = _num(ch.get("delta_pct_pt"))
        if d <= MAJOR_HOLDER_CUT_PT:
            reductions.append({
                "delta_pct_pt": d,
                "holder": ch.get("hyslr_nm") or "",
                "reason": ch.get("chnge_resn") or "",
                "rcept_no": ch.get("rcept_no") or "",
            })
    if reductions:
        flags.append("major_holder_reduction")

    inst_pct = _num(stock.get("held_pct_institutions"))
    overhang = inst_pct >= INST_OVERHANG_PCT

    return {
        "ticker": stock.get("ticker"),
        "name": stock.get("name"),
        "flags": flags,
        "flag_count": len(flags),       # ⚠️ 점수 아님 — 발화한 사실 플래그 수
        "detail": {
            "foreign_net": f_net,
            "institution_net": i_net,
            "foreign_consec_sell": f_consec,
            "inst_consec_sell": i_consec,
            "major_holder_reductions": reductions,
            "held_pct_institutions": inst_pct,
            "institution_overhang": overhang,
        },
        "observation_only": True,
        "score": None,                  # 🚨 점수 wire 0 (RULE 7)
        "lagged_incomplete": True,
        "disclaimer": DISCLAIMER,
    }


def build_distribution_observations(
    stocks: List[Dict[str, Any]], observed_at: Optional[str] = None
) -> List[Dict[str, Any]]:
    """recommendations 종목 리스트 → 분산매도 정황 관측 엔트리 리스트.

    flag 1개 이상 발화한 종목만 (정황 없는 종목은 noise 제외).
    """
    ts = observed_at or now_kst().isoformat()
    out: List[Dict[str, Any]] = []
    for s in stocks:
        if not isinstance(s, dict) or not s.get("ticker"):
            continue
        fp = compute_distribution_footprint(s)
        if fp["flag_count"] > 0:
            fp["observed_at"] = ts
            fp["source"] = "distribution_footprint.v0"
            out.append(fp)
    return out


def log_distribution_observations(stocks: List[Dict[str, Any]]) -> int:
    """관측 jsonl append. Returns: 적재 엔트리 수.

    feedback_data_collection_verification_mandatory 정합: try/finally + logged stderr.
    """
    entries = build_distribution_observations(stocks)
    logged = 0
    try:
        os.makedirs(OBS_DIR, exist_ok=True)
        with open(OBS_PATH, "a", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
                logged += 1
    except Exception as ex:
        print(f"[distribution_footprint] jsonl 적재 실패 — {type(ex).__name__}: {ex}",
              file=sys.stderr, flush=True)
    finally:
        print(f"[distribution_footprint] observed={logged}/{len(stocks)} (flag>0 만 적재)",
              file=sys.stderr, flush=True)
    return logged
