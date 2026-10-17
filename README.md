# Conexo OS Public Runner

Isolated public CI for non-sensitive validation only. No private repository access, no secrets, no deployments, no external command execution.

## Run locally

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/validate.py samples
```

## GitHub Actions

Use **Actions > Public validation > Run workflow**, or push changes to `main`. The workflow has read-only repository permissions. Do not add credentials, internal data, private source files or proprietary configuration.
