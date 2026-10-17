"""Offline, standard-library-only task queue. Store the database on durable storage."""
import argparse
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY,
 payload TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','running','done','failed')),
 attempts INTEGER NOT NULL DEFAULT 0,
 updated_at TEXT NOT NULL
)
"""

def now():
    return datetime.now(timezone.utc).isoformat()

def connect(db):
    path = Path(db)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute(SCHEMA)
    conn.commit()
    return conn

def enqueue(db, task_id, payload):
    with closing(connect(db)) as conn:
        with conn:
            conn.execute("INSERT OR IGNORE INTO tasks(id,payload,status,updated_at) VALUES(?,?,'pending',?)",
                         (task_id, json.dumps(payload, sort_keys=True), now()))
            return conn.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()[0]

def summary(db):
    with closing(connect(db)) as conn:
        return dict(conn.execute("SELECT status,COUNT(*) FROM tasks GROUP BY status").fetchall())

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="local-state/queue.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("enqueue")
    p.add_argument("id")
    p.add_argument("--payload", default="{}")
    sub.add_parser("status")
    args = parser.parse_args()
    if args.command == "enqueue":
        result = enqueue(args.db, args.id, json.loads(args.payload))
    else:
        result = summary(args.db)
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    main()
