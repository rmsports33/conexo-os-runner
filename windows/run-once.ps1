# Conexo OS runner: one safe, local, offline maintenance cycle.
# Run from repository root. Requires Python 3.12+ on PATH.
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$state = Join-Path (Get-Location) 'local-state'
$backups = Join-Path $state 'backups'
New-Item -ItemType Directory -Force -Path $backups | Out-Null
$db = Join-Path $state 'queue.sqlite3'
if (-not (Test-Path $db)) {
    Write-Host 'No existing queue database; skipping recovery and backup.'
    exit 0
}
python -m scripts.maintenance --db $db check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# Dry-run only. Never automatically reclaim live or unknown workers.
python -m scripts.recovery --db $db --stale-seconds 3600
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m scripts.worker --db $db --limit 10
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffffffZ')
$backup = Join-Path $backups ("queue-$stamp.sqlite3")
python -m scripts.maintenance --db $db backup $backup
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# Keep newest 30 verified snapshots. Never delete the active queue.
$all = @(Get-ChildItem -LiteralPath $backups -File -Filter 'queue-*.sqlite3' | Sort-Object Name -Descending)
if ($all.Count -gt 30) {
    $all | Select-Object -Skip 30 | Remove-Item -Force
}
# Offline module supervision.
$workspace = (Resolve-Path (Join-Path (Get-Location) "..")).Path
$moduleReport = Join-Path $state "modules-latest.json"
python -m scripts.module_inventory --workspace $workspace --output $moduleReport
if ($LASTEXITCODE -eq 0) {
    python -m scripts.module_history --report $moduleReport --history (Join-Path $state "modules-history.jsonl") --changes (Join-Path $state "modules-changes.json")
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Module history failed; queue maintenance completed."
    }
}
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Module inventory failed; queue maintenance completed."
}
# M03: Generate portable status locally, without network access.
python -m scripts.conexo_status
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Portable status generation failed; maintenance completed."
}
exit 0
