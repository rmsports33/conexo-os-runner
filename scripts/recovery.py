"""Recover only stale tasks with bounded attempts. For synthetic idempotent jobs only."""
import argparse
import json
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from scripts.continuity import connect, now
from scripts.ownership import prepare

def recover_stale(db, stale_seconds=3600, max_attempts=3, *, dry_run=True, clock=None):
    if stale_seconds < 60 or max_attempts < 1:
        raise ValueError("stale_seconds must be >=60 and max_attempts >=1")
    current = clock or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("clock must be timezone-aware")
    cutoff = (current - timedelta(seconds=stale_seconds)).isoformat()
    with closing(connect(db)) as conn:
        with conn:
            prepare(conn)
            conn.execute('BEGIN IMMEDIATE')
            rows = conn.execute(
                """SELECT t.id,t.attempts FROM tasks t LEFT JOIN task_leases l ON l.task_id=t.id
                WHERE t.status='running' AND COALESCE(l.heartbeat_at,t.updated_at)<=? ORDER BY t.id""",
                (cutoff,)).fetchall()
            retry = [task_id for task_id, attempts in rows if attempts < max_attempts]
            exhausted = [task_id for task_id, attempts in rows if attempts >= max_attempts]
            if not dry_run:
                for task_id in retry:
                    conn.execute(
                        "UPDATE tasks SET status='pending',updated_at=? WHERE id=? AND status='running' ",
                        (now(), task_id))
                    conn.execute("DELETE FROM task_leases WHERE task_id=?", (task_id,))
                for task_id in exhausted:
                    conn.execute(
                        "UPDATE tasks SET status='failed',updated_at=? WHERE id=? AND status='running' ",
                        (now(), task_id))
                    conn.execute("DELETE FROM task_leases WHERE task_id=?", (task_id,))
    return {"dry_run": dry_run, "retry": retry, "exhausted": exhausted}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="local-state/queue.sqlite3")
    parser.add_argument("--stale-seconds", type=int, default=3600)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--apply", action="store_true", help="Explicitly modify stale tasks")
    args = parser.parse_args()
    print(json.dumps(recover_stale(Path(args.db), args.stale_seconds,
        args.max_attempts, dry_run=not args.apply), sort_keys=True))

if __name__ == "__main__":
    main()
