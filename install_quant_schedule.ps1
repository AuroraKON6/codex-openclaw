[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$TaskName = "QuantResearch_Daily_Internal",
    [ValidatePattern('^([01]\d|2[0-3]):[0-5]\d$')]
    [string]$At = "19:00",
    [Parameter(Mandatory)]
    [string]$ApprovedRunDir,
    [Parameter(Mandatory)]
    [string]$ApprovalPath,
    [Parameter(Mandatory)]
    [string]$ForwardCampaignPath,
    [Parameter(Mandatory)]
    [string]$ExperimentRegistryPath,
    [ValidateRange(1, 365)]
    [int]$AuthorizationDays = 90,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "quant_python.ps1")
$python = Resolve-QuantPython -ProjectRoot $scriptDir
$runner = Join-Path $scriptDir "run_daily_research.ps1"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Daily runner is missing: $runner"
}
$ApprovedRunDir = (Resolve-Path -LiteralPath $ApprovedRunDir).Path
$ApprovalPath = (Resolve-Path -LiteralPath $ApprovalPath).Path
$ForwardCampaignPath = (Resolve-Path -LiteralPath $ForwardCampaignPath).Path
$ExperimentRegistryPath = (Resolve-Path -LiteralPath $ExperimentRegistryPath).Path
$registryMetadataPath = Join-Path $ExperimentRegistryPath "registry.json"
if (-not (Test-Path -LiteralPath $registryMetadataPath)) {
    throw "Experiment registry metadata is missing: $registryMetadataPath"
}
$registryMetadataSha256 = (Get-FileHash -LiteralPath $registryMetadataPath -Algorithm SHA256).Hash.ToLowerInvariant()
$env:EXPERIMENT_REGISTRY_PATH = $ExperimentRegistryPath
$registryText = & $python -m quant_agents experiment-status `
    --registry $ExperimentRegistryPath `
    --runs-root (Join-Path $scriptDir "runs")
if ($LASTEXITCODE -ne 0) { throw "Experiment registry integrity or reconciliation failed" }
$registry = ($registryText | Out-String) | ConvertFrom-Json

$integrityText = & $python -m quant_agents verify-run --run-dir $ApprovedRunDir
if ($LASTEXITCODE -ne 0) { throw "Approved run failed current integrity verification" }
$integrity = ($integrityText | Out-String) | ConvertFrom-Json
$decisionText = & $python -m quant_agents release-verify --run-dir $ApprovedRunDir --approval $ApprovalPath
if ($LASTEXITCODE -ne 0) { throw "Release approvals are not currently valid" }
$decision = ($decisionText | Out-String) | ConvertFrom-Json
if ($decision.status -ne "APPROVED_FOR_INTERNAL_REVIEW") {
    throw "Release decision is not approved for internal review"
}
$campaignMetadataPath = Join-Path $ForwardCampaignPath "campaign.json"
if (-not (Test-Path -LiteralPath $campaignMetadataPath)) {
    throw "Forward campaign metadata is missing: $campaignMetadataPath"
}
$campaignMetadataSha256 = (Get-FileHash -LiteralPath $campaignMetadataPath -Algorithm SHA256).Hash.ToLowerInvariant()
$campaignText = & $python -m quant_agents forward-status `
    --campaign $ForwardCampaignPath `
    --expected-campaign-sha256 $campaignMetadataSha256
