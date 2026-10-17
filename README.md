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

The SQLite file must reside on persistent local storage; GitHub-hosted runner disks are ephemeral. Recovery of interrupted running tasks is **explicit**, not automatic, because retrying a task that has side effects could duplicate work. Do not use this prototype to publish content or execute external commands.

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

The worker has a bounded 3-attempt retry policy. Failed tasks remain marked `failed` after the limit. Recovery of stale tasks is previewed with `python -m scripts.recovery --db local-state/queue.sqlite3`. Applying recovery requires an explicit `--apply` and must not overlap active workers. SQLite and result records must be stored on a persistent machine or volume; hosted GitHub Actions runners do not provide durable queue storage. This is a test prototype, not a production task scheduler.

## SQLite maintenance and backups

Run an integrity check on a trusted persistent host:

```bash
python -m scripts.maintenance --db local-state/queue.sqlite3 check
```

Create a consistent snapshot (destination must not already exist):

```bash
python -m scripts.maintenance --db local-state/queue.sqlite3 backup local-state/backups/queue-001.sqlite3
```

The backup uses SQLite's online backup API and verifies the resulting database. Store backups on durable media with suitable access controls. This prototype does **not** schedule backups, rotate old snapshots, restore databases, or provide cross-device synchronization. Do not commit SQLite files to this public repository.

## Optional Windows scheduler (not installed automatically)

Requires Windows PowerShell, Python 3.12+ on PATH, a local checkout and persistent storage. Review the scripts before enabling. From the repository root:

```powershell
powershell -NoProfile -File windows/run-once.ps1
powershell -NoProfile -File windows/install-task.ps1
powershell -NoProfile -File windows/uninstall-task.ps1
```

The scheduled task runs every 60 minutes by default, only when the Windows host is available. It does not grant elevated permissions or install a background cloud worker. The maintenance cycle previews recovery but does not apply it. Backups accumulate until manually managed; ensure free disk space. Only synthetic `echo` and `count` tasks are supported. Run the test suite before opting in; this is not production-ready and does not synchronize across devices.
