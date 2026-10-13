# run_weekly_report.ps1 - 生成周报 (Pi runtime)
param(
    [switch]$Mock,
    [string]$Since = "",
    [string]$Until = "",
    [ValidateSet("pi")]
    [string]$Runtime = "pi"
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

if (-not $Since) { $Since = (Get-Date).AddDays(-7).ToString("yyyyMMdd") }
if (-not $Until) { $Until = (Get-Date).ToString("yyyyMMdd") }

Write-Host "=== CSI 500 Weekly Report ===" -ForegroundColor Cyan
Write-Host "Period: $Since ~ $Until"
Write-Host "Runtime: $Runtime"
Write-Host "Mode: $(if ($Mock) { 'MOCK' } else { 'REAL' })"
Write-Host ""

$envFile = Join-Path $scriptDir ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.+)$') {
            $key = $Matches[1].Trim()
            $val = $Matches[2].Trim().Trim('"').Trim("'")
            if (-not [Environment]::GetEnvironmentVariable($key, "Process")) {
                [Environment]::SetEnvironmentVariable($key, $val, "Process")
            }
        }
    }
}

$pythonArgs = @("-m", "quant_agents", "weekly", "--runtime", $Runtime, "--since", $Since, "--until", $Until)
if ($Mock) {
    $pythonArgs += "--mock"
}
Write-Host "Running: $python $($pythonArgs -join ' ')" -ForegroundColor Yellow

& $python @pythonArgs
$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "=== Done ===" -ForegroundColor Green
} elseif ($exitCode -eq 2) {
    Write-Host "=== FAILED: weekly aggregation could not complete ===" -ForegroundColor Red
} else {
    Write-Host "=== Done with errors (exit $exitCode) ===" -ForegroundColor Yellow
}

exit $exitCode
