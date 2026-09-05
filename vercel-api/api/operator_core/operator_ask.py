# -*- coding: utf-8 -*-
"""OperatorAsk — 종목 질문에 필요한 자체 사실·신선도 번들을 만드는 온디맨드 레이어.

🚨 오퍼레이터 전용 (PM 2026-08-03 지시)
  "종목 상담·분석·추천이 들어가니 공개용은 절대 안 됨. 지금처럼 터미널에서 대화할 때 바로바로
  나오게 만드는 게 가장 퀄리티와 반응성이 좋다. 알파네스트 공개·비공개 전부에서 수집·축적된
  데이터와 바로바로 연동되어야 해."
  → 산출물을 공개 발행 경로(data/ 발행 목록·Blob·framer-components)에 **절대** 싣지 말 것.
    유사투자자문 회피 = 공개 노출 0 이 전제. 본인 전용이라 판단·전망 포함 가능.

2026-09-05 PM 결정:
  · 구형 Perplexity → Gemini → Claude 직렬 합성과 배치 사전판단은 종료한다.
  · 이 모듈은 사실 조인, 소스 커버리지, 신선도, 외부 확인이 필요한 결손 질문만 반환한다.
  · 최종 해석은 Codex 세션이 원문 직조회와 근거 대장을 거쳐 수행한다.
  · 서버 런타임에서 생성형 모델을 호출하지 않는다.

grounding = ticker_facts.collect() — 우리가 가진 전 발행물 + 로컬 + private bucket.
  🚨 2026-06-03 챗 환각 사고(삼성전자 "65,000원 지지선", 실제 ~365,000원) 재발 방지:
  자체 사실을 먼저 붙이고, **"없는 것" 목록을 프롬프트에 명시**해 지어내지 못하게 한다.

사용:
  python api/intelligence/operator_ask.py 제이엠티 --facts-only
  python api/intelligence/operator_ask.py 제이엠티 --questions --q "오늘 급등 이유"
"""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# 소비자 2곳에서 모두 import 되어야 한다 (SSOT = api/intelligence/, 복제 = vercel-api/api/_operator/).
#   · 패키지 컨텍스트(api.intelligence / api._operator) → 상대 import
#   · 스크립트 직접 실행(python api/intelligence/operator_ask.py) → sys.path[0]=이 디렉토리
try:
    from . import ticker_facts  # type: ignore[attr-defined]
except ImportError:  # noqa: BLE001
    import ticker_facts  # type: ignore[no-redef]

_KST = timezone(timedelta(hours=9))


def _now() -> datetime:
    return datetime.now(_KST)


def _fingerprint(*parts: str) -> str:
    """판단 원장과의 호환용 안정 지문. 외부 모델 캐시에는 더 이상 쓰지 않는다."""
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]


# ── ① Perplexity — 결측(gap) 위임 리서치 ─────────────────────────────────────
# PM 2026-08-03: "네가 정보 모을 때 퍼플렉시티 등에게 부가적 요소를 맡길 수 있는거지."
#
# 🚨 옛 구현은 한 번에 뭉뚱그려 물었다 —
#     f"{name}({ticker}) 관련 최근 뉴스·공시·주가 급변 사유. 질문: {question}"
#    ① 우리가 이미 가진 것(재무·밸류에이션)까지 질문에 섞여 검색이 흐려지고
#    ② 날짜가 고정되지 않고 ③ 국내 소스 유도가 없어 동명 영문 법인·무관 시황이 잡혔다.
#    2026-08-03 094970 +12% 사유 조회가 이 방식으로 실패("단정할 수 없습니다").
#    → **우리 데이터에 구멍이 난 축만** 골라 축별 질문으로 분리 위임한다.

