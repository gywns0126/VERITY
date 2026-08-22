#!/usr/bin/env python3
"""로고 후보 수집 + 검수 HTML 생성 — 사람 작업을 '찾기' 에서 '고르기' 로 줄인다.

왜: logo.dev 가 못 채운 잔여 종목을 사람이 직접 찾으면 장당 2~4분(336장 ≈ 17시간)이다.
찾기는 기계가 하고 사람은 **맞는지 한 번 고르기만** 하면 종목당 3초 — 20분으로 준다.
🚨 고르는 단계를 없애면 안 된다. 자동 판별은 실측에서 **23% 오수확**했고 최악은
   타사 로고 혼입(혜인 자리에 Vermeer)이었다 — 조용히 틀린 로고는 없는 것보다 나쁘다.

후보 3소스 (겹치게 모아 사람이 고르게 한다):
  ① 홈페이지 스크레이핑  — DART hm_url → 헤더 img/CSS배경/srcset/위치휴리스틱 (단독 적중 33%)
  ② 네이버 이미지 검색    — "<회사명> CI" (단독 정확도 낮지만 후보로는 유효)
  ③ logo.dev 도메인 변형  — 등록 도메인 표기가 흔들리는 경우 회수 (co.kr↔com, 서브도메인 제거)

산출: data/metadata/logo_candidates.json + logo_review.html (자기완결 — 이미지 data URI 내장,
      서버 불필요. 브라우저에서 클릭 → JSON 내려받기)

사용:
  python3 scripts/logo/candidates.py --missing            # logo_coverage.json 의 미보유 전체
  python3 scripts/logo/candidates.py --tickers 005930,000660
  python3 scripts/logo/candidates.py --missing --limit 40 # 먼저 소량으로 확인
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import html as htmlmod
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import requests
import urllib3
from PIL import Image

urllib3.disable_warnings()
KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
COVERAGE = os.path.join(_ROOT, "data", "metadata", "logo_coverage.json")
DOM_CACHE = os.path.join(_ROOT, "data", "metadata", "corp_homepage.json")
OUT_JSON = os.path.join(_ROOT, "data", "metadata", "logo_candidates.json")
OUT_HTML = os.path.join(_ROOT, "data", "metadata", "logo_review.html")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/126 Safari/537.36"}
THUMB = 150


def _env(k):
    try:
        for l in open(os.path.join(_ROOT, ".env"), encoding="utf-8", errors="ignore"):
            if "=" in l and l.split("=", 1)[0].strip() == k:
                return l.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return os.environ.get(k)


# ── ① 홈페이지 스크레이핑 ─────────────────────────────────────────────────────
def scrape_urls(domain):
    """헤더 로고 후보 URL. 🚨 favicon 은 제외 — 16~32px 라 쓸 수 없다(실측)."""
    if not domain:
        return []
    base = "https://" + domain
    try:
        r = requests.get(base, headers=UA, timeout=12, verify=False)
        page, base = r.text, r.url
    except Exception:  # noqa: BLE001
        return []
    out = {}

    def add(u, sc):
        if u and not u.startswith("data:"):
            u = requests.compat.urljoin(base, u.strip())
            out[u] = max(out.get(u, 0), sc)

    for tag in re.findall(r"<img[^>]+>", page, re.I):
        low = tag.lower()
        sc = ("logo" in low) * 5 + ("symbol" in low) * 3 + ("brand" in low) * 3 + ("header" in low) * 2
        m = re.search(r'src=["\']([^"\']+)', tag, re.I)
        if m and sc:
            add(m.group(1), sc)
    for m in re.finditer(r"url\(['\"]?([^)'\"]+)['\"]?\)", page, re.I):
        seg = page[max(0, m.start() - 160):m.start()].lower()
        if "logo" in seg or "symbol" in seg:
            add(m.group(1), 4)
    head = re.search(r"<(header|nav)[^>]*>(.{0,4000}?)</\1>", page, re.I | re.S)
    if head:
        m = re.search(r'<img[^>]+src=["\']([^"\']+)', head.group(2), re.I)
        if m:
            add(m.group(1), 4)
    return [u for u, _ in sorted(out.items(), key=lambda kv: -kv[1])][:4]


# ── ② 네이버 이미지 검색 ──────────────────────────────────────────────────────
def naver_urls(name):
    cid, csec = _env("NAVER_Client_ID"), _env("NAVER_Client_Secret")
    if not (cid and csec):
        return []
    try:
        r = requests.get("https://openapi.naver.com/v1/search/image",
                         params={"query": f"{name} CI 로고", "display": 4, "sort": "sim"},
                         headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec},
                         timeout=10)
        return [it["link"] for it in (r.json().get("items") or [])][:4] if r.status_code == 200 else []
    except Exception:  # noqa: BLE001
        return []


# ── ③ logo.dev 도메인 변형 ────────────────────────────────────────────────────
def logodev_urls(domain, name, token):
    if not token:
        return []
    out = []
    if domain:
        variants = {domain}
        variants.add(re.sub(r"\.co\.kr$", ".com", domain))
        variants.add(re.sub(r"^[a-z0-9-]+\.(?=[a-z0-9-]+\.[a-z.]+$)", "", domain))  # 서브도메인 제거
        for d in variants:
            out.append(f"https://img.logo.dev/{d}?token={token}&size=480&fallback=404")
    out.append(f"https://img.logo.dev/name/{requests.utils.quote(name)}?token={token}&size=480&fallback=404")
    return out[:4]


def fetch_thumb(url):
    """다운로드 → 썸네일 data URI. 실패·부적격은 None."""
    try:
        r = requests.get(url, headers=UA, timeout=10, verify=False)
        if r.status_code != 200 or len(r.content) < 300:
            return None
        im = Image.open(io.BytesIO(r.content))
        w, h = im.size
        if max(w, h) < 60 or w * h < 3000:
            return None
        im = im.convert("RGBA")
        im.thumbnail((THUMB, THUMB))
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        return {"url": url, "w": w, "h": h,
                "thumb": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}
    except Exception:  # noqa: BLE001
        return None


def gather(row, token):
    tk, nm, dom = row["ticker"], row["name"], row.get("domain") or ""
    urls = []
    for u in logodev_urls(dom, nm, token):
        urls.append(("logo.dev", u))
    for u in scrape_urls(dom):
        urls.append(("홈페이지", u))
    for u in naver_urls(nm):
        urls.append(("네이버", u))
    cands, seen = [], set()
    for src, u in urls:
        if u in seen:
            continue
        seen.add(u)
        t = fetch_thumb(u)
        if t:
            t["src"] = src
            cands.append(t)
        if len(cands) >= 6:
            break
    return {"ticker": tk, "name": nm, "domain": dom, "candidates": cands}


HTML_HEAD = """<meta charset="utf-8"><title>로고 검수</title>
<style>
 body{font:14px/1.5 -apple-system,'Apple SD Gothic Neo',sans-serif;margin:0;background:#f6f7f9;color:#111}
 header{position:sticky;top:0;background:#fff;border-bottom:1px solid #e3e6ea;padding:12px 18px;z-index:9;
   display:flex;gap:16px;align-items:center}
 header b{font-size:16px} #prog{color:#555}
 button{font:inherit;padding:7px 14px;border-radius:8px;border:1px solid #d0d4da;background:#fff;cursor:pointer}
 button.pri{background:#111;color:#fff;border-color:#111}
 .row{background:#fff;margin:10px 14px;border:1px solid #e3e6ea;border-radius:12px;padding:12px 14px}
 .row.done{opacity:.45}
 .hd{display:flex;gap:10px;align-items:baseline;margin-bottom:9px}
 .hd .nm{font-weight:600} .hd .tk{color:#888;font-size:12px} .hd .dm{color:#aaa;font-size:12px}
 .cands{display:flex;gap:10px;flex-wrap:wrap}
 .c{border:2px solid #e3e6ea;border-radius:10px;padding:6px;cursor:pointer;text-align:center;width:150px;background:#fff}
 .c:hover{border-color:#8a8f98}
 .c.sel{border-color:#111;box-shadow:0 0 0 2px #1113}
 .c img{max-width:136px;max-height:120px;display:block;margin:0 auto}
 .c .meta{font-size:11px;color:#888;margin-top:5px}
 .none{width:150px;height:150px;display:flex;align-items:center;justify-content:center;color:#999}
 .none.sel{border-color:#c33;color:#c33}
</style>"""

HTML_JS = """
<script>
const sel={};
function pick(tk,idx,el){
  sel[tk]=idx;
  const row=el.closest('.row');
  row.querySelectorAll('.c,.none').forEach(x=>x.classList.remove('sel'));
  el.classList.add('sel'); row.classList.add('done');
  document.getElementById('prog').textContent=Object.keys(sel).length+' / '+TOTAL+' 선택';
}
function save(){
  const out={_meta:{picked_at:new Date().toISOString(),total:TOTAL,picked:Object.keys(sel).length},picks:{}};
  for(const tk in sel){ const i=sel[tk];
    out.picks[tk] = (i<0) ? null : DATA[tk].candidates[i].url; }
  const b=new Blob([JSON.stringify(out,null,1)],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(b);
  a.download='logo_picks.json'; a.click();
}
</script>"""


def build_html(rows):
    data = {r["ticker"]: {"candidates": [{"url": c["url"]} for c in r["candidates"]]} for r in rows}
    parts = [HTML_HEAD,
             f"<header><b>로고 검수</b><span id='prog'>0 / {len(rows)} 선택</span>"
             "<span style='color:#888'>맞는 로고를 클릭 · 없으면 '없음'</span>"
             "<button class='pri' onclick='save()'>선택 저장(JSON)</button></header>"]
    for r in rows:
        parts.append(f"<div class='row'><div class='hd'><span class='nm'>{htmlmod.escape(r['name'])}</span>"
                     f"<span class='tk'>{r['ticker']}</span>"
                     f"<span class='dm'>{htmlmod.escape(r['domain'] or '도메인 없음')}</span></div><div class='cands'>")
        for i, c in enumerate(r["candidates"]):
            parts.append(f"<div class='c' onclick=\"pick('{r['ticker']}',{i},this)\">"
                         f"<img src='{c['thumb']}'><div class='meta'>{c['src']} · {c['w']}x{c['h']}</div></div>")
        parts.append(f"<div class='c none' onclick=\"pick('{r['ticker']}',-1,this)\">없음</div>")
        parts.append("</div></div>")
    parts.append(f"<script>const TOTAL={len(rows)};const DATA={json.dumps(data, ensure_ascii=False)};</script>")
    parts.append(HTML_JS)
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--missing", action="store_true", help="logo_coverage.json 의 미보유 종목")
    ap.add_argument("--tickers", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--token", default=None)
    a = ap.parse_args()
    token = a.token or _env("LOGODEV_TOKEN")

    doms = json.load(open(DOM_CACHE, encoding="utf-8")) if os.path.exists(DOM_CACHE) else {}
    rows = []
    if a.missing:
        if not os.path.exists(COVERAGE):
            print("[cand] logo_coverage.json 없음 — census.py 먼저", file=sys.stderr)
            return 2
        cov = json.load(open(COVERAGE, encoding="utf-8"))
        rows = [{"ticker": s["ticker"], "name": s["name"], "domain": s.get("domain") or ""}
                for s in cov["stocks"] if not (s["ticker_ok"] or s["domain_ok"])]
    elif a.tickers:
        uni = {s["ticker"]: (s.get("name") or s["ticker"])
               for s in json.load(open(os.path.join(_ROOT, "data", "stock_report_public.json"),
                                       encoding="utf-8"))["stocks"]}
        for tk in [x.strip() for x in a.tickers.split(",") if x.strip()]:
            rows.append({"ticker": tk, "name": uni.get(tk, tk), "domain": doms.get(tk, "")})
    else:
        print("[cand] --missing 또는 --tickers 필요", file=sys.stderr)
        return 2
    if a.limit:
        rows = rows[:a.limit]
    print(f"[cand] 대상 {len(rows)}종목 · 후보 수집 시작", file=sys.stderr)

    with cf.ThreadPoolExecutor(6) as ex:
        got = list(ex.map(lambda r: gather(r, token), rows))
    withc = [g for g in got if g["candidates"]]
    doc = {"_meta": {"generated_at": datetime.now(KST).isoformat(),
                     "targets": len(got), "with_candidates": len(withc),
                     "note": "후보일 뿐 채택 아님. 사람이 고른 결과만 자산이 된다(자동 판별 오수확 23% 실측)."},
           "stocks": [{k: v for k, v in g.items() if k != "candidates"} |
                      {"candidates": [{kk: vv for kk, vv in c.items() if kk != "thumb"}
                                      for c in g["candidates"]]} for g in got]}
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    json.dump(doc, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False)
    open(OUT_HTML, "w", encoding="utf-8").write(build_html(got))
    mb = os.path.getsize(OUT_HTML) / 1e6
    print(f"[cand] 후보 보유 {len(withc)}/{len(got)} · HTML {mb:.1f}MB -> "
          f"{os.path.relpath(OUT_HTML, _ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
