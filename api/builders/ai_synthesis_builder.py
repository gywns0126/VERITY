"""AI 사실 종합 — 검증된 공개 사실을 LLM이 자연스러운 2문장으로 '다듬기만'. 의견·추천·등급 0.

🚨 RULE 6: ungrounded LLM narrative 금지지만, **자기 trail(검증 데이터) 위 종합 = 권장 방향**(escape hatch).
   ChatGPT가 못 보는 우리 DART/KRX/공정위 사실 위에서 종합 → "못한 ChatGPT" 아님.
🚨 RULE 7 / held-2027 / 유사투자자문 법: 사실 종합·연결만. **평가·의견·추천·전망·매수의견·등급 절대 0.**
   - 결정론으로 사실 선택(평가어 미포함) → LLM은 그 사실만 자연스럽게 연결(내용·숫자·전망 추가 금지).
   - post-filter: verdict/평가 단어 검출 시 LLM 출력 폐기 → 결정론 사실선 fallback.
소스 = data/stock_report_public.json (이미 발행된 공개-safe 사실). 출력 = data/ai_synthesis.json.
LLM = Gemini flash-lite(GEMINI_MODEL_CHAT, news_translation 동일). 키 없으면 결정론 종합만.
캐시 = ai_synthesis_cache.json (fact-fingerprint → text). 가격 jitter 캐시버스트 방지 위해 PER/PBR 등은 1자리 반올림 핑거프린트.
"""
import hashlib
import json
import os
import re
import sys
from typing import Any, Dict, List

from api.config import now_kst

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_PATH = os.path.join(_ROOT, "data", "stock_report_public.json")
OUT_PATH = os.path.join(_ROOT, "data", "ai_synthesis.json")
CACHE_PATH = os.path.join(_ROOT, "data", "ai_synthesis_cache.json")
BATCH = 18           # Gemini 1콜당 종목 수
MAX_NEW_PER_RUN = 600  # 신규 LLM 종목 상한(비용 가드). 캐시 hit는 무제한.

# 🚨 verdict/평가 차단어 — LLM 출력에 하나라도 있으면 폐기(결정론 fallback). 유사투자자문/held 경계.
_BAN = ["매수", "매도", "추천", "저평가", "고평가", "매력", "유망", "주목", "기대", "전망",
        "비중확대", "비중축소", "목표주가", "목표가", "상승여력", "투자의견", "사야", "팔아",
        "바람직", "긍정적", "부정적", "우려", "호재", "악재", "좋", "나쁘", "강세", "약세", "전망치"]


def _round1(v: Any) -> str:
    m = re.search(r"-?\d+\.?\d*", str(v or ""))
    if not m:
        return str(v or "")
    try:
        return str(round(float(m.group(0)), 1)) + str(v)[m.end():]
    except ValueError:
        return str(v or "")


def _fact_parts(s: Dict[str, Any]) -> List[str]:
    """결정론 사실 선택 — 평가어 미포함. peer vs 방향은 '업종 대비 낮음/높음'(사실)만."""
    f = s.get("facts") or {}
    rows = {r.get("key"): r for r in ((s.get("peer") or {}).get("rows") or [])}

    def vs_tag(k: str) -> str:
        r = rows.get(k)
        if not r:
            return ""
        return " (업종 대비 낮음)" if r.get("vs") == "below" else " (업종 대비 높음)" if r.get("vs") == "above" else ""

    parts: List[str] = []
    if s.get("business"):
        parts.append(str(s["business"]))
    if f.get("PER"):
        parts.append(f"PER {f['PER']}{vs_tag('PER')}")
    if f.get("PBR"):
        parts.append(f"PBR {f['PBR']}{vs_tag('PBR')}")
    if f.get("ROE"):
        parts.append(f"ROE {f['ROE']}{vs_tag('ROE')}")
    if f.get("부채비율"):
        parts.append(f"부채비율 {f['부채비율']}{vs_tag('부채비율')}")
    if f.get("Altman-Z"):
        parts.append(f"Altman-Z {f['Altman-Z']}")
    own = s.get("ownership") or {}
    if own.get("family_pct") is not None:
        parts.append(f"총수일가 지분 {own['family_pct']}%")
    ins = s.get("insider")
    n_disc = len(s.get("disclosures") or [])
    if n_disc:
        parts.append(f"최근 공시 {n_disc}건")
    return parts


def _fingerprint(name: str, parts: List[str]) -> str:
    # PER/PBR 등 숫자 1자리 반올림 → 가격 미세변동 캐시버스트 방지.
    stable = name + "|" + "|".join(_round1(p) for p in parts)
    return hashlib.sha1(stable.encode("utf-8")).hexdigest()[:16]


def _deterministic(name: str, parts: List[str]) -> str:
    return f"{name} — " + " · ".join(parts)


def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", str(t or "")).strip()


