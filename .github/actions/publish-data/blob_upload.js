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
 *   - cacheControlMaxAge: 30s (Framer 빠른 갱신 보장)
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
const RETIRED_BLOBS = ["public_price_snapshot.json", "ranking_board.json", "trending_kr.json"];
const CACHE_MAX_AGE = 30; // 30s — Framer 가 매 페이지 진입마다 fresh 받음

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
        cacheControlMaxAge: CACHE_MAX_AGE,
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
    for (const [fp, blobPath] of entries) {
        const gr = guardCore(fp, blobPath);
        if (!gr.ok) {
            // 핵심 데이터 붕괴 = 결함본 업로드 차단. Blob 의 직전 GOOD 본이 계속 서빙됨.
            console.error(`  ⛔ HOLD ${blobPath} — ${gr.reason} · 직전 GOOD 유지(발행 안 함)`);
            held.push({ file: blobPath, reason: gr.reason });
            continue;
        }
        try {
            const url = await uploadFile(fp, blobPath);
            console.log(`  ✓ ${blobPath} → ${url}`);
            ok++;
        } catch (e) {
            console.error(`  ✗ ${blobPath} — ${e.message}`);
            fail++;
        }
    }
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
