const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const ORIGIN_DIGEST = 'ea626a8e77cd6f778a3851c5305224c7a0c9de2a296ca370337f16944cf6bad0';
const BLOB = 'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/';
const PREFIX = 'market-close/v1/';
const INDEX = PREFIX + 'index.json';
const ID = /^\d{4}-\d{2}-\d{2}-\d{2}$/;
const SHA = /^[a-f0-9]{64}$/;
const PERMALINK = /^https:\/\/(?:www\.)?instagram\.com\/(?:reel|p)\/[A-Za-z0-9_-]+\/?$/;
const PUBLICATION_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
const MARKETS = new Map([['국장 마감', 'KR'], ['미장 마감', 'US']]);
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const validTitle = title => typeof title === 'string' && !!title.trim() &&
    title.length <= 500 && !/[\u0000-\u001f]|obnw_[A-Za-z0-9_-]{15,}/i.test(title);
const transientError = error => ['TypeError', 'TimeoutError', 'AbortError'].includes(error.name);
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

function checkBlobToken(token) {
    const match = /^vercel_blob_rw_([a-z\d]+)_[^\s]+$/i.exec(token);
    assert(match && new URL(BLOB).hostname.startsWith(`${match[1].toLowerCase()}.`), 'wrong Blob store');
}

async function readBounded(response, limit) {
    assert(response.ok && response.body, 'read failed');
    assert(Number(response.headers.get('content-length') || 0) <= limit, 'response too large');
    const reader = response.body.getReader();
    const chunks = [];
    let size = 0;
    try {
        while (true) {
            const { value, done } = await reader.read();
            if (done) return Buffer.concat(chunks, size);
            size += value.length;
            assert(size <= limit, 'response too large');
            chunks.push(value);
        }
    } finally {
        await reader.cancel().catch(() => {});
    }
}

function sourceClient(origin, key, fetcher = fetch) {
    assert(digest(origin) === ORIGIN_DIGEST, 'unexpected source origin');
    assert(/^obnw_[A-Za-z0-9]{10}_[A-Za-z0-9_-]{43}$/.test(key), 'missing source key');
    return (endpoint, timeout) => fetcher(origin + endpoint, {
        headers: { Authorization: `Bearer ${key}` }, redirect: 'error', signal: AbortSignal.timeout(timeout),
    });
}

async function readSource(request, endpoint, mime, limit, timeout) {
    for (let attempt = 0; ; attempt++) {
        let retryAfter = 2;
        try {
            const response = await request(endpoint, timeout);
            if (response.status === 429 || response.status >= 500) {
                retryAfter = Number(response.headers.get('retry-after') || 2);
                await response.body?.cancel();
                assert(attempt === 0 && Number.isFinite(retryAfter) && retryAfter >= 0 && retryAfter <= 30, 'source unavailable');
            } else {
                assert.equal(response.headers.get('content-type')?.split(';')[0], mime, 'unexpected source MIME');
                return await readBounded(response, limit);
            }
        } catch (error) {
            if (attempt || !transientError(error)) throw error;
        }
        await new Promise(resolve => setTimeout(resolve, (retryAfter + 1) * 1000));
    }
}

function fileFor(post, role, mime, maxBytes) {
    const files = post.files?.filter(file => file.role === role);
    assert(files?.length === 1, 'ambiguous source file');
    const { name, bytes, sha256, url } = files[0];
    assert(/^[0-9]{2}-[a-z0-9_-]+\.(?:mp4|jpg|jpeg|png|webp)$/.test(name), 'invalid source file name');
    const endpoint = `/api/media/posts/${post.id}/files/${name}`;
    assert.equal(url, endpoint, 'invalid source file URL');
    assert(files[0].mime === mime && Number.isSafeInteger(bytes) && bytes > 0 && bytes <= maxBytes && SHA.test(sha256), 'invalid source file metadata');
    return { endpoint, mime, bytes, sha256 };
}

function wideFiles(post) {
    if (post.hasWide !== true) return undefined;
    assert(post.wide && typeof post.wide === 'object' && !Array.isArray(post.wide), 'missing wide metadata');
    const video = fileFor(post, 'video_wide', 'video/mp4', 40 * 1024 * 1024);
    const poster = fileFor(post, 'cover_wide', 'image/jpeg', 2 * 1024 * 1024);
    assert(post.wide.video === video.endpoint && post.wide.cover === poster.endpoint &&
        post.wide.bytes === video.bytes && post.wide.sha256 === video.sha256, 'wide source binding mismatch');
    return { video, poster };
}

