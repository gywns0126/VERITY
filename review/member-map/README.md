# AlphaNest standalone member-map review

Temporary integration surface: `https://project-yw131.vercel.app/member-map-review`.
This is not a replacement for the accepted Sites v36 design and is not a Framer Publish.

## Boundaries

- Existing AlphaNest Google/email sign-in; no new provider, test identity creation, or session transfer.
- The review shell is publicly downloadable; holdings and map records require the existing member JWT and owner checks. `noindex` is not an access control.
- Holdings are read-only in this client. Map positions, notes and marks are drafts until explicit save; existing revision-conflict and account-switch protections are unchanged.
- `Map.snapshot.tsx` is a generated projection of the tested local `PortfolioMapReview.entry.tsx` and its real-controller module graph. It supersedes the earlier two-section visual-only projection. Existing auth, member-state transport, document sources, quote normalizer and API routes are unchanged. This standalone snapshot has not been saved back into Framer.
- `Auth.snapshot.tsx` was fresh-read from `k5Rb6uP` on 2026-09-29 KST; it matches the local mirror after whitespace normalization. It is reused, not pushed back to Framer. Only normal browser login creates the session.
- PublicAuth remains mounted when its account panel is hidden so refresh/listeners survive. The map is not mounted while signed out.
- Only the exact review return URL may be added to Supabase's existing redirect list. Existing URLs and Site URL must remain unchanged.
- The review uses the API's own origin: no CORS allowlist expansion, proxy or origin spoofing.
- Document mode represents company-to-source-document associations, not automatically verified events. Separate reviewed modes contain seven official documents, three dated relationships and two historical common announcements (NVDA/INTC/TSM and SK hynix). Document count is not independent-publisher count: the SK hynix 2024-04-19 Korean/English releases are two editions of one announcement. TSMC's 2023-09-28 memory-partner release corroborates the broader HBM relationship, not that later MOU or current production. These are not a current market-wide feed or evidence of investment impact. Missing matching holdings produce an honest empty state.

## Data and records delivery — 2026-09-29

The current priority is actual data and explicit private persistence; further design alignment is deferred. New reviewed state uses `reviewed:relationships:<id>` and `reviewed:events:<id>` keys. Only personal marks and an equality-only content fingerprint are stored, not copied source documents. Existing notes, positions and document marks are preserved. Content changes request re-reading; the fingerprint is not an event timestamp or an ordered version.

The read-only holdings list reuses the same holdings response; it neither edits holdings nor treats the 30-company map window as a holdings limit. Quantity and cost are shown only when valid, and duplicate lots are not incorrectly summed. Closing-price eligibility remains unchanged; no sample quote replaces missing or permission-blocked data.

Prior source validation: 47/47 focused renderer, reviewed-state and fresh-controller journey checks, strict TypeScript, and 3/3 reviewed-mark payloads accepted by the local API validator. Those used synthetic transport and do not prove deployed member acceptance. After delivery, separately verify authenticated save acknowledgement and a fresh-page restore. No DB, API, CORS, provider or redirect change is part of this delivery.

## Holdings token-rotation recovery — 2026-09-30

The map reads the current same-member session immediately before requesting holdings. After a 401 it retries once only if the normal authentication flow has already produced a different token for that same member. Both attempts share the original 15-second timeout. Logout, account changes, disposal and superseding requests prevent stale results or retries. An unchanged token or a second 401 remains an explicit error; this does not refresh credentials, poll for a future refresh or change shared authentication. The prior live first-load failure was not traced to a captured token race, so synthetic regression coverage alone does not establish its original cause or complete resolution.

## Earlier compact design provenance (historical)

The same local renderer passed 53 focused checks plus bounded 30-company browser checks before projection into this snapshot. Rebuilt with existing esbuild (`bundle`, ESM, classic JSX transform, UTF-8, React/ReactDOM/Framer external), only these two source sections were substituted; the other generated sections were compared exactly before writing:

- `PortfolioMapCanvas.tsx`: `e4943d3a267add06d2acb95723a1be69ebef6afcd842b71b5454c2d3b8b5e611`
- `PublicPortfolioMap.tsx`: `8271b591aeee91241d02c119ffb1b082dde03a5b6ea9a40c9c3b60975841b03c`
- Resulting `Map.snapshot.tsx`: `d5aec3b9cf7263e3f16f55d65e750efa0b59c6e968078a64581f9a18a7b4d700`

Long-title follow-up: each card title and subtitle is limited to two visible lines. Full text stays in the DOM, accessible name, hover and detail panel; saved coordinates are not rewritten. A synthetic 30-company / 6-long-document view measured 78px document heights and zero overlapping pairs out of 630 at the default layout. This does not prevent a user from deliberately dragging cards on top of each other.

This brings the accepted v36 compact controls, source colors, pan/zoom grid, measured cards and above-card hover placement into the authenticated review. Actual document content and evidence boundaries intentionally differ from the fictional design fixture. A real pointer-hover placement acceptance remains separate from the source/geometry checks.

## Build

`node review/member-map/build.cjs /path/to/existing/verity/workspace`

The path supplies already-installed esbuild/React and existing `.env` public Supabase URL/anon key. The build validates project ref and `role=anon`; no service key, private response or member record is included. No source map or external script is loaded. Review-specific CSP/robots/cache headers do not modify existing API routes, `ignoreCommand`, authentication or database permissions.

Static files belong under the API project's existing `vercel-api/public/` output directory. `public/member-map-review.html` is served at `/member-map-review` with the existing `cleanUrls` setting; its script and stylesheet live under `public/member-map-review/`. Do not place them beside `vercel.json`: the existing `public` directory means those root-level files are not served.

## Verify

Check the signed-out page and console first. Once deployed, read back HTML/asset hashes and scoped headers, then have the user complete normal Google sign-in. Verify holdings retrieval, existing map-state retrieval, explicit test edits, save acknowledgement and a fresh page restoration separately. Preserve existing notes/layouts/marks. Do not infer browser acceptance from prior API-runner tests.
