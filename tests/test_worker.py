import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.continuity import connect, enqueue, recover, summary
from scripts.worker import MAX_ATTEMPTS, process_one, run

class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "queue.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

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

    def test_recovery_requires_explicit_action(self):
        enqueue(self.db, "interrupted", {"type": "echo", "value": 1})
        from scripts.continuity import claim
        self.assertEqual(claim(self.db)["id"], "interrupted")
        self.assertIsNone(process_one(self.db))
        self.assertEqual(recover(self.db), 1)
        self.assertEqual(process_one(self.db)["status"], "done")
        with closing(connect(self.db)) as conn:
            attempts = conn.execute("SELECT attempts FROM tasks WHERE id='interrupted'").fetchone()[0]
        self.assertEqual(attempts, 2)

    def test_limit(self):
        with self.assertRaises(ValueError):
            run(self.db, 0)

if __name__ == "__main__":
    unittest.main()
