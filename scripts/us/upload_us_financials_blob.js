#!/usr/bin/env node
/**
 * upload_us_financials_blob.js — US per-ticker 재무 스냅샷 1500 → Vercel Blob.
 *
 * 2026-06-21 신설. us_financials 1500 per-ticker 시계열(87MB, gitignore=git-bloat 회피)을
 * Blob `us_financials/<TICKER>.json` 로 직업로드 → deep 재무카드(USFinancialsCard,
 * vercel-api/api/us_financials.py DEFAULT_SOURCE = blob/us_financials) 1500 활성.
 *
 * 로컬 전용(파일이 gitignore라 CI publish 불가). blob_upload.js 와 동일 put() 옵션(URL 안정).
 * usage: BLOB_READ_WRITE_TOKEN=... node scripts/us/upload_us_financials_blob.js [--limit N]
 */
const { put } = require("@vercel/blob");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const SRC_DIR = path.join(ROOT, "data", "us_financials");
const CONCURRENCY = 8;          // 병렬 PUT (속도 + rate 안전)
const CACHE_MAX_AGE = 30;       // blob_upload.js 정합

function loadToken() {
    // env 우선 (BLOB_READ_WRITE_TOKEN=@vercel/blob 표준 / VERCEL_BLOB_TOKEN=GH 시크릿명)
    if (process.env.BLOB_READ_WRITE_TOKEN) return process.env.BLOB_READ_WRITE_TOKEN;
    if (process.env.VERCEL_BLOB_TOKEN) return process.env.VERCEL_BLOB_TOKEN;
    // .env fallback (dotenv 의존 회피 — 직접 파싱, 두 이름 다)
    try {
        const env = fs.readFileSync(path.join(ROOT, ".env"), "utf-8");
        const m = env.match(/^(?:BLOB_READ_WRITE_TOKEN|VERCEL_BLOB_TOKEN)=(.+)$/m);
        if (m) return m[1].trim().replace(/^["']|["']$/g, "");
    } catch (e) {}
    return null;
}

async function main() {
    const token = loadToken();
    if (!token) {
        console.error("[blob] BLOB_READ_WRITE_TOKEN 없음 — abort");
        process.exit(1);
    }
    const limitArg = process.argv.indexOf("--limit");
    const limit = limitArg >= 0 ? parseInt(process.argv[limitArg + 1], 10) : 0;

    let files = fs.readdirSync(SRC_DIR).filter((f) => f.endsWith(".json"));
    if (limit > 0) files = files.slice(0, limit);
    console.log(`[blob] 업로드 대상 ${files.length} 파일 → us_financials/ (concurrency ${CONCURRENCY})`);

    let ok = 0, fail = 0, done = 0;
    const queue = files.slice();

    async function worker() {
        while (queue.length) {
            const f = queue.shift();
            const buf = fs.readFileSync(path.join(SRC_DIR, f));
            try {
                await put(`us_financials/${f}`, buf, {
                    access: "public",
                    addRandomSuffix: false,
                    allowOverwrite: true,
                    contentType: "application/json",
                    cacheControlMaxAge: CACHE_MAX_AGE,
                    token,
                });
                ok++;
            } catch (e) {
                fail++;
                if (fail <= 8) console.error(`[blob] ${f} 실패: ${String(e).slice(0, 90)}`);
            }
            done++;
            if (done % 100 === 0 || done === files.length) {
                console.log(`[blob] ${done}/${files.length} (ok ${ok} fail ${fail})`);
            }
        }
    }

    await Promise.all(Array.from({ length: CONCURRENCY }, () => worker()));
    console.log(`[blob] 완료 — ok ${ok} / fail ${fail} / total ${files.length}`);
    process.exit(fail > 0 && ok === 0 ? 1 : 0);
}

main();
