. (Join-Path $PSScriptRoot 'conexo-recovery-policy-m0333.ps1')
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$state = Join-Path $root "local-state"
$queue = Join-Path $state "operations-queue.json"
$report = Join-Path $state "operations-status.json"
$mutex = New-Object System.Threading.Mutex($false, "Local\ConexoOS_M0323_Worker")
$locked = $false

function Add-ConexoBlockedAudit {
    param($Job, [string]$Decision, [int]$Attempts)
    if ($null -eq $Job.PSObject.Properties["recovery_audit"]) {
        $Job | Add-Member -NotePropertyName recovery_audit -NotePropertyValue @()
    }
    $history = @($Job.recovery_audit | Where-Object { $null -ne $_ })
    $duplicate = @($history | Where-Object {
        $_.decision -eq $Decision -and
        [int]$_.attempts_before -eq $Attempts
    }).Count -gt 0
    if (!$duplicate) {
        $event = [pscustomobject]@{
            time = (Get-Date).ToString("o")
            decision = $Decision
            attempts_before = $Attempts
        }
        $Job.recovery_audit = @($history) + @($event)
    }
}

try {
    $locked = $mutex.WaitOne(0)
    if (!$locked) { Write-Host "WORKER_OCUPADO"; return }
    $data = Get-Content -LiteralPath $queue -Raw | ConvertFrom-Json
    if ($data.schema_version -ne 1) { throw "Fila incompativel." }
    $allowed = @{
        check_localrunner = "ConexoOS-LocalRunner"
        check_autoops = "ConexoOS-AutoOps-Check"
        check_watchdog = "ConexoOS-Watchdog"
    }
    foreach ($job in @($data.tasks)) {
        if ($job.status -eq "CONCLUIDA") { continue }
        if ($job.status -eq "EM_EXECUCAO") {
            $currentAttempts = 0
            if ($null -ne $job.PSObject.Properties["attempts"]) {
                $currentAttempts = [int]$job.attempts
            }
            $policyResult = Get-ConexoRecoveryDecision -Operation ([string]$job.operation) -Status ([string]$job.status) -Attempts $currentAttempts
            if ($policyResult.decision -ne "AUTORIZAR_RECUPERACAO") {
                Add-ConexoBlockedAudit -Job $job -Decision ([string]$policyResult.decision) -Attempts $currentAttempts
            }
            $attempts = 0
            if ($null -ne $job.PSObject.Properties["attempts"]) {
                $attempts = [int]$job.attempts
            }
            $decision = Get-ConexoRecoveryDecision -Operation ([string]$job.operation) -Status ([string]$job.status) -Attempts $attempts
            if ($decision.decision -eq "AUTORIZAR_RECUPERACAO") {
                if ($null -eq $job.PSObject.Properties["recovery_audit"]) {
                    $job | Add-Member -NotePropertyName recovery_audit -NotePropertyValue @()
                }
                $event = [pscustomobject]@{
                    time = (Get-Date).ToString("o")
                    decision = $decision.decision
                    attempts_before = $attempts
                }
                $job.recovery_audit = @($job.recovery_audit) + @($event)
                $job.status = "PENDENTE"
            }
        }
        if ($job.status -eq "PENDENTE") {
            $attempts = 0
            if ($null -ne $job.PSObject.Properties["attempts"]) {
                $attempts = [int]$job.attempts
            }
            if ($attempts -ge 2 -or $attempts -lt 0) {
                $reason = "BLOQUEAR_LIMITE"
                if ($attempts -lt 0) { $reason = "BLOQUEAR_TENTATIVAS_INVALIDAS" }
                Add-ConexoBlockedAudit -Job $job -Decision $reason -Attempts $attempts
                continue
            }
        }
        if ($job.status -ne "PENDENTE") { continue }
        if (!$allowed.ContainsKey([string]$job.operation)) {
            Add-ConexoBlockedAudit -Job $job -Decision "BLOQUEAR_OPERACAO" -Attempts ([int]$job.attempts)
            $job.status = "FALHOU"
            $job.message = "Operacao nao permitida"
            continue
        }
        $job.status = "EM_EXECUCAO"
        if ($null -eq $job.PSObject.Properties["attempts"]) {
            $job | Add-Member -NotePropertyName attempts -NotePropertyValue 0
        }
        $job.attempts = [int]$job.attempts + 1
$checkpointJson = $data | ConvertTo-Json -Depth 8
$checkpointTemp = Join-Path $state ("m0331-" + [guid]::NewGuid().ToString("N") + ".tmp")
try {
    [IO.File]::WriteAllText($checkpointTemp, $checkpointJson, (New-Object System.Text.UTF8Encoding($false)))
    [IO.File]::Replace($checkpointTemp, $queue, ($queue + ".previous"))
} finally {
    if (Test-Path -LiteralPath $checkpointTemp) { Remove-Item -LiteralPath $checkpointTemp -Force }
}
        try {
            $name = $allowed[[string]$job.operation]
            $task = Get-ScheduledTask -TaskName $name -ErrorAction Stop
            $info = $task | Get-ScheduledTaskInfo
            $job.message = "Estado: $($task.State); codigo: $($info.LastTaskResult)"
            $job.status = "CONCLUIDA"
        } catch {
            $job.status = "FALHOU"
            $job.message = $_.Exception.Message
        }
        $job.completed_at = (Get-Date).ToString("o")
    }
    $data.updated_at = (Get-Date).ToString("o")
    $json = $data | ConvertTo-Json -Depth 8
    $temp = Join-Path $state ("queue-" + [guid]::NewGuid().ToString("N") + ".tmp")
    try {
        [IO.File]::WriteAllText($temp, $json, (New-Object System.Text.UTF8Encoding($false)))
        [IO.File]::Replace($temp, $queue, ($queue + ".previous"))
    } finally {
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
    }
    $summary = @{
        updated_at = $data.updated_at
        total = @($data.tasks).Count
        completed = @($data.tasks | Where-Object { $_.status -eq "CONCLUIDA" }).Count
        failed = @($data.tasks | Where-Object { $_.status -eq "FALHOU" }).Count
    }
    $summary | ConvertTo-Json | Set-Content -LiteralPath $report -Encoding UTF8
    Write-Host "WORKER: OK"
    Write-Host "CONCLUIDAS: $($summary.completed)"
    Write-Host "FALHAS: $($summary.failed)"
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
