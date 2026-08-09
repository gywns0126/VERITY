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
from typing import Any, Dict, List, Optional, Tuple

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


def _add_ttm(rows: List[Dict[str, Any]]) -> None:
    """기간 일관 TTM 계열 추가. 🚨 기존 필드 의미는 건드리지 않는다 —
    조용히 바꾸면 이미 나간 산출물(8/9 안심점수 검정 등)이 재현 불가가 된다.

    변환: Q1·Q2·Q3 = 3개월치 그대로 · **Q4 = FY − (Q1+Q2+Q3)** 로 복원 →
          어느 분기에서든 직전 4개 분기 합 = TTM.
    한 분기라도 비면 그 시점 TTM 은 None (0 대체 금지).
    """
    by_tk: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for r in rows:
        by_tk.setdefault(r["ticker"], {})[r["quarter_end"]] = r
    for tk, qs in by_tk.items():
        years = sorted({q[:4] for q in qs})
        q3m: Dict[str, Dict[str, Optional[float]]] = {}     # 분기말 → 3개월치
        for y in years:
            k = {m: f"{y}-{m}" for m in ("03-31", "06-30", "09-30", "12-31")}
            for fld in ("net_income", "operating_cashflow"):
                v1, v2, v3 = (qs.get(k["03-31"], {}).get(fld), qs.get(k["06-30"], {}).get(fld),
                              qs.get(k["09-30"], {}).get(fld))
                fy = qs.get(k["12-31"], {}).get(fld)
                for kk, vv in ((k["03-31"], v1), (k["06-30"], v2), (k["09-30"], v3)):
                    q3m.setdefault(kk, {})[fld] = vv
                q4 = (fy - (v1 + v2 + v3)) if None not in (fy, v1, v2, v3) else None
                q3m.setdefault(k["12-31"], {})[fld] = q4
        order = sorted(q3m)
        for i, qe in enumerate(order):
            if i < 3 or qe not in qs:
                continue
            win = order[i - 3:i + 1]
            # 🚨 연속 4분기가 아니면(상장 전 공백 등) TTM 을 만들지 않는다
            if not _is_consecutive(win):
                continue
            rec = qs[qe]
            for fld, out in (("net_income", "net_income_ttm"),
                             ("operating_cashflow", "operating_cashflow_ttm")):
                vals = [q3m[w].get(fld) for w in win]
                if all(v is not None for v in vals):
                    rec[out] = round(sum(vals), 1)
            if rec.get("net_income_ttm") is not None and rec.get("assets"):
                rec["roa_ttm"] = round(rec["net_income_ttm"] / rec["assets"] * 100.0, 4)


def _is_consecutive(qends: List[str]) -> bool:
    seq = ["03-31", "06-30", "09-30", "12-31"]
    idx = []
    for q in qends:
        try:
            idx.append(int(q[:4]) * 4 + seq.index(q[5:]))
        except ValueError:
            return False
    return all(idx[i + 1] - idx[i] == 1 for i in range(len(idx) - 1))


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
                               # 🚨 2026-08-10 추가. DART `thstrm_amount` 는 분기보고서에서
                               #   **3개월치**, 사업보고서에서 **연간**이다(실호출 확정:
                               #   005930 2024 Q1 6.75조 / 반기 9.84조 / 3Q 10.10조 / 사업 34.45조,
                               #   Q1+Q2+Q3 = 26.70조 = 3분기 누적). 즉 이 패널의 net_income·
                               #   operating_cashflow·roa 는 **기간이 섞여 있다.**
                               #   기간 일관 지표가 필요하면 아래 *_ttm 을 쓸 것.
                               "period": "FY" if qe[5:7] == "12" else "Q",
                               "fetched_at": r.get("fetched_at")}
        for m in _METRICS:
            v = _num(r.get(m))
            if v is not None:
                rec[m] = v
                filled[m] += 1
        # 자산 = 자기 행의 ni/roa 역산(같은 기간이라 정합). 스톡이라 분기·연간 무관.
        assets = None
        _ni, _roa = rec.get("net_income"), rec.get("roa")
        if _ni is not None and _roa is not None and abs(_roa) >= 0.5:
            assets = _ni / (_roa / 100.0)
            rec["assets"] = round(assets, 1)
            _dr = rec.get("debt_ratio")
            if _dr is not None and _dr > -100:
                # 부채비율 = 부채/자본×100 · 자산 = 부채+자본 → 자본 = 자산/(1+부채비율/100)
                # 실측 검증(2026-08-10, N=18 실 DART 대조): 중앙오차 0.0% · 최대 0.7%
                rec["equity"] = round(assets / (1.0 + _dr / 100.0), 1)
        acc, why = _accruals(rec.get("net_income"), rec.get("operating_cashflow"),
                             rec.get("roa"))
        if acc is not None:
            rec["accrual_ratio"] = acc
            acc_ok += 1
        elif why:
            acc_reasons[why] = acc_reasons.get(why, 0) + 1
        rows.append(rec)

    _add_ttm(rows)

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
