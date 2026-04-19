"""
꼬리위험(전쟁·대규모 재난·시장 쇼크 등) — 내부 헤드라인·RSS만으로 Gemini 판별 후 고심각도만 텔레그램.
- quick/full: 매 실행 1회(헤드라인 있을 때) Gemini
- realtime: 키워드 프리필터 통과 + 쿨다운 시에만 Gemini (비용·쿼터 절약)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from google import genai

from api.config import (
    CLAUDE_TAIL_RISK_VERIFY,
    DATA_DIR,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    KST,
    TAIL_RISK_DIGEST_ENABLED,
    TAIL_RISK_HEADLINE_MAX,
    TAIL_RISK_IN_REALTIME,
    TAIL_RISK_NEWS_FLASH_HOURS,
    TAIL_RISK_PREFILTER_EXTRA,
    TAIL_RISK_REALTIME_COOLDOWN_MINUTES,
    TAIL_RISK_SEVERITY_MIN,
    now_kst,
)
from api.mocks import mockable
from api.notifications.telegram import send_message

_RAW_DATA_PATH = os.path.join(DATA_DIR, "raw_data.json")
_NEWS_FLASH_PATH = os.path.join(DATA_DIR, "news_flash.json")
_DEDUPE_META = "_tail_risk_digest_dedupe"
_RT_LAST_GEMINI = "_tail_risk_rt_last_gemini"

_PREFILTER_EN = (
    "earthquake",
    "tsunami",
    "wildfire",
    "airstrike",
    "air strike",
    "ballistic missile",
    "military invasion",
    "terrorist attack",
    "mass casualty",
    "state of emergency",
    "evacuation order",
    "nuclear plant",
    "armed conflict",
    "military strike",
    "declaration of war",
    "flash crash",
    "circuit breaker",
)
_PREFILTER_KO = (
    "지진",
    "쓰나미",
    "대형 산불",
    "미사일",
    "도발",
    "전쟁",
    "침공",
    "테러",
    "대형 화재",
    "긴급 대피",
    "비상사태",
    "군사",
    "무력",
)


def _prefilter_phrases() -> List[str]:
    out = list(_PREFILTER_EN) + list(_PREFILTER_KO) + list(TAIL_RISK_PREFILTER_EXTRA)
    return out


def _title_matches_prefilter(title: str) -> bool:
    t = title or ""
    cf = t.casefold()
    for p in _prefilter_phrases():
        pl = p.strip()
        if not pl:
            continue
        if any("\uac00" <= c <= "\ud7a3" for c in pl):
            if pl in t:
                return True
        elif pl.casefold() in cf:
            return True
    return False


def _prefilter_matches_headlines(items: List[Dict[str, str]]) -> bool:
    for it in items:
        if _title_matches_prefilter(it.get("title", "")):
            return True
    return False


def _realtime_gemini_cooldown_ok(portfolio: Dict[str, Any]) -> bool:
    raw = portfolio.get(_RT_LAST_GEMINI)
    if not raw:
        return True
    try:
        s = str(raw).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        ts = datetime.fromisoformat(s)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=KST)
        return (now_kst() - ts) >= timedelta(minutes=max(1, TAIL_RISK_REALTIME_COOLDOWN_MINUTES))
    except ValueError:
        return True


def _mark_realtime_gemini_done(portfolio: Dict[str, Any]) -> None:
    portfolio[_RT_LAST_GEMINI] = now_kst().isoformat()


def _escape_html(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _load_json(path: str, default: Any) -> Any:
    if not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _parse_iso_dt(s: str) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        try:
            return datetime.fromisoformat(s[:19]).replace(tzinfo=KST)
        except ValueError:
            return None


def _recent_news_flash(rows: List[Dict[str, Any]], hours: int) -> List[Dict[str, str]]:
    cutoff = now_kst() - timedelta(hours=max(1, hours))
    out: List[Dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = (row.get("title") or "").strip()
        if not title:
            continue
        pub = _parse_iso_dt(str(row.get("published_at") or ""))
        if pub is not None:
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=KST)
            if pub < cutoff:
                continue
        out.append(
            {
                "title": title,
                "source": str(row.get("source") or ""),
                "link": str(row.get("link") or ""),
            }
        )
    return out[: TAIL_RISK_HEADLINE_MAX]


def _flatten_headlines(portfolio: Dict[str, Any]) -> List[Dict[str, str]]:
    lines: List[Dict[str, str]] = []
    for key in ("headlines", "bloomberg_google_headlines"):
        for h in portfolio.get(key) or []:
            if not isinstance(h, dict):
                continue
            t = (h.get("title") or "").strip()
            if not t:
                continue
            lines.append(
                {
                    "title": t,
                    "source": str(h.get("source") or key),
                    "link": str(h.get("link") or ""),
                }
            )
    seen = set()
    uniq: List[Dict[str, str]] = []
    for item in lines:
        k = re.sub(r"\s+", " ", item["title"].casefold())[:120]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(item)
    return uniq[: TAIL_RISK_HEADLINE_MAX]


def _watchlist_names(portfolio: Dict[str, Any]) -> str:
    names: List[str] = []
    for h in portfolio.get("vams", {}).get("holdings") or []:
        if isinstance(h, dict) and h.get("name"):
            names.append(str(h["name"]))
    for r in portfolio.get("recommendations") or []:
        if isinstance(r, dict) and r.get("name"):
            names.append(str(r["name"]))
    out: List[str] = []
    seen = set()
    for n in names:
        n = n.strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return ", ".join(out[:25]) if out else "(없음)"


def _extract_json_obj(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", t)
    if m:
        t = m.group(1)
    else:
        i = t.find("{")
        j = t.rfind("}")
        if i >= 0 and j > i:
            t = t[i : j + 1]
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _dedupe_key(result: Dict[str, Any]) -> str:
    cat = str(result.get("category", ""))
    summ = str(result.get("summary_ko", ""))[:160]
    return hashlib.sha256(f"{cat}|{summ}".encode("utf-8")).hexdigest()[:20]


def _was_recently_sent(portfolio: Dict[str, Any], key: str, hours: int = 24) -> bool:
    raw = portfolio.get(_DEDUPE_META)
    bucket: Dict[str, str] = raw if isinstance(raw, dict) else {}
    portfolio[_DEDUPE_META] = bucket
    ts_s = bucket.get(key)
    if not ts_s:
        return False
    try:
        s = str(ts_s).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        ts = datetime.fromisoformat(s)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=KST)
        return (now_kst() - ts) < timedelta(hours=hours)
    except ValueError:
        return False


def _mark_sent(portfolio: Dict[str, Any], key: str) -> None:
    bucket = portfolio.setdefault(_DEDUPE_META, {})
    if not isinstance(bucket, dict):
        bucket = {}
        portfolio[_DEDUPE_META] = bucket
    bucket[key] = now_kst().isoformat()


@mockable("gemini.tail_risk")
def maybe_send_tail_risk_digest(portfolio: Dict[str, Any], is_realtime: bool = False) -> None:
    if not TAIL_RISK_DIGEST_ENABLED:
        return
    if not GEMINI_API_KEY:
        print("[tail_risk] GEMINI_API_KEY 없음 — 스킵")
        return
    if is_realtime and not TAIL_RISK_IN_REALTIME:
        return

    nf_raw = _load_json(_NEWS_FLASH_PATH, [])
    news_flash = nf_raw if isinstance(nf_raw, list) else []

    flash_items = _recent_news_flash(news_flash, TAIL_RISK_NEWS_FLASH_HOURS)
    head_items = _flatten_headlines(portfolio)
    combined: List[Dict[str, str]] = []
    seen_t = set()
    for block in (flash_items, head_items):
        for it in block:
            k = it["title"].casefold()[:200]
            if k in seen_t:
                continue
            seen_t.add(k)
            combined.append(it)
    combined = combined[: TAIL_RISK_HEADLINE_MAX]

    if not combined:
        print("[tail_risk] 헤드라인 없음 — 스킵")
        return

    if is_realtime:
        if not _prefilter_matches_headlines(combined):
            return
        if not _realtime_gemini_cooldown_ok(portfolio):
            print("[tail_risk] realtime 쿨다운 중 — Gemini 스킵")
            return

    briefing_hl = (portfolio.get("briefing") or {}).get("headline") or ""
    watch = _watchlist_names(portfolio)

    lines_txt = []
    for i, it in enumerate(combined, 1):
        src = it.get("source", "")
        lines_txt.append(f"{i}. [{src}] {it['title']}")

    prompt = f"""다음은 금융/거시 뉴스 헤드라인 목록이다. JSON 한 개만 출력해라. 마크다운 금지.

