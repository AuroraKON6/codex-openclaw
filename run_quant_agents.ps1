# run_quant_agents.ps1 - 运行量化研究 Agent 系统 (Pi runtime)
param(
    [switch]$Mock,
    [Alias("Input")]
    [string]$InputPath = "strategy_round.example.json",
    [ValidateSet("pi")]
    [string]$Runtime = "pi",
    [string]$RequestId,
    [string]$RetryOf
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

Write-Host "=== CSI 500 Quant Research Agent System ===" -ForegroundColor Cyan
Write-Host "Input: $InputPath"
Write-Host "Runtime: $Runtime"
Write-Host "Mode: $(if ($Mock) { 'MOCK' } else { 'REAL' })"
Write-Host "Fallback: disabled (Mock requires -Mock)"
Write-Host ""

# Load .env if exists
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
    Write-Host "Loaded .env file" -ForegroundColor Green
}

& $python -m quant_agents recover --runs-root runs
if ($LASTEXITCODE -ne 0) {
    throw "Stale-run recovery check failed with exit code $LASTEXITCODE"
}

$pythonArgs = @("-m", "quant_agents", "run", "--runtime", $Runtime, "--input", $InputPath)
if ($Mock) {
    $pythonArgs += "--mock"
}
if ($RequestId) {
    $pythonArgs += @("--request-id", $RequestId)
}
if ($RetryOf) {
    if (-not $RequestId) {
        throw "-RetryOf requires -RequestId"
    }
    $pythonArgs += @("--retry-of", $RetryOf)
}
Write-Host "Running: $python $($pythonArgs -join ' ')" -ForegroundColor Yellow
Write-Host ""

& $python @pythonArgs
$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "=== Done ===" -ForegroundColor Green
} elseif ($exitCode -eq 2) {
    Write-Host "=== FAILED: real-mode preflight did not pass ===" -ForegroundColor Red
    Write-Host "Run .\check_pi.ps1 and $python -m quant_agents health --runtime $Runtime" -ForegroundColor Yellow
} else {
    Write-Host "=== Done with errors (exit $exitCode) ===" -ForegroundColor Yellow
}

exit $exitCode
