import json
import tempfile
import unittest
from pathlib import Path

from scripts.module_history import detect_changes, update_history


def report(commit="abc123", dirty=False):
    return {
        "mode": "read-only",
        "network_used": False,
        "workspace": "test",
        "modules": [
            {
                "id": "core",
                "repository": "example/conexo-os",
                "local": {
                    "exists": True,
                    "git": True,
                    "branch": "main",
                    "commit": commit,
                    "dirty": dirty,
                    "remote_configured": True,
                },
            }
        ],
    }


class ModuleHistoryTests(unittest.TestCase):

    def test_detects_commit_change(self):
        changes = detect_changes(report("abc"), report("def"))
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["field"], "commit")
        self.assertEqual(changes[0]["before"], "abc")
        self.assertEqual(changes[0]["after"], "def")

    def test_detects_dirty_change(self):
        changes = detect_changes(
            report(dirty=False),
            report(dirty=True),
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["field"], "dirty")

    def test_identical_state_not_duplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "report.json"
            history = root / "history.jsonl"
            changes = root / "changes.json"

            source.write_text(json.dumps(report()), encoding="utf-8")

            first = update_history(source, history, changes)
            second = update_history(source, history, changes)

            self.assertTrue(first["recorded"])
            self.assertFalse(second["recorded"])
            self.assertEqual(len(history.read_text(
                encoding="utf-8"
            ).splitlines()), 1)

    def test_changed_state_creates_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "report.json"
            history = root / "history.jsonl"
            changes = root / "changes.json"

            source.write_text(
                json.dumps(report("abc")),
                encoding="utf-8",
            )
            update_history(source, history, changes)

            source.write_text(
                json.dumps(report("def")),
                encoding="utf-8",
            )
            result = update_history(source, history, changes)

            self.assertTrue(result["recorded"])
            self.assertEqual(result["change_count"], 1)
            self.assertEqual(len(history.read_text(
                encoding="utf-8"
            ).splitlines()), 2)

    def test_rejects_online_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "report.json"
            source.write_text(
                json.dumps({
                    **report(),
                    "network_used": True,
                }),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                update_history(
                    source,
                    root / "history.jsonl",
                    root / "changes.json",
                )


if __name__ == "__main__":
    unittest.main()