판별 기준:
- 실제 군사 충돌·전쟁 발발·대규모 인명피해 재난(지진·쓰나미·대형 화재)·주요 인프라 마비 등 시장에 비선형 충격을 줄 수 있는지 판단.
- 영화·게임·무역전쟁 수사·일상 정치 보도만이면 irrelevant.
- category는 소문자 영단어 하나: war | disaster | market_shock | geopolitics | irrelevant

출력 스키마(필수 키):
{{"severity_1_10": 정수, "category": 문자열, "summary_ko": "2~4문장 한국어", "portfolio_angle": "관심종목 연결 1문장 또는 빈 문자열", "primary_title": "가장 핵심으로 본 원문 제목 그대로"}}

비서 한줄 요약(참고): {briefing_hl or "없음"}
관심 종목명(참고): {watch}

헤드라인:
{chr(10).join(lines_txt)}
"""

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "temperature": 0.15,
                "max_output_tokens": 800,
            },
        )
        text = (resp.text or "").strip()
    except Exception as e:
        print(f"[tail_risk] Gemini 호출 실패: {e}")
        return

    if is_realtime:
        _mark_realtime_gemini_done(portfolio)

    result = _extract_json_obj(text)
    if not result:
        print(f"[tail_risk] JSON 파싱 실패, 원문 일부: {text[:200]}")
        return

    try:
        sev = int(result.get("severity_1_10", 0))
    except (TypeError, ValueError):
        sev = 0

    cat = str(result.get("category", "")).lower().strip()

    # Claude 교차 검증: Gemini severity 7+ 시 Claude에게도 판별
    if CLAUDE_TAIL_RISK_VERIFY and sev >= 7:
        try:
            from api.analyzers.claude_analyst import verify_tail_risk
            claude_result = verify_tail_risk(chr(10).join(lines_txt), sev)
            if claude_result:
                claude_sev = int(claude_result.get("severity_1_10", sev))
                avg_sev = (sev + claude_sev) // 2
                agrees = claude_result.get("agrees_with_gemini", True)
                print(f"[tail_risk] Claude 교차검증: {claude_sev}/10 ({'동의' if agrees else '반대'}) | 평균 {avg_sev}")
                sev = avg_sev
                if claude_result.get("category") == "irrelevant" and not agrees:
                    cat = "irrelevant"
        except Exception as e:
            print(f"[tail_risk] Claude 교차검증 스킵: {e}")

    if cat == "irrelevant" or sev < TAIL_RISK_SEVERITY_MIN:
        print(f"[tail_risk] 전송 안 함 (category={cat}, severity={sev})")
        return

    dk = _dedupe_key(result)
    if _was_recently_sent(portfolio, dk, hours=24):
        print(f"[tail_risk] 24h 내 동일 요약 전송됨 — 스킵")
        return

    summ = str(result.get("summary_ko") or "").strip()
    angl = str(result.get("portfolio_angle") or "").strip()
    ptitle = str(result.get("primary_title") or "").strip()
    link = ""
    if ptitle:
        for it in combined:
            t = it["title"]
            if ptitle in t or t in ptitle:
                link = it.get("link") or ""
                break

    body_parts = [
        "<b>🚨 VERITY 꼬리위험 알림</b>",
        f"<i>{_escape_html(cat)} · 심각도 {sev}/10</i>",
        "",
        _escape_html(summ),
    ]
    if angl:
        body_parts.extend(["", f"<b>포트 연결</b> {_escape_html(angl)}"])
    if link:
        body_parts.extend(["", f'<a href="{_escape_html(link)}">기사 링크</a>'])

    ok = send_message("\n".join(body_parts))
    if ok:
        _mark_sent(portfolio, dk)
        one = summ.replace("\n", " ").strip()
        if len(one) > 140:
            one = one[:137] + "…"
        portfolio["tail_risk_digest_last"] = {
            "date_kst": now_kst().strftime("%Y-%m-%d"),
            "one_liner": one,
        }
        print(f"[tail_risk] 텔레그램 전송 완료 (severity={sev})")
    else:
        print("[tail_risk] 텔레그램 전송 실패(토큰 등) — dedupe 미기록")
