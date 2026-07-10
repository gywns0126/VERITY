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

import json
import os
import re
import sys
import time
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
import hashlib
_PLACEHOLDER_MD5 = {"ad18dbe2ba", "38926c4ecb"}  # w미지정 310B / w=76 2588B 두 변형


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
        ok = len(b) > 0 and hashlib.md5(b).hexdigest()[:10] not in _PLACEHOLDER_MD5
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


def main() -> int:
    ok = False
    try:
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

        got = sum(1 for v in cache.values() if v)
        doc = {
            "_meta": {"generated_at": datetime.now(KST).isoformat(),
                      "source": "Brandfetch Logo Link 커버리지 실측 (빌드타임 확정)",
                      "total": len(cache), "with_logo": got, "fetched_this_run": fetched},
            "logos": {k: v for k, v in cache.items() if v},  # 발행은 보유분만 (경량)
            "_tried": {k: "" for k, v in cache.items() if not v},  # 증분 skip 용 시도 기록
        }
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
