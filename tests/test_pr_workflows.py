"""Exercise the workflow shell steps without copying the shared title policy."""

import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
CHECKS = (ROOT / ".github/workflows/battery-tests.yml").read_text()
TITLE = (ROOT / ".github/workflows/pr-title-check.yml").read_text()


def step_script(workflow, name):
    """Extract a named step's run command, not a replacement YAML parser."""
    lines = workflow.splitlines()
    start = lines.index(f"      - name: {name}")
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("      - "):
            break
        if not line.startswith("        run: "):
            continue
        command = line.removeprefix("        run: ")
        if command != "|":
            return command + "\n"
        script = []
        for line in lines[index + 1:]:
            if line and not line.startswith("          "):
                break
            script.append(line[10:] if line else "")
        return "\n".join(script) + "\n"
    raise AssertionError(f"Missing run command for {name}")


HYGIENE = step_script(CHECKS, "Check changed-line whitespace")
TITLE_GATE = step_script(TITLE, "Require successful shared title validation")


class WorkflowContractTests(unittest.TestCase):
    def test_required_gates_and_existing_runner(self):
        self.assertIn("    name: Run checks\n", CHECKS)
        self.assertIn("      - run: bash tests/run-checks.sh\n", CHECKS)
        self.assertIn("      - run: python3 tests/test_pr_workflows.py\n", CHECKS)
        self.assertIn("python-version: '3.13'", CHECKS)
        self.assertIn("    name: Validate PR Title\n", TITLE)
        self.assertIn("    needs: title\n", TITLE)
        self.assertIn("    if: ${{ always() }}\n", TITLE)
        self.assertIn("RESULT: ${{ needs.title.result }}", TITLE)
        self.assertIn(
            "uses: Gambit-Defense/Automation/.github/workflows/pr-title.yml@v1",
            TITLE,
        )

    def test_events_and_read_only_execution(self):
        self.assertIn("  push:\n", CHECKS)
        for workflow in (CHECKS, TITLE):
            self.assertIn("    branches: [develop, main]\n", workflow)
            self.assertNotIn("pull_request_target", workflow)
            self.assertNotIn("continue-on-error", workflow)
            self.assertNotIn("secrets:", workflow)
            self.assertNotIn("paths:", workflow)
        self.assertIn("types: [opened, edited, reopened, synchronize]", CHECKS)
        self.assertIn(
            "types: [opened, edited, reopened, synchronize, labeled, unlabeled]",
            TITLE,
        )
        self.assertIn("ref: ${{ github.event.pull_request.head.sha || github.sha }}", CHECKS)
        self.assertIn("fetch-depth: 0", CHECKS)
        self.assertIn("persist-credentials: false", CHECKS)
        self.assertIn("permissions:\n  contents: read\n", CHECKS)
        self.assertIn("permissions:\n  pull-requests: read\n", TITLE)
        self.assertIn("    permissions: {}\n", TITLE)
        self.assertNotIn("actions/checkout", TITLE)
        self.assertIn("group: pr-title-check-${{ github.ref }}", TITLE)
        self.assertIn("cancel-in-progress: true", TITLE)

    def test_title_gate_requires_success(self):
        for result in ("success", "failure", "cancelled", "skipped", ""):
            with self.subTest(result=result):
                completed = subprocess.run(
                    ["bash", "-c", TITLE_GATE],
                    env={**os.environ, "RESULT": result},
                    text=True, capture_output=True, timeout=5,
                )
                self.assertEqual(completed.returncode == 0, result == "success")


class ChangedLineHygieneTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="pr-workflow-")
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Workflow test")
        self.git("config", "user.email", "workflow-test@example.invalid")
        self.git("config", "core.whitespace", "trailing-space,space-before-tab")
        self.base = self.commit("historical whitespace \n", "historical.txt")
        self.git("update-ref", "refs/remotes/origin/develop", self.base)
        self.head = self.commit("clean added line\n")

    def git(self, *args):
        completed = subprocess.run(
            ["git", "-C", str(self.repo), *args],
            text=True, capture_output=True, check=True, timeout=10,
        )
        return completed.stdout.strip()

    def commit(self, content, filename="fixture.txt"):
        (self.repo / filename).write_text(content)
        self.git("add", filename)
        self.git("commit", "-qm", "Workflow fixture")
        return self.git("rev-parse", "HEAD")

    def run_hygiene(self, **metadata):
        env = {
            **os.environ,
            "EVENT_NAME": "push",
            "EXPECTED_SHA": self.git("rev-parse", "HEAD"),
            "BASE_SHA": self.base,
            "BEFORE_SHA": self.base,
        }
        env.update(metadata)
        return subprocess.run(
            ["bash", "-c", HYGIENE], cwd=self.repo, env=env,
            text=True, capture_output=True, timeout=10,
        )

    def test_clean_changes_ignore_historical_whitespace(self):
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                completed = self.run_hygiene(EVENT_NAME=event)
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertIn(f"Checked source: {self.head}", completed.stdout)
                self.assertIn(f"Hygiene base: {self.base}", completed.stdout)

    def test_added_trailing_whitespace_fails(self):
        self.commit("bad added line \n")
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                completed = self.run_hygiene(EVENT_NAME=event)
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("trailing whitespace", completed.stdout)

    def test_pr_uses_merge_base(self):
        self.git("checkout", "-q", "--detach", self.base)
        target = self.commit("target-only change\n", "target.txt")
        self.git("checkout", "-q", "--detach", self.head)
        completed = self.run_hygiene(EVENT_NAME="pull_request", BASE_SHA=target)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn(f"Hygiene base: {self.base}", completed.stdout)

    def test_new_branch_uses_develop(self):
        completed = self.run_hygiene(BEFORE_SHA="0" * 40)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn(f"New branch baseline: {self.base}", completed.stdout)
        self.assertIn(f"Hygiene base: {self.base}", completed.stdout)

    def test_unrelated_new_branch_uses_empty_tree(self):
        self.git("checkout", "-q", "--orphan", "unrelated")
        self.git("rm", "-rf", ".")
        self.commit("clean new root\n")
        completed = self.run_hygiene(BEFORE_SHA="0" * 40)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        empty = self.git("hash-object", "-t", "tree", "--stdin")
        self.assertIn(f"Hygiene base: {empty}", completed.stdout)
        completed = self.run_hygiene(EVENT_NAME="pull_request")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Cannot determine PR merge base", completed.stderr)
        self.commit("bad new root \n")
        completed = self.run_hygiene(BEFORE_SHA="0" * 40)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("trailing whitespace", completed.stdout)

    def test_missing_or_invalid_metadata_fails(self):
        for metadata in (
            {"BEFORE_SHA": "f" * 40},
            {"BEFORE_SHA": "--help"},
            {"EVENT_NAME": "pull_request", "BASE_SHA": "f" * 40},
            {"EVENT_NAME": "unsupported"},
        ):
            with self.subTest(metadata=metadata):
                completed = self.run_hygiene(**metadata)
                self.assertNotEqual(completed.returncode, 0)

    def test_wrong_source_fails(self):
        completed = self.run_hygiene(EXPECTED_SHA=self.base)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Unexpected checked-out source SHA", completed.stderr)

    def test_missing_develop_history_fails(self):
        self.git("update-ref", "-d", "refs/remotes/origin/develop")
        completed = self.run_hygiene(BEFORE_SHA="0" * 40)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Missing origin/develop history", completed.stderr)


if __name__ == "__main__":
    unittest.main()
