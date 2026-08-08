#!/usr/bin/env node
/**
 * Blob prefix 목록 → 티커 파일(줄바꿈 구분). 2026-08-08 신설.
 *
 * 왜 필요한가: us_chart_history 는 레포에 커밋하지 않고 Blob 에만 올린다(1.9GB). 그래서
 * CI run 은 매번 빈 디스크로 시작하고, 수집기의 "파일 존재 = 체크포인트" 재개 장치가
 * CI 에서는 작동하지 않았다. 2026-08-08 첫 실행이 야후 차단으로 45.4% 에서 멈췄을 때
 * 다음 run 이 처음부터 다시 받아야 하는 구조였다.
 * → Blob 에 이미 있는 티커 목록을 내려받아 수집기에 --skip-list 로 넘긴다. 누적 진행이 된다.
 *
 * 출력은 티커만 담는다(경로·확장자 제거). 업로드 단계는 여전히 "로컬에 있는 파일" 만
 * 올리므로, skip 된 티커가 빈 파일로 덮이는 일은 생기지 않는다.
 *
 * 호출: node blob_list_prefix.js <prefix> <출력파일>
 *   예: node blob_list_prefix.js us_chart_history/ data/us_chart_history_remote.txt
 */

const { list } = require("@vercel/blob");
const fs = require("fs");
const path = require("path");

async function main() {
    const prefix = process.argv[2];
    const outPath = process.argv[3];
    if (!prefix || !outPath) {
        console.error("usage: node blob_list_prefix.js <prefix> <outfile>");
        process.exit(2);
    }
    if (!process.env.BLOB_READ_WRITE_TOKEN) {
        console.error("[blob_list] BLOB_READ_WRITE_TOKEN 없음");
        process.exit(1);
    }

    const names = new Set();
    let cursor = undefined;
    let pages = 0;
    do {
        const res = await list({ prefix, cursor, limit: 1000 });
        for (const b of res.blobs || []) {
            const base = path.basename(b.pathname || "");
            if (!base.endsWith(".json")) continue;
            const t = base.slice(0, -5);
            if (t && !t.startsWith("_")) names.add(t);   // _meta.json 제외
        }
        cursor = res.cursor;
        pages += 1;
    } while (cursor);

    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, Array.from(names).sort().join("\n") + "\n", "utf-8");
    console.log(`[blob_list] ${prefix} — ${names.size}건 (${pages} page) -> ${outPath}`);
}

main().catch((e) => {
    // 목록 실패는 치명이 아니다 — 빈 skip-list 로 전량 수집하면 될 뿐이다.
    console.error(`[blob_list] 실패(무시 가능): ${e && e.message}`);
    process.exit(1);
});
