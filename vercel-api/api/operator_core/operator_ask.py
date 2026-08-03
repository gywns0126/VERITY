# -*- coding: utf-8 -*-
"""OperatorAsk — 종목 질문 하나에 **자체 사실 조인 + 3종 LLM 종합**으로 답하는 온디맨드 레이어.

🚨 오퍼레이터 전용 (PM 2026-08-03 지시)
  "종목 상담·분석·추천이 들어가니 공개용은 절대 안 됨. 지금처럼 터미널에서 대화할 때 바로바로
  나오게 만드는 게 가장 퀄리티와 반응성이 좋다. 알파네스트 공개·비공개 전부에서 수집·축적된
  데이터와 바로바로 연동되어야 해."
  → 산출물을 공개 발행 경로(data/ 발행 목록·Blob·framer-components)에 **절대** 싣지 말 것.
    유사투자자문 회피 = 공개 노출 0 이 전제. 본인 전용이라 판단·전망 포함 가능.

재능 배치 (PM 확정, 월 $50 제약)
  · Perplexity  = 신선한 외부 사실 (오늘 급등 이유처럼 우리 T+1 데이터에 없는 것). 인용 필수.
  · Gemini      = 구조화 (사실 덩어리 → 축 정리)
  · Claude opus-5 = 종합 (최종 판단). 적응형 thinking 기본 on, effort 로 깊이 조절.

grounding = ticker_facts.collect() — 우리가 가진 전 발행물 + 로컬 + private bucket.
  🚨 2026-06-03 챗 환각 사고(삼성전자 "65,000원 지지선", 실제 ~365,000원) 재발 방지:
  자체 사실을 먼저 붙이고, **"없는 것" 목록을 프롬프트에 명시**해 지어내지 못하게 한다.

비용 가드
  · 질문당 대략 $0.06 (opus-5 종합 ~$0.05 + Perplexity ~$0.005 + Gemini ~$0.002)
  · 일 호출 상한 ASK_DAILY_LIMIT(기본 15) → 월 ~$27. 초과 시 사실 조인만 수행.
  · 같은 질문+같은 기준일 = fingerprint 캐시로 재호출 스킵.

사용:
  python api/intelligence/operator_ask.py 제이엠티 --q "오늘 급등 이유와 향후 추이"
  python api/intelligence/operator_ask.py 제이엠티 --facts-only   # LLM 0, 비용 0
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# 소비자 2곳에서 모두 import 되어야 한다 (SSOT = api/intelligence/, 복제 = vercel-api/api/_operator/).
#   · 패키지 컨텍스트(api.intelligence / api._operator) → 상대 import
#   · 스크립트 직접 실행(python api/intelligence/operator_ask.py) → sys.path[0]=이 디렉토리
try:
    from . import ticker_facts  # type: ignore[attr-defined]
except ImportError:  # noqa: BLE001
    import ticker_facts  # type: ignore[no-redef]

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_KST = timezone(timedelta(hours=9))
_STATE_BASE = os.environ.get("OPERATOR_CACHE_DIR") or (
    "/tmp/verity" if os.environ.get("VERCEL") else os.path.join(_ROOT, ".cache")
)
_STATE_DIR = os.path.join(_STATE_BASE, "operator_ask")
DAILY_LIMIT = int(os.environ.get("ASK_DAILY_LIMIT", "15"))

CLAUDE_MODEL = "claude-opus-5"          # PM 선택. 종합 = 최상위 모델
CLAUDE_EFFORT = os.environ.get("ASK_EFFORT", "high")   # low|medium|high|xhigh|max
PPLX_MODEL = os.environ.get("ASK_PPLX_MODEL", "sonar")
PPLX_MODEL_PRO = os.environ.get("ASK_PPLX_MODEL_PRO", "sonar-pro")  # 급변 사유 축만
GEMINI_MODEL = os.environ.get("ASK_GEMINI_MODEL", "gemini-2.5-flash")


def _now() -> datetime:
    return datetime.now(_KST)


# ── 비용 가드 ────────────────────────────────────────────────────────────────
def _usage_path() -> str:
    return os.path.join(_STATE_DIR, "usage.json")


def _budget_check_and_bump() -> tuple:
    """(허용여부, 오늘 사용량, 상한). 상한 초과면 LLM 단계를 건너뛴다."""
    today = _now().strftime("%Y-%m-%d")
    try:
        with open(_usage_path(), encoding="utf-8") as f:
            doc = json.load(f)
    except Exception:
        doc = {}
    n = int(doc.get(today) or 0)
    if n >= DAILY_LIMIT:
        return False, n, DAILY_LIMIT
    doc = {today: n + 1}  # 당일만 유지 — 파일이 자라지 않는다
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(_usage_path(), "w", encoding="utf-8") as f:
            json.dump(doc, f)
    except Exception:
        pass
    return True, n + 1, DAILY_LIMIT


def _fingerprint(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]


def _cache_get(fp: str) -> Optional[Dict[str, Any]]:
    try:
        with open(os.path.join(_STATE_DIR, fp + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _cache_put(fp: str, doc: Dict[str, Any]) -> None:
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(os.path.join(_STATE_DIR, fp + ".json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
    except Exception:
        pass


def _post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str],
               timeout: int = 120) -> Optional[Dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json"}
    h.update(headers)
    try:
        req = urllib.request.Request(url, data=body, headers=h, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:400]  # type: ignore[attr-defined]
        except Exception:
            detail = str(e)[:400]
        print(f"[operator_ask] 호출 실패 {url.split('/')[2]}: {detail}", file=sys.stderr)
        return None


# ── ① Perplexity — 결측(gap) 위임 리서치 ─────────────────────────────────────
# PM 2026-08-03: "네가 정보 모을 때 퍼플렉시티 등에게 부가적 요소를 맡길 수 있는거지."
#
# 🚨 옛 구현은 한 번에 뭉뚱그려 물었다 —
#     f"{name}({ticker}) 관련 최근 뉴스·공시·주가 급변 사유. 질문: {question}"
#    ① 우리가 이미 가진 것(재무·밸류에이션)까지 질문에 섞여 검색이 흐려지고
#    ② 날짜가 안 박히고 ③ 국내 소스 유도가 없어 동명 영문 법인·무관 시황이 잡혔다.
#    2026-08-03 094970 +12% 사유 조회가 이 방식으로 실패("단정할 수 없습니다").
#    → **우리 데이터에 구멍이 난 축만** 골라 축별 질문으로 분리 위임한다.

_PPLX_RULES = (
    "규칙: ① 확인된 사실과 출처(URL)만. 추정·전망·투자의견 금지. "
    "② 확인 안 되면 반드시 '확인 안 됨'이라고 답하고 지어내지 마라. "
    "③ 한국거래소 KIND·DART·네이버금융·국내 경제지 등 **국내 1차 소스** 우선. "
    "④ 동명 해외 법인(영문 사명)과 혼동 금지 — 한국 상장사만. ⑤ 한국어."
)


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
    who = f"한국 상장사 {name}(종목코드 {tk})"
    gaps: List[Dict[str, str]] = []

    rep = _sec_data(facts, "리포트") or {}
    mkt = rep.get("market") or ""
    who = f"{'코스닥' if 'KOSDAQ' in str(mkt) else '코스피' if 'KOSPI' in str(mkt) else '한국'} 상장사 {name}(종목코드 {tk})"

    # ① 급변 사유 미상 — 최우선. 우리 데이터로는 "얼마나" 만 알고 "왜" 를 모른다.
    mv = _move_pct(facts)
    if mv is not None and abs(mv) >= 5.0:
        direction = "급등" if mv > 0 else "급락"
        gaps.append({
            "key": "catalyst",
            "label": f"{direction} 사유 ({mv:+.1f}%)",
            "recency": "day",
            "tier": "pro",
            "query": (
                f"{who} 주가가 {today} 장중 {mv:+.1f}% {direction}했다. 그 사유는 무엇인가?\n"
                f"확인할 것: (1) {today} 또는 직전 영업일에 나온 공시(KIND·DART 포함, "
                f"단일판매·공급계약, 최대주주 변경, 무상증자, 자기주식 취득, 조회공시 요구 등) "
                f"(2) 관련 뉴스·보도 (3) 이 종목이 속한 테마·업종의 동반 급등 여부 "
                f"(4) 특징주·급등주 코너 언급.\n{_PPLX_RULES}"
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
                f"거래소 조치(투자경고·불성실공시) 중심.\n{_PPLX_RULES}"
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
                    f"확정 일정이 공표됐는가? 직전 분기 실적 수치와 함께 알려줘.\n{_PPLX_RULES}"
                ),
            })
        break

    # ④ 컨센서스 부재 — 우리 consensus_available=false 는 "없다" 가 아니라 "우리가 못 모았다".
    #    다만 마이크로캡은 실제로 커버리지가 없는 경우가 대부분이라 우선순위는 뒤로 둔다.
    cons = rep.get("consensus") or {}
    if not cons.get("target_price") and not cons.get("opinion"):
        gaps.append({
            "key": "consensus",
            "label": "증권사 커버리지",
            "recency": "year",
            "tier": "base",
            "query": (
                f"{who}를 커버하는 증권사 리서치 리포트가 최근 1년 내 존재하는가?\n"
                f"있으면 증권사명·발간일·투자의견·목표주가를, 없으면 "
                f"'커버리지 없음'이라고 명확히 답해줘.\n{_PPLX_RULES}"
            ),
        })

    # ⑤ 어떤 구멍도 안 잡혔는데 PM 질문이 외부 사실을 요구하면 그것만 위임
    if not gaps and question.strip():
        gaps.append({"key": "freeform", "label": "PM 질문", "recency": "week", "tier": "base",
                     "query": f"{who}에 대한 질문: {question.strip()}\n{_PPLX_RULES}"})

    return gaps[:3]


def _perplexity_one(gap: Dict[str, str]) -> Optional[Dict[str, Any]]:
    key = os.environ.get("PERPLEXITY_API_KEY")
    if not key:
        return None
    # 급변 사유만 상위 tier — 검색 품질이 답을 좌우하는 유일한 축. 실패 시 기본 모델로 강등.
    models = [PPLX_MODEL_PRO, PPLX_MODEL] if gap.get("tier") == "pro" else [PPLX_MODEL]
    for model in models:
        doc = _post_json(
            "https://api.perplexity.ai/chat/completions",
            {
                "model": model,
                "messages": [{"role": "user", "content": gap["query"]}],
                "search_recency_filter": gap.get("recency") or "week",
                "max_tokens": 900,
            },
            {"Authorization": f"Bearer {key}"},
        )
        try:
            text = doc["choices"][0]["message"]["content"]  # type: ignore[index]
        except Exception:
            continue
        return {"key": gap["key"], "label": gap["label"], "model": model, "text": text,
                "citations": doc.get("citations") or doc.get("search_results") or []}
    return None


def _perplexity(facts: Dict[str, Any], question: str) -> List[Dict[str, Any]]:
    """결측 축별 병렬 위임. 축이 없으면 호출 0 (비용 0)."""
    gaps = research_gaps(facts, question)
    if not gaps:
        return []
    with ThreadPoolExecutor(max_workers=len(gaps)) as ex:
        res = list(ex.map(_perplexity_one, gaps))
    return [r for r in res if r]


# ── ② Gemini — 구조화 ────────────────────────────────────────────────────────
def _gemini(facts_text: str, question: str) -> Optional[str]:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    prompt = (
        "아래는 한 종목에 대해 우리 시스템이 보유한 사실 데이터다. 질문에 답하기 위해 "
        "**사실을 축별로 구조화**만 하라. 새 사실 생성 금지, 전망·추천 금지. "
        "없는 항목은 '없음'으로 남겨라.\n\n"
        f"[질문] {question}\n\n[사실]\n{facts_text[:60000]}"
    )
    doc = _post_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        {"contents": [{"parts": [{"text": prompt}]}],
         "generationConfig": {"maxOutputTokens": 2000}},
        {"x-goog-api-key": key},
    )
    if not doc:
        return None
    try:
        return doc["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return None


# ── ③ Claude opus-5 — 종합 ───────────────────────────────────────────────────
SYNTH_SYSTEM = """너는 VERITY/AlphaNest 오퍼레이터의 분석 파트너다. 청중은 운영자 본인 1명이며
산출물은 공개되지 않는다. 따라서 판단·해석·리스크 지적을 해도 된다. 단 규율은 지킨다.

