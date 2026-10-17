import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from pathlib import Path
from scripts.continuity import enqueue, summary
from scripts.ownership import acquire, complete, heartbeat
from scripts.recovery import recover_stale
from contextlib import closing
from datetime import datetime, timedelta, timezone
from scripts.continuity import connect

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

    def test_stale_owner_cannot_complete_after_recovery(self):
        enqueue(self.db, "reclaimed", {"type": "echo", "value": 1})
        first = acquire(self.db, "old-worker")
        clock = datetime.now(timezone.utc) + timedelta(hours=2)
        result = recover_stale(self.db, clock=clock, dry_run=False)
        self.assertEqual(result["retry"], ["reclaimed"])
        second = acquire(self.db, "new-worker")
        self.assertNotEqual(first["token"], second["token"])
        self.assertFalse(complete(self.db, "reclaimed", first["token"], {"old": True}))
        self.assertTrue(complete(self.db, "reclaimed", second["token"], {"new": True}))
        self.assertEqual(summary(self.db), {"done": 1})

    def test_heartbeat_blocks_stale_recovery(self):
        enqueue(self.db, "alive", {"type": "echo", "value": 1})
        first = acquire(self.db, "active-worker")
        with closing(connect(self.db)) as conn:
            with conn:
                conn.execute("UPDATE tasks SET updated_at=? WHERE id='alive'",
                    ((datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),))
        self.assertTrue(heartbeat(self.db, "alive", first["token"]))
        self.assertEqual(recover_stale(self.db, dry_run=False)["retry"], [])
        self.assertTrue(complete(self.db, "alive", first["token"], {"ok": True}))

    def test_concurrent_claims_are_exclusive(self):
        enqueue(self.db, "single", {"type": "echo", "value": 1})
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda i: acquire(self.db, "worker-" + str(i)), range(8)))
        claimed = [item for item in results if item is not None]
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0]["id"], "single")

    def test_concurrent_settlement_only_one_wins(self):
        enqueue(self.db, "settle-once", {"type": "echo", "value": 1})
        owned = acquire(self.db, "settlement-worker")
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda i: complete(self.db, "settle-once", owned["token"], {"winner": i}),
                range(8)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(summary(self.db), {"done": 1})
        with closing(connect(self.db)) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM task_results WHERE task_id='settle-once'"
            ).fetchone()[0], 1)

    def test_missing_owner_rejected(self):
        with self.assertRaises(ValueError):
            acquire(self.db, "")

if __name__ == "__main__":
    unittest.main()
