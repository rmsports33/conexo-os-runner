# Conexo OS Public Runner

Isolated public CI for non-sensitive validation only. No private repository access, no secrets, no deployments, no external command execution.

## Automated checks

GitHub Actions runs tests on pushes and pull requests to `main`, on manual dispatch, and daily at 09:17 UTC. The runner uses read-only permissions. Scheduled executions may be delayed by GitHub.

## Offline continuity prototype

`scripts/continuity.py` implements an idempotent SQLite task queue with pending, running, done and failed states. The workflow tests it using temporary databases and synthetic tasks only.

Example on a trusted local machine:

```bash
python scripts/continuity.py --db local-state/queue.sqlite3 enqueue demo-1 --payload '{"demo":true}'
python scripts/continuity.py --db local-state/queue.sqlite3 claim
python scripts/continuity.py --db local-state/queue.sqlite3 finish demo-1
python scripts/continuity.py --db local-state/queue.sqlite3 status
```

The SQLite file must reside on persistent local storage; GitHub-hosted runner disks are ephemeral. Recovery of interrupted running tasks is **explicit**, not automatic, because retrying a task that has side effects could duplicate work. Do not use this prototype to publish content or execute external commands.

## Run tests locally

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/validate.py samples
```

Do not add credentials, internal data, private source files or proprietary configuration.
