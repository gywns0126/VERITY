"""Discovery list projection and the shared publication preflight."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

from api.builders.stock_report_list_public_builder import build, project, SCHEMA


ROOT = Path(__file__).resolve().parents[1]
REPORTS = {
    "stock_report_public.json": "stock_report_list_public.json",
    "us_stock_report_public.json": "us_stock_report_list_public.json",
    "us_stock_report_us_smallcap.json": "us_smallcap_report_list_public.json",
}
PANEL_FACTS = (
    "시가총액", "PER", "PBR", "ROE", "부채비율", "D/E",
    "영업이익률", "순이익률", "Altman-Z",
)


def mock_blob_upload(directory, fail_name=""):
    """Run the real uploader with in-memory Blob and manifest substitutes."""
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("Node is required for uploader integration")
    script = r'''
    const fs = require("fs"), vm = require("vm");
    const [sourcePath, dir, failName] = process.argv.slice(2);
    const attempts = {}, puts = {}, errors = [], order = [];
    const context = {
      require: name => name === "@vercel/blob" ? {
        put: async (name, body, options) => {
          attempts[name] = (attempts[name] || 0) + 1;
          if (name === failName) throw Error("simulated source PUT failure");
          order.push(name);
          if (name.startsWith("_blob_manifest__")) {
            process.stdout.write(JSON.stringify({attempts, puts, errors, order,
              manifest: JSON.parse(body.toString())}));
          } else puts[name] = {maxAge: options.cacheControlMaxAge};
          return {url: "https://example.invalid/" + name};
        },
        del: async () => {}
      } : require(name),
      process: {argv: ["node", "uploader", dir],
        env: {BLOB_READ_WRITE_TOKEN: "local-fake"},
        exit: code => {throw Error("unexpected exit " + code);}},
      fetch: async () => ({ok: false, status: 404}),
      Buffer, setTimeout,
      console: {log: () => {}, error: (...args) => errors.push(args.join(" "))}
    };
    vm.runInNewContext(fs.readFileSync(sourcePath, "utf8"), context);
    '''
    result = subprocess.run(
        [node, "-", str(ROOT / ".github/actions/publish-data/blob_upload.js"),
         str(directory), fail_name], input=script, text=True, capture_output=True, timeout=15,
    )
    if result.returncode or not result.stdout:
        raise AssertionError(f"mock uploader failed: {result.stderr}")
    return json.loads(result.stdout)


def present_fields(source, projected, keys):
    for key in keys:
        if key in source:
            assert key in projected and projected[key] == source[key], key
        else:
            assert key not in projected, key


class DiscoveryListTest(unittest.TestCase):
    def test_all_published_rows_preserve_discovery_inputs(self):
        total = 0
        for source_name in REPORTS:
            with self.subTest(source=source_name):
                source_bytes = (ROOT / "data" / source_name).read_bytes()
                source = json.loads(source_bytes)
                listing = project(source_bytes, source_name)
                self.assertEqual(listing["_meta"]["schema"], SCHEMA)
                self.assertEqual(listing["_meta"]["source_sha256"], hashlib.sha256(source_bytes).hexdigest())
                self.assertEqual(listing["_meta"]["generated_at"], source["_meta"]["generated_at"])
                self.assertEqual(len(listing["stocks"]), len(source["stocks"]))
                for original, row in zip(source["stocks"], listing["stocks"]):
                    total += 1
                    present_fields(original, row, ("ticker", "name", "market", "business"))
                    if "facts" in original and original["facts"] is not None:
                        present_fields(original["facts"], row["facts"], PANEL_FACTS)
                    else:
                        present_fields(original, row, ("facts",))
                    for nested, keys in (("overview", ("sector",)), ("peer", ("sector",)),
                                         ("ownership", ("group", "family_pct", "sub_count"))):
                        if nested in original and original[nested] is not None:
                            present_fields(original[nested], row[nested], keys)
                        else:
                            present_fields(original, row, (nested,))
                    if original.get("peer") and "rows" in original["peer"]:
                        if original["peer"]["rows"] is None:
                            self.assertIsNone(row["peer"]["rows"])
                        else:
                            self.assertEqual(len(row["peer"]["rows"]), len(original["peer"]["rows"]))
                            for a, b in zip(original["peer"]["rows"], row["peer"]["rows"]):
                                present_fields(a, b, ("key", "value", "median", "vs"))
                    if original.get("ownership"):
                        own, small = original["ownership"], row["ownership"]
                        if "cross_check" in own:
                            if own["cross_check"] is None:
                                self.assertIsNone(small["cross_check"])
                            else:
                                present_fields(own["cross_check"], small["cross_check"], ("status",))
                        if "shareholders" in own:
                            if own["shareholders"] is None:
                                self.assertIsNone(small["shareholders"])
                            else:
                                self.assertEqual(len(small["shareholders"]), min(3, len(own["shareholders"])))
                                for a, b in zip(own["shareholders"][:3], small["shareholders"]):
                                    present_fields(a, b, ("type", "name", "pct"))
        self.assertGreater(total, 10000)

    def test_missing_and_null_remain_distinct_and_failure_keeps_old_file(self):
        source = {"_meta": {"generated_at": "2026-10-26T00:00:00+09:00"}, "stocks": [
            {"ticker": "A", "name": "A", "facts": {"PER": None}, "peer": None,
             "ownership": {"shareholders": None}},
            {"ticker": "B", "name": "B"},
        ]}
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            inp, out = directory / "stock_report_public.json", directory / "stock_report_list_public.json"
            inp.write_text(json.dumps(source))
            build(inp, out)
            rows = json.loads(out.read_text())["stocks"]
            self.assertEqual(rows[0]["facts"], {"PER": None})
            self.assertIsNone(rows[0]["peer"])
            self.assertIsNone(rows[0]["ownership"]["shareholders"])
            self.assertNotIn("facts", rows[1])
            self.assertNotIn("peer", rows[1])
            old = out.read_bytes()
            inp.write_text('{"stocks": [')
            with self.assertRaises(json.JSONDecodeError):
                build(inp, out)
            self.assertEqual(out.read_bytes(), old)
            inp.write_text(json.dumps({"_meta": {}, "stocks": source["stocks"]}))
            with self.assertRaisesRegex(ValueError, "generated_at"):
                build(inp, out)
            self.assertEqual(out.read_bytes(), old)

    def test_publication_preflight_binds_list_to_accepted_source(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for source_name, list_name in REPORTS.items():
                source = {"_meta": {"generated_at": "2026-10-26T00:00:00+09:00"},
                          "stocks": [{"ticker": str(i).zfill(6) if source_name.startswith("stock_") else f"US{i}",
                                      "facts": {"PER": "1", "PBR": "1"}} for i in range(100)]}
                (directory / source_name).write_text(json.dumps(source))
                build(directory / source_name, directory / list_name)

            def preflight():
                return subprocess.run(
                    ["node", str(ROOT / ".github/actions/publish-data/blob_upload.js"),
                     "--verify-core", str(directory)], capture_output=True, text=True,
                )

            self.assertEqual(preflight().returncode, 0)
            listing = directory / REPORTS["stock_report_public.json"]
            good = listing.read_bytes()
            source_path = directory / "stock_report_public.json"
            source = json.loads(source_path.read_text())
            source["stocks"][0]["facts"]["PER"] = None
            source_path.write_text(json.dumps(source))
            self.assertNotEqual(preflight().returncode, 0)  # stale source SHA
            source_path.write_text(json.dumps({"_meta": source["_meta"], "stocks": []}))
            self.assertNotEqual(preflight().returncode, 0)  # rejected full source
            source_path.write_text(json.dumps(source))
            build(source_path, listing)
            tampered = json.loads(listing.read_text())
            tampered["stocks"][0]["secret"] = "private"
            listing.write_text(json.dumps(tampered))
            self.assertNotEqual(preflight().returncode, 0)  # allowlist
            listing.write_bytes(good)

    def test_real_uploader_source_failure_holds_its_list_and_other_pairs_continue(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            for source_name, list_name in REPORTS.items():
                kr = source_name == "stock_report_public.json"
                rows = [{"ticker": f"{i:06}" if kr else f"US{i}",
                         "facts": {"PER": "1", "PBR": "1"}} for i in range(100)]
                source = {"_meta": {"generated_at": "2026-10-26T00:00:00+09:00"},
                          "stocks": rows}
                (directory / source_name).write_text(json.dumps(source))
                build(directory / source_name, directory / list_name)
            result = mock_blob_upload(directory, "stock_report_public.json")
            attempts, puts, hashes = result["attempts"], result["puts"], result["manifest"]["hashes"]
            self.assertEqual(attempts["stock_report_public.json"], 2)
            self.assertNotIn("stock_report_public.json", puts)
            self.assertNotIn("stock_report_list_public.json", attempts)
            self.assertNotIn("stock_report_public.json", hashes)
            self.assertNotIn("stock_report_list_public.json", hashes)
            self.assertTrue(any("HOLD stock_report_list_public.json" in error for error in result["errors"]))
            for source, listing, age in (
                ("us_stock_report_public.json", "us_stock_report_list_public.json", 7200),
                ("us_stock_report_us_smallcap.json", "us_smallcap_report_list_public.json", 21600),
            ):
                self.assertEqual(puts[source]["maxAge"], age)
                self.assertEqual(puts[listing]["maxAge"], age)
                self.assertIn(source, hashes)
                self.assertIn(listing, hashes)
            healthy = mock_blob_upload(directory)
            for source, listing, age in (
                ("stock_report_public.json", "stock_report_list_public.json", 7200),
                ("us_stock_report_public.json", "us_stock_report_list_public.json", 7200),
                ("us_stock_report_us_smallcap.json", "us_smallcap_report_list_public.json", 21600),
            ):
                self.assertEqual(healthy["puts"][source]["maxAge"], age)
                self.assertEqual(healthy["puts"][listing]["maxAge"], age)

    def test_chart_directory_remains_independent_of_report_list_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            for root, folder in (("_chart_dist", "kr_chart_daily"),
                                 ("_history_dist", "kr_chart_history"),
                                 ("_us_history_dist", "us_chart_history")):
                with self.subTest(root=root):
                    directory = Path(temp) / root
                    (directory / folder).mkdir(parents=True)
                    (directory / folder / "fixture.json").write_text("{}")
                    result = mock_blob_upload(directory)
                    expected = f"{folder}/fixture.json"
                    self.assertEqual(set(result["puts"]), {expected})
                    self.assertEqual(set(result["manifest"]["hashes"]), {expected})
                    self.assertEqual(result["errors"], [])

    def test_business_receipt_is_last_and_put_failures_hold_it(self):
        business_sources = (
            "universe_search.json", "stock_report_public.json", "us_stock_report_public.json",
            "public_disclosure_feed.json", "us_disclosure_feed.json", "kr_business_overview_public.json",
        )
        artifact_name = "portfolio_public_business_index.json"
        receipt_name = "portfolio_public_business_release.json"
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "_public_dist"
            directory.mkdir()
            for source_name, list_name in REPORTS.items():
                source = {"_meta": {"generated_at": "2026-10-26T00:00:00+09:00"},
                          "stocks": [{"ticker": f"{i:06}" if source_name == "stock_report_public.json" else f"US{i}",
                                      "facts": {"PER": "1", "PBR": "1"}}
                                     for i in range(100)]}
                (directory / source_name).write_text(json.dumps(source))
                build(directory / source_name, directory / list_name)
            for name in business_sources:
                if not (directory / name).exists():
                    (directory / name).write_text("{}")
            day = datetime.now(timezone.utc).date().isoformat()
            artifact = {"schema": "portfolio-public-business-index-v1",
                        "matcher_version": "business-matchers-2026-10-26-v1",
                        "implementation_sha256": "a" * 64, "source_revision": "b" * 64,
                        "utc_day": day, "index": {}}
            artifact_bytes = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode()
            (directory / artifact_name).write_bytes(artifact_bytes)
            receipt = {"schema": "portfolio-public-business-release-v1",
                       "artifact_sha256": hashlib.sha256(artifact_bytes).hexdigest(),
                       "implementation_sha256": artifact["implementation_sha256"],
                       "source_revision": artifact["source_revision"], "utc_day": day}
            (directory / receipt_name).write_text(json.dumps(receipt))

            preflight = subprocess.run(
                ["node", str(ROOT / ".github/actions/publish-data/blob_upload.js"),
                 "--verify-core", str(directory)], capture_output=True, text=True,
            )
            self.assertEqual(preflight.returncode, 0, preflight.stderr)
            self.assertIn("6/6 core reports and lists passed", preflight.stdout)
            self.assertIn("optional business pair passed", preflight.stdout)

            good = mock_blob_upload(directory)
            self.assertIn(receipt_name, good["puts"], good["errors"])
            self.assertTrue(all(good["order"].index(name) < good["order"].index(artifact_name)
                                for name in business_sources))
            self.assertLess(good["order"].index(artifact_name), good["order"].index(receipt_name))
            self.assertEqual(good["order"][-2], receipt_name)  # manifest is last

            for failed_name in ("public_disclosure_feed.json", artifact_name):
                with self.subTest(failed=failed_name):
                    failed = mock_blob_upload(directory, failed_name)
                    self.assertEqual(failed["attempts"][failed_name], 2)
                    self.assertNotIn(receipt_name, failed["attempts"])
                    self.assertNotIn(receipt_name, failed["manifest"]["hashes"])
                    self.assertTrue(any(f"HOLD {receipt_name}" in error
                                        for error in failed["errors"]))
                    if failed_name in business_sources:
                        self.assertNotIn(artifact_name, failed["attempts"])
                        self.assertNotIn(artifact_name, failed["manifest"]["hashes"])
                    self.assertIn("stock_report_list_public.json", failed["puts"])

            action = (ROOT / ".github/actions/publish-data/action.yml").read_text()
            hold_step = action.split(
                "    - name: Hold invalid optional business candidate before either public write\n", 1
            )[1].split("\n    - name:", 1)[0]
            hold_script = textwrap.dedent(hold_step.split("      run: |\n", 1)[1])
            hold_script = hold_script.replace("${{ github.action_path }}", str(ROOT / ".github/actions/publish-data"))
            hold_script = hold_script.replace("${{ github.workspace }}", str(Path(temp)))
            for defect in ("checksum", "utc_day"):
                with self.subTest(defect=defect):
                    candidate = dict(artifact)
                    marker = dict(receipt)
                    if defect == "checksum":
                        marker["artifact_sha256"] = "0" * 64
                    else:
                        candidate["utc_day"] = "2000-01-01"
                        marker["utc_day"] = "2000-01-01"
                        candidate_bytes = json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
                        marker["artifact_sha256"] = hashlib.sha256(candidate_bytes).hexdigest()
                        (directory / artifact_name).write_bytes(candidate_bytes)
                    (directory / receipt_name).write_text(json.dumps(marker))
                    core = subprocess.run(
                        ["node", str(ROOT / ".github/actions/publish-data/blob_upload.js"),
                         "--verify-core", str(directory)], capture_output=True, text=True,
                    )
                    self.assertEqual(core.returncode, 0, core.stderr)
                    self.assertIn("6/6 core reports and lists passed", core.stdout)
                    self.assertIn("optional business pair held", core.stdout)
                    optional = subprocess.run(
                        ["node", str(ROOT / ".github/actions/publish-data/blob_upload.js"),
                         "--verify-business", str(directory)], capture_output=True, text=True,
                    )
                    self.assertNotEqual(optional.returncode, 0)
                    self.assertTrue((directory / artifact_name).exists())  # read-only checks
                    action_result = subprocess.run(
                        ["bash", "-c", hold_script], cwd=temp, capture_output=True, text=True,
                    )
                    self.assertEqual(action_result.returncode, 0, action_result.stderr)
                    self.assertFalse((directory / artifact_name).exists())
                    self.assertFalse((directory / receipt_name).exists())
                    self.assertTrue((directory / "stock_report_public.json").exists())
                    self.assertTrue((directory / "stock_report_list_public.json").exists())
                    (directory / artifact_name).write_bytes(artifact_bytes)

    def test_business_receipt_is_excluded_from_primary_and_restored_for_blob(self):
        action = (ROOT / ".github/actions/publish-data/action.yml").read_text()
        stages = (
            "Build optional public business index and publisher receipt",
            "Validate core public reports before either public write",
            "Hold invalid optional business candidate before either public write",
            "Reserve business receipt for final Blob publication",
            "Deploy to VERITY-data main branch",
            "Recover VERITY-data publish after commit_refs failure",
            "Dual-write to Vercel Blob",
        )
        positions = [action.index(stage) for stage in stages]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('mv "$receipt" "$receipt_dir/portfolio_public_business_release.json"', action)
        self.assertIn('steps.reserve_business_receipt.outputs.path', action)


if __name__ == "__main__":
    unittest.main()
