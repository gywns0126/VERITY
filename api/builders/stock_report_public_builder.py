"""stock_report_public_builder — 공개 터미널 "종목 리포트" public-safe 합성 빌더.

배경 (2026-06-18, 멀티에이전트 RULE10 감사 결과):
  recommendations.json (운영 풀 26 레코드, 종목당 90키) 가 거의 모든 사실의 1차 원천.
  대부분 사실이 레코드에 임베드 → strip 후 노출. 공시 원문은 dart_catalyst_alerts.jsonl.

🚨 RULE 7 — **allowlist 방식** (blacklist 아님). 노출 가능 사실 키만 골라 담는다.
  신규 점수 키가 recommendations 에 추가돼도 자동 누출 안 됨 (안전 방향).
  비노출(strip): brain_score / grade / recommendation / multi_factor / verity_brain /
    trade_plan / prediction / timing / lynch_kr / *_score / ai_verdict / sentiment 등 전부.
  노출(사실): PER/PBR/ROE/부채비율/Altman-Z(zone)/시가총액 / 공시(원문 deep-link) /
    지분(공정위 총수일가) / 컨센서스(증권사 집계 — 자체 추천 아님) / 일정(실적발표).

  flow(수급): recommendations.flow = 26/26 dead(전부 0), 개인키 부재 → 노출 보류(gap).
  change_pct: 일간 전일종가 단일 필드 부재 → null (UI 미표시). 신뢰 불가값 노출 금지.

순수 변환 — 외부호출/KIS 0. 입력 read-only.
publish: data/stock_report_public.json → publish-data action 목록 추가 의무(RULE 4).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REC_PATH = os.path.join(_ROOT, "data", "recommendations.json")
CATALYST_PATH = os.path.join(_ROOT, "data", "dart_catalyst_alerts.jsonl")
OUTPUT_PATH = os.path.join(_ROOT, "data", "stock_report_public.json")
DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="

# 총수일가 = 공정위 분류상 동일인 + 친족 (소속회사는 그룹 지배지분, 별도)
FAMILY_TYPES = {"동일인", "친족"}


def _now_kst() -> datetime:
    return datetime.now(KST)


def _is_kr(rec: Dict[str, Any]) -> bool:
    cur = str(rec.get("currency") or "")
    mkt = str(rec.get("market") or "")
    if cur == "USD":
        return False
    return "KOSPI" in mkt or "KOSDAQ" in mkt or "KRX" in mkt or bool(rec.get("ticker", "").isdigit())


def _fmt_cap(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if x <= 0:
        return "—"
    if x >= 1e12:
        return f"{x / 1e12:.1f}조"
    if x >= 1e8:
        return f"{x / 1e8:.0f}억"
    return f"{x:,.0f}"


def _num(v: Any, suffix: str = "", digits: int = 1) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    s = f"{x:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{x:.0f}"
    return f"{s}{suffix}"


def _load_catalyst_by_ticker() -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    if not os.path.isfile(CATALYST_PATH):
        return out
    seen: set = set()
    with open(CATALYST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                a = json.loads(line)
            except json.JSONDecodeError:
                continue
            tk = str(a.get("ticker") or "")
            rc = str(a.get("rcept_no") or "")
            if not tk or not rc or rc in seen:
                continue
            seen.add(rc)
            dt = str(a.get("rcept_dt") or "")
            date = f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}" if len(dt) == 8 else dt
            out.setdefault(tk, []).append({
                "title": a.get("report_nm") or "",
                "label": a.get("pblntf_label") or "",
                "date": date,
                "is_correction": bool(a.get("is_correction")),
                "filer": a.get("flr_nm") or "",
                "source_url": DART + rc,
            })
    for tk in out:
        out[tk].sort(key=lambda d: d["date"], reverse=True)
    return out


def _ownership(rec: Dict[str, Any]) -> Dict[str, Any] | None:
    ftc = ((rec.get("group_structure") or {}).get("ftc_official") or {})
    sh = ftc.get("shareholders") or []
    if not isinstance(sh, list) or not sh:
        return None
    family = 0.0
    for s in sh:
        if str(s.get("type") or "") in FAMILY_TYPES:
            try:
                family += float(s.get("qota_rate") or 0)
            except (TypeError, ValueError):
                pass
    top = [{"name": s.get("name"), "type": s.get("type"), "qota_rate": s.get("qota_rate")}
           for s in sh[:5]]
    return {
        "family_pct": round(family, 2),
        "note": "동일인+친족 합산 (소속회사 지배지분 별도) · 공정위 분류",
        "source": "공정거래위원회 기업집단포털" + (f" ({ftc.get('as_of_year')})" if ftc.get("as_of_year") else ""),
        "top_holders": top,
    }


def _consensus(rec: Dict[str, Any]) -> Dict[str, Any] | None:
    c = rec.get("consensus") or {}
    if not c.get("consensus_available"):
        return None
    out: Dict[str, Any] = {}
    if c.get("target_price"):
        try:
            out["target_price"] = f"{float(c['target_price']):,.0f}원"
        except (TypeError, ValueError):
            pass
    if c.get("investment_opinion"):
        out["opinion"] = str(c["investment_opinion"])  # 증권사 집계 — 자체 추천 아님
    eps = rec.get("eps")
    try:
        if eps and float(eps) != 0:
            out["eps"] = f"{float(eps):,.0f}원"
    except (TypeError, ValueError):
        pass
    return out or None


def build_stock(rec: Dict[str, Any], catalyst: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    ticker = str(rec.get("ticker") or "")
    altman = (((rec.get("quant_factors") or {}).get("quality") or {}).get("altman") or {})

    facts: Dict[str, str] = {}
    fnote: Dict[str, str] = {}
    if rec.get("per") is not None:
        facts["PER"] = _num(rec.get("per"), digits=1)
    if rec.get("pbr") is not None:
        facts["PBR"] = _num(rec.get("pbr"), digits=1)
    if rec.get("roe") is not None:
        facts["ROE"] = _num(rec.get("roe"), suffix="%", digits=1)
    if rec.get("debt_ratio") is not None:
        facts["부채비율"] = _num(rec.get("debt_ratio"), suffix="%", digits=0)
    if altman.get("z_score") is not None:
        facts["Altman-Z"] = _num(altman.get("z_score"), digits=1)
        if altman.get("zone"):
            fnote["Altman-Z"] = "안전구간" if altman["zone"] == "safe" else str(altman["zone"])
    if rec.get("market_cap"):
        facts["시가총액"] = _fmt_cap(rec.get("market_cap"))

    return {
        "ticker": ticker,
        "name": rec.get("name") or ticker,
        "market": rec.get("market") or "",
        "business": rec.get("company_tagline") or rec.get("company_type") or "",
        "price": rec.get("price"),
        "change_pct": None,  # 일간 전일종가 부재 — 신뢰 불가값 노출 금지
        "currency": rec.get("currency") or "KRW",
        "facts": facts,
        "facts_note": fnote,
        "flow": None,  # recommendations.flow 26/26 dead — 노출 보류
        "disclosures": catalyst.get(ticker, [])[:8],
        "ownership": _ownership(rec),
        "consensus": _consensus(rec),
        "calendar": (
            [{"event": "실적발표", "kind": "실적", "date": (rec.get("earnings") or {}).get("next_earnings")}]
            if (rec.get("earnings") or {}).get("next_earnings") else []
        ),
    }


def main() -> int:
    ok = False
    try:
        if not os.path.isfile(REC_PATH):
            print("[stock_report_public] recommendations.json 부재 — skip", file=sys.stderr)
            return 0
        with open(REC_PATH, "r", encoding="utf-8") as f:
            recs = json.load(f)
        if not isinstance(recs, list):
            recs = []
        catalyst = _load_catalyst_by_ticker()

        stocks = [build_stock(r, catalyst) for r in recs if _is_kr(r) and r.get("ticker")]
        # 시총 큰 순 정렬 (노출 우선순위 — 사실 기반)
        stocks.sort(key=_capnum, reverse=True)

        out = {
            "_meta": {
                "generated_at": _now_kst().isoformat(),
                "source": "DART (전자공시) · 공정위 · FnGuide 집계",
                "count": len(stocks),
                "note": "공개 사실만 (RULE 7 allowlist) — 점수·등급·추천 비노출. 컨센서스는 증권사 집계(자체 의견 아님).",
            },
            "stocks": stocks,
        }
        if not stocks and os.path.isfile(OUTPUT_PATH):
            print("[stock_report_public] 0 stocks — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"[stock_report_public] logged=True · {len(stocks)} 종목 -> "
              f"{os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[stock_report_public] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[stock_report_public] logged=False", file=sys.stderr)


def _capnum(s: Dict[str, Any]) -> float:
    v = s.get("facts", {}).get("시가총액", "")
    try:
        if v.endswith("조"):
            return float(v[:-1]) * 1e12
        if v.endswith("억"):
            return float(v[:-1]) * 1e8
    except (ValueError, AttributeError):
        pass
    return 0.0


if __name__ == "__main__":
    sys.exit(main())