_RULES_COMMON = (
    "규칙: ① 확인된 사실과 출처(URL)만. 추정·전망·투자의견 금지. "
    "② 확인 안 되면 반드시 '확인 안 됨'이라고 답하고 지어내지 마라. "
)
_RULES_KR = _RULES_COMMON + (
    "③ 한국거래소 KIND·DART·네이버금융·국내 경제지 등 **국내 1차 소스** 우선. "
    "④ 동명 해외 법인(영문 사명)과 혼동 금지 — 한국 상장사만. ⑤ 한국어."
)
_RULES_US = _RULES_COMMON + (
    "③ SEC EDGAR·발행사(운용사) 공식 자료·미국 경제지 등 **미국 1차 소스** 우선. "
    "④ 동명 한국 상장사와 혼동 금지 — 미국 상장 종목만. ⑤ 한국어로 답하되 "
    "회사·상품명과 인용 문구는 원문 표기를 병기."
)
_PPLX_RULES = _RULES_KR      # 하위호환 (KR 기본)


def _market_of(facts: Dict[str, Any], ticker: str) -> str:
    """KR / US 판별.

    🚨 2026-08-08 수리: 이전에는 시장을 보지 않고 전 종목을 "한국 상장사" 로 단정했다.
       미국 종목(TSLL 등)에 대해 KIND·DART 를 1차 소스로 지정하고, 규칙 ④가
       "동명 해외 법인 혼동 금지 — 한국 상장사만" 이라 **정답 방향을 적극 차단**했다.
       위임 질문은 우리 데이터가 빈 종목에 쓰는 도구인데, 그 종목이 대개 미국 종목이다.
    """
    mkt = str(((_sec_data(facts, "리포트") or {}) or {}).get("market") or "").upper()
    if "KOSPI" in mkt or "KOSDAQ" in mkt or "KRX" in mkt:
        return "KR"
    if "NYSE" in mkt or "NASDAQ" in mkt or "AMEX" in mkt or "ARCA" in mkt:
        return "US"
    t = str(ticker or "")
    return "KR" if (len(t) == 6 and t.isdigit()) else "US"


def _sec_data(facts: Dict[str, Any], *label_prefixes: str) -> Optional[Any]:
    for sec in facts.get("sections") or []:
        lab = str(sec.get("label") or "")
        if any(lab.startswith(p) for p in label_prefixes):
            return sec.get("data")
    return None


def _move_pct(facts: Dict[str, Any]) -> Optional[float]:
    """오늘 등락률(실시간 우선, 없으면 직전 확정 종가)."""
    for lab in ("실시간 시세", "종가"):
        d = _sec_data(facts, lab)
        if isinstance(d, dict) and d.get("등락률"):
            try:
                return float(str(d["등락률"]).replace("%", "").replace("+", ""))
            except (TypeError, ValueError):
                pass
    return None