절대 규율:
1. **주어진 사실 밖의 수치를 만들지 마라.** 특히 가격·목표가·지지선·저항선. 컨텍스트에 없으면
   "우리 데이터에 없음"이라고 쓴다. (2026-06-03 챗이 삼성전자를 "65,000원 지지선"이라 답한 사고
   — 실제 ~365,000원. 학습 기억으로 가격을 지어내면 같은 사고다.)
2. 모든 수치에 **출처와 기준일**을 붙여라. 가격은 두 종류이고 **섞지 마라**:
   · "실시간 시세 (KIS · 본인 이용)" 섹션이 있으면 **그게 현재가**다. 오늘 장중 등락을 여기서 읽어라.
   · "종가 (T+1 · 실시간 아님)" 은 직전 거래일 확정 종가다. 실시간이 있는데 종가로 "오늘"을
     말하면 틀린다(2026-08-03 사고: 실시간을 안 보고 "오늘 움직임은 확인 불가"라고 답했다).
   · 실시간 섹션이 없으면(장 마감·미도달·미국주식) 그때만 "오늘 장중은 확인 불가"라고 말해라.
3. 외부 사실(Perplexity)과 자체 사실(발행 데이터)을 **분리해서** 표기하라. 섞지 마라.
4. 검증 trail이 얕다(N<252). 확률·기대수익률을 단정하지 마라. 근거의 강도를 같이 적어라.
5. 없는 데이터는 "없다"고 말하고, 그게 판단에 어떤 한계를 만드는지 한 줄로 적어라.

