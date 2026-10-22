# Conexo OS M03.11 - prepare allowlisted portable summary locally.
# Read-only source; no Git operations, network requests, or scheduled task changes.
$ErrorActionPreference = 'Stop'
$runner = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$state = Join-Path $runner 'local-state'
$source = Join-Path $state 'autoops-status.json'
$destination = Join-Path $state 'CONEXO_PORTABLE_STATUS.md'
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw 'M03.10 status JSON not found.' }
$status = Get-Content -LiteralPath $source -Raw -Encoding UTF8 | ConvertFrom-Json
if ([int]$status.schema_version -ne 1) { throw 'Unsupported status schema.' }
$allowedOverall = @('OK', 'ERROR')
$allowedSync = @('PENDENTE_APROVACAO', 'SINCRONIZADO', 'ERRO')
$overall = [string]$status.overall
$sync = [string]$status.sync_state
if ($allowedOverall -cnotcontains $overall) { throw 'Unknown overall status; manual review required.' }
if ($allowedSync -cnotcontains $sync) { throw 'Unknown sync status; manual review required.' }
if ([string]$status.branch -cne 'local-runner') { throw 'Unexpected branch.' }
$updated = [datetimeoffset]::Parse([string]$status.updated_at, [Globalization.CultureInfo]::InvariantCulture).ToString('yyyy-MM-ddTHH:mm:sszzz')
$published = if ($status.publication_performed -eq $true) { 'Sim' } else { 'Nao' }
$approval = if ($sync -ceq 'PENDENTE_APROVACAO') { 'Sim' } else { 'Nao' }
$lines = @(
  '# Conexo OS - Resumo operacional portatil',
  '',
  'Formato: M03.11 / v1',
  "Atualizado em: $updated",
  "Estado geral: $overall",
  "Sincronizacao: $sync",
  "Aprovacao pendente: $approval",
  "Publicacao na ultima verificacao: $published",
  '',
  'Este resumo foi gerado localmente a partir de campos permitidos do AutoOps.',
  'A existencia deste arquivo nao implica publicacao no GitHub.'
)
# Explicit UTF-8 without BOM; only a local ignored-state file is written.
[System.IO.File]::WriteAllLines($destination, $lines, (New-Object System.Text.UTF8Encoding($false)))
Write-Output "M03.11 summary prepared locally: $destination"
Write-Output 'No Git publication or scheduled task changes performed.'
