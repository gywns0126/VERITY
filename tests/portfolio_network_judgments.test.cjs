const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const canvasPath = path.join(__dirname, '../vercel-api/public/member-map-canvas.html')
const canvas = fs.readFileSync(canvasPath, 'utf8')

function functionSource(source, name) {
    const start = source.indexOf(`function ${name}(`)
    assert.ok(start >= 0, `canvas defines ${name}`)
    const signatureEnd = source.indexOf('){', start)
    assert.ok(signatureEnd >= 0, `${name} has a closed parameter list`)
    const begin = signatureEnd + 1
    let depth = 0
    for (let index = begin; index < source.length; index += 1) {
        if (source[index] === '{') depth += 1
        else if (source[index] === '}' && --depth === 0) return source.slice(start, index + 1)
    }
    assert.fail(`unterminated ${name}`)
}

const actualFunctions = [
    'memberValidDate',
    'memberEvidenceToday',
    'memberLifecycle',
    'memberTemporalEvidence',
    'memberCompanyJudgment',
    'memberCompanyTemporalEvidence',
    'memberEconomicImportance',
    'memberBusinessVisual',
    'memberEdgeVisual',
    'memberNetworkJudgments',
]

function makeRecord(id = 'event:synthetic') {
    const day = new Date().toISOString().slice(0, 10)
    const compactDay = day.replaceAll('-', '')
    const record = {
        id,
        kind: 'event',
        recordKind: 'relationship',
        layer: 'reported',
        status: 'active',
        asOf: day,
        read_revision: 712345,
        topic: 'supply',
        evidence: [],
    }
    const stocks = [1, 2, 3].map((number) => ({
        id: `stock-${number}`,
        kind: 'stock',
        market: 'KR',
        ticker: `00000${number}`,
        name: `Synthetic ${number}`,
    }))
    const rows = stocks.map((stock, index) => {
        const receipt = `${compactDay}${String(index + 1).padStart(6, '0')}`
        const sourceUrl = `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipt}`
        record.evidence.push({ url: sourceUrl, title: `Synthetic filing ${index + 1}` })
        return {
            record_id: record.id,
            company_id: `${stock.market}:${stock.ticker}`,
            read_revision: record.read_revision,
            published_on: day,
            reviewed_on: day,
            status: 'accepted',
            source_id: `source:dart:${receipt}`,
            source_url: sourceUrl,
            quote: `Synthetic relationship evidence ${index + 1}`,
            scope_quote: `Synthetic company scope ${index + 1}`,
            period_quote: `${day} reporting period`,
            degree: 'medium',
            impact: { direction: 'unknown', condition: 'Synthetic condition' },
            economic_v2: {
                materiality: {
                    status: 'accepted',
                    value: 'material',
                    scope: 'division',
                    scope_quote: `Synthetic division ${index + 1}`,
                    period_quote: `${day} reporting period`,
                    mechanism_quote: 'Synthetic mechanism',
                    quote: 'Synthetic materiality evidence',
                    reviewed_on: day,
                    review_reasons: [],
                },
            },
        }
    })
    return { day, record, stocks, rows }
}

function runtime(fixture) {
    const context = {
        Array,
        Date,
        Map,
        Math,
        Number,
        Object,
        RegExp,
        Set,
        String,
        URL,
        nodeById: Object.fromEntries([fixture.record, ...fixture.stocks].map((node) => [node.id, node])),
        memberCompanyJudgmentRows: fixture.rows,
        // These are unrelated base-map gates; the business visual and binding
        // helpers under test are the actual source functions from the canvas.
        memberDisplayDecision: (record) => ({ evidence: record.layer === 'candidates' ? 'pending' : 'reported' }),
        memberConnectionDegree: () => ({ measure: null, sourceDegree: { grade: 0, label: '미평가' } }),
    }
    const definitions = actualFunctions.map((name) => functionSource(canvas, name)).join('\n')
    vm.runInNewContext(definitions, context)
    return context
}

function edge(record, stock, id = `${record.id}->${stock.id}`) {
    return {
        id,
        from: record.id,
        to: stock.id,
        type: 'direct',
        confirmation: 'confirmed',
        asOf: record.asOf,
        evidence: [{ url: 'https://example.test/synthetic-source', title: 'Synthetic edge source' }],
    }
}

function visualFor(context, relation, link) {
    return context.memberEdgeVisual(link, relation, { stockIds: [link.to] })
}

test('actual source-bound network helper deduplicates by record and company, and drops mismatched bindings', () => {
    const fixture = makeRecord()
    const context = runtime(fixture)
    const [first, second, third] = fixture.stocks
    const links = [
        edge(fixture.record, first, 'first-link'),
        edge(fixture.record, first, 'duplicate-company-link'),
        edge(fixture.record, second, 'second-company-link'),
        edge(fixture.record, third, 'third-company-invalid-row'),
        { ...edge(fixture.record, { id: 'other-record', kind: 'event' }, 'non-company-link') },
    ]
    const invalidRevision = { ...fixture.rows[2], read_revision: fixture.record.read_revision + 1 }
    const before = JSON.stringify({ links, rows: fixture.rows })
    context.memberCompanyJudgmentRows = [fixture.rows[0], fixture.rows[1], invalidRevision]

    const result = context.memberNetworkJudgments(fixture.record, links)

    assert.deepEqual(Array.from(result, (row) => row.company_id), ['KR:000001', 'KR:000002'])
    assert.equal(new Set(result.map((row) => `${row.record_id}|${row.company_id}`)).size, result.length)
    assert.equal(JSON.stringify({ links, rows: fixture.rows }), before, 'inputs remain unchanged')
})

