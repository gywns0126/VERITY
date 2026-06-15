"""say_do_divergence.py — 셀사이드 의견(말) vs 외국인·기관 flow(행동) 괴리 관측 v0.

2026-06-15 신설. 동기 = PM 아이디어: "기관이 좋다 하면서 팔고, 나쁘다 하면서 사는" 패턴을
하나의 측정 기준으로. 단 차이니즈월 때문에 개별 하우스의 say-do 인과는 입증 불가 →
**집계 레벨의 중립 통계**로 좁힘: "셀사이드 컨센서스(말)의 방향 부호" vs "외국인+기관
실제 순매매(행동)의 방향 부호"가 갈리는가.

  말(say)  = report_summaries.json signal_direction/dominant_opinion + consensus investment_opinion
  행동(do) = 네이버 frgn 최근 N거래일 외국인+기관 순매매 합의 부호 (scripts.kr.flow 재사용)

🚨 관측 ONLY — 점수/brain wire 0 (RULE 7). 추종(herding)이 먹히냐 역행(contrarian)이
먹히냐는 학술적으로 둘 다 존재 → 부호를 미리 정하지 않고 forward return 과 N 누적 후
사전등록([[project_observation_scoring_prereg_queue]]). prior art = consensus_score.py
_attach_export_divergence(기관 낙관 vs 수출 실물 괴리).

저장: data/observations/say_do_divergence.jsonl (append + date dedupe, crowding_observations 패턴).
KR 종목만(ticker6 isdigit). flow 는 네이버 직접 fetch 라 GH cron 가능(parquet 비의존).
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

logger = logging.getLogger(__name__)

OBS_DIR = os.path.join(DATA_DIR, "observations")
SAYDO_PATH = os.path.join(OBS_DIR, "say_do_divergence.jsonl")
REPORT_PATH = os.path.join(DATA_DIR, "report_summaries.json")
CONSENSUS_PATH = os.path.join(DATA_DIR, "consensus_data.json")

FLOW_LOOKBACK_DAYS = 5  # 최근 N거래일 순매매 합 부호 = 행동

# 한국 증권사 투자의견 → 부호 (중립/보유/관망 = 0)
_BUY = {"매수", "강력매수", "적극매수", "비중확대", "buy", "strong buy", "overweight"}
_SELL = {"매도", "비중축소", "sell", "strong sell", "underweight", "reduce"}


def _opinion_sign(op: Optional[str]) -> int:
    if not op:
        return 0
    s = str(op).strip().lower()
    if s in _BUY:
        return 1
    if s in _SELL:
        return -1
    return 0


def _load_json(path: str) -> Optional[Any]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _say_signals() -> Dict[str, Dict[str, Any]]:
    """ticker6 → 말(say) 신호 조립. report(signal_direction/dominant) + consensus(opinion)."""
    out: Dict[str, Dict[str, Any]] = {}

    rep = _load_json(REPORT_PATH) or {}
    for tk, agg in (rep.get("summaries") or {}).items():
        tk = str(tk)
        if not tk.isdigit():  # KR 6자리만
            continue
        if not isinstance(agg, dict):
            continue
        sd = agg.get("signal_direction")
        sd_sign = 1 if sd == "bullish" else (-1 if sd == "bearish" else 0)
        out.setdefault(tk, {})
        out[tk]["report_sign"] = sd_sign
        out[tk]["report_dominant"] = agg.get("dominant_opinion")
        out[tk]["analyst_sentiment"] = agg.get("analyst_sentiment_score")

    cons = _load_json(CONSENSUS_PATH) or {}
    for row in (cons.get("stocks") or []):
        if not isinstance(row, dict):
            continue
        tk = str(row.get("ticker") or "").zfill(6)
        if not tk.isdigit():
            continue
        out.setdefault(tk, {})
        out[tk]["consensus_sign"] = _opinion_sign(row.get("investment_opinion"))
        out[tk]["consensus_upside_pct"] = row.get("upside_pct")

    return out


def _say_sign(s: Dict[str, Any]) -> int:
    """report_sign + consensus_sign 종합 부호 (합의 방향, 0=상충/중립/결손)."""
    vals = [v for v in (s.get("report_sign"), s.get("consensus_sign")) if v is not None]
    if not vals:
        return 0
    tot = sum(vals)
    return 1 if tot > 0 else (-1 if tot < 0 else 0)


def _do_signal(panel: List[Dict], lookback: int) -> Dict[str, Any]:
    """flow panel 최근 lookback거래일 외국인+기관 순매매 합 → 행동(do) 부호."""
    rows = [r for r in (panel or []) if r.get("date")][-lookback:]
    if not rows:
        return {"foreign_net_sum": None, "inst_net_sum": None,
                "smart_net_sum": None, "do_sign": 0, "days": 0}
    fn = sum((r.get("foreign_net") or 0) for r in rows)
    inn = sum((r.get("inst_net") or 0) for r in rows)
    tot = fn + inn
    return {
        "foreign_net_sum": fn,
        "inst_net_sum": inn,
        "smart_net_sum": tot,
        "do_sign": 1 if tot > 0 else (-1 if tot < 0 else 0),
        "days": len(rows),
    }


def _resolve_fetch_flow_panel():
    """scripts.kr.flow_observation_logger.fetch_flow_panel 재사용 (중복 fetch 코드 회피).

    namespace import 우선, 실패 시 파일 경로 직접 로드 fallback.
    """
    try:
        from scripts.kr.flow_observation_logger import fetch_flow_panel  # type: ignore
        return fetch_flow_panel
    except Exception:
        import importlib.util
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(root, "scripts", "kr", "flow_observation_logger.py")
        spec = importlib.util.spec_from_file_location("_flow_logger", path)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod.fetch_flow_panel


def _build_record(per: Dict[str, Dict[str, Any]], lookback: int) -> Optional[Dict[str, Any]]:
    if not per:
        return None
    now = now_kst()
    n_div = sum(1 for v in per.values() if v.get("divergence"))
    return {
        "observed_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "date": now.strftime("%Y-%m-%d"),
        "flow_lookback_days": lookback,
        "n_tickers": len(per),
        "n_divergence": n_div,
        "per_ticker": per,
        "spec": "say_do_divergence_v0_raw_observation",
        "_note": ("관측 only. 말(셀사이드 의견) vs 행동(외국인+기관 순매매) 부호괴리. "
                  "점수 wire 0. 추종/역행 부호는 forward return + N 누적 후 사전등록(RULE 7)."),
    }


def _append(rec: Optional[Dict[str, Any]], target: str) -> None:
    if rec is None:
        return
    os.makedirs(os.path.dirname(target), exist_ok=True)
    # date dedupe — 같은 날 중복 append 차단
    try:
        with open(target, encoding="utf-8") as f:
            seen = {json.loads(line).get("date") for line in f if line.strip()}
        if rec["date"] in seen:
            return
    except OSError:
        pass
    with open(target, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run_say_do_observation(
    max_tickers: Optional[int] = None,
    delay: float = 0.4,
    lookback: int = FLOW_LOOKBACK_DAYS,
    path: Optional[str] = None,
    _fetch=None,
) -> Dict[str, Any]:
    """말 신호가 있는 KR 종목별 flow fetch → say vs do 부호괴리 관측 1스냅샷 append. graceful."""
    target = path or SAYDO_PATH
    say = _say_signals()
    tickers = sorted(say.keys())
    if max_tickers:
        tickers = tickers[:max_tickers]
    if not tickers:
        logger.info("say 신호 종목 0 — skip")
        return {"tickers": 0, "flow_ok": 0, "divergences": 0, "logged": False}

    fetch = _fetch or _resolve_fetch_flow_panel()
    import requests
    sess = requests.Session()

    per: Dict[str, Dict[str, Any]] = {}
    flow_ok = 0
    for tk in tickers:
        say_sign = _say_sign(say[tk])
        try:
            panel = fetch(tk, sess)
        except Exception as e:  # noqa: BLE001 — 종목 1개 실패는 skip
            logger.warning("%s flow fetch 실패: %s", tk, e)
            panel = []
        do = _do_signal(panel, lookback)
        diverge = bool(say_sign != 0 and do["do_sign"] != 0 and say_sign * do["do_sign"] < 0)
        per[tk] = {
            "say_sign": say_sign,
            "report_sign": say[tk].get("report_sign"),
            "consensus_sign": say[tk].get("consensus_sign"),
            "consensus_upside_pct": say[tk].get("consensus_upside_pct"),
            **do,
            "divergence": diverge,
        }
        if do["days"]:
            flow_ok += 1
        if delay:
            time.sleep(delay)

    rec = _build_record(per, lookback)
    _append(rec, target)
    return {
        "tickers": len(tickers),
        "flow_ok": flow_ok,
        "divergences": sum(1 for v in per.values() if v["divergence"]),
        "logged": rec is not None,
    }


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=None, help="테스트용 종목 상한")
    ap.add_argument("--delay", type=float, default=0.4, help="요청 간 지연(초, anti-bot)")
    ap.add_argument("--lookback", type=int, default=FLOW_LOOKBACK_DAYS)
    args = ap.parse_args()
    try:
        r = run_say_do_observation(max_tickers=args.max, delay=args.delay, lookback=args.lookback)
        print(f"[say_do] tickers={r['tickers']} flow_ok={r['flow_ok']} "
              f"divergences={r['divergences']} logged={r['logged']}")
    except Exception as e:  # noqa: BLE001 — 관측은 부수효과, 파이프라인 fail 금지
        sys.stderr.write(f"[say_do] 실패 (graceful exit 0): {type(e).__name__}: {e}\n")
    sys.exit(0)
