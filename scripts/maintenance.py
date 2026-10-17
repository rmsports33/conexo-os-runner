"""Offline SQLite integrity check and consistent backups; no network or secrets."""
import argparse
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

def check(db):
    path = Path(db)
    if not path.is_file():
        raise FileNotFoundError(path)
    with closing(sqlite3.connect(path)) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError("Database integrity check failed: " + result)
        rows = conn.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status").fetchall()
    return {"integrity": result, "queue": dict(rows)}

def backup(db, destination):
    source = Path(db)
    target = Path(destination)
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.resolve() == target.resolve():
        raise ValueError("Backup destination must differ from source")
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with closing(sqlite3.connect(source)) as original:
            with closing(sqlite3.connect(target)) as copy:
                original.backup(copy)
        result = check(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return {"backup": str(target), "created_utc": datetime.now(timezone.utc).isoformat(), **result}

def restore(source, destination):
    """Restore a verified backup only when the destination does not exist."""
    origin = Path(source)
    target = Path(destination)
    if not origin.is_file():
        raise FileNotFoundError(origin)
    if origin.resolve() == target.resolve():
        raise ValueError("Restore destination must differ from source")
    check(origin)
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental overwrites of live queue state.
    with closing(sqlite3.connect(origin)) as original:
        with target.open("xb") as reserved:
            pass
        try:
            with closing(sqlite3.connect(target)) as copy:
                original.backup(copy)
            return {"restored": str(target), **check(target)}
        except Exception:
            target.unlink(missing_ok=True)
            raise

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="local-state/queue.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    p = sub.add_parser("backup")
    p.add_argument("destination")
    p = sub.add_parser("restore")
    p.add_argument("source")
    p.add_argument("destination")
    args = parser.parse_args()
    if args.command == "check":
        result = check(args.db)
    elif args.command == "backup":
        result = backup(args.db, args.destination)
    else:
        result = restore(args.source, args.destination)
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    main()
