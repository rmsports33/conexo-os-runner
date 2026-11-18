import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.continuity import enqueue, summary
from scripts.worker import MAX_ATTEMPTS, process_one


class MemoryCheckRegressionTests(unittest.TestCase):
    def test_missing_repository_is_settled_with_bounded_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite3"
            missing = str(Path(tmp) / "missing")
            enqueue(db, "memory-test", {
                "type": "memory_check",
                "category": "executor",
            })
            with patch.dict(os.environ, {"CONEXO_MEMORY_REPOS": missing}):
                results = [process_one(db) for _ in range(MAX_ATTEMPTS)]
            self.assertEqual(
                [item["status"] for item in results],
                ["pending"] * (MAX_ATTEMPTS - 1) + ["failed"],
            )
            self.assertTrue(all("error" in item for item in results))
            self.assertEqual(summary(db), {"failed": 1})
            self.assertIsNone(process_one(db))


if __name__ == "__main__":
    unittest.main()
