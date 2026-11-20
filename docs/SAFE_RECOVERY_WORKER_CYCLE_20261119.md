# Safe recovery integrated into the worker cycle — 2026-11-19

## Scope

This change integrates the existing `scripts.safe_recovery.recover_safe` routine into `scripts.worker.run`. It does not introduce a second recovery implementation.

## Runtime behavior

At the beginning of each worker cycle:

1. Inspect stale tasks using the existing lease heartbeat and task timestamp.
2. Validate each payload against the worker's exact `perform` contract.
3. Recover only the existing synthetic, idempotent allowlist: `echo` and `count`.
4. Return eligible tasks below the attempt limit to `pending`; mark exhausted tasks `failed`.
5. Leave unsupported or potentially side-effecting tasks unchanged.
6. Claim pending tasks using the existing atomic ownership and fencing-token mechanism.

The default stale threshold is 3600 seconds and can be overridden with `--stale-seconds`. The existing 3-attempt limit remains in force.

## Safety boundaries

- This is an isolated SQLite prototype, not cloud persistence.
- The GitHub-hosted runner disk is ephemeral and must not be treated as a durable queue.
- Recovery does not make external side effects exactly-once. Do not add publication, WordPress writes, shell execution, or other external effects to the allowlist.
- The existing Windows maintenance cycle already calls the same allowlisted recovery before invoking the worker; the second check is idempotent and sees no stale task after successful recovery.
- No workflow dispatch, deploy, webhook activation, production write, or cloud resource creation is part of this change.

## Validation

Seven focused worker tests were run locally against the same worker, queue, ownership, and safe-recovery source files:

- normal echo/count processing;
- bounded retries;
- atomic result/state persistence;
- stale safe task recovery and reclaim;
- unsupported stale task remains untouched;
- exhausted stale task moves to failed;
- invalid worker limit is rejected.

Result: **7 passed, 0 failed**. Full repository CI and the cloud handoff remain separate acceptance requirements.