test('stock selection resolves each opposite record and keeps distinct record/company judgments', () => {
    const first = makeRecord('event:first')
    const second = makeRecord('event:second')
    const context = runtime(first)
    context.nodeById[second.record.id] = second.record
    context.memberCompanyJudgmentRows = [first.rows[0], second.rows[0]]
    const stock = first.stocks[0]
    const links = [edge(first.record, stock, 'first-event'), edge(second.record, stock, 'second-event')]

    const result = context.memberNetworkJudgments(stock, links)

    assert.deepEqual(Array.from(result, (row) => row.record_id), ['event:first', 'event:second'])
    assert.ok(result.every((row) => row.company_id === 'KR:000001'))
})

test('network judgment helper safely returns no rows when its optional binding resolver is absent', () => {
    const helper = functionSource(canvas, 'memberNetworkJudgments')
    const context = { Map, nodeById: {} }
    vm.runInNewContext(helper, context)
    assert.deepEqual(Array.from(context.memberNetworkJudgments({ id: 'record', kind: 'event' }, [])), [])
})

test('actual edge integration maps accepted direction and degree without changing the relation kind', () => {
    const fixture = makeRecord()
    const context = runtime(fixture)
    const link = edge(fixture.record, fixture.stocks[0])
    const row = fixture.rows[0]
    const cases = [
        ['high', 'positive', 3.6, 'var(--red)'],
        ['medium', 'positive', 2.4, 'var(--red)'],
        ['low', 'positive', 1.4, 'var(--red)'],
        ['high', 'negative', 3.6, 'var(--blue)'],
        ['medium', 'negative', 2.4, 'var(--blue)'],
        ['low', 'negative', 1.4, 'var(--blue)'],
        ['high', 'unknown', 3.6, 'var(--an-topic,var(--an-accent))'],
        ['medium', 'unknown', 2.4, 'var(--an-topic,var(--an-accent))'],
        ['low', 'unknown', 1.4, 'var(--an-topic,var(--an-accent))'],
    ]

    for (const [degree, direction, width, color] of cases) {
        row.degree = degree
        row.impact.direction = direction
        const result = visualFor(context, fixture.record, link)
        assert.equal(result.width, width, `${degree} width`)
        assert.equal(result.color, color, `${direction} color`)
        assert.equal(result.kind, 'direct', 'review does not promote or downgrade the verified relation kind')
        assert.match(result.summaryLabel, new RegExp(direction === 'unknown' ? '영향 미평가' : direction === 'positive' ? '조건부 수혜' : '조건부 부담'))
    }
})

test('actual materiality helper accepts one bound company judgment but refuses to combine issuers', () => {
    const fixture = makeRecord()
    const context = runtime(fixture)
    const firstLink = edge(fixture.record, fixture.stocks[0])
    const secondLink = edge(fixture.record, fixture.stocks[1])
    context.memberCompanyJudgmentRows = [fixture.rows[0]]

    const one = context.memberEconomicImportance(fixture.record, [firstLink], { stockIds: [fixture.stocks[0].id] })
    assert.equal(one.materiality, 'material')
    assert.equal(one.materialityScope, 'division')
    assert.equal(one.materialityCompany, 'KR:000001')

    context.memberCompanyJudgmentRows = fixture.rows.slice(0, 2)
    const combined = context.memberEconomicImportance(fixture.record, [firstLink, secondLink], {
        stockIds: [fixture.stocks[0].id, fixture.stocks[1].id],
    })
    assert.equal(combined.materiality, 'unrated', 'different issuer scopes never become a combined company-wide rating')
    assert.equal(combined.materialityCompany, null)
})

test('held, candidate, and lifecycle visual states remain distinct around the reviewed overlay', () => {
    const fixture = makeRecord()
    const context = runtime(fixture)
    const link = edge(fixture.record, fixture.stocks[0])
    const row = fixture.rows[0]

    row.status = 'held'
    const held = visualFor(context, fixture.record, link)
    assert.equal(held.color, 'var(--an-topic,var(--an-accent))')
    assert.match(held.summaryLabel, /영향 판단 보류/)

    row.status = 'accepted'
    fixture.record.layer = 'candidates'
    row.impact.direction = 'positive'
    const candidate = visualFor(context, fixture.record, link)
    assert.equal(candidate.kind, 'reference')
    assert.equal(candidate.statusLabel, '관계 후보')
    assert.equal(candidate.dash, '2 6')
    assert.equal(candidate.color, 'var(--red)', 'conditional direction may color a candidate without confirming it')
    assert.equal(candidate.animate, false)

    fixture.record.layer = 'reported'
    fixture.record.lifecycle = { terminationNoticeCount: 1 }
    const lifecycle = visualFor(context, fixture.record, link)
    assert.equal(lifecycle.kind, 'review')
    assert.equal(lifecycle.dash, '8 4 2 4')
    assert.equal(lifecycle.color, 'var(--an-line)')
    assert.equal(lifecycle.animate, false)
})
