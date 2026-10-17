"""Safe offline worker with atomic task settlement and bounded retries."""
import argparse
import json
from contextlib import closing
from pathlib import Path
from scripts.continuity import claim, connect, now, summary

MAX_ATTEMPTS = 3

def perform(payload):
    if not isinstance(payload, dict):
        raise ValueError("Payload must be an object")
    kind = payload.get("type")
    if kind == "echo":
        value = payload.get("value")
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError("Echo accepts scalar values only")
        return {"echo": value}
    if kind == "count":
        values = payload.get("items")
        if not isinstance(values, list) or len(values) > 1000:
            raise ValueError("Count requires a list with at most 1000 items")
        return {"count": len(values)}
    raise ValueError("Unsupported task type")

def settle(db, task_id, result=None, error=None):
    """Write result and status in the same transaction; never acknowledge separately."""
    with closing(connect(db)) as conn:
        with conn:
            row = conn.execute("SELECT status,attempts FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None or row[0] != "running":
                raise RuntimeError("Task not running")
            attempts = row[1]
            state = "done" if error is None else ("pending" if attempts < MAX_ATTEMPTS else "failed")
            conn.execute("""CREATE TABLE IF NOT EXISTS task_results (
                task_id TEXT PRIMARY KEY, result TEXT, error TEXT, updated_at TEXT NOT NULL
            )""")
            conn.execute("""INSERT INTO task_results(task_id,result,error,updated_at)
                VALUES(?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET
                result=excluded.result,error=excluded.error,updated_at=excluded.updated_at""",
                (task_id, json.dumps(result, sort_keys=True) if result is not None else None, error, now()))
            conn.execute("UPDATE tasks SET status=?,updated_at=? WHERE id=? AND status='running'",
                         (state, now(), task_id))
            return state, attempts

def process_one(db):
    item = claim(db)
    if item is None:
        return None
    task_id = item["id"]
    try:
        result = perform(item["payload"])
    except (ValueError, TypeError) as exc:
        message = str(exc)
        state, attempts = settle(db, task_id, error=message)
        return {"id": task_id, "status": state, "attempts": attempts, "error": message}
    state, attempts = settle(db, task_id, result=result)
    return {"id": task_id, "status": state, "attempts": attempts, "result": result}

def run(db, limit=10):
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be 1..100")
    processed = []
    for _ in range(limit):
        item = process_one(db)
        if item is None:
            break
        processed.append(item)
    return {"processed": processed, "queue": summary(db)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="local-state/queue.sqlite3")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(run(Path(args.db), args.limit), sort_keys=True))

if __name__ == "__main__":
    main()
