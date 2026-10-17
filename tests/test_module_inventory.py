"""Tests for registered module inventory."""
import json
import tempfile
import unittest
from pathlib import Path
from scripts.module_inventory import module_inventory

class ModuleInventoryTests(unittest.TestCase):
    def test_manifest_lists_modules_without_cloning(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "modules.json"
            manifest.write_text(json.dumps({
                "schema_version": 1, "policy": {"mode": "read-only", "network_access": False},
                "modules": [{"id": "runner", "repository": "example/runner",
                             "visibility": "public", "purpose": "test", "archived": False}]
            }), encoding="utf-8")
            result = module_inventory(manifest, tmp)
            self.assertFalse(result["network_used"])
            self.assertFalse(result["modules"][0]["local"]["exists"])
            self.assertFalse((Path(tmp) / "runner").exists())

    def test_rejects_network_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "modules.json"
            manifest.write_text(json.dumps({
                "schema_version": 1, "policy": {"mode": "read-only", "network_access": True},
                "modules": []
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                module_inventory(manifest, tmp)

if __name__ == "__main__":
    unittest.main()
