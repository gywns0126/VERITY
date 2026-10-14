"""Exercise manual deploy failure boundaries using a fake CLI; no network."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/vercel_deploy.sh"

class ManualDeployTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "scripts").mkdir()
        shutil.copyfile(SCRIPT, self.root / "scripts/vercel_deploy.sh")
        self.app = self.root / "vercel-api"
        (self.app / ".vercel").mkdir(parents=True)
        self.link = self.app / ".vercel/project.json"
        self.link.write_text(json.dumps(dict(projectId="prj_expected", orgId="team_expected", projectName="verity-api")))
        self.calls = self.root / "calls"
        self.cli = self.root / "cli"
        self.cli.write_text('''#!/usr/bin/env bash
printf "%s\\n" "$*" >> "$TEST_CALLS"
if [[ "$*" == *"project inspect"* ]]; then
  echo "${TEST_PROJECT:-prj_expected}"
fi
''')
        self.cli.chmod(0o755)
        self.env = dict(os.environ, VERCEL_CLI=str(self.cli), TEST_CALLS=str(self.calls))

    def run_script(self):
        return subprocess.run(["bash", str(self.root / "scripts/vercel_deploy.sh")], env=self.env, capture_output=True, text=True)

    def test_deploy_existing_project_without_mutating_link_or_git(self):
        before = self.link.read_bytes()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, self.link.read_bytes())
        calls = self.calls.read_text().splitlines()
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[-1], f"deploy --cwd {self.app} --prod --yes")
        self.assertFalse((self.root / ".git").exists())

    def test_missing_link_stops_before_cli(self):
        self.link.unlink()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_wrong_local_project_stops_before_cli(self):
        self.link.write_text(json.dumps(dict(projectId="other", orgId="team_expected", projectName="other")))
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_resolved_project_mismatch_never_deploys(self):
        self.env["TEST_PROJECT"] = "prj_other"
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertNotIn("deploy --cwd", self.calls.read_text())

    def test_missing_cli_does_not_install_or_deploy(self):
        self.env["VERCEL_CLI"] = str(self.root / "missing")
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertFalse(self.calls.exists())

if __name__ == "__main__":
    unittest.main()
