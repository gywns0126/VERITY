const assert = require('node:assert/strict');
const test = require('node:test');
const { selectEpisodes, sessionDate, readBounded, checkBlobToken } = require('../scripts/publish_market_close.cjs');

function episode(id, subcategory, publishedAt, title = '마감 브리핑') {
    return {
        id, category: 'market', format: 'reel', subcategory, publishedAt, title,
        instagram: 'https://www.instagram.com/reel/Example_1/',
        files: [
            { role: 'video', name: '01-video.mp4', mime: 'video/mp4', bytes: 100, sha256: 'a'.repeat(64) },
            { role: 'cover', name: '02-cover.jpg', mime: 'image/jpeg', bytes: 100, sha256: 'b'.repeat(64) },
        ].map(file => ({ ...file, url: `/api/media/posts/${id}/files/${file.name}` })),
    };
}

const now = Date.parse('2026-11-10T21:00:00+09:00');
const kr = episode('2026-11-10-17', '국장 마감', '2026-11-10T16:30:00+09:00', '11월 10일 국장 마감');
const us = episode('2026-11-10-13', '미장 마감', '2026-11-10T07:30:00+09:00', '11월 9일 미국 증시 마감');

test('chooses the latest explicit close for each market, keeping the session and upload dates separate', () => {
    const older = episode('2026-11-09-01', '국장 마감', '2026-11-09T16:30:00+09:00');
    const unrelated = episode('2026-11-10-18', '장전', '2026-11-10T20:30:00+09:00');
    const rows = selectEpisodes({ posts: [us, unrelated, older, kr] }, now);
    assert.deepEqual(rows.map(r => [r.id, r.market, r.sessionDate, r.publishedAt]), [
        [kr.id, 'KR', '2026-11-10', kr.publishedAt], [us.id, 'US', '2026-11-09', us.publishedAt],
    ]);
    assert.equal(rows[0].sourceFingerprint, rows[1].sourceFingerprint);
});

test('invalid or missing market data fails closed', () => {
    assert.throws(() => selectEpisodes({ posts: [kr] }, now), /both market/);
    assert.throws(() => selectEpisodes({ posts: [kr, { ...us, instagram: 'https://example.org/' }] }, now), /invalid episode/);
    assert.throws(() => selectEpisodes({ posts: [kr, { ...us, instagram: [us.instagram] }] }, now), /invalid episode/);
    assert.throws(() => selectEpisodes({ posts: [kr, { ...us, id: [us.id] }] }, now), /invalid episode/);
    assert.throws(() => selectEpisodes({ posts: [kr, { ...us, publishedAt: '2026-11-11T00:00:00+09:00' }] }, now), /publication time/);
    const files = [{ ...us.files[0], url: '//example.org/video.mp4' }, us.files[1]];
    assert.throws(() => selectEpisodes({ posts: [kr, { ...us, files }] }, now), /file URL/);
});

test('preflight checks the SDK token store identifier before any public write', () => {
    assert.doesNotThrow(() => checkBlobToken('vercel_blob_rw_rte5GuenhOnW9fzn_fixture'));
    assert.throws(() => checkBlobToken('vercel_blob_rw_wrongstore_fixture'), /wrong Blob store/);
    assert.throws(() => checkBlobToken(''), /wrong Blob store/);
});

test('does not invent the market date when the headline has no unambiguous date', () => {
    assert.equal(sessionDate('코스피 상승', kr.publishedAt), undefined);
    assert.equal(sessionDate('2월 30일 코스피', '2026-03-01T07:00:00+09:00'), undefined);
    assert.equal(sessionDate('12월 31일 미국 증시', '2027-01-01T08:00:00+09:00'), '2026-12-31');
});

test('response reader rejects oversized content even without a declared length', async () => {
    assert.equal((await readBounded(new Response('small'), 5)).toString(), 'small');
    await assert.rejects(readBounded(new Response('longer'), 5), /response too large/);
});
