param()

$ErrorActionPreference = "Stop"
$utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$env:PYTHONIOENCODING = "utf-8"
$env:PI_OFFLINE = "1"
$env:PI_TELEMETRY = "0"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir
. (Join-Path $scriptDir "quant_python.ps1")
$python = Resolve-QuantPython -ProjectRoot $scriptDir

& $python -m quant_agents extensions-audit
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$cli = Join-Path $scriptDir "pi_runtime\node_modules\@earendil-works\pi-coding-agent\dist\cli.js"
$extension = Join-Path $scriptDir ".pi\extensions\quant-ops-readonly.mjs"
$stateDir = Join-Path $scriptDir ".cache\pi-agent"
$env:PI_CODING_AGENT_DIR = $stateDir

Write-Host "Pi read-only operator console. Use /quant-status or /quant-status clear."
Write-Host "No tools, skills, automatic extensions, sessions, context files, or startup network are enabled."

& node $cli `
    --provider deepseek `
    --model deepseek-v4-pro `
    --thinking off `
    --no-session `
    --no-tools `
    --no-extensions `
    --extension $extension `
    --no-skills `
    --no-prompt-templates `
    --no-themes `
    --no-context-files `
    --no-approve `
    --offline `
    --system-prompt "You are a read-only quant operations console. Return JSON only. Do not provide market analysis or real-money trading advice."

exit $LASTEXITCODE
