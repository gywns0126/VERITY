# Universe persistence-gap recovery

`universe_gap_backfill.py` handles the 2026-09-08 through 2026-09-11 gap.
It does **not** append reconstructed observations to production files.

## Inputs and outputs

1. Eight identified GitHub Actions runs provide recorded append counts, coarse
   filter counts, and candidate-difference counts. Only allowlisted log lines are
   saved. Candidate differences used the last **persisted** previous snapshot,
   not the previous failed run; they are not day-to-day membership transitions.
2. The Sep 7 / Sep 12 raw snapshot rosters at immutable commit
   `9129a576367d81db4cf14c30be8701b62c00d787` supply a boundary-union proxy roster.
   This is not the lost runs' exact membership. Source bytes are checked before
   and after collection, and no fundamentals are copied into the price sidecar.
3. Yahoo chart responses supply the four daily OHLCV bars. `date` is the
   exchange-local trading day; `retrieved_at` records actual recovery time.
   Provider bar timestamps are preserved, but are not treated as capture times.
   Quote prices are stored as returned, with `adj_close` separate. Provider
   corporate-action adjustments can be revised retrospectively, so these are
   not original intraday quotes or a point-in-time fundamental dataset.
   For missing KR bars only, Naver daily history is a fallback. Those records
   retain a different `source_url`; `provider_bar_timestamp` and `adj_close`
   remain null because that endpoint does not supply them. Existing Yahoo bars
   are never silently replaced by a fallback or later provider revision.
4. Outputs go only to `data/research/universe_gap_20260908_20260911/`, already
   excluded from the public repository. Back up explicit output paths to the
   existing private repository. No public Blob, API, Framer, recommendations,
   cron, production price lake, or score/trail consumer is changed.

## Reproduce / resume

Use a clean history checkout whose two Q3 snapshot files match the anchor commit:

```sh
python3 scripts/recovery/universe_gap_backfill.py \
  --history-root /absolute/path/to/anchor-checkout \
  --output /absolute/path/to/project/data/research/universe_gap_20260908_20260911
```

`--limit 3` makes a smoke run without shrinking the coverage denominator.
Normal reruns resume unattempted targets. `--retry-missing` retries targets with
missing days. Good saved bars remain unchanged; repeated runs do not duplicate
them. A single-writer lock prevents concurrent checkpoint replacement.

The manifest always reports `partial_original_recovery`: the original missing
full snapshots have **not** been recovered. `price_backfill_status` separately
reports price coverage. Exit 2 indicates price gaps; it must not be represented
as complete recovery. Missing prices remain missing, never zero/interpolated.

Verify after collection has stopped (not during an active checkpoint write):

```sh
python3 scripts/recovery/verify_universe_gap_backfill.py \
  /absolute/path/to/project/data/research/universe_gap_20260908_20260911 \
  --cross-source --report /absolute/path/to/project/data/research/universe_gap_20260908_20260911/verification.json
```

The optional cross-source check covers three KR sample instruments through Naver.
It reports OHLC and volume matches separately; provider differences are retained,
not corrected by guessing. This sample is not independent full-universe proof.

Files:

- `run_evidence.json`: eight source-linked historical log observations.
- `targets.json`: proxy roster and boundary observation dates.
- `prices_daily.jsonl`: one typed backfilled record per instrument/trading day.
- `attempts.json`: per-instrument collection outcomes.
- `coverage.json`: denominators and exact unresolved instrument/date list.
- `manifest.json`: scope, provenance, original losses, checksums, coverage.
- `verification.json` (optional): readback and separately scoped source checks.

Consumers of `data/stock_history/*.jsonl` intentionally cannot see this sidecar.
Use it explicitly for historical price research, not to erase freshness alarms
or inflate actual decision/observation sample sizes.
