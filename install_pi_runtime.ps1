[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeDir = Join-Path $scriptDir "pi_runtime"
$cliPath = Join-Path $runtimeDir "node_modules\@earendil-works\pi-coding-agent\dist\cli.js"
$stateDir = Join-Path $scriptDir ".cache\pi-agent"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js is required; install Node >= 22.19.0"
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is required to install the pinned Pi runtime"
}

$nodeVersionText = (& node --version).Trim().TrimStart("v")
$nodeVersion = [version]$nodeVersionText
if ($nodeVersion -lt [version]"22.19.0") {
    throw "Pi 0.84.2 requires Node >= 22.19.0; found $nodeVersionText"
}

$env:npm_config_cache = Join-Path $env:TEMP "quant-pi-npm-cache"
Push-Location $runtimeDir
try {
    & npm ci --ignore-scripts --no-audit --no-fund --registry=https://registry.npmjs.org
    if ($LASTEXITCODE -ne 0) {
        throw "npm ci failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $cliPath -PathType Leaf)) {
    throw "Pi CLI was not installed at $cliPath"
}
$piVersion = (& node $cliPath --version).Trim()
if ($LASTEXITCODE -ne 0 -or $piVersion -ne "0.84.2") {
    throw "Installed Pi version is '$piVersion'; expected 0.84.2"
}

New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$env:PI_CODING_AGENT_DIR = $stateDir
$env:PI_OFFLINE = "1"
$env:PI_TELEMETRY = "0"
$models = & node $cliPath --list-models deepseek --offline
if ($LASTEXITCODE -ne 0 -or ($models -join "`n") -notmatch '(?m)^deepseek\s+deepseek-v4-pro\s+') {
    throw "Pinned Pi runtime does not expose deepseek/deepseek-v4-pro"
}

$receipt = [ordered]@{
    schema_version = 1
    installed_at = [DateTimeOffset]::UtcNow.ToString("o")
    package = "@earendil-works/pi-coding-agent"
    version = $piVersion
    node_version = $nodeVersionText
    package_lock_sha256 = (Get-FileHash -LiteralPath (Join-Path $runtimeDir "package-lock.json") -Algorithm SHA256).Hash.ToLowerInvariant()
    cli_sha256 = (Get-FileHash -LiteralPath $cliPath -Algorithm SHA256).Hash.ToLowerInvariant()
    install_scripts_disabled = $true
    model = "deepseek-v4-pro"
}
$receiptPath = Join-Path $stateDir "install_receipt.json"
[IO.File]::WriteAllText(
    $receiptPath,
    ($receipt | ConvertTo-Json -Depth 5),
    $utf8NoBom
)

$receipt | Add-Member -NotePropertyName receipt_path -NotePropertyValue $receiptPath
$receipt | ConvertTo-Json -Depth 5
