# Conexo OS - M03.7: controlled synchronization of portable status.
# Default: read-only preview. -Publish: explicit confirmation, commit and push.
param([switch]$Publish)

$ErrorActionPreference = 'Stop'
$runner = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$core = if ($env:CONEXO_CORE_DIR) {
    [IO.Path]::GetFullPath($env:CONEXO_CORE_DIR)
} else {
    Join-Path (Split-Path $runner -Parent) 'conexo-os'
}
$source = Join-Path $runner 'local-state\CONEXO_STATUS.md'
$destination = Join-Path $core 'CONEXO_STATUS.md'

function Invoke-Git([string[]]$Arguments) {
    $result = & git -C $core @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Git failed: $($Arguments -join ' ')" }
    return $result
}

try {
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw 'Source report not found.' }
    if (-not (Test-Path -LiteralPath (Join-Path $core '.git'))) { throw 'Private Git repository not found.' }

    $branch = [string](Invoke-Git -Arguments @('branch', '--show-current'))
    if ($branch.Trim() -cne 'local-runner') { throw 'Unexpected branch. Cancelled.' }

    $remote = [string](Invoke-Git -Arguments @('remote', 'get-url', 'origin'))
    if ($remote.Trim() -notmatch '^(https://github\.com/|git@github\.com:)rmsports33/conexo-os(\.git)?$') {
        throw 'Unexpected remote. Cancelled.'
    }

    # Never touch a file already modified or staged locally.
    $staged = @(Invoke-Git -Arguments @('diff', '--cached', '--name-only'))
    if ($staged.Count -gt 0) { throw 'Existing staged changes. Review before synchronizing.' }
    $destinationStatus = @(Invoke-Git -Arguments @('status', '--porcelain', '--', 'CONEXO_STATUS.md'))
    if ($destinationStatus.Count -gt 0) { throw 'Destination has local changes. Review before synchronizing.' }

    $content = [System.IO.File]::ReadAllText($source, [System.Text.Encoding]::UTF8)
    if ($content -notmatch '\A\uFEFF?# Conexo OS - Estado operacional\r?\n') {
        throw 'Unexpected report format.'
    }
    if ($content -match '(?i)([a-z]:\\users\\|/home/|password|secret|token|api[_-]?key|BEGIN [A-Z ]*PRIVATE KEY)') {
        throw 'Potential sensitive content. Manual review required.'
    }

    $srcHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    $same = (Test-Path -LiteralPath $destination -PathType Leaf) -and
        ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -eq $srcHash)
    if ($same) {
        Write-Host 'Report unchanged. No commit or push needed.'
        exit 0
    }

    Write-Host 'New report available. Destination: private local-runner branch.'
    if (-not $Publish) {
        Write-Host 'Preview only: no files changed, no commit or push.'
        exit 0
    }

    $answer = Read-Host 'Copy, commit and push this report to the PRIVATE repository? Type SIM'
    if ($answer -cne 'SIM') { Write-Host 'Cancelled. No changes made.'; exit 0 }

    # Recheck for concurrent changes immediately before writing.
    $staged = @(Invoke-Git -Arguments @('diff', '--cached', '--name-only'))
    $destinationStatus = @(Invoke-Git -Arguments @('status', '--porcelain', '--', 'CONEXO_STATUS.md'))
    if ($staged.Count -gt 0 -or $destinationStatus.Count -gt 0) {
        throw 'Git state changed during confirmation. Cancelled.'
    }

    Copy-Item -LiteralPath $source -Destination $destination
    Invoke-Git -Arguments @('add', '--', 'CONEXO_STATUS.md') | Out-Null
    $names = @(Invoke-Git -Arguments @('diff', '--cached', '--name-only'))
    if ($names.Count -ne 1 -or $names[0] -cne 'CONEXO_STATUS.md') {
        throw 'Unexpected staged content. No commit or push.'
    }
    Invoke-Git -Arguments @('diff', '--cached', '--check') | Out-Null
    Invoke-Git -Arguments @('commit', '-m', 'docs: update portable operational status', '--only', '--', 'CONEXO_STATUS.md') | Out-Host
    Invoke-Git -Arguments @('push', 'origin', 'local-runner') | Out-Host
    Write-Host 'Private synchronization completed.'
}
catch {
    Write-Error $_
    exit 1
}
