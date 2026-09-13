// Single-object, additive search repair. No private data, deletes, manifests or other uploads.
const fs = require("fs");
const cp = require("child_process");
const assert = require("node:assert/strict");
const crypto = require("crypto");
const NAME = "universe_search.json";
const URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/" + NAME;

function validate(current, next, catalog) {
    for (const d of [current, next]) {
        assert(Array.isArray(d.stocks) && d.stocks.length >= 1000, "search coverage below floor");
        assert.equal(d._meta.count, d.stocks.length, "count mismatch");
        assert.equal(new Set(d.stocks.map(r => r.ticker)).size, d.stocks.length, "duplicate ticker");
    }
    const date = Date.parse(next._meta.generated_at);
    assert(Number.isFinite(date) && date >= Date.parse(current._meta.generated_at), "stale target");
    assert.equal(catalog._meta.scope, "search_only_not_trading_universe");
    assert(catalog.stocks.length >= 100 && catalog._meta.count === catalog.stocks.length, "catalog coverage");
    const by = new Map(next.stocks.map(r => [r.ticker, r]));
    for (const row of current.stocks) {
        assert(by.has(row.ticker), "would drop " + row.ticker);
        for (const [k, v] of Object.entries(row)) {
            assert.deepEqual(by.get(row.ticker)[k], v, "would replace existing " + row.ticker + "." + k);
        }
    }
    for (const row of catalog.stocks) {
        assert.equal(by.get(row.ticker)?.market, "US", "missing US reference " + row.ticker);
    }
    assert.equal(next._meta.depositary_reference_at, catalog._meta.generated_at, "reference date mismatch");
    return { total: next.stocks.length, catalog: catalog.stocks.length, preserved: current.stocks.length };
}

async function main() {
    assert(process.env.BLOB_READ_WRITE_TOKEN, "existing Blob secret required");
    const body = fs.readFileSync("data/" + NAME);
    const next = JSON.parse(body);
    const catalog = JSON.parse(fs.readFileSync("data/us_depositary_search.json", "utf8"));
    const { put, head } = require("@vercel/blob");
    // CDN GET can return a weak W/ ETag. Conditional writes need the storage ETag.
    const metadata = await head(URL);
    const response = await fetch(URL + "?verify=" + Date.now(), {signal: AbortSignal.timeout(30000)});
    assert(response.ok, "current public read failed: " + response.status);
    const etag = metadata.etag;
    assert(etag, "missing ETag; conditional overwrite required");
    assert.equal(response.headers.get("etag")?.replace(/^W\//, ""), etag.replace(/^W\//, ""), "CDN and storage differ");
    const current = await response.json();
    const coverage = validate(current, next, catalog);
    // A concurrent main update invalidates this checkout; never publish a stale target.
    cp.execFileSync("git", ["fetch", "origin", "main", "--quiet"]);
    const latest = cp.execFileSync("git", ["show", "origin/main:data/" + NAME], {maxBuffer: 12000000});
    assert(body.equals(latest), "main changed; re-run with fresh checkout");
    const result = await put(NAME, body, {
        access: "public", addRandomSuffix: false, allowOverwrite: true,
        contentType: "application/json", cacheControlMaxAge: 3600,
        ifMatch: etag,
    });
    assert.equal(result.url, URL, "unexpected store/target");
    const check = await fetch(URL + "?verify=" + Date.now(), {signal: AbortSignal.timeout(30000)});
    assert(check.ok, "public readback failed");
    const readback = Buffer.from(await check.arrayBuffer());
    assert(body.equals(readback), "public bytes differ after upload");
    console.log(JSON.stringify({file: NAME, ...coverage, generated_at: next._meta.generated_at,
        sha256: crypto.createHash("sha256").update(body).digest("hex"), published: "1/1"}));
}

module.exports = {validate};
if (require.main === module) main().catch(e => {
    // Never print SDK request URLs/credentials.
    const safe = String(e.message || "").split(process.env.BLOB_READ_WRITE_TOKEN || "__NO_TOKEN__").join("[redacted]")
        .replace(/https?:\/\/\S+/g, "[url]").replace(/vercel_blob_rw_[A-Za-z0-9_]+/g, "[redacted]");
    console.error("search-only publish failed: " + (e.code || e.constructor.name) + " " + safe);
    process.exitCode = 1;
});
