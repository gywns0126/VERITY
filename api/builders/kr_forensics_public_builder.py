"""kr_forensics_public_builder — 공개 터미널 KR 종목 forensics(특수관계자 거래·우발부채·소송) public-safe 빌더.

입력(이미 수집·커밋): data/dart_related_party_cache.json + data/dart_litigation_cache.json (by_ticker).
출력: data/kr_forensics_public.json → PublicStockReport forensics 섹션 배선.

🚨 RULE 7 / RULE 6 — 사실만. 노출 = 원문 인용 사실 리스트:
  · 특수관계자 거래: major_transactions (거래상대·금액·유형 — DART 특수관계자 거래 주석)
  · 우발부채: contingent_liabilities (지급보증·이행보증 등 금액)
  · 소송: pending_litigation / material_sanctions
  비노출(자체 판단·해석) = related_party_risk_score / litigation_risk_score / severity / tunneling_flags(의심 서술) / summary(서술 요약).
순수 변환 — 외부호출 0. publish: data/kr_forensics_public.json (action.yml 등재).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RELATED_PATH = os.path.join(_ROOT, "data", "dart_related_party_cache.json")
LITIGATION_PATH = os.path.join(_ROOT, "data", "dart_litigation_cache.json")
CB_BW_PATH = os.path.join(_ROOT, "data", "dart_cb_bw_cache.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "kr_forensics_public.json")


def _now_kst() -> datetime:
    return datetime.now(KST)


def _load(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return (json.load(f) or {}).get("by_ticker") or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _latest_year(by_year: Dict[str, Any]) -> Any:
    """{'2024': {...}, '2025': {...}} → 최신 연도 dict. 없으면 None."""
    if not isinstance(by_year, dict) or not by_year:
        return None
    try:
        yr = max(by_year.keys(), key=lambda k: int(k))
    except (ValueError, TypeError):
        yr = sorted(by_year.keys())[-1]
    return by_year.get(yr), yr


def _str_list(v: Any, cap: int = 8) -> List[str]:
    """리스트 → 사실 문자열 리스트(빈/비문자 제거, cap 제한)."""
    if not isinstance(v, list):
        return []
    out = []
    for x in v:
        s = str(x).strip()
        if s:
            out.append(s)
        if len(out) >= cap:
            break
    return out


def _litig_str(v: Any, cap: int = 8) -> List[str]:
    """소송 항목 — dict{counterparty, claim_amount, issue} 또는 str → 사실 문자열."""
    out: List[str] = []
    for x in (v if isinstance(v, list) else []):
        if isinstance(x, dict):
            cp = str(x.get("counterparty") or "").strip()
            amt = str(x.get("claim_amount") or "").strip()
            iss = str(x.get("issue") or "").strip()
            parts = []
            if cp and cp != "미상":
                parts.append("상대 " + cp)
            if amt:
                parts.append("청구액 " + amt)
            if iss:
                parts.append(iss)
            s = " · ".join(parts)
        else:
            s = str(x).strip()
        if s:
            out.append(s)
        if len(out) >= cap:
            break
    return out


def build() -> Dict[str, Any]:
    related = _load(RELATED_PATH)
    litig = _load(LITIGATION_PATH)
    cbw = _load(CB_BW_PATH)
    tickers = set(related.keys()) | set(litig.keys()) | set(cbw.keys())
    stocks: Dict[str, Any] = {}
    for tk in tickers:
        block: Dict[str, Any] = {}
        years = set()
        rp = _latest_year(related.get(tk) or {})
        if rp and rp[0]:
            rec, yr = rp
            txns = _str_list(rec.get("major_transactions"))
            if txns:
                block["related_party_transactions"] = txns
                years.add(yr)
        lp = _latest_year(litig.get(tk) or {})
        if lp and lp[0]:
            rec, yr = lp
            cl = _str_list(rec.get("contingent_liabilities"))
            pl = _litig_str(rec.get("pending_litigation"))
            ms = _str_list(rec.get("material_sanctions"))
            if cl:
                block["contingent_liabilities"] = cl
            if pl:
                block["pending_litigation"] = pl
            if ms:
                block["material_sanctions"] = ms
            if cl or pl or ms:
                years.add(yr)
        cb = cbw.get(tk) or {}
        if cb.get("n_instruments"):
            block["cb_bw"] = {
                "n_instruments": cb.get("n_instruments"),
                "dilution_pct": cb.get("dilution_pct"),
                "total_issuable_shares": cb.get("total_issuable_shares"),
                "instruments": [
                    {k: ins.get(k) for k in ("type", "bond_kind", "issue_amount", "strike", "issuable_shares", "resolved_date")}
                    for ins in (cb.get("instruments") or [])[:6] if isinstance(ins, dict)
                ],
                "note": "DART 주요사항보고 발행 기준(전환·상환 미반영) · 희석률=발행가능÷발행주식",
            }
        if block:
            block["year"] = sorted(years)[-1] if years else None
            block["source_note"] = "DART 공시 원문 사실(특수관계자·우발부채·소송·CB/BW) · 자체 위험판단 아님"
            stocks[tk] = block
    return {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "source": "DART 사업보고서·주요사항 (dart_related_party / dart_litigation / dart_cb_bw)",
            "count": len(stocks),
            "note": "공개 사실만 (RULE 7) — 위험점수·심각도·터널링 의심서술·요약 비노출. 원문 인용.",
        },
        "stocks": stocks,
    }


def main() -> int:
    ok = False
    try:
        out = build()
        if not out["stocks"] and os.path.isfile(OUTPUT_PATH):
            print("[kr_forensics_public] 0 stocks — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[kr_forensics_public] logged=True · {len(out['stocks'])} 종목 -> "
              f"{os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[kr_forensics_public] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[kr_forensics_public] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
