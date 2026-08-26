"""
dart_business_overview — 사업보고서 「II. 사업의 내용 › 1. 사업의 개요」 결정론 추출.

2026-08-23 신설. PM 지적 = "1,210종목 사업보고서 원문을 이미 받아놓고 「사업의 개요」를 안 뽑고 있다".

| 왜 여기인가 | `dart_kam` 과 같은 원천(`dart_raw_cache` 의 `raw_text`)을 읽는다 |
| 방법 | 정규식 슬라이스. **LLM 0 · 과금 0**. 디스크 캐시가 있으면 네트워크도 0 |
| 왜 LLM 이 아닌가 | KAM 선례 — 구조가 있으면 결정론이 이긴다(Gemini 0/5 vs 파서 12/12). |
|                 | 게다가 이건 요약이 아니라 **원문 발췌**라 모델이 손댈수록 사실이 흐려진다 |

🚨 게이트 캘리브레이션 이력 (지어내지 말 것 — 실측이다):
  · 1차 게이트가 주어 토큰("당사"/"회사")을 요구했더니 86건이 반려됐는데, 표본을 읽어보니
    대부분 **정상 개요**였다. 푸른저축은행 "당 저축은행" · 백산 "지배기업인 (주)백산" ·
    송원산업 "연결기업" 처럼 주어 표현이 회사마다 다르다. → 주어 게이트 **폐기**.
  · 대체 = **서술밀도**(종결어미/1000자). 통과군 실측 p05 = 3.8. 임계 1.0 은 그 아래
    표·용어정리표만 있는 슬라이스를 거른다.
  · [[project_segment_donut_abandoned_2026_08_21]] 은 게이트가 쓰레기를 통과시킨 실패였고,
    여기 1차는 게이트가 정상을 자른 실패다. 둘 다 원인은 **캘리브레이션 부재** 하나다.
"""
from __future__ import annotations

import logging
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 「1. 사업의 개요」 — 줄 전체가 소제목인 경우만. 본문 안 언급("…사업의 개요를 참조")과 구분된다.
# 🚨 괄호 수식어 허용 — 실측 '1. (제조서비스업)사업의 개요'(카카오 2025). 이 한 글자
#   차이로 시총 상위 종목이 통째로 반려됐다. DartScout `_BIZ_OVERVIEW_HEAD` 와 같은 형태.
ANCHOR = re.compile(
    r"(?m)^[ \t]*(?:[1１]\s*[.)]|가\s*[.)])?\s*(?:[\(（][^)）\n]{0,20}[\)）])?"
    r"\s*사업의?\s*개요\s*(?:[\(（][^)）\n]{0,20}[\)）])?\s*$")
# 다음 소제목 = 줄 전체가 "N. 제목" (N=2~9). 🚨 "3.8%" 오검출 방지 = 점 뒤 공백 + 비숫자 시작 요구.
NEXT_HEAD = re.compile(r"(?m)^[ \t]*([2-9])\s*[.)]\s+(?![0-9])(\S[^\n]{0,40})[ \t]*$")
# 로마숫자 상위 섹션(III. 재무에 관한 사항 등) = 확실한 종료 경계
NEXT_ROMAN = re.compile(r"(?m)^[ \t]*(?:Ⅲ|III|Ⅱ|II|3)\s*[.)]\s*\S")
IMG_LINE = re.compile(r"(?m)^[^\n]{0,60}\.(?:jpg|jpeg|png|gif|bmp)[ \t]*$", re.I)
WS = re.compile(r"[ \t]+")
BLANKS = re.compile(r"\n{3,}")
HANGUL = re.compile(r"[가-힣]")
# 서술 종결어미 — 음슴체(있음/함/됨)까지. 통과군 실측 p05 = 3.8/1000자.
SENT_END = re.compile(r"(?:니다|습니다|입니다|한다|된다|있다|이다|하고|있음|없음|됨|함|임)[.\s]")
# 본문 앞머리에 붙는 용어정리표 — 서술 시작 전까지 잘라낸다.
GLOSSARY_HEAD = re.compile(
    r"^\s*(?:\[\s*용어[^\]]{0,20}\]|※\s*용어[^\n]{0,20}|용어\s*(?:의?\s*)?(?:정리|설명|해설)[^\n]{0,20})")

MIN_CHARS = 150            # 이보다 짧으면 개요가 아니라 참조 문구다
MIN_HANGUL_RATIO = 0.25    # 표·수치 덩어리 반려
MIN_SENT_DENSITY = 1.0     # /1000자
DEFAULT_MAX_CHARS = 2500


def _clean(text: str) -> str:
    """이미지 캡션 줄·중복 공백 정리. 본문 문장은 손대지 않는다."""
    text = IMG_LINE.sub("", text)
    text = WS.sub(" ", text)
    text = BLANKS.sub("\n\n", text)
    return text.strip()


