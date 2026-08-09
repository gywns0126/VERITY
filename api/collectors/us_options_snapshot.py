"""us_options_snapshot — 미장 옵션 관측(IV·미결제·P/C·스큐) 일별 스냅샷. 2026-08-09 신설.

**왜 신설했나.** 2026-08-09 커버리지 점검에서 미장 판단 재료 중 **가격 미시구조가 통째로
비어 있다**는 것이 드러났다. 그때 나는 "옵션은 유료 벤더 계약 후에만" 이라고 PM 에게 보고했는데
**그건 Polygon 무료 tier(스냅샷 403)만 보고 내린 결론이었고 틀렸다**. yfinance 가 옵션 체인을
그대로 준다 — 실호출 확인(2026-08-09): AAPL 만기 20개 · calls 47행 · impliedVolatility·
openInterest·volume 전부 포함. 종목당 약 2.2초.

🚨 RULE 7 — 여기 담는 것은 **관측 사실**이다: 시장이 붙인 IV, 거래소 미결제약정·거래량, 그리고
   그 위의 단순 산술(P/C 비율·스큐 차). 우리 점수·등급·매매신호 0. "IV 가 높으니 비싸다" 류
   해석은 이 층에서 하지 않는다.
🚨 스큐 정의를 코드와 산출물에 같이 남긴다 — 정의가 없는 스큐 숫자는 비교 불가라 사실도 아니다.
   🚨 2026-08-09 **이중 산출**로 전환 — 정의가 다르면 다른 값이고, 하나만 싣고 "스큐" 라 부르면
   거짓이 된다. skew_rr_pp = OTM 풋 − OTM 콜(리스크 리버설 계열, 실무 측도) ·
   skew_xzz_pp = OTM 풋 − ATM 콜(Xing-Zhang-Zhao 2010 JFQA 계열, 학술 표준).
   둘 다 델타가 아니라 **행사가 기준 근사**다. 델타 스큐와 같은 자로 재지 말 것.

소스 = yfinance(무료·키 0). 전 유니버스 rotation + carry-forward + wall-clock budget.
출력 = data/us_options.json (L3 스냅샷) + data/us_options_trail.jsonl (L2 누적)
🚨 L2 누적이 IV rank/percentile 의 유일한 근거다 — 252거래일이 필요하므로 지금 시작한다.
   트랙 A 규율: **수집만, 스코어 통합 금지.** 검정은 누적 후.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.builders.us_insider_trades_public_builder import _now_kst, _ordered_universe  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_options.json")

OUTPUT_TRAIL = os.path.join(_ROOT, "data", "us_options_trail.jsonl")

MAX_SECONDS = int(os.environ.get("US_OPTIONS_MAX_SECONDS", "1800"))
THROTTLE_SEC = 0.15
# 옵션이 상장된 종목만 의미가 있다 — 미상장은 즉시 빠지므로 예산을 거의 안 쓴다.
SKEW_PUT_MONEYNESS = 0.90
SKEW_CALL_MONEYNESS = 1.10
STALE_DROP_DAYS = 14   # 이보다 오래된 carry-forward 는 버린다(옵션은 빨리 늙는다)

# ── 만기 선택 (2026-08-09 등록) ─────────────────────────────────────
# 🚨 v0 는 "근월 1개" 였는데 **20개 만기 중 왜 그것인지 근거가 없었다.** 근월은 만기가
#   다가올수록 IV 가 구조적으로 튀고(만기 효과) 잔존일이 매일 달라져 시계열 비교가 깨진다.
#   → 잔존일이 목표 창에 가장 가까운 만기를 고른다. 잔존일을 산출물에 같이 실어
#   나중에 "며칠짜리 IV 였나" 를 되짚을 수 있게 한다.
TARGET_DTE = int(os.environ.get("US_OPTIONS_TARGET_DTE", "30"))
MIN_DTE = 7      # 만기 임박 구간 제외(감마 폭주로 IV 왜곡)
MAX_DTE = 90

# ── 호가 품질 필터 (2026-08-09 등록) ────────────────────────────────
# 🚨 yfinance IV 는 체결이 없는 stale 호가에서도 값이 나온다. 필터 없이 계산한 IC 는 쓸 수 없다.
#   최소 미결제·최대 상대스프레드로 거른 뒤에만 IV 를 채택한다. 거른 결과가 부족하면
#   그 종목은 값을 내지 않는다(빈 값이 잘못된 값보다 낫다).
MIN_OI = int(os.environ.get("US_OPTIONS_MIN_OI", "10"))
MAX_REL_SPREAD = float(os.environ.get("US_OPTIONS_MAX_REL_SPREAD", "0.5"))  # (ask-bid)/mid


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # NaN 제거


def _quality_mask(df):
    """호가 품질 필터 — 최소 미결제 + 최대 상대스프레드. 통과 행만 남긴 프레임 반환."""
    if df is None or len(df) == 0:
        return df
    try:
        d = df.copy()
        oi = d["openInterest"].fillna(0)
        bid = d["bid"].fillna(0)
        ask = d["ask"].fillna(0)
        mid = (bid + ask) / 2
        # mid<=0 이면 양방향 호가가 없다 = 가격 발견 자체가 없는 행
        rel = (ask - bid) / mid.where(mid > 0)
        keep = (oi >= MIN_OI) & (mid > 0) & (rel <= MAX_REL_SPREAD)
        return d[keep]
    except (KeyError, ValueError, TypeError):
        return df


def _pick_expiry(exps) -> Optional[tuple]:
    """목표 잔존일(TARGET_DTE)에 가장 가까운 만기 → (만기문자열, 잔존일). 없으면 None.

    근월 고정은 만기 효과로 IV 가 튀고 잔존일이 매일 달라져 시계열 비교가 깨진다.
    """
    from datetime import date as _date
    today = _now_kst().date()
    cand = []
    for e in exps:
        try:
            y, m, dd = (int(x) for x in str(e).split("-"))
            dte = (_date(y, m, dd) - today).days
        except (ValueError, TypeError):
            continue
        if MIN_DTE <= dte <= MAX_DTE:
            cand.append((abs(dte - TARGET_DTE), e, dte))
    if not cand:
        return None
    cand.sort()
    return (cand[0][1], cand[0][2])


def _nearest_iv(df, target: float) -> Optional[float]:
    """target 행사가에 가장 가까운 행의 IV. 빈 프레임이면 None."""
    if df is None or len(df) == 0:
        return None
    try:
        idx = (df["strike"] - target).abs().idxmin()
        return _num(df.loc[idx, "impliedVolatility"])
    except (KeyError, ValueError):
        return None


def _one(ticker: str) -> Optional[Dict[str, Any]]:
    import yfinance as yf

    t = yf.Ticker(ticker)
    try:
        exps = t.options
    except Exception:  # noqa: BLE001 — 개별 실패 격리
        return None
    if not exps:
        return None
    picked = _pick_expiry(exps)
    if picked is None:
        return None
    expiry, dte = picked
    try:
        spot = _num(t.fast_info.last_price)
        ch = t.option_chain(expiry)
    except Exception:  # noqa: BLE001
        return None
    calls_raw, puts_raw = ch.calls, ch.puts
    if calls_raw is None or puts_raw is None or (len(calls_raw) == 0 and len(puts_raw) == 0):
        return None

    def _sum(df, col) -> float:
        try:
            return float(df[col].fillna(0).sum())
        except (KeyError, ValueError):
            return 0.0

    # 집계량(거래량·미결제·P/C)은 **필터 전 원본** 기준 — 시장 전체 활동의 사실이다.
    cv, pv = _sum(calls_raw, "volume"), _sum(puts_raw, "volume")
    coi, poi = _sum(calls_raw, "openInterest"), _sum(puts_raw, "openInterest")

    # IV·스큐는 **품질 통과 행에서만** 뽑는다. stale 호가 IV 를 섞으면 IC 가 무너진다.
    calls, puts = _quality_mask(calls_raw), _quality_mask(puts_raw)
    kept = (len(calls) if calls is not None else 0) + (len(puts) if puts is not None else 0)

    iv_c = _nearest_iv(calls, spot) if spot else None
    iv_p = _nearest_iv(puts, spot) if spot else None
    iv_atm = None
    if iv_c is not None and iv_p is not None:
        iv_atm = round((iv_c + iv_p) / 2 * 100, 2)
    elif iv_c is not None or iv_p is not None:
        iv_atm = round((iv_c if iv_c is not None else iv_p) * 100, 2)

    # 🚨 스큐 이중 산출 — 정의가 다르면 다른 값이다. 하나만 싣고 "스큐" 라고 부르면 거짓이 된다.
    #   rr  = OTM 풋 − OTM 콜 (리스크 리버설 계열, 실무 측도)
    #   xzz = OTM 풋 − ATM 콜 (Xing-Zhang-Zhao 2010 JFQA 계열, 학술 표준)
    skew_rr = skew_xzz = None
    if spot:
        otm_p = _nearest_iv(puts, spot * SKEW_PUT_MONEYNESS)
        otm_c = _nearest_iv(calls, spot * SKEW_CALL_MONEYNESS)
        if otm_p is not None and otm_c is not None:
            skew_rr = round((otm_p - otm_c) * 100, 2)
        if otm_p is not None and iv_c is not None:
            skew_xzz = round((otm_p - iv_c) * 100, 2)

    return {
        "ticker": ticker,
        "spot": round(spot, 4) if spot else None,
        "expiry": expiry,
        "dte": dte,                      # 잔존일 — 시계열 비교 시 필수
        "expiry_count": len(exps),
        "iv_atm_pct": iv_atm,
        "skew_rr_pp": skew_rr,
        "skew_xzz_pp": skew_xzz,
        "quality_rows": kept,            # 품질 통과 행 수 — 값의 신뢰도 표기
        "pc_volume": round(pv / cv, 3) if cv else None,
        "pc_oi": round(poi / coi, 3) if coi else None,
        "call_volume": int(cv), "put_volume": int(pv),
        "call_oi": int(coi), "put_oi": int(poi),
        "as_of": _now_kst().isoformat(),
    }


def append_trail(records: List[Dict[str, Any]]) -> int:
    """L2 누적 — 축별 append-only jsonl. IV rank/percentile 의 유일한 근거.

    🚨 v0(2026-08-08)는 최신 스냅샷만 덮어썼다. 그래서 "이 종목 IV 가 평소 대비 높은가" 에
       구조적으로 답할 수 없었다 — 숫자는 있는데 해석 기준이 없는 상태.
       IV rank 는 252거래일이 필요하므로 **지금 시작하지 않으면 2027년에도 못 한다.**
       docs/DATA_LAYER_RESEARCH_20260809.md §4-3 트랙 A.

    🚨 스코어 통합 금지 — 트랙 A 는 수집만 한다. 검정은 누적 후(§3-2 게이트).
    슬림 필드만 적재: 하루 2,200종 × ~120B ≈ 260KB, 252거래일 ≈ 65MB/년.
    """
    if not records:
        return 0
    day = _now_kst().strftime("%Y-%m-%d")
    n = 0
    try:
        os.makedirs(os.path.dirname(OUTPUT_TRAIL), exist_ok=True)
        with open(OUTPUT_TRAIL, "a", encoding="utf-8") as f:
            for r in records:
                slim = {
                    "d": day,
                    "t": r.get("ticker"),
                    "dte": r.get("dte"),
                    "iv": r.get("iv_atm_pct"),
                    "rr": r.get("skew_rr_pp"),
                    "xzz": r.get("skew_xzz_pp"),
                    "pcv": r.get("pc_volume"),
                    "pco": r.get("pc_oi"),
                    "q": r.get("quality_rows"),
                }
                f.write(json.dumps(slim, ensure_ascii=False, separators=(",", ":")) + "\n")
                n += 1
    except OSError as e:
        print(f"[us_options] trail 적재 실패(무시): {type(e).__name__}: {e}", file=sys.stderr)
        return 0
    return n


def _load_prev() -> Dict[str, Dict[str, Any]]:
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            doc = json.load(f)
        return {str(s.get("ticker") or ""): s for s in (doc.get("stocks") or []) if s.get("ticker")}
    except (OSError, ValueError):
        return {}


def _age_days(iso: str) -> float:
    from datetime import datetime
    try:
        return (_now_kst() - datetime.fromisoformat(iso)).days
    except (ValueError, TypeError):
        return 1e9


def collect() -> int:
    prev = _load_prev()
    order = _ordered_universe()
    t0 = time.monotonic()
    fresh: Dict[str, Dict[str, Any]] = {}
    tried = no_options = 0

    for tk in order:
        if time.monotonic() - t0 > MAX_SECONDS:
            print(f"[us_options] budget 도달 ({int(time.monotonic()-t0)}s) — 나머지 carry-forward",
                  file=sys.stderr)
            break
        tried += 1
        try:
            rec = _one(tk)
        except Exception as e:  # noqa: BLE001
            print(f"[us_options] {tk} 실패: {type(e).__name__}", file=sys.stderr)
            rec = None
        if rec:
            fresh[tk] = rec
        else:
            no_options += 1
        time.sleep(THROTTLE_SEC)

    # carry-forward — 단 오래된 것은 버린다. 옵션 스냅샷은 며칠만 지나도 사실이 아니다.
    merged = {k: v for k, v in prev.items() if _age_days(v.get("as_of", "")) <= STALE_DROP_DAYS}
    merged.update(fresh)
    # L2 누적 — 이번 run 에서 실제로 관측한 것만 적재(carry-forward 는 적재하지 않는다).
    trail_n = append_trail(list(fresh.values()))
    stocks = sorted(merged.values(), key=lambda s: (s.get("call_oi") or 0) + (s.get("put_oi") or 0),
                    reverse=True)

    if not stocks:
        print("[us_options] 산출 0건 — 발행하지 않는다", file=sys.stderr)
        return 1

    doc = {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "source": "yfinance 옵션 체인 (근월 만기) — IV·미결제약정·거래량 관측",
            "stock_count": len(stocks),
            "fresh_this_run": len(fresh),
            "trail_appended": trail_n,
            "tried_this_run": tried,
            "no_options_this_run": no_options,
            "skew_definition": (
                f"skew_rr_pp = 풋 IV(행사가≈현재가×{SKEW_PUT_MONEYNESS}) − 콜 IV(행사가≈현재가×"
                f"{SKEW_CALL_MONEYNESS}) · skew_xzz_pp = 같은 OTM 풋 IV − ATM 콜 IV. 단위 %p. "
                "둘 다 행사가 기준 근사이며 델타 기준 스큐와 다르다. 정의가 다르면 다른 값이다."
            ),
            "expiry_policy": (
                f"잔존일 {MIN_DTE}~{MAX_DTE}일 중 {TARGET_DTE}일에 가장 가까운 만기 1개. "
                "근월 고정은 만기 효과로 IV 가 튀고 잔존일이 매일 달라져 시계열 비교가 깨진다."
            ),
            "quality_filter": (
                f"IV·스큐는 미결제≥{MIN_OI} 이고 상대스프레드≤{MAX_REL_SPREAD} 인 호가에서만 산출. "
                "거래량·미결제·P/C 집계는 필터 전 원본 기준(시장 활동의 사실)."
            ),
            "carry_forward_drop_days": STALE_DROP_DAYS,
            "note": "시장 관측 사실(IV·OI·거래량)과 그 위의 단순 산술만. 자체 점수·매매신호 0(RULE 7). "
                    "근월 만기 1개 기준이라 만기 구조(term structure)는 담지 않는다.",
        },
        "stocks": stocks,
    }
    tmp = OUTPUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUTPUT_PATH)
    m = doc["_meta"]
    print(f"[us_options] {m['stock_count']:,}종 보유 (이번 run 신규 {m['fresh_this_run']:,} · "
          f"시도 {tried:,} · 옵션 미상장 {no_options:,})")
    return 0


if __name__ == "__main__":
    raise SystemExit(collect())
