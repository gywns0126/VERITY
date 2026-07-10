#!/usr/bin/env python3
"""daily_briefing_builder — 모닝 브리핑 (홈 최상단 카드 단일 채널, PM 2026-07-05).

기존 발행 피드 재조립만 (신규 수집 0 · LLM 0 · 결정론 — RULE 6/7).
전 섹션 = 일어난 사실 + 예정된 사실. "주목/추천/유망" 류 판단 동사 금지.

섹션:
  us_filings   — 밤사이 미국: us_financials_incremental 이 감지·재수집한 10-K/Q 제출 종목
  earnings     — 실적 공시 예상 창(±7일)에 든 종목 (자체계산 어닝 캘린더, KR+US)
  disclosures  — 최근 DART 카탈리스트 공시 (최신 수집일 기준)
  insider      — 최근 7일 내부자 변동 상위 (|증감 주식수| 기준 사실 나열)
  flow         — 최근 거래일 외인·기관 동반 순매수 (추정금액 = 순매수주수×종가, 자체계산 라벨)
  warnings_n   — KRX 시장경보 종목 수

출력: data/daily_briefing.json (채널 중립 구조체 — 후일 발송 렌더러 재사용)
      + data/daily_briefing_history.jsonl append (v1 diff 용)
🚨 RULE 4: 신규 산출 2파일 = cron git add data/ (broad) 로 커버. publish-data allowlist 등재 필수.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT_PATH = os.path.join(_ROOT, "data", "daily_briefing.json")
HIST_PATH = os.path.join(_ROOT, "data", "daily_briefing_history.jsonl")

CATALYST_PATH = os.path.join(_ROOT, "data", "dart_catalyst_alerts.jsonl")
INSIDER_PATH = os.path.join(_ROOT, "data", "insider_trades.json")
WARN_PATH = os.path.join(_ROOT, "data", "market_warnings.json")
FLOW_PATH = os.path.join(_ROOT, "data", "stock_flow_5d.json")
INDEX_PATH = os.path.join(_ROOT, "data", "kr_index_daily.json")
CHART_DIR = os.path.join(_ROOT, "data", "kr_chart_daily")
HOT_PATH = os.path.join(_ROOT, "data", "hot_stock.json")
US_STATE_PATH = os.path.join(_ROOT, "data", "metadata", "us_fin_incremental_state.json")
KR_REPORT_PATH = os.path.join(_ROOT, "data", "stock_report_public.json")
US_REPORT_PATH = os.path.join(_ROOT, "data", "us_stock_report_public.json")


def _load(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _names() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for p in (KR_REPORT_PATH, US_REPORT_PATH):
        doc = _load(p, {})
        arr = doc.get("stocks") or []
        rows = arr if isinstance(arr, list) else list(arr.values())
        for s in rows:
            tk = str(s.get("ticker") or "")
            if tk:
                out[tk] = str(s.get("name_ko") or s.get("name") or tk)
    return out


def _sec_us_filings(names: Dict[str, str]) -> Dict[str, Any]:
    st = _load(US_STATE_PATH, {})
    tks = [str(t) for t in (st.get("last_run_tickers") or [])][:8]
    return {
        "title": "밤사이 미국 공시",
        "items": [{"ticker": t, "name": names.get(t, t), "text": "10-K/Q 재무 공시 제출 → 재무 반영 완료"} for t in tks],
        "note": f"SEC EDGAR 일일 인덱스 감지분 (기준 {st.get('last_processed') or '—'})",
    }


def _sec_earnings(names: Dict[str, str], today: datetime) -> Dict[str, Any]:
    lo = today.strftime("%Y-%m-%d")
    hi = (today + timedelta(days=7)).strftime("%Y-%m-%d")
    items: List[Dict[str, Any]] = []
    for p in (KR_REPORT_PATH, US_REPORT_PATH):
        doc = _load(p, {})
        arr = doc.get("stocks") or []
        rows = arr if isinstance(arr, list) else list(arr.values())
        for s in rows:
            for c in (s.get("calendar") or []):
                d = str(c.get("date") or "")
                if c.get("kind") == "실적" and lo <= d <= hi:
                    items.append({"ticker": str(s.get("ticker") or ""), "name": names.get(str(s.get("ticker") or ""), s.get("name")), "date": d})
                    break
    items.sort(key=lambda x: x["date"])
    return {
        "title": "이번 주 실적 공시 예상",
        "items": items[:10],
        "note": "과거 제출 패턴 자체계산 ±7일 창 · 확정 공시 시 갱신",
    }


def _sec_disclosures() -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    try:
        with open(CATALYST_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    if not rows:
        return {"title": "최근 주요 공시", "items": [], "note": "DART 접수 기준"}
    last_dt = max(str(r.get("rcept_dt") or "") for r in rows)
    day = [r for r in rows if str(r.get("rcept_dt") or "") == last_dt]
    items = []
    seen = set()
    for r in day:
        key = (str(r.get("ticker") or ""), str(r.get("pblntf_label") or r.get("report_nm") or ""))
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "ticker": key[0],
            "name": str(r.get("name") or ""),
            "text": key[1],
            "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + str(r.get("rcept_no") or ""),
        })
        if len(items) >= 8:
            break
    d = f"{last_dt[:4]}.{last_dt[4:6]}.{last_dt[6:]}" if len(last_dt) == 8 else last_dt
    return {"title": "최근 주요 공시", "items": items, "note": f"DART 접수 {d} 기준 · 카탈리스트 유형 필터"}


def _sec_insider(names: Dict[str, str], today: datetime) -> Dict[str, Any]:
    doc = _load(INSIDER_PATH, {})
    lo = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    rows: List[Dict[str, Any]] = []
    for s in (doc.get("stocks") or []):
        for t in (s.get("trades") or []):
            d = str(t.get("date") or "")
            ch = t.get("change")
            if d >= lo and isinstance(ch, (int, float)) and ch:
                rows.append({"ticker": str(s.get("ticker") or ""), "name": str(s.get("name") or ""),
                             "person": str(t.get("person") or ""), "change": ch, "date": d})
    rows.sort(key=lambda x: abs(x["change"]), reverse=True)
    items = []
    for r in rows[:6]:
        side = "매수" if r["change"] > 0 else "매도"
        items.append({"ticker": r["ticker"], "name": r["name"],
                      "text": f"{r['person']} · {abs(r['change']):,.0f}주 {side} ({r['date'][5:]})"})
    return {"title": "최근 7일 내부자 변동", "items": items, "note": "DART 임원·주요주주 보고 사실 · 증감 주식수 기준"}


def _sec_flow(names: Dict[str, str]) -> Dict[str, Any]:
    doc = _load(FLOW_PATH, {})
    flows = doc.get("flows") or {}
    latest = ""
    for _tk, arr in flows.items():
        if isinstance(arr, list) and arr:
            d = str(arr[-1].get("date") or "")
            if d > latest:
                latest = d
    rows: List[Dict[str, Any]] = []
    for tk, arr in flows.items():
        if not (isinstance(arr, list) and arr):
            continue
        r = arr[-1]
        if str(r.get("date") or "") != latest:
            continue
        fn, inn, close = r.get("foreign_net"), r.get("inst_net"), r.get("close")
        if not all(isinstance(v, (int, float)) for v in (fn, inn, close)):
            continue
        if fn > 0 and inn > 0:  # 동반 순매수 (사실 필터)
            rows.append({"ticker": str(tk), "amt": (fn + inn) * close})
    rows.sort(key=lambda x: x["amt"], reverse=True)
    items = [{"ticker": r["ticker"], "name": names.get(r["ticker"], r["ticker"]),
              "text": f"외인·기관 동반 순매수 · 추정 {r['amt'] / 1e8:,.0f}억원"} for r in rows[:5]]
    d = f"{latest[5:]}" if latest else "—"
    return {"title": "외인·기관 동반 순매수", "items": items,
            "note": f"거래일 {d} · 추정금액 = 순매수주수×종가 (자체계산)"}


def _sec_market_recap(names: Dict[str, str]) -> Dict[str, Any]:
    """전 거래일 시장 분해 — 지수·종목/섹터 breadth + 급등락×같은날 공시 병기 (PM 2026-07-11 v2).

    전부 사실: 지수/섹터 등락(금융위 지수시세정보) · 전 종목 등락 개수(금융위 주식시세) ·
    같은 날 DART 공시 병기. 흐름 한 줄 = breadth 개수 조건 템플릿 (LLM 0, 결정론).
    🚨 인과 단어 금지 — "때문/영향/재료" 없이 병렬 사실만. 인과 조립 = 독자.
    병기 우선순위 = 공시 유형 사전 고정 (I 공급·수주 > B 주요사항 > C 발행 > D 지분) —
    지분공시만 있는 날은 1행 상한 (도배 방지, 사전 고정 규칙 = 편집 판단 0).
    """
    idx_doc = _load(INDEX_PATH, {})
    indices = idx_doc.get("indices") or {}
    anchor = str((idx_doc.get("_meta") or {}).get("as_of") or "")
    ks = (indices.get("코스피") or {}).get("c") or []
    kq = (indices.get("코스닥") or {}).get("c") or []
    if not (anchor and ks and kq):
        return {"title": "지난 거래일 시장", "items": []}
    ks_chg, kq_chg = ks[-1][2], kq[-1][2]

    # 코스피200 섹터 — 파생 변형(비중상한/TOP/테마) 제외한 순수 섹터만
    _EXCL = ("비중상한", "TOP", "제외", "ESG", "기후", "고배당", "중소형")
    sect = []
    for n, e in indices.items():
        if not n.startswith("코스피 200 ") or any(x in n for x in _EXCL):
            continue
        c = e.get("c") or []
        if c and c[-1][2] is not None:
            sect.append((n.replace("코스피 200 ", ""), c[-1][2]))
    s_up = sorted([x for x in sect if x[1] > 0], key=lambda x: -x[1])
    s_down = sorted([x for x in sect if x[1] < 0], key=lambda x: x[1])

    # 같은 날 공시 map — 유형 우선순위 (I 공급·수주=0 > B=1 > C=2 > D=3), 낮을수록 먼저
    _PRIO = {"I": 0, "B": 1, "C": 2, "D": 3}
    cat: Dict[str, tuple] = {}
    try:
        with open(CATALYST_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(r.get("rcept_dt") or "") != anchor or not r.get("ticker"):
                    continue
                nm = str(r.get("report_nm") or "").strip()
                for pre in ("[기재정정]", "[첨부정정]", "[첨부추가]"):
                    if nm.startswith(pre):
                        nm = nm[len(pre):]
                # 일상 프로그램 발행(ELS/DLS 일괄신고 등) = 사업 사건 아님 — 병기 제외 (결정론 블랙리스트)
                if "일괄신고" in nm or "파생결합증권" in nm:
                    continue
                pr = _PRIO.get(str(r.get("pblntf_ty") or ""), 4)
                tk = str(r["ticker"])
                if tk not in cat or pr < cat[tk][0]:
                    cat[tk] = (pr, nm[:26])
    except OSError:
        pass

    # 전 종목 등락 breadth + 급등락×공시 교집합 — kr_chart_daily 전 청크 1패스
    n_up = n_down = 0
    movers: List[Dict[str, Any]] = []
    try:
        for i in range(40):
            ch = _load(os.path.join(CHART_DIR, f"chunk_{i:02d}.json"), {})
            for tk, ent in (ch.get("stocks") or {}).items():
                c = ent.get("c") or []
                if len(c) < 2 or str(c[-1][0]) != anchor or not c[-2][4]:
                    continue
                chg = (c[-1][4] / c[-2][4] - 1) * 100
                if chg > 0:
                    n_up += 1
                elif chg < 0:
                    n_down += 1
                if tk in cat and abs(chg) >= 3 and c[-1][4] * c[-1][5] >= 3e9:
                    # 등락 3%↑ + 거래대금 30억↑ (표시 노이즈 제외, display 필터)
                    movers.append({"ticker": tk, "name": ent.get("n") or names.get(tk, tk),
                                   "chg": chg, "prio": cat[tk][0], "nm": cat[tk][1]})
    except OSError:
        pass
    n_tot = n_up + n_down

    # 흐름 한 줄 — 종목 breadth 조건 템플릿 (사실 파생 문장, 인과 0)
    headline = ""
    if n_tot >= 100 and ks_chg is not None:
        if ks_chg > 0 and n_down >= n_tot * 2 / 3:
            headline = f"코스피는 올랐지만 {n_tot:,}개 종목 중 {n_down:,}개는 내렸어요"
        elif ks_chg < 0 and n_down >= n_tot * 2 / 3:
            headline = f"{n_tot:,}개 종목 중 {n_down:,}개가 내린 넓은 하락이었어요"
        elif ks_chg > 0 and n_up >= n_tot * 2 / 3:
            headline = f"{n_tot:,}개 종목 중 {n_up:,}개가 오른 넓은 상승이었어요"
        elif ks_chg < 0 and n_up >= n_tot * 2 / 3:
            headline = f"코스피는 내렸지만 {n_tot:,}개 종목 중 {n_up:,}개는 올랐어요"
        else:
            headline = f"종목 상승 {n_up:,} · 하락 {n_down:,} — 방향이 갈린 날이었어요"

    items: List[Dict[str, Any]] = [
        {"name": "지수", "text": f"코스피 {ks_chg:+.2f}% · 코스닥 {kq_chg:+.2f}%"},
    ]
    if headline:
        items.append({"name": "흐름", "text": headline})
    if s_down:
        items.append({"name": "내린 쪽", "text": " · ".join(f"{n} {v:+.1f}%" for n, v in s_down[:2])})
    if s_up:
        items.append({"name": "올린 쪽", "text": " · ".join(f"{n} {v:+.1f}%" for n, v in s_up[:2])})
    hot_doc = _load(HOT_PATH, {}) or {}
    hot = hot_doc.get("hot") or {}
    if hot.get("ticker") and str((hot_doc.get("_meta") or {}).get("as_of")) == anchor:
        items.append({"ticker": hot["ticker"], "name": hot.get("name", hot["ticker"]),
                      "text": "거래대금 1위"})

    # 병기 rows — 우선순위(유형) → |등락| 정렬. 지분공시(D)뿐인 날 = 1행 상한 (도배 방지)
    movers.sort(key=lambda x: (x["prio"], -abs(x["chg"])))
    picked = movers[:3]
    if picked and all(m["prio"] >= 3 for m in picked):
        picked = picked[:1]
    for m in picked:
        items.append({"ticker": m["ticker"], "name": m["name"],
                      "text": f"{m['chg']:+.1f}% · 같은 날 공시: {m['nm']}", "mover": True})

    d = f"{anchor[4:6]}/{anchor[6:8]}"
    return {"title": "지난 거래일 시장", "items": items,
            "recap": {"date": d, "kospi": ks_chg, "kosdaq": kq_chg, "headline": headline},
            "note": f"기준 {d} · 지수·섹터·등락 = 금융위 공공데이터(전 거래일) · 공시 병기 = 사실, 인과 해석 아님"}


def main() -> int:
    ok = False
    try:
        now = datetime.now(KST)
        names = _names()
        warn_doc = _load(WARN_PATH, {})
        warnings = warn_doc.get("warnings") or {}
        sections = [
            _sec_market_recap(names),
            _sec_us_filings(names),
            _sec_earnings(names, now),
            _sec_disclosures(),
            _sec_insider(names, now),
            _sec_flow(names),
        ]
        sections = [s for s in sections if s.get("items")]  # 빈 섹션 숨김 (정직 — 채우기용 잡음 금지)
        out = {
            "date": now.strftime("%Y-%m-%d"),
            "generated_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            "weekday": ["월", "화", "수", "목", "금", "토", "일"][now.weekday()],
            "warnings_n": len(warnings),
            "sections": sections,
            "disclaimer": "전부 공시·수집 사실과 자체계산 예상 창 · 점수·추천·매매의견 아님",
        }
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        with open(HIST_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"date": out["date"], "n_sections": len(sections),
                                "n_items": sum(len(s["items"]) for s in sections)}, ensure_ascii=False) + "\n")
        print(f"[daily_briefing] logged=True · {out['date']} · 섹션 {len(sections)} · "
              f"항목 {sum(len(s['items']) for s in sections)} -> {os.path.relpath(OUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[daily_briefing] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[daily_briefing] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
