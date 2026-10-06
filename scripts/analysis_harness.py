#!/usr/bin/env python3
"""Private AlphaConsole analysis harness (local, no automatic model or orders).

Prepare via --ticker (existing live reader) OR --facts-file (offline bundle).
Use template to create an editable review, inspect the original packet and verify
primary evidence, validate, then finalize. status never means monitoring is active.
Default output is private/decisions/analysis_harness; do not publish its contents.

python scripts/analysis_harness.py prepare --facts-file /path/to/facts.json
python scripts/analysis_harness.py template --packet ID --output /private/path/review.json
python scripts/analysis_harness.py inspect --packet ID
python scripts/analysis_harness.py validate --review /private/path/review.json
python scripts/analysis_harness.py finalize --review /private/path/review.json
python scripts/analysis_harness.py status --packet ID

Review basis_axes are packet section IDs (s1, s2, ...). Every section needs
reviewed/not_used plus a reason. Acknowledged gaps are listed by inspect; this
acknowledgement is not evidence that a source was fetched. Confirmed basis claims
need section_id, claim, value (text), primary URL, source_as_of (ISO date), excerpt,
checked_at (timezone-aware ISO), source_kind=primary, status=confirmed.
Use unresolved/refuted when appropriate. Counterevidence, limitations and
change_conditions are mandatory. Unknown/stale basis permits only 보류/low.
valid_until is reviewer-declared validity, not an automatic monitoring schedule.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.intelligence import analysis_harness as harness
from api.intelligence import operator_context as context


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runtime", type=Path, default=harness.RUNTIME)
    parser.add_argument("--journal", type=Path, help="Alternate PRIVATE journal; use only for isolated tests")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    source = prepare.add_mutually_exclusive_group(required=True)
    source.add_argument("--ticker")
    source.add_argument("--facts-file", type=Path)
    prepare.add_argument("--question", default="")
    for name in ("inspect", "status", "template"):
        command = sub.add_parser(name)
        command.add_argument("--packet", required=True)
        if name == "inspect":
            command.add_argument("--full", action="store_true", help="Private raw facts; never public output")
        if name == "template":
            command.add_argument("--output", type=Path, required=True)
    for name in ("validate", "finalize"):
        command = sub.add_parser(name)
        command.add_argument("--review", type=Path, required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--before", required=True)
    compare.add_argument("--after", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            if args.facts_file:
                packet = harness.build_packet(context.read_json(args.facts_file), args.question)
                harness.save_packet(packet, args.runtime)
            else:
                packet = harness.prepare(args.ticker, args.question, runtime=args.runtime)
            result = dict(packet_id=packet["packet_id"], state="awaiting_review",
                          packet_path=str(harness.packet_path(args.runtime, packet["packet_id"])),
                          section_count=len(packet["sections"]), sources=packet["sources"]["counts"],
                          model_calls=0, orders_authorized=False)
        elif args.command == "compare":
            result = harness.compare(harness.load_packet(args.before, args.runtime),
                                     harness.load_packet(args.after, args.runtime))
        elif args.command == "status":
            result = harness.status(args.packet, runtime=args.runtime, journal_path=args.journal)
        elif args.command in ("inspect", "template"):
            packet = harness.load_packet(args.packet, args.runtime)
            if args.command == "template":
                # Exclusive creation: never overwrite a user's in-progress review.
                args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with open(args.output, "x", encoding="utf-8",
                          opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
                    stream.write(json.dumps(harness.review_template(packet), ensure_ascii=False, indent=2) + "\n")
                result = dict(review_template=str(args.output), state="unreviewed_template")
            elif args.full:
                result = packet
            else:
                result = dict(packet_id=args.packet, ticker=packet["facts"]["ticker"],
                              sections=packet["sections"], sources=packet["sources"],
                              missing=packet["facts"]["missing"], gap_ids=harness.gap_ids(packet))
        else:
            review = context.read_json(args.review)
            if not isinstance(review, dict):
                raise ValueError("review file must contain an object")
            if args.command == "validate":
                result = harness.validate_review(harness.load_packet(review.get("packet_id"), args.runtime), review)
            else:
                record = harness.finalize(review.get("packet_id"), review, runtime=args.runtime, journal_path=args.journal)
                result = dict(record_id=record["record_id"], saved_at=record["ts_kst"],
                              state="recorded", orders_authorized=False)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, harness.journal.JournalError) as exc:
        # Errors contain contract names, not the private input document.
        print(f"analysis harness: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
