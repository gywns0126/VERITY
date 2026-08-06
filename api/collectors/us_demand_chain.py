#!/usr/bin/env python3
"""
미국 수요 체인 관측 v0 — 국장에 선행하는 미국 벤치마크 대형주 바스켓.

PM 사고 (2026-08-05): "중동 전쟁 긴장 완화, AI 수요 확인(팔란티어 실적/캐터필러 실적),
앤트로픽-브로드컴 대규모 계약 — 코스피 견인에 큰 힘. 넌 알고 있었는지?"
→ 답 = **몰랐다**. 원인 두 가지를 실측으로 확인했다:
  ① earnings_surprise 관측기는 **우리 유니버스만** 본다 (ALB/VICI/KHC 같은 중소형).
     시장을 움직이는 PLTR·CAT·AVGO 는 유니버스 밖이라 관측 자체가 0 이었다.
  ② global_events 는 지표 **일정표**(ISM/NFP/CPI 예정일)일 뿐 — 실제 발생한 기업
     이벤트는 한 건도 들어오지 않는다.

이 모듈이 메우는 것 = **국장 판단에 선행하는 미국 수요 신호를, 유니버스와 무관하게 관측**.

설계 원칙:
  · **가격이 1차 증거.** "실적이 좋았나"를 LLM 에게 묻지 않는다. 갭 + 거래량 급증이
    실제 이벤트 발생의 관측 가능한 흔적이다. 서프라이즈 수치는 Finnhub 로 **보강**하되
    (키 없으면 graceful skip) 없어도 체인 관측은 성립한다.
  · **체인 단위 집계.** 개별 종목이 아니라 수요 체인(AI 반도체 / AI 소프트웨어 /
    데이터센터 인프라 / 전기차·2차전지 / 바이오) 평균으로 본다. 한 종목의 개별 악재와
    체인 전체의 수요 변화를 구분하기 위함.
  · **국장 연결은 매핑까지만.** 체인별 KR 대응 종목을 병기하되 인과를 단정하지 않는다
    (RULE 7 — 검증 안 된 인과 주장 금지). "같은 체인" 이라는 사실 병기까지.

🚨 관측 ONLY — 점수/결정 wire 0 (shadow=true, brain_input=false).
   승격(점수 편입)은 사전등록 통과 후 하나씩 ([[project_observation_scoring_prereg_queue]],
   [[feedback_methodology_pre_registration]]). 리포트에는 **컨텍스트로만** 주입한다.

임계는 이론 고정 — N<50 구간에서 데이터로 튜닝하면 곡선 맞추기가 된다
([[feedback_threshold_calibration_overfit_guard]]). 이벤트 스터디 관례값을 그대로 쓴다:
  · |z| ≥ 3.0          = **1차 판정**. z = 일간수익률 / 60일 표준편차.
        절대 %는 종목 변동성을 무시한다 — 저변동 산업재의 +5.6% 가 고변동 반도체의
        +7% 보다 큰 사건인데 절대 임계는 후자만 잡는다. 정본(Brown & Warner 1985)이
        쓰는 초과수익 σ 정규화를 따른다. 3σ = 관례.
  · |일간 변동| ≥ 7%   = 보조. σ 추정이 불안정한 신규 상장·저유동 종목 안전망.
  · 거래량 ≥ 20일 평균의 3배 = 이벤트 확증 (가격만으로는 노이즈와 구분 불가)
  · 체인 평균 |변동| ≥ 2.5% = 체인 레벨 수요 신호
조정하려면 사전등록 후 1회만.

소급 검증 (2026-08-04, PM 이 지목한 그 날):
  PLTR +29.5% · AVGO +6.6% · AMD +7.0% · CAT +5.6% → 코스피는 다음 거래일 8/5 반응.
  절대 7% 단독이면 CAT·AVGO 를 놓친다. 3σ 병용 시 넷 다 포착.

출력:
  data/observations/us_demand_chain.jsonl  append-only 관측 원장(자기 trail 자산)
  data/us_demand_chain.json                 최신 스냅샷(리포트 컨텍스트 소비용)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
OBS_DIR = os.path.join(DATA_DIR, "observations")
OBS_PATH = os.path.join(OBS_DIR, "us_demand_chain.jsonl")
SNAPSHOT_PATH = os.path.join(DATA_DIR, "us_demand_chain.json")

# ── 임계 (이론 고정, 사전등록 없이 조정 금지) ─────────────────────────
EVENT_Z = 3.0               # 1차 판정 — 일간수익률 / 60일 σ (이벤트 스터디 관례 3σ)
EVENT_MOVE_PCT = 7.0        # 보조 — σ 불안정 종목 안전망
EVENT_VOL_RATIO = 3.0       # 거래량 급증 배수
CHAIN_SIGNAL_PCT = 2.5      # 체인 평균 수요 신호
VOL_LOOKBACK = 20           # 거래량 평균 산정 구간(거래일)
SIGMA_LOOKBACK = 60         # σ 추정 구간(거래일)

# ── 수요 체인 정의 ────────────────────────────────────────────────
#   선정 기준 = "국장 특정 섹터의 수요를 선행 관측할 수 있는 미국 상장 대표주".
#   유니버스(보유·후보)와 무관 — 우리가 사려는 종목이 아니라 **읽으려는 지표**다.
#   구성 변경 = 사전등록 대상 (임의 교체 시 관측 연속성 붕괴).
CHAINS: Dict[str, Dict[str, Any]] = {
    "ai_semi": {
        "label": "AI 반도체",
        "thesis": "AI 가속기·HBM 수요. 국장 반도체 대형주의 전방 수요",
        "tickers": ["NVDA", "AVGO", "AMD", "MU", "TSM", "SMCI"],
        "kr_link": [("005930", "삼성전자"), ("000660", "SK하이닉스"), ("042700", "한미반도체")],
    },
    "ai_software": {
        "label": "AI 소프트웨어",
        "thesis": "AI 실수요(도입·매출화) 확인. 반도체 수요의 지속성 근거",
        "tickers": ["PLTR", "MSFT", "GOOGL", "META", "ORCL", "NOW"],
        "kr_link": [("035420", "NAVER"), ("035720", "카카오"), ("053800", "안랩")],
    },
    "datacenter_infra": {
        "label": "데이터센터 인프라",
        "thesis": "AI 의 물리 병목 = 전력·냉각·건설. 국장 전력기기 수출과 직결",
        "tickers": ["CAT", "ETN", "VRT", "PWR"],
        "kr_link": [("267260", "HD현대일렉트릭"), ("010120", "LS일렉트릭"), ("298040", "효성중공업")],
    },
    "ev_battery": {
        "label": "전기차·2차전지",
        "thesis": "셀·소재 수요. 국장 배터리 3사 가동률 선행",
        "tickers": ["TSLA", "ALB", "RIVN"],
        "kr_link": [("373220", "LG에너지솔루션"), ("006400", "삼성SDI"), ("247540", "에코프로비엠")],
    },
    "biotech": {
        "label": "바이오",
        "thesis": "글로벌 신약 수요·CDMO 물량. 국장 CDMO 수주 선행",
        "tickers": ["LLY", "NVO", "VRTX"],
        "kr_link": [("207940", "삼성바이오로직스"), ("068270", "셀트리온")],
    },
}


def _all_tickers() -> List[str]:
    seen: List[str] = []
    for c in CHAINS.values():
        for t in c["tickers"]:
            if t not in seen:
                seen.append(t)
    return seen


def fetch_daily_bars(tickers: List[str], metrics: Optional[dict] = None) -> Dict[str, Dict[str, Any]]:
    """티커별 최근 종가·변동률·거래량비 — yfinance 1회 batch.

    batch 실패 시 종목별 fallback (일부 티커 상폐/티커변경이 batch 전체를 죽이지 않도록).
    반환값 = {ticker: {close, change_pct, volume, vol_ratio, date}}
    """
    import yfinance as yf
    from api.collectors.yfinance_safe import safe_yf_call

    out: Dict[str, Dict[str, Any]] = {}

    def _from_frame(tk: str, closes, vols) -> Optional[Dict[str, Any]]:
        closes = closes.dropna()
        vols = vols.dropna()
        if len(closes) < 2:
            return None
        last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
        if prev <= 0:
            return None
        chg = (last / prev - 1) * 100
        # 거래량비 = 당일 / 직전 VOL_LOOKBACK 평균(당일 제외 — 자기 자신 포함 시 배수 희석)
        vol_ratio = None
        if len(vols) >= 3:
            base = vols.iloc[-(VOL_LOOKBACK + 1):-1]
            if len(base) > 0 and float(base.mean()) > 0:
                vol_ratio = round(float(vols.iloc[-1]) / float(base.mean()), 2)
        # z = 당일수익률 / 직전 SIGMA_LOOKBACK σ. 당일을 σ 추정에서 제외해야
        # 큰 사건이 자기 분모를 부풀려 z 를 스스로 깎는 문제를 피한다.
        z = None
        rets = closes.pct_change().dropna()
        if len(rets) >= 20:
            base_r = rets.iloc[-(SIGMA_LOOKBACK + 1):-1]
            sd = float(base_r.std())
            if sd > 0:
                z = round((chg / 100) / sd, 2)
        return {
            "close": round(last, 2),
            "change_pct": round(chg, 2),
            "z": z,
            "volume": int(vols.iloc[-1]) if len(vols) else None,
            "vol_ratio": vol_ratio,
            "date": str(closes.index[-1])[:10],
        }

    df = safe_yf_call(
        lambda: yf.download(tickers, period="3mo", interval="1d",
                            group_by="column", auto_adjust=True, progress=False, threads=False),
        label="us_demand_chain_batch", metrics=metrics,
    )
    if df is not None and not df.empty:
        for t in tickers:
            try:
                rec = _from_frame(t, df["Close"][t], df["Volume"][t])
            except Exception:
                rec = None
            if rec:
                out[t] = rec

    # batch 가 못 채운 티커만 개별 재시도
    for t in [x for x in tickers if x not in out]:
        try:
            from api.collectors.yfinance_safe import yf_ticker
            h = safe_yf_call(lambda tk=t: yf_ticker(tk).history(period="3mo"),
                             label=f"us_demand_chain:{t}", metrics=metrics)
            if h is not None and not h.empty:
                rec = _from_frame(t, h["Close"], h["Volume"])
                if rec:
                    out[t] = rec
        except Exception as e:
            logger.debug("us_demand_chain fallback fail %s: %s", t, e)
    return out


def fetch_surprises(tickers: List[str], api_key: str) -> Dict[str, Dict[str, Any]]:
    """최근 분기 EPS 서프라이즈 — 가격 반응의 원인 후보를 수치로 보강.

    키 없으면 {} (관측은 가격만으로도 성립). Finnhub 무료 60req/min, 클라이언트가 자체 throttle.
    """
    if not api_key:
        return {}
    from api.collectors.finnhub_client import get_earnings_surprises

    out: Dict[str, Dict[str, Any]] = {}
    for t in tickers:
        try:
            rows = get_earnings_surprises(t, api_key) or []
        except Exception as e:
            logger.debug("finnhub surprise fail %s: %s", t, e)
            continue
        if not rows:
            continue
        r = rows[0]  # 최신 분기
        actual, est = r.get("actual"), r.get("estimate")
        if actual is None or est in (None, 0):
            continue
        try:
            out[t] = {
                "period": r.get("period"),
                "actual": actual,
                "estimate": est,
                "surprise_pct": round((float(actual) - float(est)) / abs(float(est)) * 100, 2),
            }
        except (TypeError, ValueError, ZeroDivisionError):
            continue
    return out


def build_observation(metrics: Optional[dict] = None) -> Dict[str, Any]:
    """체인별 집계 + 이벤트 감지. 순수 관측 — 점수 산출 없음."""
    from api.config import FINNHUB_API_KEY
    from api.utils.market_calendar import now_kst

    tickers = _all_tickers()
    bars = fetch_daily_bars(tickers, metrics=metrics)
    surprises = fetch_surprises(list(bars.keys()), FINNHUB_API_KEY)

    chains: Dict[str, Any] = {}
    events: List[Dict[str, Any]] = []

    for key, spec in CHAINS.items():
        members = []
        for t in spec["tickers"]:
            b = bars.get(t)
            if not b:
                continue
            m = {"ticker": t, "change_pct": b["change_pct"], "z": b.get("z"),
                 "vol_ratio": b.get("vol_ratio"), "close": b["close"]}
            sp = surprises.get(t)
            if sp:
                m["eps_surprise_pct"] = sp["surprise_pct"]
                m["eps_period"] = sp["period"]
            members.append(m)

            triggers = []
            if abs(b.get("z") or 0) >= EVENT_Z:
                triggers.append("sigma")
            if abs(b["change_pct"]) >= EVENT_MOVE_PCT:
                triggers.append("move")
            if (b.get("vol_ratio") or 0) >= EVENT_VOL_RATIO:
                triggers.append("volume")
            if triggers:
                events.append({
                    "ticker": t,
                    "chain": key,
                    "chain_label": spec["label"],
                    "change_pct": b["change_pct"],
                    "z": b.get("z"),
                    "vol_ratio": b.get("vol_ratio"),
                    "trigger": "+".join(triggers),
                    "eps_surprise_pct": (surprises.get(t) or {}).get("surprise_pct"),
                    "kr_link": [n for _, n in spec["kr_link"]],
                    "date": b["date"],
                })

        if not members:
            chains[key] = {"label": spec["label"], "coverage": 0, "note": "데이터 없음"}
            continue

        avg = round(sum(m["change_pct"] for m in members) / len(members), 2)
        up = sum(1 for m in members if m["change_pct"] > 0)
        chains[key] = {
            "label": spec["label"],
            "thesis": spec["thesis"],
            "avg_change_pct": avg,
            "breadth": f"{up}/{len(members)}",
            "coverage": len(members),
            "signal": "확장" if avg >= CHAIN_SIGNAL_PCT else ("위축" if avg <= -CHAIN_SIGNAL_PCT else "중립"),
            "kr_link": [{"code": c, "name": n} for c, n in spec["kr_link"]],
            "members": sorted(members, key=lambda m: -abs(m["change_pct"])),
        }

    events.sort(key=lambda e: -abs(e["change_pct"]))
    return {
        "ts_kst": now_kst().isoformat(),
        "shadow": True,
        "brain_input": False,
        "caveat": (
            "관측-only 가설. 점수 미반영(brain_input=false). 체인-국장 연결은 '같은 수요 체인' "
            "사실 병기까지이며 인과 단정 아님. 임계(7%/3x/2.5%)=이론 고정, 사전등록 없이 조정 금지."
        ),
        "thresholds": {"move_pct": EVENT_MOVE_PCT, "vol_ratio": EVENT_VOL_RATIO, "chain_pct": CHAIN_SIGNAL_PCT},
        "coverage": {"requested": len(tickers), "fetched": len(bars), "with_surprise": len(surprises)},
        "chains": chains,
        "events": events,
    }


def _append_jsonl(rec: Dict[str, Any]) -> None:
    os.makedirs(OBS_DIR, exist_ok=True)
    with open(OBS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _write_snapshot(rec: Dict[str, Any]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = SNAPSHOT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SNAPSHOT_PATH)


def run() -> Dict[str, Any]:
    rec = build_observation()
    if rec["coverage"]["fetched"] == 0:
        # 전부 실패 = 원장 오염 방지. 스냅샷도 갱신하지 않아 stale 이 그대로 보인다.
        logger.warning("us_demand_chain: 수집 0건 — 기록 skip")
        return rec
    _append_jsonl(rec)
    _write_snapshot(rec)
    return rec


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    rec = run()
    cov = rec["coverage"]
    print(f"[us_demand_chain] {cov['fetched']}/{cov['requested']} 종목 · 서프라이즈 {cov['with_surprise']} · 이벤트 {len(rec['events'])}건")
    for k, c in rec["chains"].items():
        if c.get("coverage"):
            print(f"  {c['label']:<14} {c['avg_change_pct']:+6.2f}%  {c['breadth']:>5}  {c['signal']}")
    for e in rec["events"][:8]:
        sp = f" EPS {e['eps_surprise_pct']:+.1f}%" if e.get("eps_surprise_pct") is not None else ""
        print(f"  ⚡ {e['ticker']:<6} {e['change_pct']:+6.2f}% vol×{e['vol_ratio']} [{e['chain_label']}]{sp}")
    return 0 if cov["fetched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
