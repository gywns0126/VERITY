#!/usr/bin/env python3
"""내부 전용 컨텍스트 — 관리자 챗에서만 쓰는 미발행 자산 요약.

배경 (PM 2026-07-30 "가져올 수 있는 정보의 한계치까지 뽑고"):
  공개 사이트는 재배포 권리·RULE 7 때문에 원본을 못 싣는 데이터가 많다. 그런데 그 데이터는
  백엔드에 이미 다 모여 있다. 본인만 보는 비공개 화면(= /admin, is_admin 서버 게이트)에서는
  배포가 아니므로 전량을 판단 재료로 쓸 수 있다.

🚨 이 모듈은 **관리자 경로에서만** 호출해야 한다. 공개 챗(/api/chat)에 물리면 그 순간
   재배포가 된다. 호출부 = vercel-api/api/chat_admin.py (JWT + profiles.is_admin 검증 후).
   공개 orchestrator 경로는 internal=False 기본값이라 이 모듈을 부르지 않는다.

싣는 것 (전부 미발행):
  · recommendations.json — 전 종목 원본(가격·시총·PER/PBR·ROE·성장률·추세). 공개본은 strip 됨
  · portfolio.json — VAMS 자산/수익/검증 리포트, 시스템 헬스. 공개본은 31키로 축소(Stage 3)
  · us_analyst_consensus.json — 목표가·투자의견. **발행 영구 금지**(Benzinga/S&P 실권리)
  · factor_ic_history.json — 팩터 IC 시계열
  · validation_summary.json full — funnel 신호 포함(공개본은 제외)

🚨 RULE 7 — 자기 산식은 전부 가설이다. 등급·점수·IC 를 실을 때 N 과 "가설" 표기를 함께 넣어
   합성 LLM 이 확정 사실처럼 쓰지 않게 한다. 프롬프트 단에서 지켜지도록 문구를 여기서 못 준다.
🚨 크기 — MB 급 파일이라 전량을 프롬프트에 넣을 수 없다. 질문에 걸린 종목만 상세로 펴고
   나머지는 집계로 요약한다(_MAX_TICKER_DETAIL).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

_logger = logging.getLogger(__name__)
def _find_data_dir() -> Optional[str]:
    """data/ 를 위로 올라가며 찾는다.

    🚨 고정 깊이(dirname 4회)로 잡으면 안 된다 — 이 패키지는 두 위치에 산다:
       SSOT `api/chat_hybrid/search/` (4회 = repo root ✓)
       배포 복제 `vercel-api/api/chat_hybrid/search/` (4회 = vercel-api ✗ → data 없음)
       sync_chat_hybrid.sh 가 복제하므로 같은 파일이 양쪽에서 동작해야 한다.
    """
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        cand = os.path.join(d, "data")
        if os.path.isdir(cand):
            return cand
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return None


_DATA = _find_data_dir()
# 🚨 서버리스 대비 — 내부 파일은 **미발행**이라 공개 blob URL 폴백이 없다(공개 파일과 다른 점).
#    Vercel 번들에 data/ 가 없으면 내부 블록은 조용히 빈 채로 간다(챗은 공개 컨텍스트로 계속 동작).
#    비공개 저장소를 붙일 때 이 두 env 를 쓴다. 미설정이면 로컬 파일만 시도.
_REMOTE_BASE = os.environ.get("INTERNAL_DATA_BASE", "").rstrip("/")
_REMOTE_TOKEN = os.environ.get("INTERNAL_DATA_TOKEN", "")

_MAX_TICKER_DETAIL = 6      # 질문에 걸린 종목 상세 상한
_MAX_CHARS = 14000          # 내부 블록 전체 상한 (합성 프롬프트 예산 보호)


def _load(name: str) -> Any:
    if _DATA:
        try:
            with open(os.path.join(_DATA, name), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            _logger.info("internal_context: %s 로컬 로드 실패 (%s)", name, type(e).__name__)
    if not _REMOTE_BASE:
        return None
    # 비공개 원격 폴백 — 토큰이 있을 때만. 공개 URL 을 여기에 넣지 말 것(= 재배포).
    try:
        import urllib.request

        req = urllib.request.Request(_REMOTE_BASE + "/" + name)
        if _REMOTE_TOKEN:
            req.add_header("Authorization", "Bearer " + _REMOTE_TOKEN)
        with urllib.request.urlopen(req, timeout=6) as r:
            return json.loads(r.read())
    except Exception as e:  # noqa: BLE001 — 폴백 실패는 조용히
        _logger.info("internal_context: %s 원격 로드 실패 (%s)", name, type(e).__name__)
        return None


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _fmt(v: Any, unit: str = "", digits: int = 2) -> str:
    n = _num(v)
    if n is None:
        return "—"
    return (f"{n:,.{digits}f}".rstrip("0").rstrip(".") or "0") + unit


def _rec_line(r: Dict[str, Any]) -> str:
    """추천 원본 1건 → 한 줄. 공개본에서 잘려나간 필드까지 포함."""
    bits = [f"{r.get('name') or r.get('ticker')}({r.get('ticker')})"]
    cur = str(r.get("currency") or "")
    px = _num(r.get("price"))
    if px is not None:
        bits.append(f"가격 {px:,.2f}{'$' if cur == 'USD' else '원'}")
    for k, label, unit in (
        ("per", "PER", ""), ("pbr", "PBR", ""), ("roe", "ROE", "%"),
        ("operating_margin", "영업이익률", "%"), ("revenue_growth", "매출성장", "%"),
        ("debt_ratio", "부채비율", "%"), ("div_yield", "배당수익률", "%"),
        ("drop_from_high_pct", "52주고점대비", "%"),
    ):
        if _num(r.get(k)) is not None:
            bits.append(f"{label} {_fmt(r.get(k), unit)}")
    mc = _num(r.get("market_cap"))
    if mc:
        bits.append(f"시총 {mc/1e12:.2f}조" if mc >= 1e12 else f"시총 {mc/1e8:,.0f}억")
    return " · ".join(bits)


def _sec_recommendations(tickers: List[str]) -> List[str]:
    recs = _load("recommendations.json")
    if not isinstance(recs, list) or not recs:
        return []
    out = ["[내부] 추천 유니버스 원본 — 공개본에서 strip 된 필드 포함"]
    by_tk = {str(r.get("ticker") or ""): r for r in recs if isinstance(r, dict)}
    hit = [by_tk[t] for t in tickers if t in by_tk][:_MAX_TICKER_DETAIL]
    for r in hit:
        out.append("  · " + _rec_line(r))
    if not hit:
        # 종목 특정이 없으면 전체 성격만 — 개별 나열은 프롬프트 낭비
        pers = [_num(r.get("per")) for r in recs]
        pers = [p for p in pers if p and 0 < p < 500]
        out.append(
            f"  · 총 {len(recs)}종 · PER 중앙값 "
            f"{sorted(pers)[len(pers)//2]:.1f}" if pers else f"  · 총 {len(recs)}종"
        )
    return out


def _sec_vams() -> List[str]:
    pf = _load("portfolio.json")
    if not isinstance(pf, dict):
        return []
    v = pf.get("vams") or {}
    if not v:
        return []
    out = ["[내부] VAMS 운용 실적 — 미발행(공개 portfolio 는 31키로 축소됨)"]
    ta, ret = _num(v.get("total_asset")), _num(v.get("total_return_pct"))
    if ta is not None:
        out.append(f"  · 총자산 {ta:,.0f}원 · 현금 {_fmt(v.get('cash'), '원', 0)}")
    if ret is not None:
        out.append(f"  · 누적수익률 {ret:+.2f}% · 실현손익 {_fmt(v.get('total_realized_pnl'), '원', 0)}")
    hs = v.get("holdings")
    if isinstance(hs, list) and hs:
        names = [str((h or {}).get("name") or (h or {}).get("ticker")) for h in hs[:8]]
        out.append(f"  · 보유 {len(hs)}종: {', '.join(n for n in names if n)}")
    st = v.get("simulation_stats") or {}
    if isinstance(st, dict) and st:
        n = st.get("n") or st.get("trades") or st.get("count")
        out.append(
            f"  · 시뮬 통계(🚨 가설, N={n if n is not None else '?'}): "
            + " · ".join(f"{k} {st[k]}" for k in list(st)[:5] if not isinstance(st[k], (dict, list)))
        )
    vr = v.get("validation_report")
    if isinstance(vr, dict) and vr:
        out.append("  · 검증 리포트: " + ", ".join(
            f"{k}={vr[k]}" for k in list(vr)[:5] if not isinstance(vr[k], (dict, list))))
    return out


def _sec_consensus(tickers: List[str]) -> List[str]:
    doc = _load("us_analyst_consensus.json")
    if not isinstance(doc, dict):
        return []
    rows = doc.get("stocks")
    if not isinstance(rows, list) or not rows:
        return []
    by = {str((r or {}).get("ticker") or ""): r for r in rows}
    hit = [by[t] for t in tickers if t in by][:_MAX_TICKER_DETAIL]
    if not hit:
        return [f"[내부] 미장 애널리스트 컨센서스 {len(rows)}종 보유 (🚫 발행 영구 금지 자산)"]
    out = ["[내부] 미장 애널리스트 컨센서스 — 🚫 발행 영구 금지(실권리 Benzinga/S&P). 판단 재료로만."]
    for r in hit:
        bits = [str(r.get("ticker"))]
        for k, label in (("target_mean", "목표가 평균"), ("target_high", "최고"),
                         ("target_low", "최저"), ("recommendation", "투자의견"),
                         ("analyst_count", "애널리스트 수")):
            if r.get(k) not in (None, ""):
                bits.append(f"{label} {r.get(k)}")
        out.append("  · " + " · ".join(bits))
    return out


def _sec_factor_ic() -> List[str]:
    doc = _load("factor_ic_history.json")
    if not doc:
        return []
    rows = doc if isinstance(doc, list) else (doc.get("history") or doc.get("records") or [])
    if not isinstance(rows, list) or not rows:
        return []
    last = rows[-1] if isinstance(rows[-1], dict) else {}
    out = [f"[내부] 팩터 IC 시계열 {len(rows)}건 (🚨 가설 — N<252 구간은 통계 무의미)"]
    kv = [f"{k}={last[k]}" for k in list(last)[:8] if not isinstance(last[k], (dict, list))]
    if kv:
        out.append("  · 최근: " + " · ".join(kv))
    return out


def _sec_health() -> List[str]:
    pf = _load("portfolio.json")
    if not isinstance(pf, dict):
        return []
    h = pf.get("system_health") or {}
    if not isinstance(h, dict) or not h:
        return []
    out = [f"[내부] 시스템 헬스 — status={h.get('status')} · checked_at={h.get('checked_at')}"]
    for k in ("errors", "warnings"):
        v = h.get(k)
        if isinstance(v, list) and v:
            out.append(f"  · {k} {len(v)}건: {str(v[:3])[:200]}")
    dr = h.get("data_recency")
    if isinstance(dr, dict) and dr:
        stale = [k for k, val in dr.items() if isinstance(val, (int, float)) and val > 48]
        if stale:
            out.append(f"  · 48시간 초과 stale: {', '.join(stale[:8])}")
    return out


def build_internal_context(
    tickers: Optional[List[str]] = None,
    max_chars: int = _MAX_CHARS,
) -> Dict[str, Any]:
    """관리자 챗용 내부 컨텍스트.

    Returns: {"ok": bool, "text": str, "sections": [str], "chars": int}
    실패해도 예외를 올리지 않는다 — 내부 블록이 비어도 챗은 공개 컨텍스트로 답해야 한다.
    """
    tks = [str(t).upper() for t in (tickers or []) if t]
    blocks: List[List[str]] = []
    for fn in (
        lambda: _sec_recommendations(tks),
        _sec_vams,
        lambda: _sec_consensus(tks),
        _sec_factor_ic,
        _sec_health,
    ):
        try:
            b = fn()
        except Exception as e:  # noqa: BLE001 — 개별 섹션 실패 격리
            _logger.warning("internal_context 섹션 실패: %r", e)
            b = []
        if b:
            blocks.append(b)

    if not blocks:
        return {"ok": False, "text": "", "sections": [], "chars": 0}

    head = (
        "═══ 내부 전용 자산 (미발행 · 관리자 전용) ═══\n"
        "아래는 공개 사이트에 싣지 않는 데이터다. 판단 재료로 자유롭게 쓰되:\n"
        "  · 자기 산식(등급·점수·IC·시뮬 통계)은 **가설**이다. 확정 사실처럼 쓰지 말고 N 을 함께 밝힌다.\n"
        "  · 컨센서스 목표가는 발행 금지 자산이므로 '외부 애널리스트 견해' 로만 인용한다.\n"
    )
    text = head + "\n".join("\n".join(b) for b in blocks)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…(내부 컨텍스트 길이 상한으로 절단)"
    return {
        "ok": True,
        "text": text,
        "sections": [b[0] for b in blocks],
        "chars": len(text),
    }


if __name__ == "__main__":  # 간이 점검
    for tk in ([], ["005930"], ["TSLA"]):
        r = build_internal_context(tk)
        print(f"--- tickers={tk} ok={r['ok']} chars={r['chars']}")
        for s in r["sections"]:
            print("   ", s)