function assertLandscape(stream) {
    const { width, height, sample_aspect_ratio, tags, side_data_list } = stream || {};
    assert(Number.isSafeInteger(width) && Number.isSafeInteger(height) && width >= 960 && height >= 540 &&
        Math.abs(width / height - 16 / 9) < 0.01, 'wide source dimensions rejected');
    assert(!sample_aspect_ratio || sample_aspect_ratio === '1:1' || sample_aspect_ratio === 'N/A', 'wide source pixel ratio rejected');
    assert(!Number(tags?.rotate || 0) && !(side_data_list || []).some(item => Number(item.rotation || 0)), 'wide source rotation rejected');
    return { width, height };
}

function probeLandscape(file) {
    const body = execFileSync(process.env.FFPROBE_PATH || 'ffprobe', [
        '-v', 'error', '-protocol_whitelist', 'file,pipe', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,sample_aspect_ratio:stream_tags=rotate:stream_side_data=rotation',
        '-of', 'json', file,
    ], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], timeout: 15000, maxBuffer: 65536, env: { PATH: process.env.PATH } });
    const { streams } = JSON.parse(body);
    assert(Array.isArray(streams) && streams.length === 1, 'wide source stream rejected');
    return assertLandscape(streams[0]);
}

function sessionDate(title, publishedAt) {
    const m = /^(\d{1,2})월\s*(\d{1,2})일(?:\s|,)/.exec(title);
    if (!m) return undefined;
    const uploadDate = publishedAt.slice(0, 10);
    const monthDay = m.slice(1).map(value => value.padStart(2, '0')).join('-');
    const year = Number(uploadDate.slice(0, 4));
    const day = (Number(m[1]) > Number(uploadDate.slice(5, 7)) ? year - 1 : year) + '-' + monthDay;
    const elapsed = Date.parse(uploadDate) - Date.parse(day);
    return elapsed >= 0 && elapsed <= 4 * 86400000 && new Date(day).toISOString().slice(0, 10) === day ? day : undefined;
}

function selectEpisodes(payload, now = Date.now(), previous = new Map()) {
    assert(Array.isArray(payload.posts) && payload.posts.length <= 30, 'invalid source list');
    const ordered = payload.posts.filter(post => post.category === 'market' && post.format === 'reel' && MARKETS.has(post.subcategory))
        .sort((a, b) => Date.parse(b.publishedAt) - Date.parse(a.publishedAt));
    const selected = new Map();
    for (const post of ordered) {
        const market = MARKETS.get(post.subcategory);
        if (selected.has(market)) continue;
        const title = typeof post.title === 'string' ? post.title.trim() : '';
        const publishedAt = post.publishedAt;
        const age = now - Date.parse(publishedAt);
        assert(typeof post.id === 'string' && ID.test(post.id) && validTitle(title) &&
            typeof post.instagram === 'string' && PERMALINK.test(post.instagram), 'invalid episode');
        assert(typeof publishedAt === 'string' && PUBLICATION_TIME.test(publishedAt) && age >= -60000, 'invalid publication time');
        const old = previous.get(market);
        if (old && Date.parse(publishedAt) < Date.parse(old.publishedAt)) continue;
        if (old && age > 8 * 86400000) continue;
        assert(age <= 8 * 86400000, 'invalid publication time');
        const files = wideFiles(post);
        if (!files) continue; // An unfinished native render must not replace the last published episode.
        const date = sessionDate(title, publishedAt);
        const { video, poster } = files;
        selected.set(market, {
            id: post.id, market, title, publishedAt, ...(date ? { sessionDate: date } : {}), permalink: post.instagram,
            sourceFingerprint: digest(video.sha256 + poster.sha256), layout: 'landscape', video, poster,
        });
    }
    assert([...MARKETS.values()].every(market => selected.has(market) || previous.has(market)), 'both market episodes are required');
    return [...selected.values()];
}

async function rendition(request, item, role, directory) {
    const file = item[role];
    const original = await readSource(request, file.endpoint, file.mime, file.bytes, 90000);
    assert(original.length === file.bytes && digest(original) === file.sha256, 'source file checksum mismatch');
    const video = role === 'video';
    const extension = video ? 'mp4' : 'jpg';
    const source = path.join(directory, `source.${extension}`);
    const output = path.join(directory, `web.${extension}`);
    fs.writeFileSync(source, original);
    probeLandscape(source);
    const args = video
        ? ['-map', '0:v:0', '-map', '0:a:0?', '-vf', "scale=w='min(1280,iw)':h=-2,setsar=1", '-c:v', 'libx264', '-preset', 'fast', '-crf', '22', '-maxrate', '1200k', '-bufsize', '2400k', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '64k', '-movflags', '+faststart']
        : ['-map', '0:v:0', '-frames:v', '1', '-vf', "scale=w='min(1280,iw)':h=-2,setsar=1", '-q:v', '7'];
    execFileSync(process.env.FFMPEG_PATH || 'ffmpeg', [
        '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-protocol_whitelist', 'file,pipe', '-i', source,
        ...args, '-map_metadata', '-1', '-map_chapters', '-1', output,
    ], { stdio: 'ignore', timeout: 120000, env: { PATH: process.env.PATH } });
    const body = fs.readFileSync(output);
    probeLandscape(output);
    assert(body.length > 0 && body.length <= (video ? 12 * 1024 * 1024 : 150 * 1024), 'rendition size exceeded');
    return { body, name: `${PREFIX}${item.id}/${role}-${digest(body)}.${extension}`, mime: file.mime };
}

