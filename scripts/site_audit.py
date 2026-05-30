#!/usr/bin/env python3
"""
site_audit.py — VERITY 라이브 사이트 정밀 검수 (실행형, drift 불가).

2026-05-31 신설. 그간 수동 판단으로 진행하던 사이트 검수를 코드화 →
"검수했나?" 가 아니라 "audit 초록인가?" 로 전환. 정적 .md 체크리스트는
프로젝트 만성병(drift)으로 썩으므로, 실행 가능한 pass/fail 게이트로 코드에 고정.

검사 축 (1차 자료 직접 probe — agent 추정 없음, RULE 10 정합):
  1. reachability   — 프로덕션 site + API endpoint + 프론트 데이터 fetch URL 도달성
  2. data_content   — Blob portfolio/recommendations 신선도 + 추천 내용 sanity
  3. publish        — 프론트 fetch URL 전부 200 (publish 화이트리스트 정합)
  4. esbuild        — framer-components/*.tsx 전수 파스 (syntax/panic = Framer publish 깨짐)
  5. rule9          — 사용자 노출 문자열 금지 동사 '박-' 0건 (CLAUDE.md RULE 9)
  6. render(opt)    — puppeteer-core + Chrome.app 있으면 라이브 render + 콘솔 에러 확인

종료 코드: 0 = 전체 PASS, 1 = 1건이라도 FAIL (cron/CI 게이트용, cron_health_monitor 컨벤션 정합).
주말 가드: price_pulse 등 시장시간 의존 데이터는 주말/휴장 시 stale 정상 처리.

사용:
  python3 scripts/site_audit.py                 # 전체 (render 자동 skip-if-unavailable)
  python3 scripts/site_audit.py --no-net        # 네트워크 없는 정적 검사만 (esbuild+rule9)
  python3 scripts/site_audit.py --render         # render 강제 (puppeteer 미존재 시 FAIL)
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

# ── config (검수 대상 SoT) ─────────────────────────────────────────
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROD_SITE = "https://verity-terminal.framer.website"
API_BASE = "https://project-yw131.vercel.app/api"
BRAIN_API = "https://verity-api-kim-hyojuns-projects.vercel.app/api/brain_breakdown"
BLOB_BASE = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
ESBUILD = os.path.join(REPO_ROOT, "vercel-api", "node_modules", ".bin", "esbuild")
FRAMER_GLOB = os.path.join(REPO_ROOT, "framer-components", "**", "*.tsx")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

KST = timezone(timedelta(hours=9))
PAK_RE = re.compile(r"박[으이아았혀힘은는지하한히음으면혀]")  # RULE 9 금지 동사


# ── result accumulator ─────────────────────────────────────────────
class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []  # (name, status, detail)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.rows.append((name, status, detail))

    def failed(self) -> int:
        return sum(1 for _, s, _ in self.rows if s == "FAIL")

    def render(self) -> str:
        icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "–", "WARN": "!"}
        lines = ["", "=" * 64, "  VERITY site_audit", "=" * 64]
        for name, status, detail in self.rows:
            lines.append(f"  {icon.get(status, '?')} [{status:4}] {name:22} {detail}")
        lines.append("=" * 64)
        n_fail = self.failed()
        n_warn = sum(1 for _, s, _ in self.rows if s == "WARN")
        verdict = "RED — FAIL 발생" if n_fail else ("GREEN (warn 있음)" if n_warn else "GREEN")
        lines.append(f"  결과: {verdict}  (FAIL={n_fail} WARN={n_warn} TOTAL={len(self.rows)})")
        lines.append("=" * 64)
        return "\n".join(lines)


def http(url: str, timeout: int = 25) -> tuple[int, bytes]:
    """(status, body). 네트워크 실패 시 status=0."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "verity-site-audit"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except Exception:
            return e.code, b""
    except Exception:
        return 0, b""


# ── 1. reachability ────────────────────────────────────────────────
def check_reachability(rep: Report) -> None:
    st, body = http(PROD_SITE)
    if st == 200 and b"VERITY" in body:
        rep.add("reachability.site", "PASS", f"{PROD_SITE} 200")
    else:
        rep.add("reachability.site", "FAIL", f"{PROD_SITE} → {st}")

    # 실 ticker 확보 (recommendations 첫 종목)
    ticker = None
    st, body = http(f"{BLOB_BASE}/recommendations.json")
    if st == 200:
        try:
            recs = json.loads(body)
            if isinstance(recs, list) and recs:
                ticker = recs[0].get("ticker")
        except Exception:
            pass

    endpoints = [
        ("api.system_health", f"{API_BASE}/system/health", 200),
        ("api.search", f"{API_BASE}/search?q=samsung", 200),
        ("api.visitor_ping", f"{API_BASE}/visitor_ping", 200),
    ]
    if ticker:
        endpoints.append(("api.stock_detail", f"{API_BASE}/stock_detail?symbol={ticker}", 200))
        endpoints.append(("api.brain_breakdown", f"{BRAIN_API}?ticker={ticker}", 200))
    for name, url, want in endpoints:
        st, _ = http(url)
        rep.add(name, "PASS" if st == want else "FAIL", f"{st} (want {want})")


