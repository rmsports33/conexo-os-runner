import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from scripts.continuity import connect, enqueue, summary
from scripts.ownership import acquire
from scripts.recovery import recover_stale

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "queue.sqlite3"
        self.clock = datetime(2026, 1, 2, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def age(self, task_id, attempts=1, seconds=7200):
        with closing(connect(self.db)) as conn:
            with conn:
                conn.execute("UPDATE tasks SET updated_at=?,attempts=? WHERE id=?",
                    ((self.clock - timedelta(seconds=seconds)).isoformat(), attempts, task_id))
                conn.execute("UPDATE task_leases SET heartbeat_at=? WHERE task_id=?",
                    ((self.clock - timedelta(seconds=seconds)).isoformat(), task_id))

    def test_dry_run_does_not_modify(self):
        enqueue(self.db, "a", {})
        acquire(self.db, 'recovery-test')
        self.age("a")
        result = recover_stale(self.db, clock=self.clock)
        self.assertEqual(result["retry"], ["a"])
        self.assertEqual(summary(self.db), {"running": 1})

    def test_apply_only_stale_tasks(self):
        for name in ("old", "fresh"):
            enqueue(self.db, name, {})
            acquire(self.db, 'recovery-test')
        self.age("old")
        self.age("fresh", seconds=30)
        result = recover_stale(self.db, clock=self.clock, dry_run=False)
        self.assertEqual(result["retry"], ["old"])
        self.assertEqual(summary(self.db), {"pending": 1, "running": 1})

    def test_exhausted_goes_to_failed(self):
        enqueue(self.db, "maxed", {})
        acquire(self.db, 'recovery-test')
        self.age("maxed", attempts=3)
        result = recover_stale(self.db, clock=self.clock, dry_run=False)
        self.assertEqual(result["exhausted"], ["maxed"])
        self.assertEqual(summary(self.db), {"failed": 1})

    def test_reject_unsafe_threshold(self):
        with self.assertRaises(ValueError):
            recover_stale(self.db, stale_seconds=1)

if __name__ == "__main__":
    unittest.main()
