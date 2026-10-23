"""Validate the public cross-repository validation contract; never execute it."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ValidationContractTests(unittest.TestCase):
    def test_allowlist_is_non_executable(self):
        data = json.loads((ROOT / "config" / "validation_contract.json").read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["mode"], "offline-validation")
        self.assertIs(data["execute_commands_from_queue"], False)
        self.assertIs(data["allow_secrets"], False)
        self.assertEqual(data["network_during_tests"], "not_enforced")
        modules = data["modules"]
        self.assertEqual(set(modules), {"mkt-rss"})
        module = modules["mkt-rss"]
        self.assertEqual(module["repository"], "rmsports33/MKT-RSS")
        paths = module["test_paths"]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(paths)
        for path in paths:
            self.assertTrue(path.startswith("tests/test_"))
            self.assertTrue(path.endswith(".py"))
            self.assertNotIn("..", Path(path).parts)
            self.assertNotIn("\\", path)
        self.assertIn("no-wordpress", module["required"])


if __name__ == "__main__":
    unittest.main()
