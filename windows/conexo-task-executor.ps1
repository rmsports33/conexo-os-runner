$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$state = Join-Path $root "local-state"
$queue = Join-Path $state "task-queue.json"
$report = Join-Path $state "task-executor-status.json"
$allowed = @{
    check_localrunner = "ConexoOS-LocalRunner"
    check_autoops = "ConexoOS-AutoOps-Check"
    check_watchdog = "ConexoOS-Watchdog"
}
$data = Get-Content -LiteralPath $queue -Raw | ConvertFrom-Json
if ($data.schema_version -ne 1) { throw "Fila incompatível." }
$results = @()
foreach ($job in @($data.tasks)) {
    if (!$allowed.ContainsKey([string]$job.operation)) {
        $results += @{ id = $job.id; status = "REJEITADA" }
        continue
    }
    $name = $allowed[[string]$job.operation]
    try {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction Stop
        $info = $task | Get-ScheduledTaskInfo
        $results += @{
            id = $job.id
            operation = $job.operation
            status = "SIMULADA"
            task_state = [string]$task.State
            last_result = $info.LastTaskResult
            last_run = $info.LastRunTime.ToString("o")
        }
    } catch {
        $results += @{ id = $job.id; status = "ERRO"; reason = $_.Exception.Message }
    }
}
$output = @{
    schema_version = 1
    mode = "DRY_RUN"
    updated_at = (Get-Date).ToString("o")
    results = $results
}
$json = $output | ConvertTo-Json -Depth 8
$temp = Join-Path $state ("executor-" + [guid]::NewGuid().ToString("N") + ".tmp")
try {
    [IO.File]::WriteAllText($temp, $json, (New-Object System.Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temp -Destination $report -Force
} finally {
    if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
}
Write-Host "EXECUTOR: OK"
Write-Host "MODO: SIMULACAO"
Write-Host "TAREFAS_PROCESSADAS: $($results.Count)"
