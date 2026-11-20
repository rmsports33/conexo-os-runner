"""Manual GitHub Actions executor for synthetic, side-effect-free tasks only.

The receipt is evidence for human/central review, not an authorization or
cryptographic attestation. The workflow intentionally has no secrets.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.continuity import enqueue
from scripts.worker import perform, run

TASK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$")
SHA_RE = re.compile(r"^[a-f0-9]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def execute_synthetic(*, task_id, contract_sha, payload_json, repository,
                      execution_sha, run_id, run_attempt):
    errors = []
    if not isinstance(task_id, str) or not TASK_RE.fullmatch(task_id):
        errors.append("task_id_invalid")
    if not isinstance(contract_sha, str) or not SHA_RE.fullmatch(contract_sha):
        errors.append("contract_sha_invalid")
    if not isinstance(repository, str) or not REPO_RE.fullmatch(repository):
        errors.append("repository_invalid")
    if not isinstance(execution_sha, str) or not SHA_RE.fullmatch(execution_sha):
        errors.append("execution_sha_invalid")
    if not str(run_id).isdigit() or not str(run_attempt).isdigit():
        errors.append("workflow_run_identity_invalid")

    payload = None
    if not errors:
        try:
            payload = json.loads(payload_json)
            if not isinstance(payload, dict):
                raise ValueError("payload_not_object")
            # Exact worker contract: only echo/count are accepted.
            perform(payload)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append("payload_rejected:" + str(exc)[:120])

    started_at = utc_now()
    receipt = {
        "schema_version": 1,
        "receipt_type": "synthetic-execution-evidence",
        "task_id": task_id if isinstance(task_id, str) else "",
        "repository": repository if isinstance(repository, str) else "",
        "contract_sha": contract_sha if isinstance(contract_sha, str) else "",
        "execution_sha": execution_sha if isinstance(execution_sha, str) else "",
        "executor": "github-actions",
        "workflow_run_id": str(run_id),
        "workflow_run_attempt": str(run_attempt),
        "status": "BLOCKED" if errors else "REVIEW",
        "authorization_verified": False,
        "contract_verified": False,
        "execution_identity_independently_verified": False,
        "started_at": started_at,
        "finished_at": None,
        "payload_sha256": digest(payload) if payload is not None else None,
        "result": None,
        "result_sha256": None,
        "errors": errors,
        "limitations": [
            "synthetic echo/count tasks only",
            "contract SHA is recorded but contract existence and authorization are not verified",
            "receipt is not cryptographically signed or independently attested",
            "workflow artifacts are temporary evidence, not canonical persistence",
        ],
    }

    if not errors:
        with TemporaryDirectory(prefix="conexo-actions-") as tmp:
            db = Path(tmp) / "queue.sqlite3"
            enqueue(db, task_id, payload)
            outcome = run(db, limit=1)
            processed = outcome["processed"]
            if len(processed) != 1 or processed[0].get("status") != "done":
                receipt["status"] = "BLOCKED"
                receipt["errors"].append("synthetic_execution_not_completed")
            else:
                result = processed[0]["result"]
                receipt["result"] = result
                receipt["result_sha256"] = digest(result)

    receipt["finished_at"] = utc_now()
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    receipt = execute_synthetic(
        task_id=os.getenv("CONEXO_TASK_ID", ""),
        contract_sha=os.getenv("CONEXO_CONTRACT_SHA", ""),
        payload_json=os.getenv("CONEXO_PAYLOAD_JSON", ""),
        repository=os.getenv("GITHUB_REPOSITORY", ""),
        execution_sha=os.getenv("GITHUB_SHA", ""),
        run_id=os.getenv("GITHUB_RUN_ID", ""),
        run_attempt=os.getenv("GITHUB_RUN_ATTEMPT", ""),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["status"] == "REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