def research_gaps(facts: Dict[str, Any], question: str = "") -> List[Dict[str, str]]:
    """자체 데이터의 구멍만 골라 외부 위임 질문으로 만든다.

    우리가 이미 아는 것은 묻지 않는다 — 검색이 흐려지고 비용만 든다.
    반환 = [{key, label, query, recency, tier}] (우선순위 순, 최대 3).
    """
    name = facts.get("name") or ""
    tk = facts.get("ticker") or ""
    today = _now().strftime("%Y년 %m월 %d일")
    gaps: List[Dict[str, str]] = []

    rep = _sec_data(facts, "리포트") or {}
    mkt = str(rep.get("market") or "")
    market = _market_of(facts, tk)
    if market == "KR":
        seg = "코스닥" if "KOSDAQ" in mkt else "코스피" if "KOSPI" in mkt else "한국"
        who = f"{seg} 상장사 {name}(종목코드 {tk})"
        rules = _RULES_KR
    else:
        who = f"미국 상장 종목 {name}(티커 {tk})"
        rules = _RULES_US

    # ① 급변 사유 미상 — 최우선. 우리 데이터로는 "얼마나" 만 알고 "왜" 를 모른다.
    #    단, 공시 축은 DART 직조회(ticker_facts 상설 섹션)가 이미 단정한다 — 외부에 되묻지 않는다.
    mv = _move_pct(facts)
    if mv is not None and abs(mv) >= 5.0:
        direction = "급등" if mv > 0 else "급락"
        dart_direct = _sec_data(facts, "DART 공시")
        if isinstance(dart_direct, dict) and dart_direct.get("건수") == 0:
            dart_note = ("참고: DART 직조회로 최근 30일 공시 0건은 이미 확정했다 — 공시 재확인은 "
                         "불필요하고, 뉴스·테마 동반·특징주 코너 쪽만 확인하라.\n")
        elif isinstance(dart_direct, dict) and dart_direct.get("공시"):
            titles = " / ".join(f"{r.get('date')} {r.get('title')}" for r in dart_direct["공시"][:5])
            dart_note = (f"참고: DART 직조회로 확인된 최근 공시 = {titles}. "
                         f"이 공시와 오늘 {direction}의 연관 보도가 있는지 확인하라.\n")
        else:
            dart_note = ""
        gaps.append({
            "key": "catalyst",
            "label": f"{direction} 사유 ({mv:+.1f}%)",
            "recency": "day",
            "tier": "pro",
            "query": (
                f"{who} 주가가 {today} 장중 {mv:+.1f}% {direction}했다. 그 사유는 무엇인가?\n"
                f"{dart_note}"
                f"확인할 것: (1) 관련 뉴스·보도 (2) 이 종목이 속한 테마·업종의 동반 {direction} 여부 "
                f"(3) 특징주·급등주 코너 언급"
                + ("" if dart_note else
                   f" (4) {today} 또는 직전 영업일 공시(KIND·DART — 단일판매·공급계약, "
                   f"최대주주 변경, 무상증자, 자기주식 취득, 조회공시 요구 등)")
                + f".\n{rules}"
            ),
        })

    # ② 뉴스 공백 — 우리 sentiment 수집이 헤드라인 0건이면 외부에서 채운다.
    social = rep.get("social_sentiment") or {}
    senti = _sec_data(facts, "sentiment") or {}
    hc = (senti.get("headline_count") if isinstance(senti, dict) else None)
    if hc in (0, None) and not social.get("news", {}).get("positive"):
        gaps.append({
            "key": "news",
            "label": "최근 뉴스·이슈",
            "recency": "month",
            "tier": "base",
            "query": (
                f"{who}에 대해 최근 1개월 내 보도된 뉴스·이슈를 시간순으로 정리해줘.\n"
                f"수주·계약, 실적, 신규 사업, 증설·투자, 지분 변동, 소송·제재, "
                f"거래소 조치(투자경고·불성실공시) 중심.\n{rules}"
            ),
        })

    # ③ 실적 임박 — 우리 calendar 는 제출 패턴 자체추정이라 확정 일정을 모른다.
    for ev in (rep.get("calendar") or []):
        if str(ev.get("kind")) != "실적":
            continue
        try:
            d = datetime.strptime(str(ev.get("date")), "%Y-%m-%d").replace(tzinfo=_KST)
        except (TypeError, ValueError):
            break
        if 0 <= (d - _now()).days <= 14:
            gaps.append({
                "key": "earnings",
                "label": "실적 발표 일정",
                "recency": "month",
                "tier": "base",
                "query": (
                    f"{who}의 다음 실적 발표(반기·분기보고서 제출 또는 잠정실적 공시) "
                    f"확정 일정이 공표됐는가? 직전 분기 실적 수치와 함께 알려줘.\n{rules}"
                ),
            })
        break

    # ④ 컨센서스 부재 — 우리 consensus_available=false 는 "없다" 가 아니라 "우리가 못 모았다".
    #    다만 마이크로캡은 실제로 커버리지가 없는 경우가 대부분이라 우선순위는 뒤로 둔다.
    #    증권사 리포트 수집(네이버, 2026-08-03 배선)이 이 종목을 잡았다면 로컬로 확인 끝 — 위임 생략.
    cons = rep.get("consensus") or {}
    if _sec_data(facts, "증권사 리포트"):
        cons = {"target_price": "로컬 확인", "opinion": "로컬 확인"}  # 위임 생략 표식
    if not cons.get("target_price") and not cons.get("opinion"):
        gaps.append({
            "key": "consensus",
            "label": "증권사 커버리지",
            "recency": "year",
            "tier": "base",
            "query": (
                f"{who}를 커버하는 증권사 리서치 리포트가 최근 1년 내 존재하는가?\n"
                f"있으면 증권사명·발간일·투자의견·목표주가를, 없으면 "
                f"'커버리지 없음'이라고 명확히 답해줘.\n{rules}"
            ),
        })

    # ⑤ 어떤 구멍도 안 잡혔는데 PM 질문이 외부 사실을 요구하면 그것만 위임
    if not gaps and question.strip():
        gaps.append({"key": "freeform", "label": "PM 질문", "recency": "week", "tier": "base",
                     "query": f"{who}에 대한 질문: {question.strip()}\n{rules}"})

    return gaps[:3]