def _cut_at_sentence(text: str, limit: int) -> Tuple[str, bool]:
    """limit 초과 시 마지막 문장 경계에서 자른다. → (본문, 잘렸는지)"""
    if len(text) <= limit:
        return text, False
    head = text[:limit]
    for mark in ("습니다.", "합니다.", "다."):
        i = head.rfind(mark)
        if i > limit * 0.5:
            return head[: i + len(mark)].strip(), True
    return head.rstrip() + "…", True


def extract_overview(raw_text: str, max_chars: int = DEFAULT_MAX_CHARS) -> Dict[str, Any]:
    """`raw_text`('II. 사업의 내용' 슬라이스) → 사업의 개요 본문.

    반환 = {ok, text, reason, next_heading, truncated, raw_len, sent_density, glossary_stripped}
    🚨 `ok=False` 여도 `reason` 을 반드시 채운다 — 반려를 숫자 하나로 뭉개지 않는다(RULE 13 ③).
    """
    out: Dict[str, Any] = {"ok": False, "text": "", "reason": "", "next_heading": None,
                           "truncated": False, "raw_len": 0, "sent_density": 0.0,
                           "glossary_stripped": False}
    if not raw_text:
        out["reason"] = "raw_text_empty"
        return out

    # 앵커 후보 전부 수집 → 'II. 사업의 내용' 직후 것을 우선한다(목차/재언급 회피).
    anchors = list(ANCHOR.finditer(raw_text))
    if not anchors:
        out["reason"] = "anchor_not_found"
        return out
    sec_ii = raw_text.rfind("사업의 내용")
    pick = None
    for m in anchors:
        if sec_ii >= 0 and m.start() > sec_ii:
            pick = m
            break
    if pick is None:
        pick = anchors[0]

    body = raw_text[pick.end():]
    end = len(body)
    nh = NEXT_HEAD.search(body)
    if nh:
        end = min(end, nh.start())
        out["next_heading"] = f"{nh.group(1)}. {nh.group(2).strip()}"[:48]
    nr = NEXT_ROMAN.search(body)
    if nr:
        end = min(end, nr.start())
    body = _clean(body[:end])
    out["raw_len"] = len(body)

    if len(body) < MIN_CHARS:
        out["reason"] = "too_short"
        return out
    hangul_ratio = len(HANGUL.findall(body)) / max(1, len(body))
    if hangul_ratio < MIN_HANGUL_RATIO:
        out["reason"] = f"not_hangul_prose(hangul={hangul_ratio:.2f})"
        return out

    # 앞머리 용어정리표 제거 — 서술이 시작되는 첫 문단부터 본문으로 본다.
    if GLOSSARY_HEAD.match(body):
        paras = body.split("\n\n")
        for i, para in enumerate(paras):
            if len(para) > 120 and SENT_END.search(para):
                body = "\n\n".join(paras[i:]).strip()
                out["glossary_stripped"] = True
                break
        out["raw_len"] = len(body)
        if len(body) < MIN_CHARS:
            out["reason"] = "too_short_after_glossary"
            return out

    sent_density = len(SENT_END.findall(body)) / max(1, len(body)) * 1000
    out["sent_density"] = round(sent_density, 2)
    if sent_density < MIN_SENT_DENSITY:
        out["reason"] = f"not_prose(sent={sent_density:.2f})"
        return out

    text, truncated = _cut_at_sentence(body, max_chars)
    out.update({"ok": True, "text": text, "truncated": truncated, "reason": ""})
    return out


