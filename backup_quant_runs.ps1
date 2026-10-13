param(
    [string]$RunDir,
    [string]$ArchiveRoot,
    [switch]$AllowMock
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

if (-not $RunDir) {
    $candidates = foreach ($directory in Get-ChildItem -LiteralPath "runs" -Directory -ErrorAction Stop) {
        $statePath = Join-Path $directory.FullName "state.json"
        if (-not (Test-Path -LiteralPath $statePath)) { continue }
        try {
            $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        } catch {
            continue
        }
        if ($state.status -eq "completed" -and [int]$state.error_count -eq 0 -and ($AllowMock -or -not $state.mock)) {
            [pscustomobject]@{ Directory = $directory; State = $state }
        }
    }
    $selected = $candidates | Sort-Object { $_.State.finished_at } -Descending | Select-Object -First 1
    if (-not $selected) {
        throw "No clean completed $(if ($AllowMock) { '' } else { 'real ' })run is available for backup"
    }
    $RunDir = $selected.Directory.FullName
}

$statePath = Join-Path $RunDir "state.json"
$state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($state.mock -and -not $AllowMock) {
    throw "Refusing to archive a mock run without -AllowMock"
}

$archiveText = & $python -m quant_agents archive-run --run-dir $RunDir --archive-root $ArchiveRoot
if ($LASTEXITCODE -ne 0) { throw "Archive command failed" }
$archive = ($archiveText | Out-String) | ConvertFrom-Json
$actualHash = (Get-FileHash -LiteralPath $archive.archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne ([string]$archive.sha256).ToLowerInvariant()) {
    throw "Archive SHA-256 verification failed"
}
$verifyText = & $python -m quant_agents verify-archive `
    --archive $archive.archive `
    --expected-sha256 $actualHash `
    --expected-run-id $archive.run_id `
    --expected-manifest-snapshot-id $archive.manifest_snapshot_id
if ($LASTEXITCODE -ne 0) { throw "Archive restore verification failed" }
$verification = ($verifyText | Out-String) | ConvertFrom-Json
if (-not $verification.ok -or -not $verification.restore_tested -or -not $verification.restored_integrity_ok) {
    throw "Archive did not pass the full restore and run-integrity test"
}

[ordered]@{
    status = $archive.status
    run_id = $archive.run_id
    archive = $archive.archive
    sha256 = $actualHash
    verified = $true
    restore_tested = [bool]$verification.restore_tested
    restored_integrity_ok = [bool]$verification.restored_integrity_ok
    archive_content_id = $archive.archive_content_id
    receipt = $archive.receipt
    source_mock = [bool]$state.mock
    retention_days = if ($env:RUN_RETENTION_DAYS) { [int]$env:RUN_RETENTION_DAYS } else { 365 }
    deletion_performed = $false
} | ConvertTo-Json