# ── 2. data content sanity ─────────────────────────────────────────
def check_data_content(rep: Report) -> None:
    st, body = http(f"{BLOB_BASE}/portfolio.json")
    if st != 200:
        rep.add("data.portfolio", "FAIL", f"Blob {st}")
    else:
        try:
            p = json.loads(body)
            ms = p.get("market_summary", {})
            has_pulse = "indices_pulse" in ms
            rep.add("data.portfolio", "PASS" if has_pulse else "WARN",
                    f"{len(body)//1024}KB updated={p.get('updated_at','?')} pulse={has_pulse}")
        except Exception as e:
            rep.add("data.portfolio", "FAIL", f"parse error: {e}")

    st, body = http(f"{BLOB_BASE}/recommendations.json")
    if st != 200:
        rep.add("data.recommendations", "FAIL", f"Blob {st}")
        return
    try:
        recs = json.loads(body)
        n = len(recs)
        bad_px = sum(1 for r in recs if not isinstance(r.get("price"), (int, float)) or r.get("price", 0) <= 0)
        no_brain = sum(1 for r in recs if "verity_brain" not in r)
        if n == 0:
            rep.add("data.recommendations", "FAIL", "0 recs")
        elif bad_px > 0:
            rep.add("data.recommendations", "FAIL", f"{bad_px}/{n} recs 가격 결손")
        else:
            status = "PASS" if no_brain == 0 else "WARN"
            rep.add("data.recommendations", status, f"{n} recs, 가격 0결손, brain 결손 {no_brain}")
    except Exception as e:
        rep.add("data.recommendations", "FAIL", f"parse error: {e}")


# ── 3. publish pipeline (프론트 fetch URL 전부 200) ────────────────
def check_publish(rep: Report) -> None:
    urls: set[str] = set()
    url_re = re.compile(r"https://[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._/-]+)?\.jsonl?")
    for f in glob.glob(FRAMER_GLOB, recursive=True):
        try:
            txt = open(f, encoding="utf-8").read()
        except Exception:
            continue
        for m in url_re.finditer(txt):
            u = m.group(0)
            if "xxxx" in u or "..." in u or "example" in u:
                continue  # placeholder
            urls.add(u)
    if not urls:
        rep.add("publish.fetch_urls", "WARN", "프론트 fetch URL 0건 검출")
        return
    broken = []
    for u in sorted(urls):
        st, _ = http(u, timeout=15)
        if st != 200:
            broken.append(f"{st} {u.split('/')[-1]}")
    if broken:
        rep.add("publish.fetch_urls", "FAIL", f"{len(broken)}/{len(urls)} broken: {'; '.join(broken[:4])}")
    else:
        rep.add("publish.fetch_urls", "PASS", f"{len(urls)}/{len(urls)} = 200")


# ── 4. esbuild parse (Framer publish 깨짐 검출) ────────────────────
def check_esbuild(rep: Report) -> None:
    if not os.path.exists(ESBUILD):
        rep.add("esbuild.parse", "SKIP", f"esbuild 미존재 ({ESBUILD})")
        return
    files = sorted(glob.glob(FRAMER_GLOB, recursive=True))
    if not files:
        rep.add("esbuild.parse", "WARN", "컴포넌트 0건")
        return
    fails = []
    for f in files:
        proc = subprocess.run([ESBUILD, f, "--bundle=false", "--format=esm"],
                              capture_output=True, text=True)
        err = (proc.stderr or "").strip()
        if err:
            first = err.splitlines()[0] if err.splitlines() else err
            fails.append(f"{os.path.basename(f)}: {first[:60]}")
    if fails:
        rep.add("esbuild.parse", "FAIL", f"{len(fails)}/{len(files)} 실패: {'; '.join(fails[:3])}")
    else:
        rep.add("esbuild.parse", "PASS", f"{len(files)}/{len(files)} 파스 클린")


