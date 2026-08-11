# -*- coding: utf-8 -*-
"""dart_dividend_history — DART 배당에 관한 사항 이력 (L1 원장).

2026-08-10 신설. 안심점수 미재현 47점 중 **배당 12점**의 PIT 소스다.
덤으로 **(연결)주당순이익 = 지배주주 EPS** 가 같은 응답에 있어 PER 20점의 충실도도 올린다
(시총÷전체순이익 근사 → 주가÷지배주주EPS, 운영 yfinance trailingPE 와 같은 정의).

🚨 **수집만 한다. 검정하지 않는다.** 전체 100점 검정은 별도 사전등록 대상이다.

## 콜 예산 ([[project_dart_api_2026_constraints]] 20,000/일 보호)

`alotMatter` 응답 한 건에 **당기·전기·전전기 3개 연도**가 들어 있다(`thstrm`/`frmtrm`/`lwfr`).
그래서 bsns_year 를 2019·2022·2025 세 번만 부르면 2017~2025 가 덮인다 — **종목당 3콜**.
연도별로 부르면 7콜이므로 57% 절감. `--max-calls` 로 상한을 두고 재개 가능하게 한다.

## PIT

- `rcept_no` 앞 8자리 = **실제 접수일**. 당기 수치의 진짜 관측 가능 시점이다.
- 전기·전전기는 그 해 보고서로 더 일찍 공개됐으므로 `stlm_dt + 90일` 로 보수 근사한다.
- 두 값을 모두 행에 남겨 소비 측이 고를 수 있게 한다.

출력 = `data/metadata/kr_dividend_history.jsonl`
  {"ticker","year","dps","eps_owner","div_yield_reported","payout_ratio",
   "rcept_date","stlm_dt","basis":"thstrm|frmtrm|lwfr"}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.config import DATA_DIR  # noqa: E402

OUT_PATH = os.path.join(DATA_DIR, "metadata", "kr_dividend_history.jsonl")
MAPPING_PATH = os.path.join(DATA_DIR, "mapping.json")
PANEL_PATH = os.path.join(DATA_DIR, "metadata", "kr_fundamental_panel.jsonl")
MKTCAP_PATH = os.path.join(DATA_DIR, "metadata", "krx_mktcap_history.jsonl")

# 한 콜 = 3개 연도. 2019·2022·2025 → 2017~2025 커버.
CALL_YEARS: Tuple[int, ...] = (2019, 2022, 2025)
_BASIS = (("thstrm", 0), ("frmtrm", -1), ("lwfr", -2))
SLEEP_SEC = 0.06
DEFAULT_MAX_CALLS = 15000


def _key() -> str:
    for p in (os.path.join(os.path.dirname(DATA_DIR), ".env"),
              os.path.join(os.path.dirname(DATA_DIR), "vercel-api", ".env")):
        try:
            for line in open(p, encoding="utf-8"):
                if line.strip().startswith(("DART_API_KEY", "OPENDART_API_KEY")):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            continue
    return os.environ.get("DART_API_KEY", "")


def _num(s: object) -> Optional[float]:
    t = str(s or "").replace(",", "").strip()
    if not t or t == "-":
        return None
    try:
        return float(t)
    except ValueError:
        return None


def targets() -> List[str]:
    """대상 = KRX 시총 원장에 나타난 종목 ∩ corp_code 보유. 백테스트 유니버스를 덮는다."""
    mapping = json.load(open(MAPPING_PATH, encoding="utf-8"))
    have_cc = {k for k, v in mapping.items() if isinstance(v, str) and len(v) == 8}
    seen: Set[str] = set()
    with open(MKTCAP_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                seen.add(str(json.loads(line)["t"]))
            except (json.JSONDecodeError, KeyError):
                continue
    return sorted(seen & have_cc)


def done_pairs(path: str) -> Set[Tuple[str, int]]:
    out: Set[Tuple[str, int]] = set()
    try:
        f = open(path, encoding="utf-8")
    except OSError:
        return out
    with f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("call_year") is not None:
                out.add((str(r.get("ticker")), int(r["call_year"])))
    return out


def fetch(key: str, corp_code: str, year: int) -> Optional[List[Dict[str, Any]]]:
    q = urllib.parse.urlencode({"crtfc_key": key, "corp_code": corp_code,
                                "bsns_year": str(year), "reprt_code": "11011"})
    try:
        with urllib.request.urlopen(
                f"https://opendart.fss.or.kr/api/alotMatter.json?{q}", timeout=30) as r:
            d = json.loads(r.read().decode())
    except Exception:  # noqa: BLE001 — 개별 실패가 배치를 죽이지 않는다
        return None
    if d.get("status") == "020":                 # 사용한도 초과
        raise RuntimeError("DART 사용한도 초과(status 020) — 중단")
    if d.get("status") != "000":
        return []
    return list(d.get("list") or [])


def parse(rows: List[Dict[str, Any]], ticker: str, call_year: int) -> List[Dict[str, Any]]:
    """se × stock_knd 격자 → 연도별 1행. 🚨 보통주만 채택(우선주는 별 종목코드다).

    🚨 구 공시(2019년경 이전)는 `stock_knd` 가 전부 `-` 이고 **행 순서로** 보통주/우선주를
       구분한다(실측 000020 2019: '주당 현금배당금(원)' 이 두 줄, 둘 다 knd='-',
       첫 줄 120원 = 보통주 / 둘째 줄 '-' = 우선주). knd 만 보면 구 공시 배당이 통째로
       누락돼 배당 12점이 0점으로 둔갑한다. 명시 '보통주' 우선, 없으면 **첫 등장**을 채택.
    """
    if not rows:
        return []
    rcept = str(rows[0].get("rcept_no") or "")[:8] or None
    stlm = str(rows[0].get("stlm_dt") or "") or None
    out: List[Dict[str, Any]] = []
    for field, offset in _BASIS:
        y = call_year + offset
        rec: Dict[str, Any] = {"ticker": ticker, "year": y, "call_year": call_year,
                               "basis": field, "rcept_date": rcept, "stlm_dt": stlm}
        got = False
        explicit: Set[str] = set()          # '보통주' 로 명시돼 확정된 필드
        for r in rows:
            se = str(r.get("se") or "").strip().replace(" ", "")
            knd = str(r.get("stock_knd") or "").strip()
            v = _num(r.get(field))
            if se.startswith("주당현금배당금"):
                col = "dps"
            elif se.startswith("현금배당수익률"):
                col = "div_yield_reported"
            elif "주당순이익" in se:
                col = "eps_owner"
            elif "현금배당성향" in se:
                col = "payout_ratio"
            else:
                continue
            if knd == "보통주":
                rec[col] = v
                explicit.add(col)
            elif knd in ("우선주",) or col in explicit or col in rec:
                continue                     # 우선주 / 이미 확정 / 첫 등장 이후
            else:
                rec[col] = v
            if col != "payout_ratio" and rec.get(col) is not None:
                got = True
        # 🚨 배당 0 과 미보고는 다르다. 배당 항목이 통째로 비면 행을 만들지 않는다 —
        #    소비 측이 "0원 배당" 으로 오독하면 배당 12점이 조용히 왜곡된다.
        if got:
            out.append(rec)
    return out


def run(max_calls: int = DEFAULT_MAX_CALLS, limit_tickers: int = 0) -> Dict[str, Any]:
    t0 = time.time()
    key = _key()
    if not key:
        return {"status": "no_key"}
    tks = targets()
    if limit_tickers:
        tks = tks[:limit_tickers]
    mapping = json.load(open(MAPPING_PATH, encoding="utf-8"))
    done = done_pairs(OUT_PATH)
    todo = [(t, y) for t in tks for y in CALL_YEARS if (t, y) not in done]

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    calls = written = empty = 0
    stopped = None
    with open(OUT_PATH, "a", encoding="utf-8") as f:
        for tk, yr in todo:
            if calls >= max_calls:
                stopped = "max_calls"
                break
            cc = mapping.get(tk)
            if not cc:
                continue
            try:
                rows = fetch(key, cc, yr)
            except RuntimeError as e:
                stopped = str(e)
                break
            calls += 1
            if rows is None:
                continue
            recs = parse(rows, tk, yr)
            if not recs:
                empty += 1
                # 재조회 방지용 표식 — 없으면 매 실행이 같은 빈 응답을 다시 부른다
                f.write(json.dumps({"ticker": tk, "year": None, "call_year": yr,
                                    "basis": None, "empty": True},
                                   ensure_ascii=False) + "\n")
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
                written += 1
            if calls % 500 == 0:
                print(f"  {calls:,}콜 · {written:,}행 · 빈응답 {empty:,} "
                      f"· {time.time() - t0:.0f}s", flush=True)
            time.sleep(SLEEP_SEC)

    # 🚨 [[feedback_silent_total_failure_guard]]
    status = "ok"
    if todo and calls > 0 and written == 0:
        status = "total_failure"
    return {"status": status, "tickers": len(tks), "todo_calls": len(todo),
            "calls": calls, "written": written, "empty_responses": empty,
            "stopped": stopped, "elapsed_sec": round(time.time() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    ap.add_argument("--limit-tickers", type=int, default=0)
    a = ap.parse_args()
    r = run(a.max_calls, a.limit_tickers)
    if r["status"] == "no_key":
        print("[dart_dividend_history] 🚨 DART 키 없음", file=sys.stderr)
        return 1
    if r["status"] == "total_failure":
        print(f"[dart_dividend_history] 🚨 {r['calls']}콜인데 0행 — 전량 실패", file=sys.stderr)
        return 1
    print(f"[dart_dividend_history] 종목 {r['tickers']:,} · {r['calls']:,}콜 "
          f"· {r['written']:,}행 · 빈응답 {r['empty_responses']:,} · {r['elapsed_sec']}s")
    if r["stopped"]:
        print(f"[dart_dividend_history] 중단: {r['stopped']} — 잔여 {r['todo_calls'] - r['calls']:,}콜",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
