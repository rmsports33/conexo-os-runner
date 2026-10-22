"""Static safety checks for the preserved Windows workers.

These tests never execute a worker, touch Scheduled Tasks, or open local state.
PowerShell syntax is validated separately by the hosted Windows CI job.
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ROOT / "windows"
WORKFLOW = ROOT / ".github" / "workflows" / "validate.yml"

WORKERS = (
    "conexo-autoops-check.ps1",
    "conexo-queue-worker.ps1",
    "conexo-task-executor.ps1",
    "conexo-watchdog.ps1",
)
DEPENDENCIES = (
    "conexo-recovery-policy-m0333.ps1",
    "conexo-sync.ps1",
    "conexo-m0311-prepare.ps1",
    "conexo-portable-local-sync.ps1",
)
ALL_FILES = WORKERS + DEPENDENCIES

HIGH_CONFIDENCE_SECRETS = re.compile(
    r"AKIA[0-9A-Z]{16}|"
    r"gh[pousr]_[A-Za-z0-9]{36}|"
    r"github_pat_[A-Za-z0-9_]{60,}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"AIza[0-9A-Za-z_-]{35}",
)


class WindowsWorkerStaticTests(unittest.TestCase):
    def test_workers_and_dependencies_are_versioned(self):
        for name in ALL_FILES:
            with self.subTest(name=name):
                self.assertTrue((WINDOWS / name).is_file())

    def test_no_machine_specific_home_path(self):
        patterns = (
            re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE),
            # A literal Linux home needs a user segment. `/home/|` appears in
            # conexo-sync's defensive regex and is intentionally allowed.
            re.compile(r"/home/[A-Za-z0-9._-]+", re.IGNORECASE),
        )
        for name in ALL_FILES:
            text = (WINDOWS / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                for pattern in patterns:
                    self.assertIsNone(pattern.search(text))

    def test_no_high_confidence_secret(self):
        for name in ALL_FILES:
            text = (WINDOWS / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIsNone(HIGH_CONFIDENCE_SECRETS.search(text))

    def test_state_stays_under_repository_local_state(self):
        for name in WORKERS:
            text = (WINDOWS / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIn("$PSScriptRoot", text)
                self.assertIn("local-state", text)

    def test_queue_worker_loads_versioned_recovery_policy(self):
        text = (WINDOWS / "conexo-queue-worker.ps1").read_text(encoding="utf-8")
        self.assertIn("Join-Path $PSScriptRoot 'conexo-recovery-policy-m0333.ps1'", text)

    def test_task_executor_remains_dry_run(self):
        text = (WINDOWS / "conexo-task-executor.ps1").read_text(encoding="utf-8")
        self.assertIn('mode = "DRY_RUN"', text)
        self.assertIn('status = "SIMULADA"', text)
        self.assertNotIn("Start-ScheduledTask", text)

    def test_autoops_does_not_enable_publish(self):
        text = (WINDOWS / "conexo-autoops-check.ps1").read_text(encoding="utf-8")
        self.assertIn("publication_performed = $false", text)
        self.assertNotRegex(text, r"conexo-sync\.ps1[^\r\n]*-Publish")

    def test_hosted_windows_ci_parses_every_preserved_script(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for name in ALL_FILES:
            with self.subTest(name=name):
                self.assertIn(f"windows/{name}", workflow)


if __name__ == "__main__":
    unittest.main()
