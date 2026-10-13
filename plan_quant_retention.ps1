param(
    [string]$RunsRoot = "runs",
    [string]$ArchiveRoot,
    [int]$RetentionDays = 0,
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$env:PYTHONIOENCODING = "utf-8"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir
. (Join-Path $scriptDir "quant_python.ps1")
$python = Resolve-QuantPython -ProjectRoot $scriptDir

if (-not $ArchiveRoot) {
    $ArchiveRoot = Join-Path (Split-Path -Parent $scriptDir) "quant-research-archives"
}
if ($RetentionDays -le 0) {
    $RetentionDays = if ($env:RUN_RETENTION_DAYS) { [int]$env:RUN_RETENTION_DAYS } else { 365 }
}
if (-not $OutputPath) {
    $reportRoot = Join-Path $scriptDir "drill_reports"
    New-Item -ItemType Directory -Path $reportRoot -Force | Out-Null
    $OutputPath = Join-Path $reportRoot ("retention_plan_{0:yyyyMMdd_HHmmss}.json" -f (Get-Date))
}

& $python -m quant_agents retention-plan `
    --runs-root $RunsRoot `
    --archive-root $ArchiveRoot `
    --retention-days $RetentionDays `
    --output $OutputPath
if ($LASTEXITCODE -ne 0) {
    throw "Retention planning failed"
}
