const assert = require('node:assert/strict');
const test = require('node:test');
const { selectEpisodes, sessionDate, readBounded, checkBlobToken, wideFiles, assertLandscape, probeLandscape, readPrevious } = require('../scripts/publish_market_close.cjs');

function episode(id, subcategory, publishedAt, title = '마감 브리핑') {
    const post = {
        id, category: 'market', format: 'reel', subcategory, publishedAt, title,
        hasWide: true,
        instagram: 'https://www.instagram.com/reel/Example_1/',
        files: [
            { role: 'video_wide', name: '03-video_wide.mp4', mime: 'video/mp4', bytes: 100, sha256: 'a'.repeat(64) },
            { role: 'cover_wide', name: '04-cover_wide.jpg', mime: 'image/jpeg', bytes: 100, sha256: 'b'.repeat(64) },
        ].map(file => ({ ...file, url: `/api/media/posts/${id}/files/${file.name}` })),
    };
    post.wide = { video: post.files[0].url, cover: post.files[1].url, bytes: 100, sha256: 'a'.repeat(64) };
    return post;
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

test('updates one market when the other is missing or older than the saved episode', () => {
    const previous = new Map([['US', { publishedAt: us.publishedAt }]]);
    assert.deepEqual(selectEpisodes({ posts: [kr] }, now, previous).map(row => row.id), [kr.id]);
    const olderUs = { ...us, publishedAt: '2026-11-09T07:30:00+09:00' };
    assert.deepEqual(selectEpisodes({ posts: [kr, olderUs] }, now, previous).map(row => row.id), [kr.id]);
    assert.throws(() => selectEpisodes({ posts: [] }, now, previous), /both market/);
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

test('pending native renders retain the published market rather than selecting a new portrait', () => {
    const pending = { ...kr, hasWide: false, wide: null };
    const previous = new Map([['KR', { publishedAt: '2026-11-09T16:30:00+09:00' }]]);
    assert.deepEqual(selectEpisodes({ posts: [pending, us] }, now, previous).map(row => row.market), ['US']);
    assert.throws(() => selectEpisodes({ posts: [pending, us] }, now), /both market/);
    assert.equal(wideFiles(pending), undefined);
});

test('native file URLs, roles, ID, bytes and SHA are one source binding', () => {
    assert(wideFiles(kr));
    for (const wide of [null, [], { ...kr.wide, video: us.wide.video }, { ...kr.wide, cover: us.wide.cover },
        { ...kr.wide, bytes: 101 }, { ...kr.wide, sha256: 'c'.repeat(64) }]) {
        assert.throws(() => wideFiles({ ...kr, wide }));
    }
    assert.throws(() => wideFiles({ ...kr, files: [kr.files[0], kr.files[0], kr.files[1]] }), /ambiguous/);
    assert.throws(() => wideFiles({ ...kr, files: [{ ...kr.files[0], name: '../03-video_wide.mp4' }, kr.files[1]] }), /file name/);
    assert.throws(() => wideFiles({ ...kr, files: [{ ...kr.files[0], url: kr.files[0].url + '?key=fixture' }, kr.files[1]] }), /file URL/);
});

test('same published post can upgrade to native landscape without changing the original date', () => {
    const previous = new Map([['KR', { publishedAt: kr.publishedAt }], ['US', { publishedAt: us.publishedAt }]]);
    const rows = selectEpisodes({ posts: [kr, us] }, now, previous);
    assert.equal(rows[0].id, kr.id);
    assert.equal(rows[0].publishedAt, kr.publishedAt);
    assert.equal(rows[0].layout, 'landscape');
    assert(rows[0].video.endpoint.endsWith('/03-video_wide.mp4'));
});

test('landscape guard rejects portraits, low resolution, nonsquare pixels and rotation', () => {
    assert.deepEqual(assertLandscape({ width: 1920, height: 1080, sample_aspect_ratio: '1:1' }), { width: 1920, height: 1080 });
    assertLandscape({ width: 1280, height: 720 });
    for (const stream of [null, { width: 1080, height: 1920 }, { width: 640, height: 360 },
        { width: '1280', height: 720 }, { width: 1280, height: 720, sample_aspect_ratio: '2:1' },
        { width: 1280, height: 720, tags: { rotate: '90' } },
        { width: 1280, height: 720, side_data_list: [{ rotation: -90 }] }]) assert.throws(() => assertLandscape(stream));
});

test('previous native manifest keeps its layout and legacy manifests remain readable', () => {
    const origin = 'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/market-close/v1/';
    const items = [kr, us].map(post => ({ id: post.id, market: post === kr ? 'KR' : 'US', title: post.title,
        publishedAt: post.publishedAt, permalink: post.instagram, sourceFingerprint: 'c'.repeat(64),
        layout: 'landscape', posterUrl: `${origin}${post.id}/poster-${'d'.repeat(64)}.jpg`, videoUrl: `${origin}${post.id}/video-${'e'.repeat(64)}.mp4` }));
    assert.equal(readPrevious(Buffer.from(JSON.stringify({ version: 1, items }))).get('KR').layout, 'landscape');
    const legacy = items.map(({ layout, ...item }) => item);
    assert.equal(readPrevious(Buffer.from(JSON.stringify({ version: 1, items: legacy }))).get('KR').layout, undefined);
    assert.throws(() => readPrevious(Buffer.from(JSON.stringify({ version: 1, items: [{ ...items[0], layout: 'portrait' }, items[1]] }))), /layout/);
});

test('actual FFprobe accepts a synthetic wide video and rejects a portrait', t => {
    const { execFileSync } = require('node:child_process');
    const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
    const ffmpeg = process.env.FFMPEG_PATH || 'ffmpeg';
    try {
        execFileSync(ffmpeg, ['-version'], { stdio: 'ignore' });
        execFileSync(process.env.FFPROBE_PATH || 'ffprobe', ['-version'], { stdio: 'ignore' });
    } catch (error) {
        if (process.env.MARKET_CLOSE_REQUIRE_MEDIA_TOOLS === '1') throw error;
        return t.skip('Media tools unavailable locally; required by the scheduled job test step.');
    }
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'market-close-probe-'));
    try {
        for (const [name, size] of [['wide', '1280x720'], ['portrait', '720x1280']]) {
            const file = path.join(directory, name + '.mp4');
            execFileSync(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', `color=c=black:s=${size}:r=1`, '-frames:v', '1', '-c:v', 'libx264', file], { stdio: 'ignore', timeout: 30000 });
            if (name === 'wide') assert.deepEqual(probeLandscape(file), { width: 1280, height: 720 });
            else assert.throws(() => probeLandscape(file), /dimensions/);
        }
    } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});
