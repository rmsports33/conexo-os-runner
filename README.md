# Conexo OS Public Runner

Isolated public CI for non-sensitive validation only. No private repository access, no secrets, no deployments, no external command execution.

## Automated checks

GitHub Actions runs tests on pushes and pull requests to `main`, on manual dispatch, and daily at 09:17 UTC. The runner uses read-only permissions. Scheduled executions may be delayed by GitHub.

## Offline continuity prototype

`scripts/continuity.py` implements an idempotent SQLite task queue with pending, running, done and failed states. The workflow tests it using temporary databases and synthetic tasks only.

Example on a trusted local machine:

```bash
python scripts/continuity.py --db local-state/queue.sqlite3 enqueue demo-1 --payload '{"demo":true}'
python scripts/continuity.py --db local-state/queue.sqlite3 status
```

The SQLite file must reside on persistent local storage; GitHub-hosted runner disks are ephemeral. Do not use this prototype to publish content or execute external commands.

## Run tests locally

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/validate.py samples
```

Do not add credentials, internal data, private source files or proprietary configuration.

## Safe worker prototype

The public offline worker accepts only two synthetic task types: `{"type":"echo","value":"hello"}` and `{"type":"count","items":[1,2,3]}`. Unknown types are rejected. It does not run shell commands, access networks, publish content or load secrets.

```bash
python scripts/continuity.py --db local-state/queue.sqlite3 enqueue demo --payload '{"type":"echo","value":"hello"}'
python -m scripts.worker --db local-state/queue.sqlite3 --limit 10
python scripts/continuity.py --db local-state/queue.sqlite3 status
```

The worker has a bounded 3-attempt retry policy. At the start of each worker cycle, it applies stale-task recovery only to payloads that pass the exact worker contract and are one of the idempotent synthetic types `echo` or `count`. Unsupported or side-effecting tasks are skipped and remain untouched. Tasks at the attempt limit are moved to `failed`; eligible stale tasks return to `pending` and can be reclaimed with a new fencing token. The default stale threshold is 3600 seconds and can be changed with `--stale-seconds`.

Recovery can be previewed without writes using `python -m scripts.safe_recovery --db local-state/queue.sqlite3`. Applying it directly remains explicit with `--apply`. The worker's automatic recovery is deliberately limited to the safe synthetic allowlist; it is not a general-purpose retry mechanism for external effects.

## Manual GitHub Actions executor (synthetic only)

`.github/workflows/conexo-synthetic-executor.yml` is a manual `workflow_dispatch` prototype. It accepts a task ID, a 40-character contract SHA and a JSON payload, but executes only `echo` and `count`. The payload is limited to 16 KiB. It has read-only repository permissions and no secrets.

The resulting artifact is retained for 7 days and contains a receipt with the workflow run ID, execution SHA, payload/result hashes and timestamps. The receipt is marked `REVIEW`, not `DONE`; authorization, contract existence and executor identity are explicitly **not verified**. The artifact is temporary evidence, not canonical persistence or proof of an authenticated handoff. Do not use this workflow for editorial publication, WordPress writes or production tasks.

SQLite and result records must be stored on durable storage. Hosted GitHub Actions runner disks are ephemeral, so this prototype is not yet a cloud-persistent queue or production task scheduler.

## SQLite maintenance and backups

Run an integrity check on a trusted persistent host:

```bash
python -m scripts.maintenance --db local-state/queue.sqlite3 check
```

Create a consistent snapshot (destination must not already exist):

```bash
python -m scripts.maintenance --db local-state/queue.sqlite3 backup local-state/backups/queue-001.sqlite3
```

The backup uses SQLite's online backup API and verifies the resulting database. Store backups on durable media with suitable access controls. On Windows, the opt-in local cycle creates a verified backup and retains the 30 newest matching snapshots. Restore to a new path with `python -m scripts.maintenance restore SOURCE DESTINATION`; restoration never overwrites an existing destination. Cross-device synchronization is not provided. Do not commit SQLite files to this public repository.

## Optional Windows scheduler (not installed automatically)

Requires Windows PowerShell, Python 3.12+ on PATH, a local checkout and persistent storage. Review the scripts before enabling. The installer refuses to replace an existing scheduled task with the same name. From the repository root:

```powershell
powershell -NoProfile -File windows/run-once.ps1
powershell -NoProfile -File windows/install-task.ps1
powershell -NoProfile -File windows/uninstall-task.ps1
```

The scheduled task runs every 60 minutes by default, only when the Windows host is available. It does not grant elevated permissions or install a background cloud worker. The maintenance cycle performs the same allowlisted recovery before invoking the worker. Schedule only with explicit opt-in; uninstalling the task preserves the database and backups. This is not production-ready and does not synchronize across devices.
