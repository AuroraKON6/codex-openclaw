param(
    [switch]$NoPing
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

$envFile = Join-Path $scriptDir ".env"
if (Test-Path -LiteralPath $envFile) {
    Get-Content -LiteralPath $envFile -Encoding UTF8 | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.+)$') {
            $key = $Matches[1].Trim()
            $value = $Matches[2].Trim().Trim('"').Trim("'")
            if (-not [Environment]::GetEnvironmentVariable($key, "Process")) {
                [Environment]::SetEnvironmentVariable($key, $value, "Process")
            }
        }
    }
}

& $python -m quant_agents extensions-audit
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $python -m quant_agents skills-audit
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$arguments = @("-m", "quant_agents", "health", "--runtime", "pi", "--runtime-only")
if ($NoPing) {
    $arguments += "--no-ping"
}

& $python @arguments
exit $LASTEXITCODE