if ($LASTEXITCODE -ne 0) { throw "Forward campaign integrity verification failed" }
$campaign = ($campaignText | Out-String) | ConvertFrom-Json
$campaignMetadata = Get-Content -LiteralPath $campaignMetadataPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($campaign.status -notin @("BLOCKED_NO_FORWARD_OBSERVATIONS", "OBSERVING_MINIMUM_NOT_MET", "CONTINUE_OBSERVATION", "ELIGIBLE_FOR_INDEPENDENT_VALIDATION")) {
    throw "Forward campaign is closed or requires intervention: $($campaign.status)"
}
$state = Get-Content -LiteralPath (Join-Path $ApprovedRunDir "state.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$sourceCommit = [string]$state.source_provenance.head_commit
if (-not $state.source_provenance.release_ready -or $sourceCommit -notmatch '^[0-9a-fA-F]{40,64}$') {
    throw "Approved run is not bound to a clean committed source revision"
}
if ($campaign.baseline_run_id -ne $state.run_id -or $campaignMetadata.source_head_commit -ne $sourceCommit.ToLowerInvariant()) {
    throw "Forward campaign is not bound to the approved run and source revision"
}
$stateRegistry = $state.business_controls.experiment_registry_gate
if ($stateRegistry.status -ne "finalized" -or $stateRegistry.registry_id -ne $registry.registry_id) {
    throw "Approved run is not finalized in the selected experiment registry"
}
if ($stateRegistry.registry_metadata_sha256 -ne $registryMetadataSha256) {
    throw "Approved run experiment-registry metadata binding is inconsistent"
}
$authorizationDir = Join-Path $scriptDir ".cache\schedule"
New-Item -ItemType Directory -Path $authorizationDir -Force | Out-Null
$authorizationPath = Join-Path $authorizationDir ("{0}.authorization.json" -f $TaskName)
$authorization = [ordered]@{
    schema_version = 3
    task_name = $TaskName
    authorized_at = [DateTimeOffset]::UtcNow.ToString("o")
    expires_at = [DateTimeOffset]::UtcNow.AddDays($AuthorizationDays).ToString("o")
    approved_run_id = [string]$state.run_id
    approved_run_dir = $ApprovedRunDir
    approval_path = $ApprovalPath
    approval_sha256 = (Get-FileHash -LiteralPath $ApprovalPath -Algorithm SHA256).Hash.ToLowerInvariant()
    candidate_id = [string]$decision.candidate_id
    manifest_snapshot_id = [string]$integrity.manifest_snapshot_id
    source_head_commit = $sourceCommit.ToLowerInvariant()
    forward_campaign_dir = $ForwardCampaignPath
    forward_campaign_id = [string]$campaign.campaign_id
    forward_campaign_metadata_sha256 = $campaignMetadataSha256
    experiment_registry_dir = $ExperimentRegistryPath
    experiment_registry_id = [string]$registry.registry_id
    experiment_registry_metadata_sha256 = $registryMetadataSha256
    runtime = "pi"
    model = "deepseek-v4-pro"
    scope = "scheduled_internal_research_only"
    broker_connection_enabled = $false
    external_distribution_approved = $false
}
$authorizationJson = ($authorization | ConvertTo-Json -Depth 8) + [Environment]::NewLine
$sha256 = [Security.Cryptography.SHA256]::Create()
try {
    $authorizationHash = ([BitConverter]::ToString(
        $sha256.ComputeHash($utf8NoBom.GetBytes($authorizationJson))
    )).Replace("-", "").ToLowerInvariant()
} finally {
    $sha256.Dispose()
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing -and -not $Force) {
    throw "Scheduled task $TaskName already exists; use -Force only after reviewing it"
}

$runAt = [datetime]::Today.Add([timespan]::ParseExact($At, "hh\:mm", $null))
$arguments = "-WindowStyle Hidden -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$runner`" -DeploymentAuthorization `"$authorizationPath`" -ExpectedAuthorizationSha256 $authorizationHash"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $scriptDir
$trigger = New-ScheduledTaskTrigger -Daily -At $runAt
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
$userId = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited

if ($PSCmdlet.ShouldProcess($TaskName, "Register isolated daily research task at $At")) {
    [IO.File]::WriteAllText($authorizationPath, $authorizationJson, $utf8NoBom)
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Internal CSI 500 research only; approved run $($state.run_id); source $sourceCommit; no broker/order integration." `
        -Force:$Force | Out-Null
}

[ordered]@{
    task_name = $TaskName
    daily_at = $At
    runner = $runner
    account = $userId
    logon_type = "Interactive"
    multiple_instances = "IgnoreNew"
    installed = -not [bool]$WhatIfPreference
    approved_run_id = [string]$state.run_id
    candidate_id = [string]$decision.candidate_id
    forward_campaign_id = [string]$campaign.campaign_id
    forward_campaign_dir = $ForwardCampaignPath
    forward_campaign_metadata_sha256 = $campaignMetadataSha256
    experiment_registry_id = [string]$registry.registry_id
    experiment_registry_dir = $ExperimentRegistryPath
    experiment_registry_metadata_sha256 = $registryMetadataSha256
    source_head_commit = $sourceCommit
    authorization_path = $authorizationPath
    authorization_sha256 = $authorizationHash
    authorization_expires_at = $authorization.expires_at
    note = "Daily scheduling is idempotent by resolved Tushare trade date and never falls back to mock."
} | ConvertTo-Json
