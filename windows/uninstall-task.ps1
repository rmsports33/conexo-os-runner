# Disable and remove only the Conexo OS task; keep SQLite data and backups.
$ErrorActionPreference = 'Stop'
$taskName = 'ConexoOS-LocalRunner'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Host 'Conexo OS scheduled task is not installed.'
    exit 0
}
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
Write-Host 'Conexo OS scheduled task removed. Local data preserved.'
