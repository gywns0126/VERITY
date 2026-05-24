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

const { put } = require("@vercel/blob");
const fs = require("fs");
const path = require("path");

const SKIP_FILES = new Set(["README.md", "_manifest.txt"]);
const CACHE_MAX_AGE = 30; // 30s — Framer 가 매 페이지 진입마다 fresh 받음

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
                if (SKIP_FILES.has(sub) || sub.startsWith("_")) continue;
                entries.push([path.join(fp, sub), `${f}/${sub}`]);
            }
        } else {
            entries.push([fp, f]);
        }
    }

    let ok = 0,
        fail = 0;
    for (const [fp, blobPath] of entries) {
        try {
            const url = await uploadFile(fp, blobPath);
            console.log(`  ✓ ${blobPath} → ${url}`);
            ok++;
        } catch (e) {
            console.error(`  ✗ ${blobPath} — ${e.message}`);
            fail++;
        }
    }
    console.log(`\nblob_upload: ${ok} ok / ${fail} fail`);
    // dual-write 는 보조 경로 — 실패해도 기존 VERITY-data publish 정합 깨면 안 됨.
    // 그래서 항상 exit 0. fail 누적은 stderr warning 으로만 알림.
    if (fail > 0) {
        console.error(
            `::warning::blob_upload ${fail}/${ok + fail} fail — dual-write 부분 누락 (Blob store access mode 또는 token 확인 필요)`
        );
    }
}

main().catch((e) => {
    console.error("::warning::blob_upload fatal —", e.message);
    // fatal 도 exit 0 — cron 정합 우선
});
