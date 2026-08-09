"""kr_fundamental_panel — 국장 분기 펀더멘털 **측정정화** 패널. 2026-08-09 신설 (트랙 B1).

**왜 필요한가.** 2026-08-08 백테스트는 미측정 45%(fundamental 18 · flow 13 · sentiment 10 ·
macro 12)를 "히스토리 부재" 한 덩어리로 적었다. 2026-08-09 실측 결과 fundamental 은
**부재가 아니라 연결 부재**였다 — `dart_quarterly_snapshots.jsonl` 에 2,188종 · 2021~2026 분기
패널이 채움율 82~99% 로 이미 있다. 그런데 그대로 쓰면 안 되는 오염이 둘 있다:

  ① **중복 54%** — 원행 125,365 중 고유 (종목, 분기) 는 57,545. 같은 분기를 여러 번 수집해
     쌓았다. 8/8 백테스트가 겪은 그 함정(161,774 → 105,724, 53% 부풀림)과 같은 뿌리다.
     중복을 그대로 세면 N 이 두 배로 보이고 t 값이 부풀어 **없는 유의가 생긴다.**
  ② **quarter_end 오염 1.8%**(2,209행) — 분기말이 아닌 날짜가 들어 있다. 실측 샘플:
     005930 quarter_end=2026-05-17 이고 fetched_at 도 2026-05-17, reprt_code=None.
     **수집일이 분기말 자리에 들어간 것**이다. 이 행으로 forward return 을 재면 기준일이 틀린다.

이 빌더는 판정·점수를 내지 않는다. **재료를 재기 좋은 상태로 만들고, 무엇을 얼마나 버렸는지
숫자로 신고한다.** (`feedback_measurement_audit_automation` — 사람이 훑지 말고 자동 검사가
매 run 자가 신고)

출력:
  data/metadata/kr_fundamental_panel.jsonl — 정화 패널 (ticker, quarter_end, 지표...)
  data/metadata/kr_fundamental_panel_health.json — 무엇을 왜 버렸는지

🚨 RULE 7 — 관측 사실과 그 위의 단순 산술만. 점수·등급·매매신호 0.
🚨 트랙 B 규율 — 이 패널은 **검정 재료**다. 스코어 통합은 사전등록 게이트 통과 후.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.config import DATA_DIR, now_kst  # noqa: E402

SRC = os.path.join(DATA_DIR, "dart_quarterly_snapshots.jsonl")
OUT_PANEL = os.path.join(DATA_DIR, "metadata", "kr_fundamental_panel.jsonl")
OUT_HEALTH = os.path.join(DATA_DIR, "metadata", "kr_fundamental_panel_health.json")

_QUARTER_MONTHS = {"03", "06", "09", "12"}
_METRICS = ("roa", "debt_ratio", "current_ratio", "gross_margin",
            "asset_turnover", "operating_cashflow", "net_income")


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _accruals(ni: Optional[float], ocf: Optional[float],
              roa: Optional[float]) -> Tuple[Optional[float], Optional[str]]:
    """발생액 비율 = (순이익 − 영업현금흐름) / 총자산.

    🚨 총자산 컬럼이 패널에 없다. ROA = 순이익/총자산 이므로 **총자산 = 순이익/ROA** 로 역산한다.
       역산의 실패 모드를 명시한다 — ROA 가 0 근처면 총자산이 폭발하고, 순이익 부호와 ROA 부호가
       엇갈리면 음수 자산이 나온다. 그런 행은 값을 내지 않고 사유를 남긴다.
       (원장 계정에서 직접 총자산을 받는 것이 정답이며, 그건 DART fnlttSinglAcntAll 백필 과제다.)
    """
    if ni is None or ocf is None:
        return None, "missing_ni_or_ocf"
    if roa is None or abs(roa) < 0.5:          # ROA(%) 0.5 미만 = 역산 불안정
        return None, "roa_too_small"
    assets = ni / (roa / 100.0)
    if assets <= 0:
        return None, "derived_assets_nonpositive"
    return round((ni - ocf) / assets, 6), None


def build() -> Dict[str, Any]:
    if not os.path.exists(SRC):
        return {"status": "no_source", "path": SRC}

    raw = dup = bad_qe = parse_err = 0
    best: Dict[Tuple[str, str], Dict[str, Any]] = {}

    with open(SRC, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw += 1
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                parse_err += 1
                continue
            tk = str(r.get("ticker") or "").strip()
            qe = str(r.get("quarter_end") or "")[:10]
            if not tk or len(qe) != 10:
                bad_qe += 1
                continue
            # ① 분기말이 아닌 날짜 = 수집일이 들어간 행 → 폐기
            if qe[5:7] not in _QUARTER_MONTHS:
                bad_qe += 1
                continue
            key = (tk, qe)
            # ② 중복 → fetched_at 최신 1건만 채택
            prev = best.get(key)
            if prev is not None:
                dup += 1
                if str(r.get("fetched_at") or "") <= str(prev.get("fetched_at") or ""):
                    continue
            best[key] = r

    rows = []
    acc_ok = 0
    acc_reasons: Dict[str, int] = {}
    filled: Dict[str, int] = {m: 0 for m in _METRICS}

    for (tk, qe), r in sorted(best.items()):
        rec: Dict[str, Any] = {"ticker": tk, "quarter_end": qe,
                               "fetched_at": r.get("fetched_at")}
        for m in _METRICS:
            v = _num(r.get(m))
            if v is not None:
                rec[m] = v
                filled[m] += 1
        acc, why = _accruals(rec.get("net_income"), rec.get("operating_cashflow"),
                             rec.get("roa"))
        if acc is not None:
            rec["accrual_ratio"] = acc
            acc_ok += 1
        elif why:
            acc_reasons[why] = acc_reasons.get(why, 0) + 1
        rows.append(rec)

    os.makedirs(os.path.dirname(OUT_PANEL), exist_ok=True)
    tmp = OUT_PANEL + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for rec in rows:
            f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(tmp, OUT_PANEL)

    tickers = {t for t, _ in best}
    quarters = sorted({q for _, q in best})
    health = {
        "generated_at": now_kst().isoformat(),
        "source": os.path.relpath(SRC, os.path.dirname(DATA_DIR)),
        "raw_rows": raw,
        "panel_rows": len(rows),
        "dropped": {
            "duplicate_ticker_quarter": dup,
            "quarter_end_not_quarter_end": bad_qe,
            "parse_error": parse_err,
        },
        "tickers": len(tickers),
        "quarters": len(quarters),
        "quarter_range": [quarters[0], quarters[-1]] if quarters else [],
        "filled": {m: {"n": c, "pct": round(c / len(rows) * 100, 1) if rows else 0.0}
                   for m, c in filled.items()},
        "accrual_ratio": {
            "computed": acc_ok,
            "pct": round(acc_ok / len(rows) * 100, 1) if rows else 0.0,
            "skipped_reasons": acc_reasons,
            "definition": "(순이익 − 영업현금흐름) / 총자산. 총자산은 순이익/ROA 로 역산 "
                          "(패널에 총자산 컬럼이 없음). |ROA| < 0.5% 는 역산 불안정으로 제외.",
        },
        "note": "측정정화 전용. 판정·점수 0(RULE 7). 스코어 통합은 사전등록 게이트 통과 후(트랙 B).",
    }
    tmp = OUT_HEALTH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(health, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT_HEALTH)
    return health


def main() -> int:
    h = build()
    if h.get("status") == "no_source":
        print(f"[kr_panel] 소스 없음: {h.get('path')}", file=sys.stderr)
        return 1
    d = h["dropped"]
    print(f"[kr_panel] 원행 {h['raw_rows']:,} → 패널 {h['panel_rows']:,} "
          f"(중복 {d['duplicate_ticker_quarter']:,} · 분기말오염 {d['quarter_end_not_quarter_end']:,})")
    print(f"[kr_panel] 종목 {h['tickers']:,} · 분기 {h['quarters']} "
          f"({h['quarter_range'][0] if h['quarter_range'] else '-'} ~ "
          f"{h['quarter_range'][-1] if h['quarter_range'] else '-'})")
    a = h["accrual_ratio"]
    print(f"[kr_panel] 발생액 계산 {a['computed']:,} ({a['pct']}%) · 제외 사유 {a['skipped_reasons']}")
    # 🚨 정화 결과가 비면 실패로 끝낸다 — 빈 패널을 성공으로 넘기면 다음 단계가 조용히 0을 잰다.
    return 0 if h["panel_rows"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
