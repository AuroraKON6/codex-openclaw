param(
    [switch]$SkipTests,
    [string]$Wheelhouse
)

$ErrorActionPreference = "Stop"
$utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$launcher = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not $launcher) {
    throw "Python Launcher is missing. Install an approved CPython 3.11.x runtime first."
}

$baseVersion = (& $launcher.Source -3.11 -c "import sys; print('.'.join(map(str, sys.version_info[:3])))").Trim()
if ($LASTEXITCODE -ne 0 -or $baseVersion -notmatch '^3\.11\.') {
    throw "An approved CPython 3.11.x runtime is required; py -3.11 returned '$baseVersion'."
}

$venvRoot = Join-Path $scriptDir ".venv"
$python = Join-Path $venvRoot "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    & $launcher.Source -3.11 -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the project virtual environment."
    }
}

. (Join-Path $scriptDir "quant_python.ps1")
$python = Resolve-QuantPython -ProjectRoot $scriptDir
$installArgs = @(
    "-m", "pip", "install",
    "--require-hashes",
    "--only-binary=:all:"
)
if ($Wheelhouse) {
    $resolvedWheelhouse = (Resolve-Path -LiteralPath $Wheelhouse).Path
    $installArgs += @("--no-index", "--find-links", $resolvedWheelhouse)
}
$installArgs += @("-r", (Join-Path $scriptDir "requirements.txt"))
& $python @installArgs
if ($LASTEXITCODE -ne 0) {
    throw "Hash-locked dependency installation failed."
}
& $python -m pip check
if ($LASTEXITCODE -ne 0) {
    throw "The isolated dependency set is inconsistent."
}
& $python -m quant_agents python-runtime --require-ready
if ($LASTEXITCODE -ne 0) {
    throw "The project Python runtime contract is not satisfied."
}

if (-not $SkipTests) {
    & $python -m unittest discover -s tests
    if ($LASTEXITCODE -ne 0) {
        throw "Tests failed in the isolated CPython 3.11 environment."
    }
}

Write-Host "Isolated CPython $baseVersion environment is ready: $python" -ForegroundColor Green
