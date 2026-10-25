process.env.DISCOVERY_TEST_SOURCE ||= require('node:path').resolve(__dirname, '../framer-components/public-probe/PublicDiscovery.tsx')
const { test } = require('node:test')
const assert = require('node:assert/strict')
const { runtime, kr, us, payload } = require('../scripts/r1-context/discovery-20260917/validation.test.cjs')

const sourceProps = {
    stockUrl: 'https://example.test/stock_report_public.json',
    usStockUrl: 'https://example.test/us_stock_report_public.json',
    usSmallcapUrl: 'https://example.test/us_stock_report_us_smallcap.json',
}
const lists = {
    'https://example.test/stock_report_list_public.json': { _meta: { sourceSHA: 'kr', generated_at: '2026-10-26' }, stocks: [kr] },
    'https://example.test/us_stock_report_list_public.json': { _meta: { sourceSHA: 'us', generated_at: '2026-10-26' }, stocks: [us] },
    'https://example.test/us_smallcap_report_list_public.json': { _meta: { sourceSHA: 'small', generated_at: '2026-10-26' }, stocks: [] },
}
const slice = ticker => ({ status: 'ok', report: { ...(ticker === kr.ticker ? kr : us), business: '선택 상세 전용 설명' } })
const respond = body => ({ ok: true, json: async () => body })
const fetcher = async url => {
    if (url in lists) return respond(lists[url])
    if (String(url).includes('/api/stock_slice?')) return respond(slice(new URL(url).searchParams.get('ticker')))
    return respond(payload[url] || { stocks: [] })
}

test('known full-report URLs request only lightweight lists; selection requests one slice', async () => {
    const r = runtime(undefined, { fetcher })
    try {
        r.setProps(sourceProps)
        await r.settle()
        const urls = r.calls.filter(c => c.url).map(c => String(c.url))
        for (const url of Object.keys(lists)) assert.ok(urls.includes(url), url)
        assert.equal(urls.some(url => /\/stock_report_public\.json|\/us_stock_report_public\.json|\/us_stock_report_us_smallcap\.json/.test(url)), false)
        assert.equal(urls.filter(url => url.includes('/api/stock_slice?')).length, 1)
        assert.match(r.text(), /선택 상세 전용 설명/)
        const other = r.nodes().find(n => n.props.role === 'button' && r.text(n).includes('검수 국내') && !r.text(n).includes('검수 미국'))
        assert.ok(other)
        other.props.onClick()
        await r.settle()
        assert.equal(r.calls.filter(c => String(c.url).includes('/api/stock_slice?')).length, 2)
    } finally { r.dispose() }
})

test('missing list is visible and retryable without a full-report fallback', async () => {
    const r = runtime(undefined, { fetcher: async url => String(url).includes('report_list_public.json') ? { ok: false } : fetcher(url) })
    try {
        r.setProps({ ...sourceProps, usSmallcapUrl: '' })
        await r.settle()
        assert.match(r.text(), /자료를 확인하지 못해/)
        assert.ok(r.find(n => n.type === 'button' && r.text(n) === '자료 다시 불러오기'))
        assert.equal(r.calls.some(c => /\/stock_report_public\.json|\/us_stock_report_public\.json/.test(String(c.url))), false)
    } finally { r.dispose() }
})

test('retry retains successful public rows while refresh is unresolved, and keeps them after partial failure', async () => {
    let hold, refresh = false
    const delayed = new Promise(resolve => { hold = resolve })
    const r = runtime(undefined, { fetcher: async url => {
        if (url === 'forensics' && !refresh) return { ok: false }
        if (url === 'kr' && refresh) return delayed
        if (url === 'kr') return respond({ ...payload.kr, _meta: { generated_at: '2026-10-24T13:33:20+09:00' } })
        return fetcher(url)
    } })
    try {
        await r.settle()
        assert.match(r.text(), /검수 국내/)
        const sourceDate = r.text().match(/국내 리포트 [^·]+ 생성/)?.[0]
        assert.ok(sourceDate)
        refresh = true
        r.find(n => n.type === 'button' && r.text(n) === '자료 다시 불러오기').props.onClick()
        await r.settle()
        assert.match(r.text(), /검수 국내/)
        assert.ok(r.text().includes(sourceDate))
        hold({ ok: false })
        await r.settle()
        assert.match(r.text(), /검수 국내/)
        assert.ok(r.text().includes(sourceDate))
    } finally { r.dispose() }
})

test('returning to a previously loaded public URL renders its rows before revalidation finishes', async () => {
    let hold, revisit = false
    const delayed = new Promise(resolve => { hold = resolve })
    const r = runtime(undefined, { fetcher: async url => revisit && url === 'kr' ? delayed : fetcher(url) })
    try {
        await r.settle()
        assert.match(r.text(), /검수 국내/)
        r.setProps({ stockUrl: 'replacement' })
        await r.settle()
        assert.doesNotMatch(r.text(), /검수 국내/)
        revisit = true
        r.setProps({ stockUrl: 'kr' })
        await r.settle()
        assert.match(r.text(), /검수 국내/)
        hold({ ok: false })
        await r.settle()
        assert.match(r.text(), /검수 국내/)
    } finally { r.dispose() }
})
