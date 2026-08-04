#!/usr/bin/env node
/**
 * Vercel Blob dual-write — 2026-05-24 private repo migration prep.
 *
 * 배경: VERITY / VERITY-data public repo 의 raw.githubusercontent.com 페치 의존.
 * private 전환 시 Framer 사이트 즉시 깨짐. Blob 으로 dual-write 해두면 cutover
 * 시 dataUrl 1 회 replace 후 private flip — 사이트 down 0초.
 *
 * 작동:
 *   - _public_dist/ 의 모든 *.json + equity_research/*.json 을 Blob 으로 PUT
 *   - access: 'public' / addRandomSuffix: false (URL 안정) / allowOverwrite: true
 *   - cacheControlMaxAge: 파일별 차등 (2026-08-04 — 30s 일괄이 전송량 과금 주범, 하단 MAX_AGE_RULES)
 *   - BLOB_READ_WRITE_TOKEN env 필요 (caller workflow → action input → env)
 *
 * 호출: node blob_upload.js <_public_dist>
 */

const { put, del } = require("@vercel/blob");
const fs = require("fs");
const path = require("path");

const SKIP_FILES = new Set(["README.md", "_manifest.txt"]);
// 시세 재배포 컴플라이언스(2026-07-03 Phase 2) — 발행 중단된 KRX-raw 파일의 잔존 blob 스냅샷 삭제(멱등).
// allowlist 제거만으론 마지막 업로드본이 public URL 에 계속 서빙됨 → 매 run del 로 확정 차단.
// del 은 blob URL 기준(pathname 은 SDK 버전 의존) — 스토어 host 는 사이트 컴포넌트들이 쓰는 고정 URL.
const BLOB_HOST = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com";
const RETIRED_BLOBS = [
    "public_price_snapshot.json", "ranking_board.json", "trending_kr.json",
    // 2026-07-23 분리 Stage 3 후속: 오퍼레이터 전용 크라운주얼 → private bucket 이전, 공개 blob 삭제.
    // (발행 목록 제거만으론 옛 blob 본 잔존 — del 로 노출 완전 차단. authed /api/admin?type=<name> 로 서빙.)
    "admin_todos.json", "brain_kb_usage.json", "history.json", "system_health_snapshot.json",
    // 2026-07-30 PM 은퇴 결정 — nps_fund_returns 는 **생산 경로가 존재하지 않는다**.
    // 전수 참조 감사: collector·builder·workflow 0건, 2026-04-30 에 한 번 생성된 뒤 갱신 수단 없음
    // → 91일 stale 이 아니라 영구 stale. 소비자(PublicNPSHoldings)는 404 안전
    // (`r.ok` 체크 + 렌더가 `{returns && Array.isArray(returns.annual) && ...}` 로 가드) → 패널만 사라진다.
    "nps_fund_returns.json",
];
// ── 파일별 차등 캐시 (PM 승인 2026-08-04) — Vercel $44 청구 사고 대응 ──
// 근인: 전 파일 30s 일괄 → CDN 캐시가 30초마다 만료 → 대형 JSON(portfolio 1.18MB ·
// universe_search 1.32MB · recommendations 1.36MB)이 방문자 요청마다 원본 전송(과금).
// 데이터 갱신은 대부분 일 1~2회 — 캐시 수명을 갱신 주기에 정렬해 CDN 히트율을 올린다.
// 지연 트레이드오프: 발행 후 최대 10분(기본군)~1h(일1군) — 모닝브리핑 T+1 정책 대비 수용 범위.
// 준실시간은 price_pulse 만 (60s 유지).
const MAX_AGE_RULES = [
    [/^price_pulse\.json$/, 60],
    [/^(macro_snapshot|urgent_alerts)\.json$/, 300],
    [/^(universe_search|kr_stock_names|kr_close_latest|us_investor_portfolios|us_smart_money[^/]*|sectors[^/]*)\.json$/, 3600],
    [/^equity_research\//, 1800],
];
const DEFAULT_MAX_AGE = 600; // 일 2회 갱신군 (portfolio·recommendations 등)
function maxAgeFor(blobPath) {
    for (const [re, age] of MAX_AGE_RULES) if (re.test(blobPath)) return age;
    return DEFAULT_MAX_AGE;
}

// ── 핵심 데이터 발행 가드 (fail-closed, 단일 병목) ─────────────────────────
// 핵심 배수(PER/PBR)가 붕괴한 리포트는 업로드 SKIP → Blob 의 직전 GOOD 본 유지.
// 어느 워크플로가 발행하든 여기서 차단 (2026-07-12 — 미장 PER/PBR 전량 공백 사고 계열).
// baseline 무관 절대 하한. 유니버스 작으면(<minN) 판단 보류 = 가짜 차단 방지.
const CORE_GUARD = {
    "stock_report_public.json":         { subfields: ["PER", "PBR"], floorPct: 5, minN: 100, krOnly: true },
    "us_stock_report_public.json":      { subfields: ["PER", "PBR"], floorPct: 5, minN: 100 },
    "us_stock_report_us_smallcap.json": { subfields: ["PER", "PBR"], floorPct: 5, minN: 50 },
};

function _filled(v) {
    if (v === null || v === undefined) return false;
    if (Array.isArray(v)) return v.length > 0;
    if (typeof v === "object") return Object.keys(v).length > 0;
    if (typeof v === "string") { const t = v.trim(); return t !== "" && t !== "—" && t !== "-"; }
    return true;
}

// 리포트 파일 발행 안전성 검사 → { ok:true } | { ok:false, reason }
function guardCore(fp, blobPath) {
    const g = CORE_GUARD[blobPath];
    if (!g) return { ok: true };
    let doc;
    try { doc = JSON.parse(fs.readFileSync(fp, "utf-8")); }
    catch (e) { return { ok: false, reason: `JSON 파싱 실패 (${e.message})` }; }
    let arr = Array.isArray(doc.stocks) ? doc.stocks : null;
    if (!arr) return { ok: false, reason: "stocks 배열 부재" };
    if (g.krOnly) arr = arr.filter((s) => /^\d{6}$/.test(String((s || {}).ticker || "")));
    const total = arr.length;
    if (total < g.minN) return { ok: true };  // 유니버스 부족 = 판단 보류(가짜 차단 방지)
    for (const sub of g.subfields) {
        const filled = arr.reduce((n, s) => n + (_filled(((s || {}).facts || {})[sub]) ? 1 : 0), 0);
        const pct = (filled * 100) / total;
        if (pct < g.floorPct) return { ok: false, reason: `facts.${sub} 채움율 ${pct.toFixed(1)}% < ${g.floorPct}% (N=${total}) — 붕괴` };
    }
    return { ok: true };
}

async function uploadFile(filePath, blobPath) {
    const buf = fs.readFileSync(filePath);
    const contentType = blobPath.endsWith(".json")
        ? "application/json"
        : "text/plain";
    const { url } = await put(blobPath, buf, {
        access: "public",
        addRandomSuffix: false,
        allowOverwrite: true,
        contentType,
        cacheControlMaxAge: maxAgeFor(blobPath),
    });
    return url;
}

async function main() {
    const dir = process.argv[2];
    if (!dir) {
        console.error("usage: node blob_upload.js <_public_dist>");
        process.exit(1);
    }
    if (!process.env.BLOB_READ_WRITE_TOKEN) {
        console.log("BLOB_READ_WRITE_TOKEN not set — skip");
        process.exit(0);
    }

    const entries = [];
    for (const f of fs.readdirSync(dir)) {
        if (SKIP_FILES.has(f) || f.startsWith("_")) continue;
        const fp = path.join(dir, f);
        const stat = fs.statSync(fp);
        if (stat.isDirectory()) {
            for (const sub of fs.readdirSync(fp)) {
                // 2026-05-26 fix — subdir 안의 _summary.json 류 데이터 파일 허용.
                // root level startsWith("_") 가드는 _manifest.txt 보호 위해 유지.
                if (SKIP_FILES.has(sub)) continue;
                entries.push([path.join(fp, sub), `${f}/${sub}`]);
            }
        } else {
            entries.push([fp, f]);
        }
    }

    let ok = 0,
        fail = 0;
    const held = [];

    // ── 1단계: 가드 판정 (동기, 순서 결정적) ──
    // 병렬 업로드 전에 HOLD 를 먼저 확정한다 — 가드 의미와 held 순서를 기존과 동일하게 유지.
    const queue = [];
    for (const [fp, blobPath] of entries) {
        const gr = guardCore(fp, blobPath);
        if (!gr.ok) {
            // 핵심 데이터 붕괴 = 결함본 업로드 차단. Blob 의 직전 GOOD 본이 계속 서빙됨.
            console.error(`  ⛔ HOLD ${blobPath} — ${gr.reason} · 직전 GOOD 유지(발행 안 함)`);
            held.push({ file: blobPath, reason: gr.reason });
            continue;
        }
        queue.push([fp, blobPath]);
    }

    // ── 2단계: 병렬 업로드 (워커 풀) ──
    // 🚨 2026-07-30 순차 → 병렬. 사유 = 15분 job timeout 사고.
    //   7/27 ETF 백필 신설로 etf_hist/ 가 1,196 파일까지 누적 → 파일당 1회 await put 순차 PUT 이
    //   publish step 을 13분까지 밀어올려 dart_catalyst_pulse(timeout 15)가 7/28 0/14 로 전멸.
    //   같은 publish 를 쓰는 모든 워크플로가 동일 위험이었다.
    //   업로드는 서로 다른 blobPath 로의 독립 PUT 이라 순서 무관 → 워커 풀이 안전.
    //   가드(guardCore)는 위 1단계에서 이미 완료되어 병렬화 영향 없음.
    // 동시성 8 = 보수값(레이트리밋 여유). BLOB_UPLOAD_CONCURRENCY 로 조정 가능.
    // 재시도 1회 = 병렬화로 새로 생기는 리스크(순간 레이트리밋 → 조용한 누락) 상쇄.
    //   기존 순차 코드에는 재시도가 없어 일시 실패가 곧 영구 누락이었다 — 이 점도 함께 개선.
    const CONCURRENCY = Math.max(1, parseInt(process.env.BLOB_UPLOAD_CONCURRENCY || "8", 10) || 8);
    let cursor = 0;

    async function worker() {
        while (true) {
            const i = cursor++;
            if (i >= queue.length) return;
            const [fp, blobPath] = queue[i];
            for (let attempt = 0; attempt < 2; attempt++) {
                try {
                    const url = await uploadFile(fp, blobPath);
                    console.log(`  ✓ ${blobPath} → ${url}`);
                    ok++;
                    break;
                } catch (e) {
                    if (attempt === 0) {
                        await new Promise((r) => setTimeout(r, 500));
                        continue;
                    }
                    console.error(`  ✗ ${blobPath} — ${e.message}`);
                    fail++;
                }
            }
        }
    }

    const t0 = Date.now();
    await Promise.all(
        Array.from({ length: Math.min(CONCURRENCY, queue.length || 1) }, () => worker())
    );
    console.log(
        `  (업로드 ${queue.length}건 · 동시성 ${CONCURRENCY} · ${((Date.now() - t0) / 1000).toFixed(1)}s)`
    );
    for (const blobPath of RETIRED_BLOBS) {
        try {
            await del(`${BLOB_HOST}/${blobPath}`);
            console.log(`  🗑 ${blobPath} (retired — 컴플라이언스 발행 중단)`);
        } catch (e) {
            // 이미 없음(404류) 포함 — 삭제 실패는 발행 성패에 영향 없음
            console.log(`  🗑 ${blobPath} skip — ${e.message}`);
        }
    }
    console.log(`\nblob_upload: ${ok} ok / ${fail} fail / ${held.length} held`);
    // dual-write 는 보조 경로 — 실패해도 기존 VERITY-data publish 정합 깨면 안 됨.
    // 그래서 항상 exit 0. fail 누적은 stderr warning 으로만 알림.
    if (fail > 0) {
        console.error(
            `::warning::blob_upload ${fail}/${ok + fail} fail — dual-write 부분 누락 (Blob store access mode 또는 token 확인 필요)`
        );
    }
    if (held.length) {
        // 핵심 데이터 붕괴 차단 = 라우드 신호. 마커 append(다음 run git add data/ 커밋 → cron_health 알림 소비, P5).
        //   exit 0 유지(발행 best-effort 계약 + 26 워크플로 red 캐스케이드 회피) — 보호는 HOLD 로 이미 완료.
        const ws = process.env.GITHUB_WORKSPACE;
        if (ws) {
            try {
                const mp = path.join(ws, "data", "metadata", "publish_guard.jsonl");
                fs.mkdirSync(path.dirname(mp), { recursive: true });
                fs.appendFileSync(mp, JSON.stringify({ ts: new Date().toISOString(), held }) + "\n");
            } catch (e) { console.error(`publish_guard marker write fail — ${e.message}`); }
        }
        console.error(
            `::error::publish-guard HELD ${held.length} core file(s): ${held.map((h) => `${h.file}(${h.reason})`).join(" | ")} — 결함본 발행 차단, 직전 GOOD 서빙 중. 빌더 즉시 조사.`
        );
    }
}

main().catch((e) => {
    console.error("::warning::blob_upload fatal —", e.message);
    // fatal 도 exit 0 — cron 정합 우선
});
