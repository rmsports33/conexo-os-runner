import tempfile
import unittest
from pathlib import Path
from scripts.continuity import enqueue, summary
from scripts.ownership import acquire, complete, heartbeat

class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "queue.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_owner_only(self):
        enqueue(self.db, "one", {"type": "echo", "value": 1})
        a = acquire(self.db, "worker-a")
        self.assertEqual(a["id"], "one")
        self.assertIsNone(acquire(self.db, "worker-b"))
        self.assertTrue(heartbeat(self.db, "one", a["token"]))
        self.assertFalse(heartbeat(self.db, "one", "invalid"))
        self.assertFalse(complete(self.db, "one", "invalid", {"ok": True}))
        self.assertTrue(complete(self.db, "one", a["token"], {"ok": True}))
        self.assertFalse(complete(self.db, "one", a["token"], {"ok": True}))
        self.assertEqual(summary(self.db), {"done": 1})

    def test_missing_owner_rejected(self):
        with self.assertRaises(ValueError):
            acquire(self.db, "")

if __name__ == "__main__":
    unittest.main()