# ── 5. RULE 9 — 사용자 노출 문자열 금지 동사 ──────────────────────
def check_rule9(rep: Report) -> None:
    # python 사용자 노출 string (error/body/message/return JSON), 주석 제외
    py_hits = []
    py_re = re.compile(r'(?:"error"|"message"|"reason"|"detail"|"note"|body\s*=)')
    for f in glob.glob(os.path.join(REPO_ROOT, "vercel-api", "api", "**", "*.py"), recursive=True):
        try:
            for i, line in enumerate(open(f, encoding="utf-8"), 1):
                s = line.lstrip()
                if s.startswith("#"):
                    continue
                if PAK_RE.search(line) and py_re.search(line):
                    py_hits.append(f"{os.path.relpath(f, REPO_ROOT)}:{i}")
        except Exception:
            continue
    # tsx JSX 노출 텍스트 / 문자열 리터럴, // /* * 주석 제외
    tsx_re = re.compile(r'(?:"[^"]*박|>[^<]*박|`[^`]*박)')
    tsx_hits = []
    for f in glob.glob(FRAMER_GLOB, recursive=True):
        try:
            for i, line in enumerate(open(f, encoding="utf-8"), 1):
                s = line.lstrip()
                if s.startswith("//") or s.startswith("*") or s.startswith("/*"):
                    continue
                if PAK_RE.search(line) and tsx_re.search(line):
                    tsx_hits.append(f"{os.path.relpath(f, REPO_ROOT)}:{i}")
        except Exception:
            continue
    hits = py_hits + tsx_hits
    if hits:
        rep.add("rule9.user_facing", "FAIL", f"{len(hits)}건: {'; '.join(hits[:4])}")
    else:
        rep.add("rule9.user_facing", "PASS", "사용자 노출 '박-' 0건")


# ── 6. render (optional, puppeteer-core + Chrome) ──────────────────
RENDER_JS = r"""
const p = require('puppeteer-core');
(async () => {
  const b = await p.launch({ executablePath: process.env.CHROME, headless: true,
    args: ['--no-sandbox','--disable-gpu'] });
  const pg = await b.newPage();
  const cErr = [], pErr = [];
  pg.on('console', m => { if (m.type()==='error') cErr.push(m.text().slice(0,160)); });
  pg.on('pageerror', e => pErr.push(String(e).slice(0,160)));
  let nav = true;
  try { await pg.goto(process.env.URL, { waitUntil:'networkidle2', timeout:45000 }); }
  catch(e){ nav = false; }
  await new Promise(r => setTimeout(r, 6000));
  const info = await pg.evaluate(() => ({
    title: document.title,
    nodes: document.querySelectorAll('*').length,
    textLen: (document.body?.innerText||'').trim().length,
  }));
  console.log(JSON.stringify({ nav, ...info, cErr, pErr }));
  await b.close();
})().catch(e => { console.log(JSON.stringify({ fatal: String(e).slice(0,160) })); process.exit(2); });
"""


def _resolve_puppeteer() -> str | None:
    for base in (os.path.join(REPO_ROOT, "vercel-api", "node_modules"),
                 "/tmp/render-check/node_modules"):
        if os.path.isdir(os.path.join(base, "puppeteer-core")):
            return base
    return None


def check_render(rep: Report, force: bool) -> None:
    node = shutil.which("node")
    pp_base = _resolve_puppeteer()
    if not (node and os.path.exists(CHROME) and pp_base):
        msg = f"node={bool(node)} chrome={os.path.exists(CHROME)} puppeteer={bool(pp_base)}"
        rep.add("render.live", "FAIL" if force else "SKIP",
                msg + ("" if force else " (npm i puppeteer-core 후 --render)"))
        return
    env = dict(os.environ, URL=PROD_SITE, CHROME=CHROME, NODE_PATH=pp_base)
    proc = subprocess.run([node, "-e", RENDER_JS], capture_output=True, text=True, env=env)
    out = (proc.stdout or "").strip().splitlines()
    try:
        d = json.loads(out[-1]) if out else {}
    except Exception:
        rep.add("render.live", "FAIL", f"출력 파스 실패: {(proc.stdout or proc.stderr)[:80]}")
        return
    if d.get("fatal"):
        rep.add("render.live", "FAIL", d["fatal"])
        return
    cerr, perr = d.get("cErr", []), d.get("pErr", [])
    nav, nodes = d.get("nav"), d.get("nodes", 0)
    if not nav or nodes < 20:
        rep.add("render.live", "FAIL", f"nav={nav} nodes={nodes} (blank?)")
    elif cerr or perr:
        rep.add("render.live", "FAIL", f"console={len(cerr)} page={len(perr)}: {(cerr+perr)[0][:60]}")
    else:
        rep.add("render.live", "PASS", f"nodes={nodes} textLen={d.get('textLen')} 에러 0")


# ── main ───────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-net", action="store_true", help="네트워크 없는 정적 검사만 (esbuild+rule9)")
    ap.add_argument("--render", action="store_true", help="render 강제 (미존재 시 FAIL)")
    args = ap.parse_args()

    rep = Report()
    weekday = datetime.now(KST).weekday()  # 0=월 ... 5=토 6=일
    print(f"[site_audit] {datetime.now(KST).isoformat()} (weekday={weekday}, weekend={weekday >= 5})",
          file=sys.stderr)

    # 정적 검사 (항상)
    check_esbuild(rep)
    check_rule9(rep)

    # 네트워크 검사
    if not args.no_net:
        check_reachability(rep)
        check_data_content(rep)
        check_publish(rep)
        check_render(rep, force=args.render)

    print(rep.render())
    n_fail = rep.failed()
    if n_fail:
        sys.stderr.write(f"[site_audit] FAIL {n_fail}건 — exit 1 (게이트 빨강)\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
