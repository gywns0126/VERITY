#!/usr/bin/env python3
"""logo_map_builder — 종목별 최적 로고 URL 확정 (토스 핫링킹 완전 제거, PM 2026-07-10).

전략(실측 기반 2026-07-10):
  KR = ticker/{tk}.KS|.KQ 실로고 8/10 · 글자아이콘 2/10 → 글자아이콘(≤1KB)이면 domain/{도메인} 재시도.
  US = ticker/{tk} 커버 30/30. 미보유 = 엔트리 없음 → 컴포넌트 이니셜 아바타(기존).
  Brandfetch Logo Link = 브라우저 UA·Referer 컨텍스트 필수(실사이트 <img> 자연 충족), 무료 50만/월·출처표기 불요.

- 검증 콜은 빌드타임만(사용자 트래픽 쿼터 소모 0). 증분 캐시 — 확정분 skip, 신규 종목만.
- 출력 data/logo_map.json {logos: {ticker: "ticker/005930.KS" | "domain/xxx.com"}} — 컴포넌트가
  https://cdn.brandfetch.io/{path}?c={CLIENT_ID} 로 조립. 미등재 티커 = 이니셜.
🚨 RULE 7 무관(표시 자산). client id 는 공개 자산(임베드용) — 컴포넌트 상수 OK.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import io as _io
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_PATH = os.path.join(_ROOT, "data", "logo_map.json")
KR_REPORT = os.path.join(_ROOT, "data", "stock_report_public.json")
UNIVERSE_SEARCH = os.path.join(_ROOT, "data", "universe_search.json")

# ETF 운용사 · ETN 발행 증권사 브랜드 → 도메인 (2026-07-10 Brandfetch 실검증 — 전부 실로고 확인).
# 이름 프리픽스 startswith 매칭. 네트워크 0콜 즉시 배정.
BRAND_DOMAINS = [
    ("KODEX", "samsungfund.com"), ("TIGER", "investments.miraeasset.com"),
    ("RISE", "kbfg.com"), ("KBSTAR", "kbfg.com"), ("PLUS", "hanwhafund.co.kr"),
    ("ARIRANG", "hanwhafund.co.kr"), ("KIWOOM", "kiwoom.com"), ("SOL ", "shinhangroup.com"),
    ("HANARO", "nonghyup.com"), ("TIMEFOLIO", "timefolio.co.kr"), ("TIME", "timefolio.co.kr"),
    ("WON ", "woorifg.com"), ("KoAct", "samsungactive.co.kr"), ("에셋플러스", "assetplus.co.kr"),
    ("1Q", "hanafn.com"), ("파워", "kyobo.com"), ("BNK", "bnkfg.com"),
    # ETN 증권사 (Brandfetch 실로고 검증 통과만 — 미보유 브랜드(ACE·한투·메리츠·UNICORN·MIDAS)는 이니셜)
    ("KB ", "kbfg.com"), ("삼성 ", "samsung.com"), ("미래에셋", "securities.miraeasset.com"),
    ("신한", "shinhangroup.com"), ("키움", "kiwoom.com"), ("N2", "nhqv.com"),
    ("하나 ", "hanafn.com"), ("대신", "daishin.com"),
]


def _brand_domain(name: str) -> str:
    nm = str(name or "").strip()
    for pref, dom in BRAND_DOMAINS:
        if nm.startswith(pref.strip()) and (len(pref.strip()) > 2 or nm.startswith(pref)):
            return dom
    return ""
KR_DOMAINS = os.path.join(_ROOT, "data", "kr_corp_domains.json")
US_COMBINED = os.path.join(_ROOT, "data", "us_universe_combined.json")

MAX_SECONDS = int(os.environ.get("LOGO_MAP_MAX_SECONDS", "2400"))
THROTTLE = 0.12
HDR = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
       "Referer": "https://refreshed-fern-675581.framer.app/"}


def _cid() -> str:
    v = os.environ.get("BRANDFETCH_CLIENT_ID", "").strip()
    if v:
        return v
    try:
        env = open(os.path.join(_ROOT, ".env"), encoding="utf-8").read()
        m = re.search(r"BRANDFETCH_client_ID=([A-Za-z0-9_\-]+)", env, re.IGNORECASE)
        return m.group(1) if m else ""
    except OSError:
        return ""


# 🚨 Brandfetch 는 미보유 브랜드에 404 대신 자사 'B' 플레이스홀더 이미지를 반환 (fallback=404 무시,
#   2026-07-10 실측 — 크기 기준(1KB) 판별이 뚫려 'B' 로고 대량 채택 사고). 콘텐츠 md5 로 판별.
_PLACEHOLDER_MD5 = {"ad18dbe2ba", "38926c4ecb"}  # w미지정 310B / w=76 2588B 두 변형


def _is_blank(img_bytes: bytes) -> bool:
    """단색(순백 등) 균일 이미지 판별 — 2026-07-11 전수 실측에서 순백 로고 7건 발견 (md5 는
    요청 파라미터별로 달라져 가드 불가 → 콘텐츠 기반). PIL 실패 = 판별 불가로 통과."""
    try:
        from PIL import Image
        import io as _io
        im = Image.open(_io.BytesIO(img_bytes)).convert("RGBA").resize((16, 16))
        ext = im.getextrema()  # 채널별 (min, max)
        return all(mn == mx for mn, mx in ext)
    except Exception:  # noqa: BLE001
        return False


# 아이덴티티 색 (2026-07-10 PM — 토스식 타일 배경). 로고 대표색 자동 추출 + 주요 브랜드 공식 색 오버라이드.
# 오버라이드 = 공개된 브랜드 컬러(사실). 흑백 로고(삼성·애플 등)는 추출색이 검정 → 공식 색으로 보정.
BRAND_COLOR_OVERRIDE = {
    "005930": "#1428a0", "005935": "#1428a0",  # 삼성전자 블루
    "000660": "#ec1b23",  # SK하이닉스 레드
    "005380": "#002c5f", "000270": "#05141f",  # 현대차 네이비 · 기아 미드나잇
    "051910": "#a50034", "066570": "#a50034", "373220": "#a50034", "003550": "#a50034",  # LG 레드
    "035420": "#03c75a",  # 네이버 그린
    "035720": "#fee500",  # 카카오 옐로
    "005490": "#00477f",  # 포스코 블루
    "105560": "#ffbc00", "055550": "#0046ff",  # KB 옐로 · 신한 블루
    "068270": "#77c571",  # 셀트리온 그린 (로고 실색 — Brand API accent 는 웹 색이라 오차, 2026-07-11)
    "034730": "#ec1b23", "017670": "#ec1b23", "096770": "#ec1b23",  # SK 계열 레드
    "AAPL": "#555555", "MSFT": "#0078d4", "GOOGL": "#4285f4", "GOOG": "#4285f4",
    "AMZN": "#ff9900", "META": "#0866ff", "TSLA": "#e82127", "NVDA": "#76b900",
    "NFLX": "#e50914", "AMD": "#000000", "INTC": "#0068b5", "KO": "#f40009",
}


def _dominant_color(img_bytes: bytes):
    """로고 바이트 → 대표색 hex (저채도·흰색 제외 평균). 실패/무채색뿐 = None."""
    try:
        from PIL import Image
        import io as _io
        im = Image.open(_io.BytesIO(img_bytes)).convert("RGBA").resize((24, 24))
        px = [(r, g, b) for r, g, b, a in im.getdata() if a > 200 and not (r > 235 and g > 235 and b > 235)]
        if not px:
            return None
        sat = [(r, g, b) for r, g, b in px if max(r, g, b) - min(r, g, b) > 30]
        if not sat:
            return None  # 무채색 로고 — 틴트 없이 중립 타일
        n = len(sat)
        r = sum(q[0] for q in sat) // n; g = sum(q[1] for q in sat) // n; b = sum(q[2] for q in sat) // n
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:  # noqa: BLE001
        return None


def _logo_fetch(path: str, cid: str):
    """로고 경로 → (실로고 여부, bytes). Brandfetch 상대경로 또는 절대 URL(폴백 소스). 플레이스홀더 해시 제외."""
    url = path if path.startswith("http") else f"https://cdn.brandfetch.io/{path}?c={cid}"
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=12)
        if "image" not in (r.headers.get("content-type") or ""):
            return False, b""
        b = r.read()
        ok = len(b) > 0 and hashlib.md5(b).hexdigest()[:10] not in _PLACEHOLDER_MD5 and not _is_blank(b)
        return ok, b
    except Exception:  # noqa: BLE001
        return False, b""


def _logo_real(path: str, cid: str) -> bool:
    return _logo_fetch(path, cid)[0]


def _resolve_kr(tk: str, market: str, domain: str, cid: str) -> Optional[str]:
    mk = (market or "").upper()
    sufs = ["KQ"] if "KOSDAQ" in mk else (["KS"] if mk else ["KS", "KQ"])  # 미상 = 양쪽 시도
    for suf in sufs:
        p = f"ticker/{tk}.{suf}"
        if _logo_real(p, cid):
            return p
        time.sleep(THROTTLE)
    if domain and _logo_real(f"domain/{domain}", cid):
        return f"domain/{domain}"
    return None  # 플레이스홀더/미보유 = 이니셜 (B 로고 채택 금지)


_TOSS_HOST = "static.toss.im"
_TOSS_PATH = re.compile(r"^/png-icons/securities/icn-sec-fill-[A-Za-z0-9.-]+\.png$")
_VERIFY_MAX_BODY = 256 * 1024
_VERIFY_TIMEOUT = 5
_VERIFY_MAX_SECONDS = 55
_VERIFY_RECEIPT = os.path.join(_ROOT, "data", "metadata", "logo_map_source_receipt.json")
_VERIFY_LEGACY_RECEIPT = os.path.join(_ROOT, "output", "logo-map-url-verification.json")


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_toss_url(request, timeout: int):
    return urllib.request.build_opener(_NoRedirectHandler()).open(request, timeout=timeout)


def _is_toss_logo_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname == _TOSS_HOST
                and parsed.port in (None, 443) and not parsed.username and not parsed.password
                and not parsed.query and not parsed.fragment and bool(_TOSS_PATH.fullmatch(parsed.path)))
    except (TypeError, ValueError):
        return False


def _stratified_logo_sample(doc: dict, universe: dict, sample_size: int = 16) -> list[dict]:
    if sample_size != 16:
        raise ValueError("initial logo URL verification is fixed at 16 samples")
    logos = doc.get("logos") or {}
    stocks = universe.get("stocks") or []
    markets = {str(row.get("ticker")): str(row.get("market") or "").upper()
               for row in stocks if isinstance(row, dict) and row.get("ticker")}
    eligible = {str(tk): url for tk, url in logos.items()
                if isinstance(tk, str) and _is_toss_logo_url(url)}
    groups = {
        "KR": sorted(tk for tk in eligible if markets.get(tk) in {"KR", "KONEX"}),
        "ETF": sorted(tk for tk in eligible if markets.get(tk) in {"ETF", "ETN"}),
        "US": sorted(tk for tk in eligible if markets.get(tk) == "US"),
    }
    if any(len(groups[name]) < 4 for name in groups) or len(eligible) < 16:
        raise ValueError("insufficient eligible Toss URLs for the approved 16-sample plan")
    seed = int(hashlib.sha256(json.dumps(doc.get("logos", {}), sort_keys=True).encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    chosen: list[dict] = []
    chosen_tickers: set[str] = set()
    for name in ("KR", "ETF", "US"):
        for ticker in rng.sample(groups[name], 4):
            chosen.append({"group": name, "ticker": ticker, "url": eligible[ticker]})
            chosen_tickers.add(ticker)
    remaining = sorted(set(eligible) - chosen_tickers)
    for ticker in rng.sample(remaining, 4):
        chosen.append({"group": "random", "ticker": ticker, "url": eligible[ticker]})
    return chosen


def _check_toss_logo(sample: dict) -> dict:
    url = sample["url"]
    started = time.monotonic()
    result = {"group": sample["group"], "url_sha256": hashlib.sha256(url.encode()).hexdigest(),
              "host": _TOSS_HOST, "http_status": None, "content_type": "", "bytes_read": 0,
              "body_truncated": False, "width": None, "height": None, "sha256": "",
              "decoded": False, "blank": None, "query_ok": False,
              "source_quality_bad": False, "ok": False, "failure": "", "stop_required": False}
    try:
        if not _is_toss_logo_url(url):
            result["failure"] = "unapproved_host_or_path"
            result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 1)
            return result
        request = urllib.request.Request(url, headers={"User-Agent": "VERITY-logo-url-check/1.0"}, method="GET")
        with _open_toss_url(request, timeout=_VERIFY_TIMEOUT) as response:
            result["http_status"] = response.getcode()
            if hasattr(response, "geturl") and not _is_toss_logo_url(response.geturl()):
                result["failure"] = "unapproved_redirect_target"
                result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 1)
                return result
            result["content_type"] = (response.headers.get("content-type") or "").split(";", 1)[0].lower()
            body = response.read(_VERIFY_MAX_BODY + 1)
        result["bytes_read"] = min(len(body), _VERIFY_MAX_BODY)
        result["body_truncated"] = len(body) > _VERIFY_MAX_BODY
        if result["http_status"] != 200:
            result["failure"] = "http_status"
        elif not result["content_type"].startswith("image/"):
            result["failure"] = "non_image_mime"
        elif result["body_truncated"]:
            result["failure"] = "body_over_limit"
        else:
            result["query_ok"] = True
            result["sha256"] = hashlib.sha256(body).hexdigest()
            from PIL import Image
            image = Image.open(_io.BytesIO(body))
            image.verify()
            image = Image.open(_io.BytesIO(body)).convert("RGBA")
            result["width"], result["height"] = image.size
            result["decoded"] = result["width"] > 0 and result["height"] > 0
            result["blank"] = _is_blank(body)
            result["ok"] = result["decoded"] and not result["blank"]
            if not result["ok"]:
                result["source_quality_bad"] = True
                result["failure"] = "blank_or_undecodable"
    except urllib.error.HTTPError as exc:
        result["http_status"] = exc.code
        result["failure"] = "http_status"
    except Exception as exc:  # noqa: BLE001
        result["failure"] = type(exc).__name__
        if result["query_ok"]:
            result["source_quality_bad"] = True
    result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 1)
    result["stop_required"] = result["http_status"] in (403, 429)
    return result


def validate_logo_map_source_receipt(receipt_path: str = _VERIFY_RECEIPT, map_path: str = OUT_PATH,
                                      expected_total: Optional[int] = None, now: Optional[datetime] = None) -> dict:
    """Validate receipt provenance and expose a bounded-query clock without claiming map-wide freshness."""
    try:
        receipt = json.load(open(receipt_path, encoding="utf-8"))
        map_bytes = open(map_path, "rb").read()
    except (OSError, ValueError) as exc:
        raise ValueError("logo-map source receipt or map unavailable") from exc
    map_hash = hashlib.sha256(map_bytes).hexdigest()
    try:
        map_doc = json.loads(map_bytes)
    except ValueError as exc:
        raise ValueError("logo-map source map is invalid") from exc
    if not isinstance(receipt, dict) or not isinstance(map_doc, dict):
        raise ValueError("logo-map source receipt or map structure invalid")
    logos = map_doc.get("logos") or {}
    if not isinstance(logos, dict):
        raise ValueError("logo-map source map entries invalid")
    actual_total = sum(1 for value in logos.values() if _is_toss_logo_url(value))
    if receipt.get("map_sha256") != map_hash:
        raise ValueError("logo-map source receipt map hash mismatch")
    raw_counts = {
        "total": receipt.get("total", receipt.get("eligible_toss_url_count")),
        "selected": receipt.get("selected", receipt.get("sample_target")),
        "checked": receipt.get("checked", receipt.get("sampled")),
        "passed": receipt.get("passed", receipt.get("ok")),
        "failed": receipt.get("failed"),
    }
    if any(type(value) is not int for value in raw_counts.values()):
        raise ValueError("logo-map source receipt counts must be integers")
    total, selected, checked, passed, failed = (raw_counts[k] for k in ("total", "selected", "checked", "passed", "failed"))
    if (expected_total is not None and (type(expected_total) is not int or expected_total < 0)):
        raise ValueError("expected logo-map source denominator invalid")
    if ((expected_total is not None and total != expected_total) or total != actual_total
            or not (0 <= passed <= checked <= selected <= total)):
        raise ValueError("logo-map source receipt scope invalid")
    if receipt.get("source_host", _TOSS_HOST) != _TOSS_HOST:
        raise ValueError("logo-map source receipt host invalid")
    if failed != checked - passed:
        raise ValueError("logo-map source receipt result counts inconsistent")
    rows = receipt.get("results")
    if not isinstance(rows, list) or len(rows) != checked:
        raise ValueError("logo-map source receipt result rows inconsistent")
    row_passed = 0
    row_blocked = False
    row_quality_bad = 0
    for row in rows:
        if not isinstance(row, dict) or type(row.get("ok")) is not bool:
            raise ValueError("logo-map source receipt result row invalid")
        if any(key in row for key in ("ticker", "url", "body", "response_body")):
            raise ValueError("logo-map source receipt contains disallowed detail")
        if row.get("host", _TOSS_HOST) != _TOSS_HOST:
            raise ValueError("logo-map source receipt result host invalid")
        code = row.get("http_status")
        if code is not None and type(code) is not int:
            raise ValueError("logo-map source receipt HTTP status invalid")
        blocked_row = code in (403, 429)
        row_blocked = row_blocked or blocked_row
        if "stop_required" in row and (type(row["stop_required"]) is not bool or row["stop_required"] != blocked_row):
            raise ValueError("logo-map source receipt stop flag inconsistent")
        if row["ok"] and (code != 200 or row.get("decoded") is not True
                           or row.get("blank") is not False
                           or not str(row.get("content_type", "")).startswith("image/")):
            raise ValueError("logo-map source receipt success row inconsistent")
        row_passed += int(row["ok"])
        row_quality = row.get("source_quality_bad")
        inferred_quality_bad = bool(code == 200 and (row.get("decoded") is False or row.get("blank") is True))
        if row_quality is None:
            row_quality = inferred_quality_bad
        elif type(row_quality) is not bool or row_quality != inferred_quality_bad:
            raise ValueError("logo-map source receipt quality row invalid")
        row_quality_bad += int(row_quality)
    if row_passed != passed:
        raise ValueError("logo-map source receipt passed count inconsistent")
    source_blocked = row_blocked
    for flag in ("source_blocked", "stopped_on_403_or_429"):
        if flag in receipt and (type(receipt[flag]) is not bool or receipt[flag] != source_blocked):
            raise ValueError("logo-map source receipt block summary inconsistent")
    if "source_quality_bad" in receipt:
        quality_summary = receipt["source_quality_bad"]
        if type(quality_summary) is not int or quality_summary != row_quality_bad:
            raise ValueError("logo-map source receipt quality summary inconsistent")
    all_records_revalidated = checked == total and passed == total and not source_blocked
    if "all_records_revalidated" in receipt:
        if type(receipt["all_records_revalidated"]) is not bool or receipt["all_records_revalidated"] != all_records_revalidated:
            raise ValueError("logo-map source receipt full-scope summary inconsistent")
    if "query_complete" in receipt:
        if type(receipt["query_complete"]) is not bool or receipt["query_complete"] != (checked == selected):
            raise ValueError("logo-map source receipt query summary inconsistent")
    stamp = receipt.get("checked_at")
    try:
        checked_at = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValueError("logo-map source receipt timestamp invalid")
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ValueError("logo-map source receipt timestamp must include a timezone")
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ValueError("validation clock must include a timezone")
    if checked_at.astimezone(timezone.utc) > now_utc.astimezone(timezone.utc):
        raise ValueError("logo-map source receipt timestamp is in the future")
    unattempted = selected - checked
    quality_bad = row_quality_bad
    if source_blocked:
        status, quality_reason = "source_blocked", "source_access_stop"
        expected_receipt_status = "source_blocked"
    elif checked < selected:
        status, quality_reason = "incomplete", "query_incomplete"
        expected_receipt_status = "partial"
    elif passed == selected:
        status, quality_reason = "sample_complete", ""
        expected_receipt_status = "sampled"
    elif quality_bad:
        status, quality_reason = "source_quality_error", "bad_image_payload"
        expected_receipt_status = "source_or_quality_error"
    else:
        status, quality_reason = "query_error", "source_query_failed"
        expected_receipt_status = "source_or_quality_error"
    declared_status = receipt.get("status")
    if declared_status is not None and declared_status != expected_receipt_status:
        raise ValueError("logo-map source receipt status inconsistent with scope")
    normalized = {
        "clock_kind": "bounded_logo_url_query",
        "bound_query_incomplete": checked < total,
        "checked_at": checked_at.astimezone(timezone.utc).isoformat(),
        "map_sha256": map_hash,
        "source_host": receipt.get("source_host", _TOSS_HOST),
        "scope_counts": {"selected": selected, "attempted": checked, "passed": passed,
                         "failed": failed, "unattempted": unattempted, "total": total},
        "status": status,
        "quality_reason": quality_reason,
        "source_quality_bad": quality_bad,
        "all_records_revalidated": all_records_revalidated,
    }
    if not source_blocked and checked == selected and passed == selected and passed > 0:
        normalized["completed_at"] = checked_at.astimezone(timezone.utc).isoformat()
    return normalized


def verify_existing_toss_urls(receipt_path: str = _VERIFY_RECEIPT, max_seconds: float = _VERIFY_MAX_SECONDS,
                              resume: bool = False) -> int:
    """Check a bounded sample of existing public Toss URLs without touching the map artifact."""
    with open(OUT_PATH, "rb") as f:
        map_bytes = f.read()
    doc = json.loads(map_bytes)
    map_hash = hashlib.sha256(map_bytes).hexdigest()
    receipts_to_check = [receipt_path]
    if receipt_path != _VERIFY_LEGACY_RECEIPT:
        receipts_to_check.append(_VERIFY_LEGACY_RECEIPT)
    if not resume:
        for existing_path in receipts_to_check:
            if not os.path.exists(existing_path):
                continue
            try:
                previous = json.load(open(existing_path, encoding="utf-8"))
            except (OSError, ValueError):
                previous = {}
            if (previous.get("map_sha256") == map_hash
                    and (previous.get("source_blocked") or previous.get("stopped_on_403_or_429"))):
                print("[logo_map] verify-only blocked receipt exists for unchanged map; network skipped", file=sys.stderr)
                return 1
    with open(UNIVERSE_SEARCH, encoding="utf-8") as f:
        universe = json.load(f)
    sample = _stratified_logo_sample(doc, universe)
    started = time.monotonic()
    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for offset in range(0, len(sample), 2):
            if time.monotonic() - started >= max_seconds:
                break
            batch = sample[offset:offset + 2]
            futures = [pool.submit(_check_toss_logo, item) for item in batch]
            blocked = False
            for future in concurrent.futures.as_completed(futures):
                row = future.result()
                results.append(row)
                blocked = blocked or row["stop_required"]
            if blocked:
                break
            if offset + 2 < len(sample):
                time.sleep(THROTTLE)
    elapsed = [row["elapsed_ms"] for row in results]
    successful_bytes = [row["bytes_read"] for row in results if row["ok"]]
    logos = doc.get("logos") or {}
    total_urls = sum(1 for value in logos.values() if _is_toss_logo_url(value))
    selected = len(sample)
    checked = len(results)
    passed = sum(1 for row in results if row["ok"])
    source_blocked = any(row["stop_required"] for row in results)
    receipt = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "source": "existing_logo_map_url_sample",
        "source_host": _TOSS_HOST,
        "map_sha256": map_hash,
        "map_entry_count": len(logos),
        "selected": selected,
        "checked": checked,
        "passed": passed,
        "failed": checked - passed,
        "total": total_urls,
        "all_records_revalidated": checked == total_urls and passed == total_urls and not source_blocked,
        "query_complete": checked == selected,
        "source_blocked": source_blocked,
        "source_block_reason": "http_403_or_429" if source_blocked else "",
        "source_quality_bad": sum(1 for row in results if row["source_quality_bad"]),
        "source_quality_unverified": sum(1 for row in results if not row["query_ok"]),
        "status": ("source_blocked" if source_blocked else
                   "partial" if checked < selected else
                   "sampled" if passed == selected else "source_or_quality_error"),
        "max_seconds": max_seconds,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "p50_elapsed_ms": round(sorted(elapsed)[(len(elapsed) - 1) // 2], 1) if elapsed else None,
        "mean_elapsed_ms": round(sum(elapsed) / len(elapsed), 1) if elapsed else None,
        "mean_success_bytes": round(sum(successful_bytes) / len(successful_bytes), 1) if successful_bytes else None,
        "estimated_full_request_count": total_urls,
        "estimated_full_bytes_from_sample": round(sum(successful_bytes) / len(successful_bytes) * total_urls) if successful_bytes else None,
        "results": results,
    }
    os.makedirs(os.path.dirname(receipt_path), exist_ok=True)
    temp_path = receipt_path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, receipt_path)
    print("[logo_map] verify-only logged=True · map unchanged · "
          f"sample {passed}/{checked}/{selected} · Toss URLs {total_urls} · status={receipt['status']}", file=sys.stderr)
    return 0 if checked == selected and passed == selected and not source_blocked else 1


def main() -> int:
    ok = False
    try:
        if os.environ.get("LOGO_MAP_VERIFY_EXISTING") == "1":
            result = verify_existing_toss_urls(resume=os.environ.get("LOGO_MAP_VERIFY_RESUME") == "1")
            ok = True  # A current or newly written receipt exists; block state is the nonzero exit.
            return result
        try:
            previous = json.load(open(OUT_PATH, encoding="utf-8"))
        except (OSError, ValueError):
            previous = {}
        if (previous.get("_meta") or {}).get("logo_source") == "toss_temp":
            print("[logo_map] toss_temp map preserved; use verify-only mode; no source migration performed", file=sys.stderr)
            ok = True
            return 0
        cid = _cid()
        if not cid:
            print("[logo_map] BRANDFETCH_CLIENT_ID 없음 — skip", file=sys.stderr)
            return 0
        # ── 폴백 백필 모드 (LOGO_FALLBACK_BACKFILL=1): 미보유(_tried) → nvstly(US)·공식 파비콘(KR) ──
        #   커버리지 최대화 (PM 2026-07-10 "토스 이상"). 가독성 게이트 = PIL 해상도 ≥40px (저질 파비콘 = 이니셜 유지).
        #   구글 s2 = 미보유 시 404 (플레이스홀더 無) · nvstly = MIT 계열 공개 아이콘 repo (US 소형주 커버).
        if os.environ.get("LOGO_FALLBACK_BACKFILL") == "1":
            doc = json.load(open(OUT_PATH, encoding="utf-8"))
            logos = doc.get("logos") or {}
            tried = doc.get("_tried") or {}
            try:
                domains = json.load(open(KR_DOMAINS, encoding="utf-8")).get("domains", {})
            except (OSError, ValueError):
                domains = {}

            def _img_wh(b: bytes):
                try:
                    from PIL import Image
                    import io as _io
                    return Image.open(_io.BytesIO(b)).size
                except Exception:  # noqa: BLE001
                    return (0, 0)

            def _grab(u: str):
                try:
                    r = urllib.request.urlopen(urllib.request.Request(u, headers=HDR), timeout=10)
                    if "image" not in (r.headers.get("content-type") or "") and not u.endswith(".png"):
                        return b""
                    return r.read()
                except Exception:  # noqa: BLE001
                    return b""

            t0 = time.monotonic()
            added_us = added_kr = 0
            for tk in list(tried.keys()):
                if time.monotonic() - t0 > MAX_SECONDS:
                    print("[logo_map] 폴백 budget 도달", file=sys.stderr)
                    break
                if tk in logos:
                    tried.pop(tk, None)
                    continue
                if not tk.isdigit():  # US → nvstly
                    b = _grab(f"https://raw.githubusercontent.com/nvstly/icons/main/ticker_icons/{tk}.png")
                    if len(b) > 500 and _img_wh(b)[0] >= 40:
                        logos[tk] = f"https://raw.githubusercontent.com/nvstly/icons/main/ticker_icons/{tk}.png"
                        tried.pop(tk, None)
                        added_us += 1
                else:  # KR → 공식 파비콘 (구글 s2 프록시, 도메인 필요)
                    dom = domains.get(tk)
                    if dom:
                        u = f"https://www.google.com/s2/favicons?domain={dom}&sz=128"
                        b = _grab(u)
                        if len(b) > 900 and _img_wh(b)[0] >= 40:  # 저해상(16px 업스케일 등) = 이니셜 유지
                            logos[tk] = u
                            tried.pop(tk, None)
                            added_kr += 1
                time.sleep(THROTTLE)
            doc["logos"] = logos
            doc["_tried"] = tried
            doc["_meta"]["with_logo"] = len(logos)
            json.dump(doc, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False)
            print(f"[logo_map] 폴백 logged=True · +US {added_us} +KR {added_kr} → 총 {len(logos)}", file=sys.stderr)
            return 0

        # ── 컬러 백필 모드 (LOGO_COLOR_BACKFILL=1): 확정 map 의 로고들 대표색만 채움 ──
        if os.environ.get("LOGO_COLOR_BACKFILL") == "1":
            doc = json.load(open(OUT_PATH, encoding="utf-8"))
            logos = doc.get("logos") or {}
            colors = doc.get("colors") or {}
            shapes = doc.get("shapes") or {}
            t0 = time.monotonic()
            done = 0
            for tk, path in logos.items():
                if tk in colors:
                    continue
                if time.monotonic() - t0 > MAX_SECONDS:
                    print("[logo_map] 색 백필 budget 도달", file=sys.stderr)
                    break
                okf, b = _logo_fetch(path, cid)
                # 모양(가로세로비) — 심볼(≈1.0) vs 워드마크(>2). 컴포넌트 패딩 적응용
                if okf:
                    try:
                        from PIL import Image
                        import io as _io
                        w2, h2 = Image.open(_io.BytesIO(b)).size
                        shapes[tk] = round(w2 / h2, 2) if h2 else 0
                    except Exception:  # noqa: BLE001
                        pass
                if tk in BRAND_COLOR_OVERRIDE:
                    colors[tk] = BRAND_COLOR_OVERRIDE[tk]
                else:
                    c = _dominant_color(b) if okf else None
                    colors[tk] = c or ""
                done += 1
                time.sleep(THROTTLE)
            doc["colors"] = colors
            doc["shapes"] = shapes
            # 표시 튜닝 노브 (발행 데이터 — Framer 수정 없이 조절): padS=심볼 패딩% padW=워드마크 wideRatio=기준
            doc["style"] = doc.get("style") or {"padS": 8, "padW": 15, "wideRatio": 2.2}
            doc["_meta"]["colors_n"] = sum(1 for v in colors.values() if v)
            json.dump(doc, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False)
            print(f"[logo_map] 색 백필 logged=True · 이번 {done} · 색 보유 {doc['_meta']['colors_n']}/{len(logos)}", file=sys.stderr)
            return 0
        try:
            _prev = json.load(open(OUT_PATH, encoding="utf-8"))
            cache: Dict[str, str] = dict(_prev.get("logos", {}))
            cache.update({k: "" for k in (_prev.get("_tried") or {})})  # 미보유 시도분도 skip (증분)
        except (OSError, ValueError):
            _prev = {}
            cache = {}

        # 유니버스 = universe_search 전체 (KR+ETF+ETN+KONEX+US ≈ 9,363) — 검색되는 종목 전부 커버.
        uni = json.load(open(UNIVERSE_SEARCH, encoding="utf-8")).get("stocks", [])
        # KR 주식 시장구분(KS/KQ)은 리포트 market 사용, 미상은 domain-first + 양쪽 시도
        rep = json.load(open(KR_REPORT, encoding="utf-8"))
        mk_map = {str(s.get("ticker")): str(s.get("market") or "") for s in rep.get("stocks", [])}
        kr = [(str(x.get("ticker")), mk_map.get(str(x.get("ticker")), ""))
              for x in uni if x.get("market") in ("KR", "KONEX")
              and re.match(r"^\d{6}$", str(x.get("ticker") or ""))]
        etfn = [(str(x.get("ticker")), str(x.get("name") or "")) for x in uni
                if x.get("market") in ("ETF", "ETN")]
        try:
            domains = json.load(open(KR_DOMAINS, encoding="utf-8")).get("domains", {})
        except (OSError, ValueError):
            domains = {}
        us = [str(x.get("ticker")).upper() for x in uni if x.get("market") == "US"]

        t0 = time.monotonic()
        fetched = 0
        # ETF/ETN — 브랜드 프리픽스 → 운용사/증권사 도메인 (네트워크 0콜, 실검증 맵)
        n_brand = 0
        for tk, nm in etfn:
            if tk in cache:
                continue
            d = _brand_domain(nm)
            cache[tk] = f"domain/{d}" if d else ""
            n_brand += 1
        if n_brand:
            print(f"[logo_map] ETF/ETN 브랜드 배정 {n_brand}", file=sys.stderr)
        # KR — 티커 조회 → 도메인 재시도
        for tk, mk in kr:
            if tk in cache:
                continue
            if time.monotonic() - t0 > MAX_SECONDS:
                break
            p = _resolve_kr(tk, mk, domains.get(tk, ""), cid)
            cache[tk] = p or ""
            fetched += 1
            time.sleep(THROTTLE)
        # US — 티커 조회 (실측 30/30, 크기 무관 수용: 글자아이콘도 통일감)
        for tk in us:
            if tk in cache:
                continue
            if time.monotonic() - t0 > MAX_SECONDS:
                print("[logo_map] budget 도달 — 나머지 다음 회차", file=sys.stderr)
                break
            cache[tk] = f"ticker/{tk}" if _logo_real(f"ticker/{tk}", cid) else ""
            fetched += 1
            time.sleep(THROTTLE)

        if fetched == 0:
            print("[logo_map] fetched_this_run=0; artifact and generated_at preserved", file=sys.stderr)
            ok = True
            return 0
        got = sum(1 for v in cache.values() if v)
        meta = dict(_prev.get("_meta") or {})
        meta.update({"generated_at": datetime.now(KST).isoformat(),
                     "source": "Brandfetch Logo Link incremental coverage check",
                     "total": len(cache), "with_logo": got, "fetched_this_run": fetched})
        doc = {
            "_meta": meta,
            "logos": {k: v for k, v in cache.items() if v},  # 발행은 보유분만 (경량)
            "_tried": {k: "" for k, v in cache.items() if not v},  # 증분 skip 용 시도 기록
        }
        for field in ("colors", "shapes", "style"):
            if field in _prev:
                doc[field] = _prev[field]
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        print(f"[logo_map] logged=True · 캐시 {len(cache)} · 로고 {got} · 이번확정 {fetched}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[logo_map] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[logo_map] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