function assetUrl(url, id, role) {
    const start = `${BLOB}${PREFIX}${id}/${role}-`;
    const suffix = role === 'video' ? /^[a-f0-9]{64}\.mp4$/ : /^[a-f0-9]{64}\.jpg$/;
    return typeof url === 'string' && url.startsWith(start) && suffix.test(url.slice(start.length));
}

function readPrevious(body) {
    const previous = new Map();
    if (!body) return previous;
    const { version, items } = JSON.parse(body);
    assert(version === 1 && Array.isArray(items) && items.length === 2, 'invalid previous index');
    for (const { id, market, title, publishedAt, sessionDate, permalink, sourceFingerprint, layout, posterUrl, videoUrl } of items) {
        assert(typeof id === 'string' && ID.test(id) && (market === 'KR' || market === 'US') &&
            !previous.has(market) && validTitle(title) && typeof publishedAt === 'string' &&
            PUBLICATION_TIME.test(publishedAt) && Number.isFinite(Date.parse(publishedAt)) &&
            typeof permalink === 'string' && PERMALINK.test(permalink) &&
            typeof sourceFingerprint === 'string' && SHA.test(sourceFingerprint) &&
            assetUrl(posterUrl, id, 'poster') && assetUrl(videoUrl, id, 'video'), 'invalid previous episode');
        assert(sessionDate === undefined || (typeof sessionDate === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(sessionDate) &&
            Number.isFinite(Date.parse(sessionDate)) && new Date(sessionDate).toISOString().slice(0, 10) === sessionDate), 'invalid previous session date');
        assert(layout === undefined || layout === 'landscape', 'invalid previous layout');
        previous.set(market, { id, market, title, publishedAt, ...(sessionDate ? { sessionDate } : {}), permalink, sourceFingerprint, ...(layout ? { layout } : {}), posterUrl, videoUrl });
    }
    return previous;
}

async function publicResponse(name, bypass = false, method = 'GET') {
    return fetch(BLOB + name + (bypass ? `?readback=${Date.now()}` : ''), {
        method, redirect: 'error', signal: AbortSignal.timeout(30000),
    });
}

async function assetAvailable(url, mime) {
    const name = url.slice(BLOB.length);
    let response;
    try {
        response = await publicResponse(name, true, 'HEAD');
    } catch (error) {
        if (!transientError(error)) throw error;
    }
    if (!response || response.status === 429 || response.status >= 500) {
        await wait(2000);
        response = await publicResponse(name, true, 'HEAD');
    }
    if (response.status === 404) return false;
    assert(response.ok && response.headers.get('content-type')?.split(';')[0] === mime &&
        Number(response.headers.get('content-length')) > 0, 'public asset verification failed');
    return true;
}

async function readBack(name, expected, limit, delays = [0, 2000, 2000, 2000]) {
    for (const delay of delays) {
        if (delay) await wait(delay);
        try {
            const response = await publicResponse(name, true);
            if (response.ok) {
                if (expected.equals(await readBounded(response, limit))) return;
            } else await response.body?.cancel();
        } catch (error) {
            if (!transientError(error)) throw error;
        }
    }
    throw Error('public readback mismatch');
}

async function putAsset(asset, put, token) {
    const existing = await publicResponse(asset.name);
    if (existing.status === 404) {
        const result = await put(asset.name, asset.body, {
            token, access: 'public', addRandomSuffix: false, contentType: asset.mime, cacheControlMaxAge: 604800,
        });
        assert.equal(result.url, BLOB + asset.name, 'unexpected asset store');
    } else {
        assert(existing.ok && asset.body.equals(await readBounded(existing, asset.body.length)), 'existing asset mismatch');
        return;
    }
    await readBack(asset.name, asset.body, asset.body.length);
}

