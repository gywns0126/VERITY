// Exact search bodies read from Framer PublicHoldingsTab (S2WFHHW), 2026-09-14.
// No account writes: validate holdings + transaction discovery against issued JSON.
const fs = require("fs");
const assert = require("node:assert/strict");
const matches = (query, universe) => {
const q = query, tq = query, rows = [];

        const s = q.trim().toLowerCase()
        if (!s || !universe.length) return []
        const rk = (x) => {
            const t = String(x.ticker || "").toLowerCase(),
                n = String(x.name || "").toLowerCase(),
                k = String(x.name_ko || "").toLowerCase()
            return t === s
                ? 0
                : n === s || k === s
                  ? 1
                  : t.indexOf(s) === 0
                    ? 2
                    : n.indexOf(s) === 0 || (k && k.indexOf(s) === 0)
                      ? 3
                      : 4
        }
        const held = new Set(rows.map((r) => String(r.ticker)))
        return universe
            .filter(
                (x) =>
                    String(x.ticker).toLowerCase().includes(s) ||
                    String(x.name || "")
                        .toLowerCase()
                        .includes(s) ||
                    String(x.name_ko || "").includes(q.trim())
            )
            .sort((a, b) => rk(a) - rk(b))
            .slice(0, 8)
            .map((x) => ({ ...x, _held: held.has(String(x.ticker)) }))

};
const tMatches = (query, universe) => {
const q = query, tq = query, rows = [];

        const s = tq.trim().toLowerCase()
        if (!s || !universe.length) return []
        const rk = (x) => {
            const t = String(x.ticker || "").toLowerCase(),
                n = String(x.name || "").toLowerCase(),
                k = String(x.name_ko || "").toLowerCase()
            return t === s
                ? 0
                : n === s || k === s
                  ? 1
                  : t.indexOf(s) === 0
                    ? 2
                    : n.indexOf(s) === 0 || (k && k.indexOf(s) === 0)
                      ? 3
                      : 4
        }
        return universe
            .filter(
                (x) =>
                    String(x.ticker).toLowerCase().includes(s) ||
                    String(x.name || "")
                        .toLowerCase()
                        .includes(s) ||
                    String(x.name_ko || "").includes(tq.trim())
            )
            .sort((a, b) => rk(a) - rk(b))
            .slice(0, 8)

};
const index = JSON.parse(fs.readFileSync(process.argv[2] || "data/universe_search.json","utf8"));
const catalog = JSON.parse(fs.readFileSync("data/us_depositary_search.json","utf8"));
assert.equal(index._meta.count,index.stocks.length);
for (const search of [matches,tMatches]) {
 const missingTicker = catalog.stocks.filter(r=>!search(r.ticker,index.stocks).some(x=>x.ticker===r.ticker)).map(r=>r.ticker);
 const named = catalog.stocks.filter(r=>r.name_ko);
 const missingName = named.filter(r=>!search(r.name_ko,index.stocks).some(x=>x.ticker===r.ticker)).map(r=>r.ticker);
 assert.deepEqual(missingTicker,[]);
 assert.deepEqual(missingName,[]);
 for (const [q,t] of [["TSM","TSM"],["TSMC","TSM"],["알리바바","BABA"],["노보","NVO"],["소니","SONY"],["바이오엔테크","BNTX"],["삼성전자","005930"],["AAPL","AAPL"],["QQQ","QQQ"],["CMD_GOLD","CMD_GOLD"]]) {
   assert(search(q,index.stocks).some(x=>x.ticker===t),q+" -> "+t);
 }
 console.log(search.name+": ticker "+catalog.stocks.length+"/"+catalog.stocks.length+"; display-name "+named.length+"/"+named.length+"; representative 10/10");
}
assert.equal(index.stocks.filter(r=>r.type==="commodity"||r.market==="원자재").length,12);
console.log("commodity 12/12; total "+index.stocks.length+"; generated_at "+index._meta.generated_at);
