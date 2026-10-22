$ErrorActionPreference = 'Stop'
$runner = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$core = if ($env:CONEXO_CORE_DIR) {
    [IO.Path]::GetFullPath($env:CONEXO_CORE_DIR)
} else {
    Join-Path (Split-Path $runner -Parent) 'conexo-os'
}
$source = Join-Path $runner 'local-state\CONEXO_PORTABLE_STATUS.md'
$target = Join-Path $core 'CONEXO_PORTABLE_STATUS.md'
$state = Join-Path $runner 'local-state\portable-sync.sha256'
$initialBackup = $target + '.m0317-recovery.bak'

if (!(Test-Path -LiteralPath $source -PathType Leaf)) { throw 'Origem ausente' }
if (!(Test-Path -LiteralPath $target -PathType Leaf)) { throw 'Destino ausente' }
if ((& git -C $core branch --show-current) -ne 'local-runner') { throw 'Branch incorreta' }
if ($LASTEXITCODE -ne 0) { throw 'Falha ao consultar Git' }

$current = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
$incoming = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash

if (Test-Path -LiteralPath $state -PathType Leaf) {
    $known = ([IO.File]::ReadAllText($state)).Trim()
    if ($known -notmatch '^[a-fA-F0-9]{64}$') { throw 'Estado de continuidade invalido' }
    if ($current -ne $known) { throw 'Alteracao desconhecida no Core; copia bloqueada' }
} else {
    $diff = & git -C $core diff --quiet HEAD -- CONEXO_PORTABLE_STATUS.md
    if ($LASTEXITCODE -eq 0) {
        $known = $current
    } elseif ($LASTEXITCODE -eq 1 -and (Test-Path -LiteralPath $initialBackup -PathType Leaf)) {
        $previous = (Get-FileHash -LiteralPath $initialBackup -Algorithm SHA256).Hash
        $gitCheck = & git -C $core diff --no-index --quiet --ignore-space-at-eol -- $initialBackup $target
        if ($LASTEXITCODE -ne 1) { throw 'Estado inicial inesperado' }
        $oldText = [IO.File]::ReadAllText($initialBackup)
        $newText = [IO.File]::ReadAllText($target)
        $pattern = '(?m)^Atualizado em: [^\r\n]+'
        if ($oldText -notmatch $pattern -or $newText -notmatch $pattern) { throw 'Formato inesperado' }
        $normalizedOld = [regex]::Replace($oldText,$pattern,'Atualizado em: VALIDADO')
        $normalizedNew = [regex]::Replace($newText,$pattern,'Atualizado em: VALIDADO')
        if ($normalizedOld -ne $normalizedNew) { throw 'Core possui alteracoes nao reconhecidas' }
        $known = $current
    } else {
        throw 'Nao foi possivel estabelecer a continuidade com seguranca'
    }
}

if ($incoming -eq $current) {
    [IO.File]::WriteAllText($state,$current,(New-Object Text.UTF8Encoding($false)))
    Write-Output 'M03.17: SEM ALTERACOES'
    exit 0
}

$temp = Join-Path $core ('CONEXO_PORTABLE_STATUS.md.'+[guid]::NewGuid().ToString('N')+'.tmp')
$backup = $target + '.' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.' + [guid]::NewGuid().ToString('N') + '.bak'
try {
    Copy-Item -LiteralPath $source -Destination $temp -ErrorAction Stop
    if ((Get-FileHash -LiteralPath $temp).Hash -ne $incoming) { throw 'Copia temporaria divergente' }
    Copy-Item -LiteralPath $target -Destination $backup -ErrorAction Stop
    Copy-Item -LiteralPath $temp -Destination $target -Force -ErrorAction Stop
    if ((Get-FileHash -LiteralPath $target).Hash -ne $incoming) {
        Copy-Item -LiteralPath $backup -Destination $target -Force -ErrorAction Stop
        throw 'Destino divergente; original restaurado'
    }
    [IO.File]::WriteAllText($state,$incoming,(New-Object Text.UTF8Encoding($false)))
    Write-Output 'M03.17: CORE ATUALIZADO LOCALMENTE; SEM PUBLICACAO'
} finally {
    if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
}
