import tempfile
import unittest
from pathlib import Path
from scripts.continuity import enqueue, claim
from scripts.maintenance import backup, check

class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "state" / "queue.sqlite3"
        self.destination = Path(self.tmp.name) / "backups" / "snapshot.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_backup_preserves_queue(self):
        enqueue(self.db, "demo", {"type": "echo", "value": 1})
        claim(self.db)
        result = backup(self.db, self.destination)
        self.assertEqual(result["integrity"], "ok")
        self.assertEqual(check(self.destination)["queue"], {"running": 1})

    def test_backup_never_overwrites(self):
        enqueue(self.db, "demo", {})
        backup(self.db, self.destination)
        with self.assertRaises(FileExistsError):
            backup(self.db, self.destination)

    def test_missing_db_does_not_create_backup(self):
        with self.assertRaises(FileNotFoundError):
            backup(self.db, self.destination)
        self.assertFalse(self.destination.exists())

    def test_source_cannot_be_destination(self):
        enqueue(self.db, "demo", {})
        with self.assertRaises(ValueError):
            backup(self.db, self.db)

if __name__ == "__main__":
    unittest.main()
