"""Atomic ownership and fencing tokens for isolated SQLite workers."""
import json
import uuid
from contextlib import closing
from scripts.continuity import connect, now

def prepare(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS task_leases (
      task_id TEXT PRIMARY KEY, token TEXT NOT NULL,
      owner TEXT NOT NULL, heartbeat_at TEXT NOT NULL
    )""")

def acquire(db, owner):
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("Worker owner is required")
    with closing(connect(db)) as conn:
        with conn:
            prepare(conn)
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT id,payload FROM tasks WHERE status='pending' ORDER BY updated_at,id LIMIT 1").fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            changed = conn.execute("UPDATE tasks SET status='running',attempts=attempts+1,updated_at=? WHERE id=? AND status='pending'", (now(),row[0]))
            if changed.rowcount != 1:
                raise RuntimeError("Task claim lost")
            conn.execute("""INSERT INTO task_leases(task_id,token,owner,heartbeat_at)
                VALUES(?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET
                token=excluded.token,owner=excluded.owner,heartbeat_at=excluded.heartbeat_at""",
                (row[0],token,owner,now()))
            return {"id":row[0],"payload":json.loads(row[1]),"token":token,"owner":owner}

def heartbeat(db, task_id, token):
    with closing(connect(db)) as conn:
        with conn:
            prepare(conn)
            changed=conn.execute("""UPDATE task_leases SET heartbeat_at=?
                WHERE task_id=? AND token=? AND EXISTS
                (SELECT 1 FROM tasks WHERE id=? AND status='running')""",
                (now(),task_id,token,task_id))
            return changed.rowcount == 1

def settle_owned(db, task_id, token, *, result=None, error=None, max_attempts=3):
    with closing(connect(db)) as conn:
        with conn:
            prepare(conn)
            row=conn.execute("""SELECT t.attempts FROM tasks t JOIN task_leases l ON l.task_id=t.id
                WHERE t.id=? AND t.status='running' AND l.token=?""",(task_id,token)).fetchone()
            if row is None:
                return None
            attempts=row[0]
            status="done" if error is None else ("pending" if attempts<max_attempts else "failed")
            conn.execute("""CREATE TABLE IF NOT EXISTS task_results(
                task_id TEXT PRIMARY KEY, result TEXT, error TEXT, updated_at TEXT NOT NULL)""")
            conn.execute("""INSERT INTO task_results(task_id,result,error,updated_at) VALUES(?,?,?,?)
                ON CONFLICT(task_id) DO UPDATE SET result=excluded.result,error=excluded.error,
                updated_at=excluded.updated_at""",
                (task_id,json.dumps(result,sort_keys=True) if error is None else None,error,now()))
            conn.execute("UPDATE tasks SET status=?,updated_at=? WHERE id=? AND status='running'",(status,now(),task_id))
            conn.execute("DELETE FROM task_leases WHERE task_id=? AND token=?",(task_id,token))
            return status,attempts

def complete(db, task_id, token, result):
    return settle_owned(db,task_id,token,result=result) is not None