async function main() {
    let stage = 'configuration';
    const dryRun = process.argv.includes('--dry-run');
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'market-close-'));
    try {
        const request = sourceClient(process.env.OBNW_MEDIA_ORIGIN || '', process.env.OBNW_MEDIA_KEY || '');
        const token = process.env.BLOB_READ_WRITE_TOKEN || '';
        if (!dryRun) checkBlobToken(token);
        const sdk = dryRun ? null : require('@vercel/blob');
        stage = 'source-list';
        const payload = JSON.parse(await readSource(request, '/api/media/posts?category=market&format=reel&channel=instagram&limit=30', 'application/json', 500000, 20000));
        stage = 'previous-index';
        const previous = dryRun ? null : await publicResponse(INDEX, true);
        assert(!previous || previous.ok || previous.status === 404, 'cannot read previous index');
        const before = previous?.ok ? await readBounded(previous, 16000) : null;
        const existing = readPrevious(before);
        stage = 'episode-selection';
        const episodes = selectEpisodes(payload, Date.now(), existing);
        const items = [];
        for (const old of existing.values()) {
            if (episodes.some(episode => episode.market === old.market)) continue;
            stage = 'retained-assets';
            assert((await Promise.all([
                assetAvailable(old.posterUrl, 'image/jpeg'), assetAvailable(old.videoUrl, 'video/mp4'),
            ])).every(Boolean), 'retained episode assets are missing');
            items.push(old);
        }
        for (const { video, poster, ...episode } of episodes) {
            stage = 'existing-assets';
            const old = existing.get(episode.market);
            const reusable = old?.id === episode.id && old.sourceFingerprint === episode.sourceFingerprint &&
                assetUrl(old.videoUrl, episode.id, 'video') && assetUrl(old.posterUrl, episode.id, 'poster');
            if (reusable && (await Promise.all([
                assetAvailable(old.posterUrl, poster.mime), assetAvailable(old.videoUrl, video.mime),
            ])).every(Boolean)) {
                items.push({ ...episode, posterUrl: old.posterUrl, videoUrl: old.videoUrl });
                continue;
            }
            stage = 'renditions';
            const cover = await rendition(request, { ...episode, poster }, 'poster', directory);
            const clip = await rendition(request, { ...episode, video }, 'video', directory);
            console.log(JSON.stringify({ id: episode.id, market: episode.market, videoBytes: clip.body.length, posterBytes: cover.body.length }));
            if (sdk) {
                stage = 'asset-publish';
                await putAsset(cover, sdk.put, token);
                await putAsset(clip, sdk.put, token);
            }
            items.push({ ...episode, posterUrl: BLOB + cover.name, videoUrl: BLOB + clip.name });
        }
        items.sort((a, b) => Date.parse(b.publishedAt) - Date.parse(a.publishedAt));
        const body = Buffer.from(JSON.stringify({ version: 1, items }) + '\n');
        const retainedMarkets = items.filter(item => !episodes.some(episode => episode.market === item.market)).map(item => item.market);
        const receipt = status => {
            const summary = { status, episodes: items.length, retainedMarkets, manifestBytes: body.length, sha256: digest(body),
                items: items.map(({ id, market, publishedAt, layout, sourceFingerprint, posterUrl, videoUrl }) =>
                    ({ id, market, publishedAt, layout: layout || 'legacy', sourceFingerprint, posterUrl, videoUrl })) };
            if (process.env.MARKET_CLOSE_RECEIPT_PATH) fs.writeFileSync(process.env.MARKET_CLOSE_RECEIPT_PATH, JSON.stringify(summary) + '\n', { mode: 0o600 });
            console.log(JSON.stringify(summary));
        };
        if (!sdk || before?.equals(body)) {
            receipt(dryRun ? 'dry-run' : 'unchanged');
            return;
        }
        stage = 'index-publish';
        const etag = before ? (await sdk.head(BLOB + INDEX, { token })).etag : undefined;
        assert(!before || (etag && previous.headers.get('etag')?.replace(/^W\//, '') === etag.replace(/^W\//, '')), 'index changed during publish');
        const result = await sdk.put(INDEX, body, {
            token, access: 'public', addRandomSuffix: false, allowOverwrite: !!before, ...(etag ? { ifMatch: etag } : {}),
            contentType: 'application/json', cacheControlMaxAge: 60,
        });
        assert.equal(result.url, BLOB + INDEX, 'unexpected index store');
        stage = 'index-readback';
        // An overwritten public Blob can take up to a minute to reach CDN reads.
        await readBack(INDEX, body, 16000, [0, 4000, 8000, 16000, 35000]);
        receipt('published');
    } catch (error) {
        // Diagnostics must never include request headers, keys or provider bodies.
        console.error(`market-close ${stage} failed (${error.name})`);
        process.exitCode = 1;
    } finally {
        fs.rmSync(directory, { recursive: true, force: true });
    }
}

module.exports = { selectEpisodes, sessionDate, readBounded, checkBlobToken, wideFiles, assertLandscape, probeLandscape, readPrevious };
if (require.main === module) void main();
