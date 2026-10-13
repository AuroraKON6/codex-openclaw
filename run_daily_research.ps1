param(
    [string]$Template = "strategy_round.example.json",
    [string]$AsOf,
    [string]$RetryOf,
    [string]$DeploymentAuthorization,
    [ValidatePattern('^[0-9a-fA-F]{64}$')]
    [string]$ExpectedAuthorizationSha256
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

if (-not $DeploymentAuthorization -and -not $ExpectedAuthorizationSha256) {
    throw "Daily research requires a deployment authorization bound to an approved forward campaign"
}
if ($DeploymentAuthorization -or $ExpectedAuthorizationSha256) {
    if (-not $DeploymentAuthorization -or -not $ExpectedAuthorizationSha256) {
        throw "Scheduled execution requires both deployment authorization path and expected SHA-256"
    }
    $DeploymentAuthorization = (Resolve-Path -LiteralPath $DeploymentAuthorization).Path
    $authorizationHash = (Get-FileHash -LiteralPath $DeploymentAuthorization -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($authorizationHash -ne $ExpectedAuthorizationSha256.ToLowerInvariant()) {
        throw "Deployment authorization SHA-256 mismatch"
    }
    $authorization = Get-Content -LiteralPath $DeploymentAuthorization -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($authorization.schema_version -ne 3 -or $authorization.runtime -ne "pi" -or $authorization.model -ne "deepseek-v4-pro") {
        throw "Deployment authorization runtime contract is invalid"
    }
    if ($authorization.broker_connection_enabled -ne $false -or $authorization.external_distribution_approved -ne $false) {
        throw "Deployment authorization violates broker or distribution boundaries"
    }
    $expiresAt = [DateTimeOffset]::Parse([string]$authorization.expires_at)
    if ($expiresAt -le [DateTimeOffset]::UtcNow) {
        throw "Deployment authorization has expired"
    }
    $currentCommit = (& git -C $scriptDir rev-parse HEAD 2>$null | Out-String).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or $currentCommit -ne ([string]$authorization.source_head_commit).ToLowerInvariant()) {
        throw "Current source revision does not match the approved scheduled baseline"
    }
    $sourceStatus = (& git -C $scriptDir status --porcelain=v1 --untracked-files=all | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $sourceStatus) {
        throw "Scheduled execution requires a clean source workspace"
    }
    $experimentRegistryDir = (Resolve-Path -LiteralPath ([string]$authorization.experiment_registry_dir)).Path
    $registryMetadataPath = Join-Path $experimentRegistryDir "registry.json"
    $registryMetadataHash = (Get-FileHash -LiteralPath $registryMetadataPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($registryMetadataHash -ne ([string]$authorization.experiment_registry_metadata_sha256).ToLowerInvariant()) {
        throw "Experiment registry metadata SHA-256 mismatch"
    }
    $env:EXPERIMENT_REGISTRY_PATH = $experimentRegistryDir
    $registryText = & $python -m quant_agents experiment-status `
        --registry $experimentRegistryDir `
        --runs-root (Join-Path $scriptDir "runs")
    if ($LASTEXITCODE -ne 0) { throw "Experiment registry integrity or reconciliation failed" }
    $registry = ($registryText | Out-String) | ConvertFrom-Json
    if ($registry.registry_id -ne $authorization.experiment_registry_id) {
        throw "Experiment registry identity mismatch"
    }
    $approvalPath = (Resolve-Path -LiteralPath ([string]$authorization.approval_path)).Path
    $approvalHash = (Get-FileHash -LiteralPath $approvalPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($approvalHash -ne ([string]$authorization.approval_sha256).ToLowerInvariant()) {
        throw "Approved schedule evidence changed after installation"
    }
    $decisionText = & $python -m quant_agents release-verify `
        --run-dir ([string]$authorization.approved_run_dir) `
        --approval $approvalPath
    if ($LASTEXITCODE -ne 0) { throw "Scheduled deployment approval is no longer valid" }
    $decision = ($decisionText | Out-String) | ConvertFrom-Json
    if ($decision.status -ne "APPROVED_FOR_INTERNAL_REVIEW" -or $decision.candidate_id -ne $authorization.candidate_id) {
        throw "Scheduled deployment approval identity mismatch"
    }
    $campaignDir = (Resolve-Path -LiteralPath ([string]$authorization.forward_campaign_dir)).Path
    $campaignMetadataPath = Join-Path $campaignDir "campaign.json"
    $campaignMetadataHash = (Get-FileHash -LiteralPath $campaignMetadataPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($campaignMetadataHash -ne ([string]$authorization.forward_campaign_metadata_sha256).ToLowerInvariant()) {
        throw "Forward campaign metadata SHA-256 mismatch"
    }
    $campaignText = & $python -m quant_agents forward-status `
        --campaign $campaignDir `
        --expected-campaign-sha256 $campaignMetadataHash
    if ($LASTEXITCODE -ne 0) { throw "Forward campaign integrity verification failed" }
    $campaign = ($campaignText | Out-String) | ConvertFrom-Json
    if ($campaign.campaign_id -ne $authorization.forward_campaign_id -or $campaign.baseline_run_id -ne $authorization.approved_run_id) {
        throw "Forward campaign identity mismatch"
    }
    if ($campaign.status -notin @("BLOCKED_NO_FORWARD_OBSERVATIONS", "OBSERVING_MINIMUM_NOT_MET", "CONTINUE_OBSERVATION", "ELIGIBLE_FOR_INDEPENDENT_VALIDATION")) {
        throw "Forward campaign is closed or requires intervention: $($campaign.status)"
    }
}

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

$scheduledDir = Join-Path $scriptDir "scheduled_inputs"
New-Item -ItemType Directory -Path $scheduledDir -Force | Out-Null
$outputPath = Join-Path $scheduledDir ("pending_{0:yyyyMMdd_HHmmss}.json" -f (Get-Date))
$scheduleArgs = @("-m", "quant_agents", "make-scheduled-input", "--template", $Template, "--output", $outputPath)
if ($AsOf) { $scheduleArgs += @("--as-of", $AsOf) }
if ($campaignDir) { $scheduleArgs += @("--campaign", $campaignDir) }
$scheduleText = & $python @scheduleArgs
if ($LASTEXITCODE -ne 0) {
    throw "Scheduled-input generation failed; no research run was started"
}
$schedule = ($scheduleText | Out-String) | ConvertFrom-Json
$finalInputPath = Join-Path $scheduledDir ("CSI500_{0}.json" -f $schedule.resolved_trade_date)
Move-Item -LiteralPath $outputPath -Destination $finalInputPath -Force

$priorRuns = @()
if (Test-Path -LiteralPath "runs") {
    foreach ($directory in Get-ChildItem -LiteralPath "runs" -Directory) {
        $statePath = Join-Path $directory.FullName "state.json"
        if (-not (Test-Path -LiteralPath $statePath)) { continue }
        try {
            $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($state.request_id -eq $schedule.request_id) {
                $priorRuns += $state
            }
        } catch {
            continue
        }
    }
}
$latestPrior = $priorRuns | Sort-Object started_at | Select-Object -Last 1
if ($latestPrior -and $latestPrior.status -eq "completed" -and [int]$latestPrior.error_count -eq 0) {
    [ordered]@{
        status = "no_op_already_completed"
        request_id = $schedule.request_id
        prior_run_id = $latestPrior.run_id
        resolved_trade_date = $schedule.resolved_trade_date
    } | ConvertTo-Json
    exit 0
}
if ($latestPrior -and -not $RetryOf) {
    throw "Request $($schedule.request_id) already has run $($latestPrior.run_id) with status $($latestPrior.status); an operator must review it and pass -RetryOf explicitly"
}
if ($RetryOf -and $latestPrior -and $RetryOf -ne $latestPrior.run_id) {
    throw "-RetryOf must equal the latest prior run ID $($latestPrior.run_id)"
}

$runArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $scriptDir "run_quant_agents.ps1"),
    "-InputPath", $finalInputPath,
    "-Runtime", "pi",
    "-RequestId", $schedule.request_id
)
if ($RetryOf) { $runArgs += @("-RetryOf", $RetryOf) }
& powershell @runArgs
$pipelineExit = $LASTEXITCODE
if ($pipelineExit -ne 0) { exit $pipelineExit }

$completedRun = $null
foreach ($directory in Get-ChildItem -LiteralPath "runs" -Directory) {
    $statePath = Join-Path $directory.FullName "state.json"
    if (-not (Test-Path -LiteralPath $statePath)) { continue }
    try {
        $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($state.request_id -eq $schedule.request_id -and $state.status -eq "completed" -and [int]$state.error_count -eq 0) {
            if (-not $completedRun -or [string]$state.started_at -gt [string]$completedRun.state.started_at) {
                $completedRun = [pscustomobject]@{ path = $directory.FullName; state = $state }
            }
        }
    } catch {
        continue
    }
}
if (-not $completedRun) {
    throw "Completed scheduled run could not be resolved for forward observation"
}
$recordText = & $python -m quant_agents forward-record `
    --campaign $campaignDir `
    --expected-campaign-sha256 $campaignMetadataHash `
    --run-dir $completedRun.path
if ($LASTEXITCODE -ne 0) {
    throw "Pipeline completed but forward-observation append failed; operator review is required"
}
$recordText
exit 0
