# Conexo OS M03.8 - unattended, read-only AutoOps diagnosis.
# No staging, commits, pushes, merges, or modifications to tracked files.
$ErrorActionPreference = 'Stop'
$runner = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$core = if ($env:CONEXO_CORE_DIR) {
    [IO.Path]::GetFullPath($env:CONEXO_CORE_DIR)
} else {
    Join-Path (Split-Path $runner -Parent) 'conexo-os'
}
$state = Join-Path $runner 'local-state'
$syncScript = Join-Path $runner 'windows\conexo-sync.ps1'
$portableScript = Join-Path $runner 'windows\conexo-m0311-prepare.ps1'
$log = Join-Path $state 'autoops-check.log'
$mutex = New-Object System.Threading.Mutex($false, 'Local\ConexoOS_AutoOps_M038')
$locked = $false
try {
    $locked = $mutex.WaitOne(0)
    if (-not $locked) { Write-Output 'AutoOps already running; skipped.'; exit 0 }
    if (-not (Test-Path -LiteralPath $state -PathType Container)) { New-Item -ItemType Directory -Path $state -Force | Out-Null }
    $when = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("Data: $when")
    if (-not (Test-Path -LiteralPath $syncScript -PathType Leaf)) { throw 'Sync script not found.' }
    if (-not (Test-Path -LiteralPath (Join-Path $core '.git'))) { throw 'Private repository not found.' }
    $branch = (& git -C $core branch --show-current 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $branch -cne 'local-runner') { throw 'Unexpected Git branch or Git failure.' }
    $remote = (& git -C $core remote get-url origin 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $remote -notmatch '^(https://github\.com/|git@github\.com:)rmsports33/conexo-os(\.git)?$') { throw 'Unexpected remote.' }
    $lines.Add('Branch: local-runner')
    $fetchOutput = (& git -C $core fetch --quiet origin local-runner 2>$null | Out-String).Trim()
    $fetchCode = $LASTEXITCODE
    $lines.Add("Fetch: $($fetchCode -eq 0)")
    if ($fetchCode -ne 0) { throw "Git fetch failed: $fetchOutput" }
    $aheadBehind = (& git -C $core rev-list --left-right --count 'HEAD...refs/remotes/origin/local-runner' 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Unable to compare local and remote branches.' }
    $lines.Add("AheadBehind: $aheadBehind")
    $parts = @($aheadBehind -split '\s+')
    if ($parts.Count -ne 2 -or $parts[1] -ne '0') { throw 'Remote branch is ahead or diverged; review required.' }
    $syncOutput = (& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $syncScript 2>&1 | Out-String).Trim()
    $syncCode = $LASTEXITCODE
    $lines.Add("SyncPreview: $($syncCode -eq 0)")
    $lines.Add("Result: $($syncOutput -replace '[\r\n]+', ' | ')")
    if ($syncCode -ne 0) { throw 'Sync preview failed.' }
if ($syncOutput -match 'New report available\.') {
    $syncState = 'PENDENTE_APROVACAO'
}
elseif ($syncOutput -match 'Report unchanged\.') {
    $syncState = 'SINCRONIZADO'
}
else {
    throw 'Unknown synchronization preview result.'
}

$lines.Add("SyncState: $syncState")
    # M03.10 structured state: overwrite only the ignored local-state JSON.
    $statusPath = Join-Path $state 'autoops-status.json'
    $statusTemp = Join-Path $state 'autoops-status.json.tmp'
    $statusObject = [ordered]@{
        schema_version = 1
        updated_at = (Get-Date).ToString('o')
        overall = 'OK'
        sync_state = $syncState
        branch = $branch
        ahead_behind = $aheadBehind
        fetch_ok = ($fetchCode -eq 0)
        preview_ok = ($syncCode -eq 0)
        publication_performed = $false
        last_error = $null
    }
    $statusJson = $statusObject | ConvertTo-Json -Depth 4
    [System.IO.File]::WriteAllText($statusTemp, $statusJson, (New-Object System.Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $statusTemp -Destination $statusPath -Force
    # M03.11 portable summary integration: refresh after successful JSON write.
    & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $portableScript | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Portable summary generation failed.' }
    # M03.18: isolate local portable synchronization failures.
    $syncOutput = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $runner 'windows\conexo-portable-local-sync.ps1') 2>&1
    $portableSyncExit = $LASTEXITCODE
    if ($portableSyncExit -ne 0) {
        $warning = "M03.18: Local portable sync failed (exit $portableSyncExit); main checks OK."
        Write-Warning $warning
        $lines.Add($warning)
        foreach ($item in $syncOutput) { $lines.Add([string]$item) }
    }
$lines.Add('Overall: OK')
    $lines.Add('---')
    $lines | Add-Content -LiteralPath $log -Encoding UTF8
    Write-Output "AutoOps OK. Log: $log"
}
catch {
    $message = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | AutoOps ERROR: $($_.Exception.Message)"
    if (Test-Path -LiteralPath $state -PathType Container) {
        $message | Add-Content -LiteralPath $log -Encoding UTF8
    }
    # M03.10 structured state: preserve failure visibility.
    try {
        $statusPath = Join-Path $state 'autoops-status.json'
        $statusTemp = Join-Path $state 'autoops-status.json.tmp'
        $statusObject = [ordered]@{
            schema_version = 1
            updated_at = (Get-Date).ToString('o')
            overall = 'ERRO'
            sync_state = 'ERRO'
            branch = $null
            ahead_behind = $null
            fetch_ok = $false
            preview_ok = $false
            publication_performed = $false
            last_error = [string]$_.Exception.Message
        }
        $statusJson = $statusObject | ConvertTo-Json -Depth 4
        [System.IO.File]::WriteAllText($statusTemp, $statusJson, (New-Object System.Text.UTF8Encoding($false)))
        Move-Item -LiteralPath $statusTemp -Destination $statusPath -Force
        # M03.11 portable summary integration: update summary on failure too.
        & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $portableScript | Out-Null
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Portable summary refresh failed during error handling.' }
    } catch {
        Write-Warning "Unable to write M03.10 status: $($_.Exception.Message)"
    }
    Write-Error $message
    exit 1
}
finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
