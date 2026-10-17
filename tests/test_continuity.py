import tempfile
import unittest
from pathlib import Path
from scripts.continuity import enqueue, claim, finish, recover, summary

class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "queue.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_idempotent_enqueue_and_completion(self):
        self.assertEqual(enqueue(self.db, "one", {"demo": True}), "pending")
        self.assertEqual(enqueue(self.db, "one", {"demo": False}), "pending")
        self.assertEqual(claim(self.db), {"id": "one", "payload": {"demo": True}})
        self.assertIsNone(claim(self.db))
        self.assertTrue(finish(self.db, "one"))
        self.assertFalse(finish(self.db, "one"))
        self.assertEqual(summary(self.db), {"done": 1})

    def test_explicit_recovery(self):
        enqueue(self.db, "two", {})
        self.assertEqual(claim(self.db)["id"], "two")
        self.assertEqual(recover(self.db), 1)
        self.assertEqual(claim(self.db)["id"], "two")
        self.assertTrue(finish(self.db, "two", success=False))
        self.assertEqual(summary(self.db), {"failed": 1})

if __name__ == "__main__":
    unittest.main()
