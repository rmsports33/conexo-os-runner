"""Offline history and change detection for Conexo OS modules."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


FIELDS = ("exists", "git", "branch", "commit", "dirty", "remote_configured")


def module_state(report):
    return {
        module["id"]: {
            "repository": module["repository"],
            "local": {
                field: module.get("local", {}).get(field)
                for field in FIELDS
            },
        }
        for module in report["modules"]
    }


def detect_changes(previous, current):
    before = module_state(previous)
    after = module_state(current)
    changes = []

    for module_id in sorted(before.keys() | after.keys()):
        old = before.get(module_id)
        new = after.get(module_id)

        if old == new:
            continue

        if old is None or new is None:
            changes.append({
                "module": module_id,
                "field": "module",
                "before": old,
                "after": new,
            })
            continue

        if old["repository"] != new["repository"]:
            changes.append({
                "module": module_id,
                "field": "repository",
                "before": old["repository"],
                "after": new["repository"],
            })

        for field in FIELDS:
            old_value = old["local"][field]
            new_value = new["local"][field]

            if old_value != new_value:
                changes.append({
                    "module": module_id,
                    "field": field,
                    "before": old_value,
                    "after": new_value,
                })

    return changes


def update_history(report_path, history_path, changes_path):
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    if report.get("mode") != "read-only" or report.get("network_used") is not False:
        raise ValueError("Only offline read-only reports are accepted")

    history_path = Path(history_path)
    changes_path = Path(changes_path)

    history_path.parent.mkdir(parents=True, exist_ok=True)
    changes_path.parent.mkdir(parents=True, exist_ok=True)

    previous = None

    if history_path.exists():
        with history_path.open(encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    previous = json.loads(line)["report"]

    current_state = module_state(report)

    if previous is not None and module_state(previous) == current_state:
        changes = []
        recorded = False
    else:
        changes = detect_changes(previous, report) if previous else []
        entry = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "report": report,
        }
        with history_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
        recorded = True

    result = {
        "recorded": recorded,
        "baseline": previous is None,
        "changes": changes,
        "change_count": len(changes),
    }

    changes_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="local-state/modules-latest.json")
    parser.add_argument("--history", default="local-state/modules-history.jsonl")
    parser.add_argument("--changes", default="local-state/modules-changes.json")
    args = parser.parse_args()

    result = update_history(args.report, args.history, args.changes)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
