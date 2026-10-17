"""Tests for the offline, read-only Git inventory."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from scripts.git_inventory import inspect_repo, inventory

class GitInventoryTests(unittest.TestCase):
    def test_missing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            item = inspect_repo(Path(tmp) / "absent")
            self.assertFalse(item["exists"])
            self.assertFalse(item["git"])

    def test_plain_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            item = inspect_repo(tmp)
            self.assertTrue(item["exists"])
            self.assertFalse(item["git"])

    def test_local_git_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            try:
                subprocess.run(["git", "init", "-q", tmp], check=True, capture_output=True)
            except FileNotFoundError:
                self.skipTest("Git executable not installed")
            item = inspect_repo(tmp)
            self.assertTrue(item["git"])
            self.assertFalse(item["dirty"])
            self.assertFalse(item["remote_configured"])
            self.assertIn("commit", item)
            self.assertFalse(inventory([tmp])["network_used"])

if __name__ == "__main__":
    unittest.main()
