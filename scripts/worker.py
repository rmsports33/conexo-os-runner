"""Safe offline worker with atomic task settlement and bounded retries."""
import argparse
import json
import uuid
from pathlib import Path
from scripts.continuity import summary
from scripts.ownership import acquire, settle_owned
from scripts.memory_check import check_memory

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
    if kind == "memory_check":
        return check_memory(payload)
    raise ValueError("Unsupported task type")

def process_one(db):
    owner = "worker-" + uuid.uuid4().hex
    item = acquire(db, owner)
    if item is None:
        return None
    task_id, token = item["id"], item["token"]
    try:
        result = perform(item["payload"])
    except (ValueError, TypeError) as exc:
        message = str(exc)
        settled = settle_owned(db, task_id, token, error=message, max_attempts=MAX_ATTEMPTS)
        if settled is None:
            raise RuntimeError("Task ownership lost before failure settlement")
        state, attempts = settled
        return {"id": task_id, "status": state, "attempts": attempts, "error": message}
    settled = settle_owned(db, task_id, token, result=result, max_attempts=MAX_ATTEMPTS)
    if settled is None:
        raise RuntimeError("Task ownership lost before completion")
    state, attempts = settled
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
