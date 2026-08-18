# -*- coding: utf-8 -*-
"""DecisionJournal — 터미널 판단을 남기는 실험 노트.

🚨 왜 만들었나 (2026-08-09 PM 결정)
  배리티 챗 = **이 터미널 대화 자체**다(API 아님). 종목 질문이 오면 터미널이 사실을 조인해
  종합·판단한다. 그런데 **판단이 남지 않았다.** 데이터는 저장되는데 판단은 저장되지 않아서
  같은 종목을 다시 물어도 "3개월 전에 뭐라고 했고 결과가 어땠나"를 모른다 = 단발성 치매.

  도서관(사실 조인)과 학술지(검증 trail)는 있었고, **실험 노트**가 없었다.
  학술지는 남의 검증이고 실험 노트는 내 판단의 이력이라 둘은 다른 물건이다.

기록 위치 = `private/decisions/verdicts.jsonl` (append-only).
  🚨 메인 repo 는 PUBLIC 이고 오퍼레이터 판단은 공개 금지다(verity-stock SKILL.md).
  그래서 `data/observations/` 관례를 따르되 경로만 public 밖으로 뺀다.
  public `.gitignore` 가 `/private/` 를 막고, 보존은 보조 repo(`.git-private`)가 맡는다.
  `.cache/` 는 부적합 — 비커밋이라 이력이 소실되고 다른 세션에서 못 본다.

채점 가능성이 설계의 전부다. 세 가지가 없으면 나중에 못 잰다:
  · facts_fingerprint + facts_as_of — 판단 시점 입력을 고정. 데이터가 갱신된 뒤 소급
    평가하면 결과가 오염된다.
  · ref_price — 채점 기준가. 🚨 회전 수집 파일(stock_flow_5d)의 close 는 가격이 아니다
    ([[feedback_rotating_collector_not_a_price_source]]). 여기서 거부한다.
  · brain_verdict — 산식 층 baseline 동시 기록. 있어야 "터미널 판단이 산식 단독보다
    나은가"를 **짝지은 비교**로 잰다. 별도 표본 비교보다 통계 효율이 훨씬 높다.

verdict 는 폐쇄 집합이다. 산문만 남으면 채점이 불가능하고 결국 사람이 읽고 판정하게 되는데
그건 N 이 안 쌓이는 방식이다. 🚨 나중에 세분은 가능하지만 되묶는 것은 불가능하다
(과거 기록 소급 재분류 불가) — 집합 변경은 사전등록 대상.

이 레이어는 **기록만** 한다. 채점(forward return)은 사전등록 후 별도 모듈
([[feedback_methodology_pre_registration]]).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from api.config import now_kst  # noqa: E402
from api.utils import market_calendar as _mcal  # noqa: E402


def _fingerprint(*parts: str) -> str:
    """operator_ask 의 구현을 그대로 쓴다(중복 신설 금지).

    🚨 지연 임포트인 이유가 두 가지다.
      ① 순환 차단 — ticker_facts 가 이 모듈을 읽고, operator_ask 는 ticker_facts 를 읽는다.
         모듈 최상단에서 당기면 고리가 닫힌다.
      ② 무게 — 해시 헬퍼 하나 때문에 LLM 클라이언트까지 끌어올 이유가 없다.
    """
    from api.intelligence.operator_ask import _fingerprint as _fp
    return _fp(*parts)

JOURNAL_PATH = os.path.join(_ROOT, "private", "decisions", "verdicts.jsonl")

# PM 확정 2026-08-09. N 이 얕은 구간에서 셀을 세분하면 셀당 표본이 0 으로 수렴한다
# (백테스트 비겹침 N=23~59 기준 3단이면 셀당 10~20건). 강도는 confidence 가 따로 잡는다.
# Brain 등급(75-60-45-25)과 의도적으로 분리 — 백테스트에서 근거가 무너진 임계를 물려받지 않는다.
VERDICTS = ("관심", "보류", "회피")
CONFIDENCES = ("low", "medium", "high")

# 사전등록된 채점 시계 (일). 변경은 사전등록 대상.
HORIZON_DAYS = (5, 20, 60)

CAVEAT = ("터미널 판단 관측. Brain 점수 미반영(brain_input=false). "
          "표본이 얕아 통계 판정 불가 구간이며 채점 산식은 사전등록 후 확정.")

# 🚨 회전 수집 파일은 평가 기준가가 아니다. 여기서 막지 않으면 잘못된 기준가로 채점된다.
FORBIDDEN_PRICE_SOURCES = ("stock_flow_5d",)

# 종가 섹션 data 에서 가격을 찾을 키 (우선순위). 어느 키를 썼는지 레코드에 남긴다.
_PRICE_KEYS = ("close", "종가", "price", "last", "clpr", "현재가")

# 🚨 기준가 후보 = "확정된 세션 종가" 를 들고 있는 섹션 **전부** (2026-08-17 신설).
#
#   종전에는 `종가` 섹션(kr_close_latest) 하나만 봤는데 두 가지가 동시에 깨져 있었다.
#
#   ① 룩어헤드 — kr_close_latest 는 15:30 마감 직후(15:10~19:57)에 도는데 금융위 시세가
#      T+1 이라 **항상 전 거래일**이다. 8거래일 연속 실측(8/5~8/14)에서 예외 0건이고,
#      평일·휴장 무관하게 그렇다. 마감 후에 내리는 판단은 그날 등락률을 이미 알고 내리는데
#      채점 기준가는 그 전날이라, 상승일에 판단할수록 성적이 좋아지는 **한 방향 편향**이
#      생긴다. 2026-08-17 한화오션 판단이 실례 — 8/14 +5.62% 를 알고 판단했는데 기준가는
#      8/13 종가였다.
#
#   ② 미국 종목 기준가 부재 — 라벨이 `종가` 로 시작하지 않아 저널 15건 중 11건(73%)이
#      ref_price=None 이었다. 채점 자체가 불가능한 레코드를 계속 쌓고 있었다.
#
#   고침 = 후보를 전부 열거하고 **세션일이 가장 최근인 것**을 고른다. 한 소스만 보고
#   "그게 최신" 이라고 단정하지 않는다 — 분모를 먼저 세는 규율 그대로다.
#
#   🚨 장중 스냅샷은 후보에서 제외한다. 확정 종가가 아니라서 나중에 재현이 안 된다.
#   (라벨 접두어, 세션일 해석 방식)
_CLOSE_CANDIDATES = (
    ("시총", "as_of_date"),            # krx_mktcap · bas_dd = 최종 거래일 (익일 오전 수집)
    ("종가", "as_of_date"),            # kr_close_latest · T+1
    ("일봉", "as_of_date"),            # 금융위 일봉 · T+1
    ("미국 시세·일봉", "as_of_us_ts"),  # 야후 chart · as_of = regularMarketTime(KST 표기)
    ("미국 시세 (KIS", "label_closed"),  # 라벨이 장 개폐를 자기 신고한다("🚨 장 마감")
    ("실시간 시세", "kr_session"),      # KIS KR · 캘린더로 마감 판정된 때만 인정
)

# KR 정규장 마감 15:30. 종가 확정·전송 지연을 보고 여유를 둔다.
_KR_CLOSE_SAFE = dt_time(15, 40)
# 미국 정규장 마감 16:00 ET.
_US_CLOSE_ET = dt_time(16, 0)

# as_of 를 남길 섹션 (label 접두어 → 레코드 키)
_ASOF_LABELS = (
    ("종가", "close"),
    ("실시간", "realtime"),
    ("DART 공시", "dart"),
    ("일봉", "daily_bars"),
)


class JournalError(RuntimeError):
    """기록 실패. 🚨 조용히 넘어가지 않는다 — 안 남은 판단은 없는 판단이다."""


def _sections(facts: Dict[str, Any]) -> List[Dict[str, Any]]:
    secs = facts.get("sections")
    return secs if isinstance(secs, list) else []


def _find_section(facts: Dict[str, Any], prefix: str) -> Optional[Dict[str, Any]]:
    for s in _sections(facts):
        if str(s.get("label", "")).startswith(prefix):
            return s
    return None


def facts_fingerprint(facts: Dict[str, Any]) -> str:
    """판단 시점 입력의 지문.

    (label, source, as_of, data 해시) 조합을 쓴다. 값이 바뀌면 지문이 바뀌어야
    "같은 입력이었나"를 나중에 물을 수 있다.
    """
    parts = [str(facts.get("ticker") or "")]
    for s in sorted(_sections(facts), key=lambda x: str(x.get("label", ""))):
        try:
            blob = json.dumps(s.get("data"), ensure_ascii=False, sort_keys=True, default=str)
        except (TypeError, ValueError):
            blob = str(s.get("data"))
        parts.append("|".join([
            str(s.get("label", "")), str(s.get("source", "")), str(s.get("as_of", "")),
            _fingerprint(blob),
        ]))
    return _fingerprint(*parts)


def extract_as_of(facts: Dict[str, Any]) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {}
    for prefix, key in _ASOF_LABELS:
        sec = _find_section(facts, prefix)
        out[key] = (sec or {}).get("as_of") or None
    return out


def _as_date(v: Any) -> Optional[date]:
    """'20260814' / '2026-08-14' / ISO 타임스탬프 → date. 못 읽으면 None."""
    s = str(v or "").strip()
    if not s:
        return None
    if len(s) == 8 and s.isdigit():
        try:
            return datetime.strptime(s, "%Y%m%d").date()
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


def _us_session_date_from_kst_ts(v: Any) -> Optional[date]:
    """야후 regularMarketTime(KST 표기) → 그 값이 속한 **미국 세션일**.

    🚨 라벨이 아니라 타임스탬프를 읽는다. KST 오전에 조회한 미국주식은 미국장 마감
    후라서 직전 거래일 종가인데, 섹션 제목만 보면 "실시간" 으로 읽힌다(2026-08-15 사고).
    """
    s = str(v or "").strip()
    if not s:
        return None
    try:
        dtv = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dtv.tzinfo is None:
        return None
    utc = dtv.astimezone(timezone.utc)
    off = 4 if _mcal.is_us_dst(utc.date()) else 5
    return (utc - timedelta(hours=off)).date()


def _session_date(mode: str, sec: Dict[str, Any], now: datetime) -> Optional[date]:
    """이 섹션의 가격이 속한 **확정 세션일**. 확정 못 하면 None (= 후보 탈락)."""
    if mode == "as_of_date":
        return _as_date(sec.get("as_of"))

    if mode == "as_of_us_ts":
        return _us_session_date_from_kst_ts(sec.get("as_of"))

    if mode == "label_closed":
        # 조인이 라벨에 장 개폐를 자기 신고한다. 신고가 없으면 장중일 수 있어 쓰지 않는다.
        if "장 마감" not in str(sec.get("label") or ""):
            return None
        off = 4 if _mcal.is_us_dst(now.date()) else 5
        et = now.astimezone(timezone.utc) - timedelta(hours=off)
        if _mcal.is_trading_day(et.date(), "US") and et.time() >= _US_CLOSE_ET:
            return et.date()
        return _mcal.previous_trading_day(et.date(), "US")

    if mode == "kr_session":
        # 🚨 장중이면 확정 종가가 아니다 — 후보에서 뺀다.
        today = now.date()
        if _mcal.is_trading_day(today, "KR"):
            return today if now.time() >= _KR_CLOSE_SAFE else None
        return _mcal.previous_trading_day(today, "KR")

    return None


def extract_ref_price(
    facts: Dict[str, Any], now: Optional[datetime] = None
) -> Tuple[Optional[float], Optional[str], Optional[str], Optional[str]]:
    """(가격, 출처 파일, 사용한 키, 세션일 ISO). 못 찾으면 (None, 출처|None, None, None).

    🚨 후보를 전부 열거한 뒤 **세션일이 가장 최근인 것**을 고른다. 단일 소스를 최신이라
    단정하던 것이 룩어헤드의 원인이었다(_CLOSE_CANDIDATES 주석 참조).

    🚨 회전 수집 파일 출처는 거부한다. 값을 억지로 채우는 것보다 없다고 남기는 편이
    낫다 — 없는 정밀도를 있는 척하면 채점이 조용히 틀린다.
    """
    now = now or now_kst()
    best: Optional[Tuple[date, float, Optional[str], str, Optional[date]]] = None
    fallback_source: Optional[str] = None

    for prefix, mode in _CLOSE_CANDIDATES:
        sec = _find_section(facts, prefix)
        if not sec:
            continue
        source = str(sec.get("source") or "")
        if any(bad in source for bad in FORBIDDEN_PRICE_SOURCES):
            raise JournalError(
                f"평가 기준가로 쓸 수 없는 출처다: {source}. "
                "회전 수집 파일의 close 는 가격이 아니다 — kr_close_latest 를 쓴다."
            )
        if fallback_source is None:
            fallback_source = source or None
        data = sec.get("data")
        if not isinstance(data, dict):
            continue
        price: Optional[float] = None
        key: Optional[str] = None
        for k in _PRICE_KEYS:
            v = data.get(k)
            if isinstance(v, (int, float)) and v > 0:
                price, key = float(v), k
                break
        if price is None or key is None:
            continue
        sd = _session_date(mode, sec, now)
        if sd is None:
            # 세션일을 확정 못 한 후보는 쓰지 않는다. 언제 가격인지 모르면 채점이 안 된다.
            continue
        if best is None or sd > best[0]:
            best = (sd, price, source or None, key, sd)

    if best is None:
        return None, fallback_source, None, None
    return best[1], best[2], best[3], best[0].isoformat()


def _validate(verdict: str, confidence: str) -> None:
    if verdict not in VERDICTS:
        raise JournalError(f"verdict 는 폐쇄 집합이다 {VERDICTS} — 받은 값: {verdict!r}")
    if confidence not in CONFIDENCES:
        raise JournalError(f"confidence 는 {CONFIDENCES} 중 하나여야 한다 — 받은 값: {confidence!r}")


def build_record(
    facts: Dict[str, Any],
    verdict: str,
    confidence: str,
    basis_axes: List[str],
    reasoning_brief: str,
    question: str = "",
    brain_verdict: Optional[str] = None,
) -> Dict[str, Any]:
    _validate(verdict, confidence)
    tk = facts.get("ticker")
    if not tk:
        raise JournalError("ticker 없는 판단은 기록하지 않는다 — 채점 대상을 특정할 수 없다.")

    price, price_source, price_key, price_asof = extract_ref_price(facts)
    missing = facts.get("missing")
    return {
        # 관측 규율 4종 — data/observations/*.jsonl 과 동일 계보
        "ts_kst": now_kst().isoformat(timespec="seconds"),
        "shadow": True,
        "brain_input": False,
        "caveat": CAVEAT,

        "ticker": tk,
        "name": facts.get("name") or "",
        "market": "KR" if str(tk).isdigit() and len(str(tk)) == 6 else "US",
        "question": question,

        "verdict": verdict,
        "confidence": confidence,
        "basis_axes": list(basis_axes or []),
        "reasoning_brief": reasoning_brief,

        "facts_fingerprint": facts_fingerprint(facts),
        "facts_as_of": extract_as_of(facts),
        "missing_axes": list(missing) if isinstance(missing, list) else [],

        "ref_price": price,
        "ref_price_source": price_source,
        "ref_price_key": price_key,
        # 🚨 기준가가 **어느 세션의 종가인지**. 이게 없으면 채점기가 시작점을 못 정한다.
        #   판단 시각(ts_kst)과 다를 수 있고, 달라야 정상이다(마감 후 판단 = 그날 종가).
        "ref_price_asof": price_asof,

        "brain_verdict": brain_verdict,
        "horizon_days": list(HORIZON_DAYS),
        "scored": None,
    }


def record(
    facts: Dict[str, Any],
    verdict: str,
    confidence: str,
    basis_axes: List[str],
    reasoning_brief: str,
    question: str = "",
    brain_verdict: Optional[str] = None,
    path: Optional[str] = None,
) -> Dict[str, Any]:
    """판단 1건을 append 하고 기록된 레코드를 돌려준다.

    🚨 실패는 예외다. 조용히 넘어가면 "기록했다고 믿는 안 된 판단" 이 생기고,
    그건 없는 것보다 나쁘다(#46 계열).
    """
    rec = build_record(facts, verdict, confidence, basis_axes,
                       reasoning_brief, question, brain_verdict)
    target = path or JOURNAL_PATH
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as e:
        raise JournalError(f"판단 기록 실패: {target} — {type(e).__name__}: {e}") from e
    return rec


def read_recent(ticker: str, limit: int = 5, path: Optional[str] = None) -> List[Dict[str, Any]]:
    """같은 종목의 최근 판단 (최신순). 파일이 없으면 빈 목록.

    Phase 2(되읽기)의 입력이다 — 저장만 하고 안 읽으면 여전히 치매다.
    """
    target = path or JOURNAL_PATH
    if not os.path.exists(target):
        return []
    tk = str(ticker)
    hits: List[Dict[str, Any]] = []
    with open(target, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # 손상 행 1개가 전체 조회를 막지 않는다
            if str(rec.get("ticker")) == tk:
                hits.append(rec)
    hits.sort(key=lambda r: str(r.get("ts_kst") or ""), reverse=True)
    return hits[:limit]


RECOMMENDATIONS_PATH = os.path.join(_ROOT, "data", "recommendations.json")

# 🚨 재판단 간격 = 사전등록 시계의 중간값(20 거래일).
#   매일 찍으면 forward 창이 겹쳐 N 이 안 는다 — 백테스트가 이미 겪은 함정이다
#   (naive N=75 → 비겹침 N=23~59). 20거래일 간격이면 5/20 시계가 겹치지 않는다.
#   🚨 이 값은 사전등록(docs/decision_journal_scoring_prereg_20260809.md)의 시계에서
#   따온 것이지 새로 고른 숫자가 아니다. 시계를 바꾸면 여기도 사전등록 대상이다.
REJUDGE_TRADING_DAYS = 20
_TRADING_DAYS_PER_WEEK = 5


def _due_after(last_ts: str) -> bool:
    """마지막 판단 이후 REJUDGE_TRADING_DAYS 거래일이 지났나 (달력일 근사)."""
    if not last_ts:
        return True
    try:
        last = datetime.fromisoformat(last_ts)
    except ValueError:
        return True
    # 거래일 → 달력일 근사 (주 5거래일). 정확한 거래일 달력은 채점기 몫이고,
    # 여기는 "너무 자주 찍지 않는다" 는 큐잉 목적이라 근사로 충분하다.
    span = REJUDGE_TRADING_DAYS / _TRADING_DAYS_PER_WEEK * 7
    return (now_kst() - last).days >= span


def due_candidates(path: Optional[str] = None,
                   rec_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """오늘 판단이 필요한 funnel 후보 목록.

    🚨 왜 필요한가 (2026-08-14): 지금 실험 노트는 **PM 이 물어볼 때만** 기록된다.
    3일에 1건이 쌓였고, 그보다 나쁜 건 **선택 편향**이다 — 물어보는 종목은 이미
    뭔가 있는 종목이라 표본이 한쪽으로 쏠린다. funnel 후보 전수를 대상으로 하면
    편향이 사라진다.

    🚨 매일 전수를 찍지는 않는다. 후보 집합의 연속일 겹침률이 82~100%(실측 2026-08-14)라
    매일 기록하면 같은 종목이 20번 들어가고 forward 창이 통째로 겹친다. 그래서
    **신규이거나 마지막 판단이 20거래일 이상 지난 종목만** 큐에 올린다.

    🚨 판단 자체는 코드가 하지 않는다. 이 함수는 "누가 due 인가" 만 계산하고,
    verdict 는 터미널이 사실 조인을 보고 낸다. 스크립트가 판단을 지어내면
    그건 N 이 아니라 잡음이다.
    """
    rec_file = rec_path or RECOMMENDATIONS_PATH
    try:
        with open(rec_file, encoding="utf-8") as f:
            rows = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(rows, dict):
        rows = rows.get("recommendations") or rows.get("stocks") or []

    out: List[Dict[str, Any]] = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        tk = str(r.get("ticker") or "").strip()
        if not tk:
            continue
        prev = read_recent(tk, limit=1, path=path)
        last_ts = str(prev[0].get("ts_kst") or "") if prev else ""
        if not _due_after(last_ts):
            continue
        out.append({
            "ticker": tk,
            "name": r.get("name") or "",
            "market": r.get("market") or "",
            "last_ts": last_ts[:16] or None,
            "last_verdict": (prev[0].get("verdict") if prev else None),
        })
    out.sort(key=lambda x: (x["last_ts"] or "", x["ticker"]))
    return out


def _self_test() -> int:
    """임시 경로에 기록·재읽기 왕복. 실 저장소를 건드리지 않는다."""
    import tempfile

    facts = {
        "ticker": "005930", "name": "삼성전자",
        "missing": ["컨센서스 (analyst_reports.json)"],
        "sections": [
            {"label": "종가 (T+1 · 실시간 아님)", "source": "kr_close_latest.json",
             "as_of": "2026-08-08", "data": {"close": 71500}},
            {"label": "DART 공시 (직조회 · 30일)", "source": "opendart:list.json",
             "as_of": "2026-08-09", "data": {"건수": 0}},
        ],
    }
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "verdicts.jsonl")
        rec = record(facts, "관심", "medium", ["fscore8"], "테스트 판단", "테스트 질문",
                     brain_verdict="B", path=p)
        back = read_recent("005930", path=p)
        assert len(back) == 1, back
        assert back[0]["verdict"] == "관심"
        assert back[0]["ref_price"] == 71500
        assert back[0]["ref_price_source"] == "kr_close_latest.json"
        assert back[0]["facts_as_of"]["close"] == "2026-08-08"
        assert back[0]["facts_fingerprint"] == rec["facts_fingerprint"]
        print("[decision_journal] self-test OK")
        print(json.dumps(rec, ensure_ascii=False, indent=2)[:600])
    return 0


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="판단 실험 노트 (오퍼레이터 전용)")
    ap.add_argument("--self-test", action="store_true", help="임시 경로 왕복 검증")
    ap.add_argument("--recent", metavar="TICKER", help="해당 종목 최근 판단 조회")
    ap.add_argument("--due", action="store_true",
                    help="오늘 판단이 필요한 funnel 후보 (신규 또는 20거래일 경과)")
    a = ap.parse_args()

    if a.self_test:
        sys.exit(_self_test())
    if a.due:
        rows = due_candidates()
        if not rows:
            print("판단 due 종목 없음 — 후보 전부 20거래일 이내에 기록됨")
            sys.exit(0)
        print(f"# 판단 due {len(rows)}종목 (신규 또는 {REJUDGE_TRADING_DAYS}거래일 경과)")
        print("#   판단은 터미널이 낸다. 종목별로 사실 조인을 보고 record() 로 남길 것.\n")
        for r in rows:
            prev = f"직전 {r['last_ts']} {r['last_verdict']}" if r["last_ts"] else "신규"
            print(f"  {r['ticker']:>8}  {str(r['name'])[:18]:<18} {str(r['market'])[:6]:<6} {prev}")
        sys.exit(0)
    if a.recent:
        rows = read_recent(a.recent, limit=10)
        if not rows:
            print(f"{a.recent} — 기록된 판단 없음")
            sys.exit(0)
        for r in rows:
            print(f"{r['ts_kst']}  {r['verdict']:4s} ({r['confidence']:6s})  "
                  f"기준가 {r.get('ref_price')}  근거 {','.join(r.get('basis_axes') or [])}")
            print(f"    {r.get('reasoning_brief', '')}")
        sys.exit(0)
    ap.print_help()
