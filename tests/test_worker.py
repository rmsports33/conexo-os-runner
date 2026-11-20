import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.continuity import connect, enqueue, summary
from scripts.ownership import acquire
from scripts.worker import MAX_ATTEMPTS, process_one, run


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "queue.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def _age_lease(self, task_id, *, attempts=None):
        stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        with closing(connect(self.db)) as conn:
            with conn:
                conn.execute("UPDATE tasks SET updated_at=? WHERE id=?", (stale, task_id))
                if attempts is not None:
                    conn.execute("UPDATE tasks SET attempts=? WHERE id=?", (attempts, task_id))
                conn.execute("UPDATE task_leases SET heartbeat_at=? WHERE task_id=?", (stale, task_id))

    def test_echo_and_count(self):
        enqueue(self.db, "a", {"type": "echo", "value": "hello"})
        enqueue(self.db, "b", {"type": "count", "items": [1, 2, 3]})
        result = run(self.db)
        self.assertEqual(len(result["processed"]), 2)
        self.assertEqual(summary(self.db), {"done": 2})
        self.assertEqual({x["id"]: x["result"] for x in result["processed"]},
                         {"a": {"echo": "hello"}, "b": {"count": 3}})

    def test_retries_are_bounded(self):
        enqueue(self.db, "invalid", {"type": "execute_shell", "command": "echo unsafe"})
        outcomes = [process_one(self.db) for _ in range(MAX_ATTEMPTS)]
        self.assertEqual([x["status"] for x in outcomes], ["pending", "pending", "failed"])
        self.assertEqual(summary(self.db), {"failed": 1})
        self.assertIsNone(process_one(self.db))

    def test_result_and_state_persist_together(self):
        enqueue(self.db, "persist", {"type": "echo", "value": "saved"})
        self.assertEqual(process_one(self.db)["status"], "done")
        with closing(connect(self.db)) as conn:
            status = conn.execute("SELECT status FROM tasks WHERE id='persist'").fetchone()[0]
            saved = conn.execute("SELECT result,error FROM task_results WHERE task_id='persist'").fetchone()
        self.assertEqual(status, "done")
        self.assertEqual(saved, ('{"echo": "saved"}', None))

    def test_run_recovers_stale_safe_task_and_reprocesses_it(self):
        enqueue(self.db, "stale-safe", {"type": "echo", "value": "resume"})
        acquire(self.db, "crashed-worker")
        self._age_lease("stale-safe")
        result = run(self.db, stale_seconds=60)
        self.assertEqual(result["recovery"]["retry"], ["stale-safe"])
        self.assertEqual(result["processed"][0]["id"], "stale-safe")
        self.assertEqual(result["processed"][0]["status"], "done")
        self.assertEqual(result["processed"][0]["attempts"], 2)

    def test_run_does_not_recover_unsupported_task(self):
        enqueue(self.db, "unsafe-stale", {"type": "execute_shell", "command": "echo unsafe"})
        acquire(self.db, "crashed-worker")
        self._age_lease("unsafe-stale")
        result = run(self.db, stale_seconds=60)
        self.assertEqual(result["recovery"]["skipped"], ["unsafe-stale"])
        self.assertEqual(result["processed"], [])
        self.assertEqual(summary(self.db), {"running": 1})

    def test_run_marks_exhausted_stale_task_failed(self):
        enqueue(self.db, "exhausted-stale", {"type": "echo", "value": "x"})
        acquire(self.db, "crashed-worker")
        self._age_lease("exhausted-stale", attempts=MAX_ATTEMPTS)
        result = run(self.db, stale_seconds=60)
        self.assertEqual(result["recovery"]["exhausted"], ["exhausted-stale"])
        self.assertEqual(summary(self.db), {"failed": 1})

    def test_limit(self):
        with self.assertRaises(ValueError):
            run(self.db, 0)


if __name__ == "__main__":
    unittest.main()
