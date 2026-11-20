# Safe recovery and GitHub Actions synthetic executor — 2026-11-19

## Scope

This change integrates the existing `scripts.safe_recovery.recover_safe` routine into `scripts.worker.run` and adds a manual GitHub Actions executor for synthetic, side-effect-free tasks. It does not introduce a second recovery implementation or a production dispatch path.

## Runtime recovery behavior

At the beginning of each worker cycle:

1. Inspect stale tasks using the existing lease heartbeat and task timestamp.
2. Validate each payload against the worker's exact `perform` contract.
3. Recover only the existing synthetic, idempotent allowlist: `echo` and `count`.
4. Return eligible tasks below the attempt limit to `pending`; mark exhausted tasks `failed`.
5. Leave unsupported or potentially side-effecting tasks unchanged.
6. Claim pending tasks using the existing atomic ownership and fencing-token mechanism.

The default stale threshold is 3600 seconds and can be overridden with `--stale-seconds`. The existing 3-attempt limit remains in force.

## GitHub Actions executor

`.github/workflows/conexo-synthetic-executor.yml` is manually dispatched only. It accepts task ID, contract SHA and JSON payload. The script validates identifiers and executes only the existing `echo` and `count` worker task types, with a 16 KiB UTF-8 payload limit.

It emits a short-lived artifact containing a receipt with workflow run ID, attempt, execution SHA, timestamps and payload/result SHA-256 digests. The receipt is marked `REVIEW`; it explicitly sets `authorization_verified`, `contract_verified` and `execution_identity_independently_verified` to false. The workflow does not fetch or authorize the supplied contract SHA, sign the receipt, dispatch production tasks or persist canonical state. The artifact retention is 7 days and must not be treated as a durable record.

## Safety boundaries

- This is an isolated SQLite prototype, not cloud persistence.
- The GitHub-hosted runner disk is ephemeral and must not be treated as a durable queue.
- Recovery does not make external side effects exactly-once. Do not add publication, WordPress writes, shell execution, or other external effects to the allowlist.
- The existing Windows maintenance cycle already calls the same allowlisted recovery before invoking the worker; the second check is idempotent and sees no stale task after successful recovery.
- The Actions workflow is manual only, has `contents: read` permissions, uses no secrets and does not run during PR creation.
- No workflow dispatch, deploy, webhook activation, production write, or cloud resource creation was performed as part of this change.

## Validation

Thirteen focused tests were run locally against the worker, queue, ownership, safe-recovery and Actions-executor source files:

- 7 worker tests: normal processing, bounded retries, atomic result/state persistence, stale safe task recovery, unsupported task preservation, attempt exhaustion and invalid limit;
- 6 Actions-executor tests: echo, count, unknown task rejection, malformed contract SHA, non-object payload and payload-size limit.

Result: **13 passed, 0 failed**. The workflow YAML was parsed locally and its manual trigger, read-only permission and five-minute timeout were checked. Full repository CI and a real GitHub Actions dispatch remain pending and were not executed.
