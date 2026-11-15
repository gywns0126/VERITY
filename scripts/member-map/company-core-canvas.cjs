// Candidate-only presentation: reuse the existing disclosure list and styles.
// No map node placement, camera, note, mark or persistence changes.
function applyCompanyCoreCanvas(source) {
    const old = "    const buttons=new Map([...inbox.querySelectorAll('[data-select]')].map(b=>[b.dataset.select,b]));";
    const next = "      list.append(summary);\n      for(const n of g.records)";
    if (source.split(old).length !== 2 || source.split(next).length !== 2) throw Error('company-core-canvas-boundary');
    source = source.replace(old,
        "    const priorSourceLists=new Map([...inbox.querySelectorAll('[data-member-list]')].map(el=>[el.dataset.memberList,el.open]));\n" + old);
    return source.replace(next,
        "      list.open=priorSourceLists.has(g.key)?priorSourceLists.get(g.key):g.key==='filing'&&member.coverageNotice?.startsWith('공시·재무 근거 먼저');\n" +
        "      list.append(summary);\n      for(const n of (g.key==='filing'?[...g.records].sort((a,b)=>String(b.asOf||'').localeCompare(String(a.asOf||''))||a.id.localeCompare(b.id)):g.records))");
}
module.exports = { applyCompanyCoreCanvas };
