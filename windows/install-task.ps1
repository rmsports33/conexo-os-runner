# Opt-in per-user scheduled task. No elevation or paid services required.
param([ValidateRange(15,1440)][int]$IntervalMinutes = 60)
$ErrorActionPreference = 'Stop'
# Preflight: reject unsupported Python and failing unit tests before scheduling.
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $root
try {
    python -c "import sys; assert sys.version_info >= (3, 12)"
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12+ is required' }
    python -m unittest discover -s tests -p 'test_*.py'
    if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed; task not registered' }
} finally {
    Pop-Location
}
$script = (Resolve-Path (Join-Path $PSScriptRoot 'run-once.ps1')).Path
$taskName = 'ConexoOS-LocalRunner'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -File "' + $script + '"')
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -StartWhenAvailable
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($null -ne $existing) {
    throw "Task $taskName already exists. Refusing to overwrite it; uninstall explicitly first."
}
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description 'Conexo OS local offline runner (opt-in)' | Out-Null
Write-Host "Installed $taskName (every $IntervalMinutes minutes)."
Write-Host 'To disable: powershell -File windows/uninstall-task.ps1'
