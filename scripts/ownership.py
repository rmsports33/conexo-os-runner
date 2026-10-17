"""Atomic task ownership with fencing tokens for offline SQLite workers."""
import sqlite3
import uuid
from contextlib import closing
from scripts.continuity import connect, now

def prepare(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS task_leases (
      task_id TEXT PRIMARY KEY,
      token TEXT NOT NULL,
      owner TEXT NOT NULL,
      heartbeat_at TEXT NOT NULL
    )""")

def acquire(db, owner):
    if not owner or not isinstance(owner, str):
        raise ValueError("Worker owner is required")
    with closing(connect(db)) as conn:
        with conn:
            prepare(conn)
            row = conn.execute(
                "SELECT id,payload FROM tasks WHERE status='pending' ORDER BY updated_at,id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            cur = conn.execute(
                "UPDATE tasks SET status='running',attempts=attempts+1,updated_at=? WHERE id=? AND status='pending'",
                (now(), row[0]))
            if cur.rowcount != 1:
                raise RuntimeError("Task claim lost")
            conn.execute(
                "INSERT INTO task_leases(task_id,token,owner,heartbeat_at) VALUES(?,?,?,?) "
                "ON CONFLICT(task_id) DO UPDATE SET token=excluded.token,owner=excluded.owner,heartbeat_at=excluded.heartbeat_at",
                (row[0], token, owner, now()))
            return {"id": row[0], "token": token, "owner": owner}

def heartbeat(db, task_id, token):
    with closing(connect(db)) as conn:
        with conn:
            prepare(conn)
            cur = conn.execute(
                """UPDATE task_leases SET heartbeat_at=? WHERE task_id=? AND token=?
                AND EXISTS(SELECT 1 FROM tasks WHERE id=? AND status='running')""",
                (now(), task_id, token, task_id))
            return cur.rowcount == 1

def complete(db, task_id, token, result):
    """Reject stale owners and atomically persist the result with task completion."""
    import json
    with closing(connect(db)) as conn:
        with conn:
            prepare(conn)
            lease = conn.execute("SELECT token FROM task_leases WHERE task_id=?", (task_id,)).fetchone()
            if lease is None or lease[0] != token:
                return False
            cur = conn.execute(
                "UPDATE tasks SET status='done',updated_at=? WHERE id=? AND status='running'",
                (now(), task_id))
            if cur.rowcount != 1:
                return False
            conn.execute("""CREATE TABLE IF NOT EXISTS task_results (
                task_id TEXT PRIMARY KEY, result TEXT, error TEXT, updated_at TEXT NOT NULL
            )""")
            conn.execute("""INSERT INTO task_results(task_id,result,error,updated_at) VALUES(?,?,NULL,?)
                ON CONFLICT(task_id) DO UPDATE SET result=excluded.result,error=NULL,updated_at=excluded.updated_at""",
                (task_id, json.dumps(result, sort_keys=True), now()))
            conn.execute("DELETE FROM task_leases WHERE task_id=? AND token=?", (task_id, token))
            return True