def row_from_doc(doc: Dict[str, Any], corp_code: str, bsns_year: str,
                 name: str = "", max_chars: int = DEFAULT_MAX_CHARS) -> Optional[Dict[str, Any]]:
    """DartScout 문서(dict) → 저장 row. 실패 시 None."""
    res = extract_overview((doc or {}).get("raw_text") or "", max_chars)
    if not res["ok"]:
        return None
    return {
        "corp_code": corp_code,
        "name": name,
        "rcept_no": (doc or {}).get("rcept_no"),
        "rcept_dt": (doc or {}).get("rcept_dt"),
        "bsns_year": str((doc or {}).get("bsns_year") or bsns_year),
        "report_nm": (doc or {}).get("report_nm"),
        "text": res["text"],
        "char_count": len(res["text"]),
        "truncated": res["truncated"],
        "next_heading": res["next_heading"],
        "raw_len": res["raw_len"],
        "sent_density": res["sent_density"],
        "glossary_stripped": res["glossary_stripped"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 축 실행부 — `kr_company_facts_backfill.py --axes overview` 진입점.
# ─────────────────────────────────────────────────────────────────────────────
import json      # noqa: E402
import os        # noqa: E402
import time      # noqa: E402

from api.config import DATA_DIR, now_kst   # noqa: E402

CACHE_PATH = os.path.join(DATA_DIR, "dart_business_overview.json")
_FLUSH_EVERY = 50          # 증분 저장 주기 — 긴 배치가 죽어도 파싱분을 버리지 않는다(kam 학습)
# 🚨 2026-08-24 신설 — 반려 원장(`misses`). 종전엔 재개 신호가 "성공 행 존재" **하나뿐**이라
#   *아직 안 해봄* 과 *해봤는데 게이트가 반려* 를 구분할 수 없었다. 그래서 반려 종목이
#   **매 run 다시 문서를 받아** 다시 반려됐다(실측: 남선알미늄 06:33 run, 한화에어로·고려아연·
#   한국항공우주·오뚜기 21:00 run — 종목당 4~11초 · DART 2콜). 드립이 수렴하면 매 run 예산이
#   전부 같은 반려 재조회에 쓰이고, 그 사실은 어디에도 안 남는다.
#   = `dart_kr_fin_backfill` 셀 원장과 **같은 결함 계열**([[feedback_purge_erases_the_requeue_signal]]).
MAX_OVERVIEW_ATTEMPTS = 2
# 🚨 2026-08-26 — **정본은 사업보고서다.** `[첨부정정]` 이 문서 없이 올라오면 A001 이 통째로
#   실패해 반기·분기보고서로 떨어지는데(실측 71행), 그 행도 `text` 가 있어 드립이 건너뛴다
#   = 폴백을 고쳐도 자동 전파되지 않는다. 재개 신호가 "성공 행 존재" 하나뿐인 그 결함의
#   또 다른 얼굴이다([[feedback_purge_erases_the_requeue_signal]]).
#   → 비사업보고서 출처 행은 이 횟수까지 **정본 재시도** 대상으로 본다. 신규 상장처럼
#     사업보고서가 애초에 없는 종목이 영구 재조회되지 않도록 상한을 둔다.
MAX_ANNUAL_RETRY = 2


def is_annual(report_nm) -> bool:
    """정본(사업보고서) 여부. `[기재정정]사업보고서` 도 정본이다."""
    return "사업보고서" in str(report_nm or "")


def load_cache() -> Dict[str, Any]:
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_cache(cache: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        tmp = CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        os.replace(tmp, CACHE_PATH)
    except OSError as e:
        logger.warning("[overview] 캐시 저장 실패: %s", e)


def analyze_all_overview(stocks: Dict[str, Any],
                         auto_fetch_missing: bool = True,
                         max_chars: int = DEFAULT_MAX_CHARS,
                         retry_exhausted: bool = False,
                         deadline: Optional[float] = None) -> Dict[str, Dict[str, Any]]:
    """stocks dict 일괄 사업의 개요 추출. LLM 0 · 과금 0.

    `raw_text` 우선순위 = (1) 넘겨받은 `business_facilities_raw.raw_text`,
    (2) `auto_fetch_missing` 이면 `corp_code` 로 DartScout fetch (디스크 캐시 read-through).
    🚨 (2)가 없으면 백필 경로가 raw_text 를 못 넘겨 전 종목 skip 된다 — kam 이 그렇게
       커버리지 0 을 조용히 유지했다(2026-08-16 학습).

    증분 = 같은 티커에 **같거나 더 최신 사업연도** 행이 이미 있으면 건너뛴다.
    반려는 `misses` 원장에 시도 횟수로 남고, 상한(MAX_OVERVIEW_ATTEMPTS) 도달분은
    `retry_exhausted` 없이는 다시 두드리지 않는다.
    """
    cache = load_cache()
    rows: Dict[str, Any] = cache.get("rows") or {}
    misses: Dict[str, Any] = dict(cache.get("misses") or {})
    out: Dict[str, Dict[str, Any]] = {}
    fresh = cached = skipped = exhausted_skip = budget_stopped = 0
    reject_reasons: Dict[str, int] = {}

    for ticker, info in (stocks or {}).items():
        if not isinstance(info, dict):
            continue
        year = str(info.get("bsns_year") or "")
        name = info.get("name") or info.get("corp_name") or ticker
        corp_code = info.get("corp_code")

        prev = rows.get(ticker)
        if prev and str(prev.get("bsns_year") or "") >= year and prev.get("text"):
            # 🚨 비사업보고서로 채워진 행은 정본 재시도 대상(상한 내). 위 상수 주석 참조.
            if is_annual(prev.get("report_nm")) or \
                    int(prev.get("annual_retry") or 0) >= MAX_ANNUAL_RETRY:
                out[ticker] = prev
                cached += 1
                continue

        # 🚨 축 예산 — 한 축이 job 전체를 먹으면 뒤 축이 시작조차 못 한다(2026-08-25 실사고).
        if deadline and time.time() > deadline:
            budget_stopped += 1
            continue

        # 🚨 시도 상한 도달분은 **문서를 받지 않는다** — 여기가 낭비의 발생점이었다.
        if not retry_exhausted and int((misses.get(ticker) or {}).get("n", 0)) >= MAX_OVERVIEW_ATTEMPTS:
            exhausted_skip += 1
            continue

        bf = info.get("business_facilities_raw") or {}
        doc: Dict[str, Any] = bf if isinstance(bf, dict) and bf.get("raw_text") else {}
        t_fetch = 0.0
        if not doc and auto_fetch_missing and corp_code:
            _t0 = time.monotonic()
            try:
                from api.collectors.DartScout import fetch_business_facilities_raw
                doc = fetch_business_facilities_raw(corp_code, year) or {}
            except Exception as e:  # noqa: BLE001
                logger.warning("[overview] fetch 실패(%s): %s", name, str(e)[:60])
                doc = {}
            t_fetch = time.monotonic() - _t0

        row = row_from_doc(doc, str(corp_code or ""), year, name=str(name), max_chars=max_chars)
        if row is None:
            res = extract_overview((doc or {}).get("raw_text") or "", max_chars)
            r = (res.get("reason") or "no_raw_text").split("(")[0]
            reject_reasons[r] = reject_reasons.get(r, 0) + 1
            skipped += 1
            prev_m = misses.get(ticker) or {}
            misses[ticker] = {"n": int(prev_m.get("n", 0)) + 1,
                              "last": now_kst().date().isoformat(),
                              "reason": res.get("reason") or "no_raw_text",
                              "name": str(name)[:20], "bsns_year": year,
                              "raw_len": res.get("raw_len", 0)}
            sys.stderr.write(f"[overview] {ticker} {str(name)[:12]} fetch {t_fetch:4.1f}s · skip {r}"
                             f" (누적 {misses[ticker]['n']}/{MAX_OVERVIEW_ATTEMPTS})\n")
            continue

        # 정본을 못 받았으면 재시도 횟수를 행에 남긴다(상한 도달 시 그만 둔다).
        if not is_annual(row.get("report_nm")):
            row["annual_retry"] = int((prev or {}).get("annual_retry") or 0) + 1
        rows[ticker] = row
        out[ticker] = row
        misses.pop(ticker, None)      # 채워졌으면 반려 원장에서 뺀다
        fresh += 1
        sys.stderr.write(f"[overview] {ticker} {str(name)[:12]} fetch {t_fetch:4.1f}s · {row['char_count']}자\n")
        sys.stderr.flush()

        if fresh % _FLUSH_EVERY == 0:
            cache["rows"] = rows
            cache["misses"] = misses
            cache["_meta"] = {**(cache.get("_meta") or {}), "updated_at": now_kst().isoformat(),
                              "_partial": True}
            save_cache(cache)

    if fresh or skipped or exhausted_skip:
        cache["rows"] = rows
        cache["misses"] = misses
        meta = dict(cache.get("_meta") or {})
        by_reason: Dict[str, int] = {}
        for v in misses.values():
            k = str(v.get("reason") or "?").split("(")[0]
            by_reason[k] = by_reason.get(k, 0) + 1
        meta.update({"updated_at": now_kst().isoformat(), "_partial": False,
                     "_method": "deterministic_regex_slice",
                     # 🚨 RULE 12 ② — 반려 꼬리를 산출물이 스스로 신고한다.
                     #   개수만이 아니라 **이름으로** 남겨야 다음 세션이 열거할 수 있다(RULE 13 ③).
                     "misses_n": len(misses),
                     "misses_exhausted_n": sum(
                         1 for v in misses.values()
                         if int(v.get("n", 0)) >= MAX_OVERVIEW_ATTEMPTS),
                     "misses_by_reason": by_reason,
                     "max_overview_attempts": MAX_OVERVIEW_ATTEMPTS,
                     "last_axis_run": {"fresh": fresh, "cached": cached, "skipped": skipped,
                                       "exhausted_skip": exhausted_skip,
                                       "budget_stopped": budget_stopped,
                                       "rejects": reject_reasons}})
        cache["_meta"] = meta
        save_cache(cache)
    if budget_stopped:
        sys.stderr.write(f"[overview] ⏱ 축 예산 소진 — {budget_stopped}종목 미시도"
                         f"(다음 run 이어받음)\n")
    logger.info("[overview] 신규 %d · 캐시 %d · 반려 %d · 시도소진 skip %d · 예산중단 %d · 사유 %s",
                fresh, cached, skipped, exhausted_skip, budget_stopped, reject_reasons)
    return out
