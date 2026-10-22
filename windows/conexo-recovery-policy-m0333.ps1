function Get-ConexoRecoveryDecision {
    param(
        [string]$Operation,
        [string]$Status,
        [int]$Attempts
    )
    $allowed = @{
        check_localrunner = "ConexoOS-LocalRunner"
        check_autoops = "ConexoOS-AutoOps-Check"
        check_watchdog = "ConexoOS-Watchdog"
    }
    $decision = "PRESERVAR"
    $target = $null
    if ($Attempts -lt 0) {
        $decision = "BLOQUEAR_TENTATIVAS_INVALIDAS"
    } elseif (!$allowed.ContainsKey($Operation)) {
        $decision = "BLOQUEAR_OPERACAO"
    } elseif ($Status -eq "EM_EXECUCAO") {
        if ($Attempts -ge 2) {
            $decision = "BLOQUEAR_LIMITE"
        } else {
            $decision = "AUTORIZAR_RECUPERACAO"
            $target = $allowed[$Operation]
        }
    } elseif ($Status -notin @("PENDENTE","CONCLUIDA","FALHOU")) {
        $decision = "BLOQUEAR_ESTADO"
    }
    [pscustomobject]@{
        operation = $Operation
        status = $Status
        attempts = $Attempts
        decision = $decision
        target = $target
    }
}