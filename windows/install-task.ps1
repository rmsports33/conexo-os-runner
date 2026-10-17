# Opt-in per-user scheduled task. No elevation or paid services required.
param([ValidateRange(15,1440)][int]$IntervalMinutes = 60)
$ErrorActionPreference = 'Stop'
$script = (Resolve-Path (Join-Path $PSScriptRoot 'run-once.ps1')).Path
$taskName = 'ConexoOS-LocalRunner'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -File "' + $script + '"')
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -StartWhenAvailable
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description 'Conexo OS local offline runner (opt-in)' -Force | Out-Null
Write-Host "Installed $taskName (every $IntervalMinutes minutes)."
Write-Host 'To disable: powershell -File windows/uninstall-task.ps1'
