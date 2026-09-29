# AlphaNest standalone member-map review

Temporary integration surface: `https://project-yw131.vercel.app/member-map-review`.
This is not a replacement for the accepted Sites v36 design and is not a Framer Publish.

## Boundaries

- Existing AlphaNest Google/email sign-in; no new provider, test identity creation, or session transfer.
- The review shell is publicly downloadable; holdings and map records require the existing member JWT and owner checks. `noindex` is not an access control.
- Holdings are read-only in this client. Map positions, notes and marks are drafts until explicit save; existing revision-conflict and account-switch protections are unchanged.
- `Map.snapshot.tsx` starts from the saved Framer review component (`aPYjLyI`, source SHA `e4660dcfb7e0eb814a8d6586acc739748a32a2d9032cd0b1c78ebd9819e0e0be`). The 2026-09-29 compact-design delivery replaces only its Canvas and PublicPortfolioMap presentation sections. The 11 data/workspace/detail/theme sections and original review wrapper are retained byte-for-byte. This newer standalone snapshot has not been saved back into Framer.
- `Auth.snapshot.tsx` was fresh-read from `k5Rb6uP` on 2026-09-29 KST; it matches the local mirror after whitespace normalization. It is reused, not pushed back to Framer. Only normal browser login creates the session.
- PublicAuth remains mounted when its account panel is hidden so refresh/listeners survive. The map is not mounted while signed out.
- Only the exact review return URL may be added to Supabase's existing redirect list. Existing URLs and Site URL must remain unchanged.
- The review uses the API's own origin: no CORS allowlist expansion, proxy or origin spoofing.
- Graph data represents company-to-source-document associations. Shared documents are not automatically verified common events or investment impact. Cards use source-type colors, not fabricated impact/strength scores. Verified relationship/event inputs remain pending.

## Compact design provenance

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