형식: 짧게. 결론 먼저. 표는 사실 나열에만. 그다음 근거, 마지막에 한계와 확인이 필요한 것."""


def _claude(facts_text: str, pplx: List[Dict[str, Any]], gem: Optional[str],
            name: str, ticker: str, question: str) -> Optional[Dict[str, Any]]:
    try:
        import anthropic
    except ImportError:
        print("[operator_ask] pip install anthropic 필요", file=sys.stderr)
        return None
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    blocks = [f"[질문] {question}", f"[종목] {name} ({ticker})", "", "[자체 사실 — 우리 발행/수집 데이터]", facts_text]
    if gem:
        blocks += ["", "[구조화 — Gemini]", gem]
    if pplx:
        blocks += ["", "[외부 위임 리서치 — Perplexity, 자체 데이터 아님]",
                   "우리 데이터에 구멍이 난 축만 외부에 물었다. 자체 사실과 섞지 말고 분리 표기할 것."]
        for r in pplx:
            cites = r.get("citations") or []
            cite_txt = "\n".join(f"  - {c if isinstance(c, str) else c.get('url', '')}" for c in cites[:6])
            blocks += [f"― [{r['label']}] ({r.get('model')})", r["text"],
                       ("출처:\n" + cite_txt) if cite_txt else ""]
    else:
        blocks += ["", "[외부 위임 리서치] 없음 — 위임할 결측 축이 없거나 호출 실패."]

    client = anthropic.Anthropic()
    try:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            system=SYNTH_SYSTEM,
            output_config={"effort": CLAUDE_EFFORT},
            messages=[{"role": "user", "content": "\n".join(blocks)}],
        )
    except Exception as e:  # noqa: BLE001
        print(f"[operator_ask] Claude 호출 실패: {str(e)[:300]}", file=sys.stderr)
        return None

    # 🚨 refusal 은 예외가 아니라 정상 200 — content 를 무조건 인덱싱하면 깨진다.
    if resp.stop_reason == "refusal":
        cat = getattr(getattr(resp, "stop_details", None), "category", None)
        return {"refused": True, "category": cat}
    text = "".join(b.text for b in resp.content if b.type == "text")
    return {"text": text, "usage": {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens}}


# ── 오케스트레이션 ───────────────────────────────────────────────────────────
def ask(query: str, question: str = "", facts_only: bool = False,
        no_cache: bool = False) -> Dict[str, Any]:
    facts = ticker_facts.collect(query)
    facts_text = ticker_facts.render_text(facts)
    out: Dict[str, Any] = {"facts": facts, "facts_text": facts_text}
    if facts_only or not facts.get("ticker"):
        return out

    q = question.strip() or "이 종목에 대해 우리가 가진 사실을 종합해줘."
    as_of = ""
    for sec in facts["sections"]:
        if sec["label"] == "종가":
            as_of = sec.get("as_of", "")
            break
    fp = _fingerprint(facts["ticker"], q, as_of, CLAUDE_EFFORT)
    if not no_cache:
        hit = _cache_get(fp)
        if hit:
            out.update(hit)
            out["_cached"] = True
            return out

    ok, used, cap = _budget_check_and_bump()
    if not ok:
        out["budget_blocked"] = f"일 LLM 호출 상한 {cap}회 소진 — 사실 조인만 수행"
        return out

    pplx = _perplexity(facts, q)
    gem = _gemini(facts_text, q)
    syn = _claude(facts_text, pplx, gem, facts.get("name") or query, facts["ticker"], q)

    res = {"question": q, "perplexity": pplx, "gemini": gem, "synthesis": syn,
           "_budget": f"{used}/{cap}"}
    _cache_put(fp, res)
    out.update(res)
    return out


def render(out: Dict[str, Any]) -> str:
    L = [out["facts_text"], ""]
    if out.get("budget_blocked"):
        L += ["## 예산", out["budget_blocked"], ""]
    syn = out.get("synthesis")
    if syn:
        L += ["=" * 70, "# 종합 (Claude opus-5) — 오퍼레이터 전용, 공개 금지", "=" * 70]
        if syn.get("refused"):
            L.append(f"모델이 응답을 거절함 (category={syn.get('category')}).")
        else:
            L.append(syn.get("text", ""))
            u = syn.get("usage") or {}
            L.append(f"\n[토큰 in {u.get('in')} / out {u.get('out')} · effort {CLAUDE_EFFORT}"
                     f" · {out.get('_budget', '')}{' · 캐시' if out.get('_cached') else ''}]")
    for r in (out.get("perplexity") or []):
        L += ["", "-" * 70,
              f"# 외부 위임: {r['label']} (Perplexity/{r.get('model')} — 자체 데이터 아님)",
              "-" * 70, r["text"]]
        cites = [c if isinstance(c, str) else c.get("url", "") for c in (r.get("citations") or [])]
        if any(cites):
            L += ["", "출처: " + " · ".join(c for c in cites[:5] if c)]
    return "\n".join(L)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="종목 온디맨드 종합 (오퍼레이터 전용)")
    ap.add_argument("query", help="종목명 또는 6자리 코드")
    ap.add_argument("--q", default="", help="질문")
    ap.add_argument("--facts-only", action="store_true", help="LLM 0 (비용 0)")
    ap.add_argument("--questions", action="store_true",
                    help="결측 축 위임 질문만 출력 (호출 0 · 비용 0). 웹 퍼플렉시티 Pro 복붙용")
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()

    if a.questions:
        # API 자동 검색보다 품질이 높은 경로 — PM 이 웹 Pro 에 직접 붙여넣는다.
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