def _gemini_batch(items: List[Dict[str, str]]) -> Dict[str, str]:
    """[{i, name, facts}] → {i: 다듬은 2문장}. 실패/빈값 → 결정론 fallback은 호출부에서."""
    if not items:
        return {}
    try:
        from google import genai
        from api.config import GEMINI_API_KEY, GEMINI_MODEL_CHAT
        if not GEMINI_API_KEY:
            return {}
        client = genai.Client(api_key=GEMINI_API_KEY)
        numbered = "\n".join(f'{it["i"]}. [{it["name"]}] {it["facts"]}' for it in items)
        prompt = (
            "너는 '사실 종합기'다. 각 줄은 한 종목의 검증된 사실 나열이다. "
            "이 사실들만 사용해 한국어 2문장으로 자연스럽게 이어 말하라.\n"
            "엄격 규칙:\n"
            "- 주어진 사실만. 새 숫자·비율·가격·미래 전망·예측 생성 절대 금지.\n"
            "- 평가·의견·추천 금지: 저평가/고평가/매력/유망/매수/매도/주목/기대/좋다/나쁘다/우량/강세/약세 등 판단어 사용 금지.\n"
            "- 사실 진술로만('~이다/~한 회사다/~건이다'). 사고팔라는 암시 금지.\n"
            '반드시 JSON 객체로만: {"0":"문장","1":"문장",...} (키=번호 문자열).\n\n'
            + numbered
        )
        resp = client.models.generate_content(
            model=GEMINI_MODEL_CHAT,
            contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0.2},
        )
        text = (getattr(resp, "text", "") or "").strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
        data = json.loads(text)
        out: Dict[str, str] = {}
        for it in items:
            v = data.get(str(it["i"]))
            if isinstance(v, str) and v.strip():
                out[str(it["i"])] = _clean(v)
        return out
    except Exception:  # noqa: BLE001
        return {}


def _load_cache() -> Dict[str, str]:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def build_ai_synthesis() -> Dict[str, Any]:
    logged = False
    summary: Dict[str, Any] = {"status": "skip", "n": 0, "llm": 0}
    try:
        with open(SRC_PATH, "r", encoding="utf-8") as f:
            doc = json.load(f)
        stocks = doc if isinstance(doc, list) else (doc.get("stocks") or [])
        if not stocks:
            print("[ai_synth] stock_report_public 비어 — skip", file=sys.stderr)
            return summary

        cache = _load_cache()
        synth: Dict[str, str] = {}
        misses: List[Dict[str, Any]] = []  # {tk, name, fp, parts}

        for s in stocks:
            tk = str(s.get("ticker") or "").strip()
            name = str(s.get("name") or "").strip()
            if not tk or not name:
                continue
            parts = _fact_parts(s)
            if len(parts) < 3:   # 사실 빈약 → 종합 skip
                continue
            fp = _fingerprint(name, parts)
            if fp in cache and cache[fp]:
                synth[tk] = cache[fp]
            else:
                misses.append({"tk": tk, "name": name, "fp": fp, "parts": parts})

        # LLM 다듬기 (상한 내) — 나머지/실패는 결정론 fallback
        to_llm = misses[:MAX_NEW_PER_RUN]
        llm_done = 0
        for b in range(0, len(to_llm), BATCH):
            chunk = to_llm[b:b + BATCH]
            items = [{"i": str(j), "name": c["name"], "facts": " · ".join(c["parts"])} for j, c in enumerate(chunk)]
            got = _gemini_batch(items)
            for j, c in enumerate(chunk):
                txt = got.get(str(j), "")
                if txt and not any(w in txt for w in _BAN):
                    synth[c["tk"]] = txt
                    cache[c["fp"]] = txt
                    llm_done += 1
                else:
                    synth[c["tk"]] = _deterministic(c["name"], c["parts"])  # 폐기/필터 → 결정론
        # 상한 초과분 = 결정론
        for c in misses[MAX_NEW_PER_RUN:]:
            synth[c["tk"]] = _deterministic(c["name"], c["parts"])

        out = {
            "updated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            "count": len(synth),
            "note": "검증 사실(DART/KRX/공정위) 기반 AI 종합 — 평가·추천·등급 0. LLM=사실 다듬기만.",
            "synth": synth,
        }
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        # 캐시 저장(상한 3000)
        if len(cache) > 3000:
            cache = dict(list(cache.items())[-3000:])
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        logged = True
        summary = {"status": "ok", "n": len(synth), "llm": llm_done}
        print(f"[ai_synth] logged=True · {len(synth)}종목 종합(LLM {llm_done}, 캐시/결정론 {len(synth) - llm_done})", file=sys.stderr)
        return summary
    finally:
        if not logged and summary.get("status") != "ok":
            print("[ai_synth] logged=False (graceful)", file=sys.stderr)


if __name__ == "__main__":
    print(json.dumps(build_ai_synthesis(), ensure_ascii=False, indent=2))
