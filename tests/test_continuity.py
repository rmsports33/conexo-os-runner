import tempfile
import unittest
from pathlib import Path
from scripts.continuity import enqueue, summary
from scripts.ownership import acquire, complete

class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "queue.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_idempotent_enqueue_and_completion(self):
        self.assertEqual(enqueue(self.db, "one", {"demo": True}), "pending")
        self.assertEqual(enqueue(self.db, "one", {"demo": False}), "pending")
        item = acquire(self.db, "worker-a")
        self.assertEqual(item["payload"], {"demo": True})
        self.assertIsNone(acquire(self.db, "worker-b"))
        self.assertTrue(complete(self.db, "one", item["token"], {"ok": True}))
        self.assertEqual(summary(self.db), {"done": 1})

if __name__ == "__main__":
    unittest.main()
