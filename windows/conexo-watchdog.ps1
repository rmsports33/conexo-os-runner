$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$state=Join-Path $root 'local-state'
$items=@()

foreach($name in @('ConexoOS-LocalRunner','ConexoOS-AutoOps-Check')){
    try {
        $task=Get-ScheduledTask -TaskName $name -ErrorAction Stop
        $info=$task | Get-ScheduledTaskInfo
        $age=((Get-Date)-$info.LastRunTime).TotalMinutes
        $healthy=($task.State -ne 'Disabled' -and $info.LastTaskResult -eq 0 -and $age -ge 0 -and $age -le 150)
        $items+=@{
            name=$name
            status=$(if($healthy){'OK'}else{'ATENCAO'})
            task_state=[string]$task.State
            last_run=$info.LastRunTime.ToString('o')
            next_run=$info.NextRunTime.ToString('o')
            exit_code=$info.LastTaskResult
            missed_runs=$info.NumberOfMissedRuns
        }
    } catch {
        $items+=@{name=$name;status='ERRO';message=$_.Exception.Message}
    }
}

$overall=if(@($items | Where-Object {$_.status -ne 'OK'}).Count -eq 0){'OK'}else{'ATENCAO'}
$result=@{
    schema_version=1
    updated_at=(Get-Date).ToString('o')
    overall=$overall
    tasks=$items
}
$json=$result | ConvertTo-Json -Depth 6
$target=Join-Path $state 'watchdog-status.json'
$temp=Join-Path $state ('watchdog-'+[guid]::NewGuid().ToString('N')+'.tmp')
try {
    [IO.File]::WriteAllText($temp,$json,(New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temp -Destination $target -Force
} finally {
    if(Test-Path -LiteralPath $temp){Remove-Item -LiteralPath $temp -Force}
}
Write-Output "WATCHDOG: $overall"
