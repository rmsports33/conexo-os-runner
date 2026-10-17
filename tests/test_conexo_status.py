
"""Tests for the portable Conexo OS status report."""

import tempfile
import unittest
from pathlib import Path

from scripts.conexo_status import generate_status


def inventory():
    return {
        "mode": "read-only",
        "network_used": False,
        "workspace": "C:\\Users\\PRIVATE",
        "modules": [
            {
                "id": "core",
                "repository": "example/conexo-os",
                "local": {
                    "path": "C:\\Users\\PRIVATE\\conexo-os",
                    "exists": True,
                    "git": True,
                    "branch": "secret-branch",
                    "commit": "secret-commit",
                },
            }
        ],
    }


class ConexoStatusTests(unittest.TestCase):

    def test_generates_module_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            result = generate_status(
                inventory(), None, Path(directory) / "missing.jsonl"
            )
            self.assertIn("example/conexo-os", result)
            self.assertIn("core", result)

    def test_excludes_local_paths_and_git_details(self):
        with tempfile.TemporaryDirectory() as directory:
            result = generate_status(
                inventory(), None, Path(directory) / "missing.jsonl"
            )
            self.assertNotIn("C:\\Users\\PRIVATE", result)
            self.assertNotIn("secret-branch", result)
            self.assertNotIn("secret-commit", result)

    def test_rejects_network_inventory(self):
        data = inventory()
        data["network_used"] = True

        with self.assertRaises(ValueError):
            generate_status(data, None, "missing.jsonl")

    def test_rejects_invalid_mode(self):
        data = inventory()
        data["mode"] = "write"

        with self.assertRaises(ValueError):
            generate_status(data, None, "missing.jsonl")

    def test_handles_missing_history(self):
        with tempfile.TemporaryDirectory() as directory:
            result = generate_status(
                inventory(), None, Path(directory) / "missing.jsonl"
            )
            self.assertIn("Historico indisponivel", result)


if __name__ == "__main__":
    unittest.main()