# ── 오케스트레이션 ───────────────────────────────────────────────────────────
def ask(query: str, question: str = "", facts_only: bool = False,
        no_cache: bool = False) -> Dict[str, Any]:
    """생성형 호출 없이 사실 번들과 외부 확인 질문만 반환한다.

    facts_only/no_cache 인자는 기존 CLI·Vercel 호출 호환을 위해 유지한다.
    """
    facts = ticker_facts.collect(query)
    facts_text = ticker_facts.render_text(facts)
    out: Dict[str, Any] = {
        "facts": facts,
        "facts_text": facts_text,
        "_meta": {
            "contract": "operator-facts-v2",
            "llm_calls": 0,
            "final_reasoner": "codex_session",
            "legacy_chain_retired": True,
        },
    }
    if not facts.get("ticker"):
        return out
    q = question.strip()
    if q and not facts_only:
        out["question"] = q
        out["research_questions"] = research_gaps(facts, q)
    return out


def render(out: Dict[str, Any]) -> str:
    L = [out["facts_text"], ""]
    gaps = out.get("research_questions") or []
    if gaps:
        L += ["=" * 70, "# Codex 원문 확인 대기 항목", "=" * 70]
        for i, gap in enumerate(gaps, 1):
            L += [f"[{i}] {gap.get('label', gap.get('key', '확인'))}", gap.get("query", "")]
    L += ["", "[operator-facts-v2 · 서버 LLM 호출 0 · 최종 해석=Codex 세션]"]
    return "\n".join(L)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="종목 사실·신선도 번들 (오퍼레이터 전용)")
    ap.add_argument("query", help="종목명 또는 6자리 코드")
    ap.add_argument("--q", default="", help="질문")
    ap.add_argument("--facts-only", action="store_true", help="사실 조인만")
    ap.add_argument("--questions", action="store_true",
                    help="결측 축 위임 질문만 출력 (호출 0 · 비용 0). 웹 퍼플렉시티 Pro 복붙용")
    ap.add_argument("--no-cache", action="store_true", help="과거 CLI 호환용; 현재는 효과 없음")
    a = ap.parse_args()

    if a.questions:
        # 외부 도구 또는 Codex가 원문 확인에 사용할 중립 질문만 만든다.
        f = ticker_facts.collect(a.query)
        if not f.get("ticker"):
            print(ticker_facts.render_text(f))
            sys.exit(1)
        gs = research_gaps(f, a.q)
        print(f"# {f.get('name')} ({f['ticker']}) — 외부 위임 질문 {len(gs)}건 "
              f"(호출 0 · 웹 퍼플렉시티 복붙용)\n")
        if not gs:
            print("위임할 결측 축 없음 — 자체 데이터로 충분하다.")
        for i, g in enumerate(gs, 1):
            print(f"{'─' * 70}\n[{i}] {g['label']}  (최근성 {g['recency']})\n{'─' * 70}\n{g['query']}\n")
        sys.exit(0)

    print(render(ask(a.query, a.q, a.facts_only, a.no_cache)))
