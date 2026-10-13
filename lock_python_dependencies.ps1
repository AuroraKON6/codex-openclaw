param(
    [switch]$Apply,
    [string]$IndexUrl
)

$ErrorActionPreference = "Stop"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$launcher = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not $launcher) {
    throw "Python Launcher is missing."
}
$version = (& $launcher.Source -3.11 -c "import sys; print('.'.join(map(str, sys.version_info[:3])))").Trim()
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^3\.11\.') {
    throw "CPython 3.11.x is required to regenerate the Windows lock."
}

$buildRoot = Join-Path $scriptDir (".tmp\python-lock-{0}" -f [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
& $launcher.Source -3.11 -m venv $buildRoot
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create the isolated lock environment."
}
$python = Join-Path $buildRoot "Scripts\python.exe"
& $python -m pip install "pip-tools==7.6.1"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install the pinned lock compiler."
}

$resolved = Join-Path $buildRoot "requirements.resolved.txt"
$compileArgs = @(
    "-m", "piptools", "compile",
    "--resolver=backtracking",
    "--no-header",
    "--no-emit-index-url",
    "--no-emit-trusted-host",
    "--strip-extras",
    "--output-file=$resolved"
)
if ($IndexUrl) {
    $compileArgs += @("--index-url", $IndexUrl)
}
$compileArgs += (Join-Path $scriptDir "requirements.in")
& $python @compileArgs
if ($LASTEXITCODE -ne 0) {
    throw "Dependency resolution failed."
}

$wheelhouse = Join-Path $buildRoot "wheelhouse"
$downloadArgs = @(
    "-m", "pip", "download",
    "--only-binary=:all:",
    "--dest", $wheelhouse
)
if ($IndexUrl) {
    $downloadArgs += @("--index-url", $IndexUrl)
}
$downloadArgs += @("-r", $resolved)
& $python @downloadArgs
if ($LASTEXITCODE -ne 0) {
    throw "Wheel download failed."
}

$candidate = Join-Path $buildRoot "requirements.txt"
& $python (Join-Path $scriptDir "tools\build_python_lock.py") `
    --resolved $resolved `
    --wheelhouse $wheelhouse `
    --output $candidate
if ($LASTEXITCODE -ne 0) {
    throw "Hash-lock generation failed."
}

if ($Apply) {
    Copy-Item -LiteralPath $candidate -Destination (Join-Path $scriptDir "requirements.txt") -Force
    Write-Host "Applied lock candidate. Run bootstrap, tests, Secret scan, and source-candidate before review." -ForegroundColor Yellow
} else {
    Write-Host "Lock candidate generated without modifying requirements.txt: $candidate" -ForegroundColor Green
}
