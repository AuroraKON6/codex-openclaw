param(
    [string]$TaskName = "QuantResearch_Daily_Internal"
)

$ErrorActionPreference = "Stop"
$utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir
. (Join-Path $scriptDir "quant_python.ps1")
$python = Resolve-QuantPython -ProjectRoot $scriptDir
$authorizationPath = Join-Path $scriptDir (".cache\schedule\{0}.authorization.json" -f $TaskName)
$errors = @()

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    $errors += "scheduled task is not installed"
}
if (-not (Test-Path -LiteralPath $authorizationPath)) {
    $errors += "deployment authorization is missing"
}

$authorization = $null
$authorizationHash = $null
if (Test-Path -LiteralPath $authorizationPath) {
    try {
        $authorization = Get-Content -LiteralPath $authorizationPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $authorizationHash = (Get-FileHash -LiteralPath $authorizationPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($authorization.schema_version -ne 3 -or $authorization.runtime -ne "pi" -or $authorization.model -ne "deepseek-v4-pro") {
            $errors += "deployment authorization schema is not 3 with the approved pi runtime contract"
        }
        if ($authorization.scope -ne "scheduled_internal_research_only") {
            $errors += "deployment authorization scope is invalid"
        }
        if ([DateTimeOffset]::Parse([string]$authorization.expires_at) -le [DateTimeOffset]::UtcNow) {
            $errors += "deployment authorization is expired"
        }
        if ($authorization.broker_connection_enabled -ne $false -or $authorization.external_distribution_approved -ne $false) {
            $errors += "deployment authorization boundaries are invalid"
        }
        $currentCommit = (& git -C $scriptDir rev-parse HEAD 2>$null | Out-String).Trim().ToLowerInvariant()
        if ($LASTEXITCODE -ne 0 -or $currentCommit -ne ([string]$authorization.source_head_commit).ToLowerInvariant()) {
            $errors += "current source revision does not match the approved scheduled baseline"
        }
        $sourceStatus = (& git -C $scriptDir status --porcelain=v1 --untracked-files=all | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $sourceStatus) {
            $errors += "scheduled source workspace is not clean"
        }

        $experimentRegistryDir = (Resolve-Path -LiteralPath ([string]$authorization.experiment_registry_dir)).Path
        $registryMetadataPath = Join-Path $experimentRegistryDir "registry.json"
        if (-not (Test-Path -LiteralPath $registryMetadataPath)) {
            $errors += "experiment registry metadata is missing"
        } else {
            $registryMetadataHash = (Get-FileHash -LiteralPath $registryMetadataPath -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($registryMetadataHash -ne ([string]$authorization.experiment_registry_metadata_sha256).ToLowerInvariant()) {
                $errors += "experiment registry metadata SHA-256 mismatch"
            }
        }
        $env:EXPERIMENT_REGISTRY_PATH = $experimentRegistryDir
        $registryText = & $python -m quant_agents experiment-status `
            --registry $experimentRegistryDir `
            --runs-root (Join-Path $scriptDir "runs")
        if ($LASTEXITCODE -ne 0) {
            $errors += "experiment registry integrity or reconciliation failed"
        } else {
            $registry = ($registryText | Out-String) | ConvertFrom-Json
            if ($registry.registry_id -ne $authorization.experiment_registry_id) {
                $errors += "experiment registry identity mismatch"
            }
        }

        $approvalPath = (Resolve-Path -LiteralPath ([string]$authorization.approval_path)).Path
        $approvalHash = (Get-FileHash -LiteralPath $approvalPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($approvalHash -ne ([string]$authorization.approval_sha256).ToLowerInvariant()) {
            $errors += "approved schedule evidence changed after installation"
        } else {
            $decisionText = & $python -m quant_agents release-verify `
                --run-dir ([string]$authorization.approved_run_dir) `
                --approval $approvalPath
            if ($LASTEXITCODE -ne 0) {
                $errors += "scheduled deployment approval is no longer valid"
            } else {
                $decision = ($decisionText | Out-String) | ConvertFrom-Json
                if ($decision.status -ne "APPROVED_FOR_INTERNAL_REVIEW" -or $decision.candidate_id -ne $authorization.candidate_id) {
                    $errors += "scheduled deployment approval identity mismatch"
                }
            }
        }

        $campaignMetadataPath = Join-Path ([string]$authorization.forward_campaign_dir) "campaign.json"
        if (-not (Test-Path -LiteralPath $campaignMetadataPath)) {
            $errors += "forward campaign metadata is missing"
        } else {
            $campaignHash = (Get-FileHash -LiteralPath $campaignMetadataPath -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($campaignHash -ne ([string]$authorization.forward_campaign_metadata_sha256).ToLowerInvariant()) {
                $errors += "forward campaign metadata hash mismatch"
            } else {
                $campaignText = & $python -m quant_agents forward-status --campaign ([string]$authorization.forward_campaign_dir) --expected-campaign-sha256 $campaignHash
                if ($LASTEXITCODE -ne 0) {
                    $errors += "forward campaign ledger integrity failed"
                } else {
                    $campaign = ($campaignText | Out-String) | ConvertFrom-Json
                    if ($campaign.campaign_id -ne $authorization.forward_campaign_id -or $campaign.baseline_run_id -ne $authorization.approved_run_id) {
                        $errors += "forward campaign identity mismatch"
                    }
                    if ($campaign.status -notin @("BLOCKED_NO_FORWARD_OBSERVATIONS", "OBSERVING_MINIMUM_NOT_MET", "CONTINUE_OBSERVATION", "ELIGIBLE_FOR_INDEPENDENT_VALIDATION")) {
                        $errors += "forward campaign is closed or requires intervention"
                    }
                }
            }
        }
    } catch {
        $errors += "deployment authorization or bound evidence validation failed: $($_.Exception.Message)"
    }
}

$taskInfo = $null
if ($task) {
    $actions = @($task.Actions)
    if ($actions.Count -ne 1) {
        $errors += "scheduled task must have exactly one action"
    } else {
        $action = $actions[0]
        if ([IO.Path]::GetFileName([string]$action.Execute) -ne "powershell.exe") {
            $errors += "scheduled task executable is not powershell.exe"
        }
        if (([string]$action.WorkingDirectory).TrimEnd('\') -ne $scriptDir.TrimEnd('\')) {
            $errors += "scheduled task working directory drifted"
        }
        if ($authorizationHash -and [string]$action.Arguments -notmatch [regex]::Escape($authorizationHash)) {
            $errors += "scheduled task is not bound to the authorization SHA-256"
        }
        if ([string]$action.Arguments -notmatch [regex]::Escape($authorizationPath)) {
            $errors += "scheduled task is not bound to the deployment authorization path"
        }
        if ([string]$action.Arguments -notmatch '(?i)-WindowStyle\s+Hidden') {
            $errors += "scheduled task is not configured for a hidden window"
        }
    }
    if ([string]$task.Settings.MultipleInstances -ne "IgnoreNew") {
        $errors += "scheduled task MultipleInstances must be IgnoreNew"
    }
    if ([string]$task.Principal.RunLevel -ne "Limited") {
        $errors += "scheduled task must not run elevated"
    }
    $taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
}

$result = [ordered]@{
    schema_version = 1
    checked_at = [DateTimeOffset]::UtcNow.ToString("o")
    ok = $errors.Count -eq 0
    task_name = $TaskName
    installed = [bool]$task
    authorization_path = $authorizationPath
    authorization_sha256 = $authorizationHash
    authorization_schema_version = if ($authorization) { [string]$authorization.schema_version } else { $null }
    runtime = if ($authorization) { [string]$authorization.runtime } else { $null }
    model = if ($authorization) { [string]$authorization.model } else { $null }
    approved_run_id = if ($authorization) { [string]$authorization.approved_run_id } else { $null }
    candidate_id = if ($authorization) { [string]$authorization.candidate_id } else { $null }
    source_head_commit = if ($authorization) { [string]$authorization.source_head_commit } else { $null }
    experiment_registry_id = if ($authorization) { [string]$authorization.experiment_registry_id } else { $null }
    experiment_registry_dir = if ($authorization) { [string]$authorization.experiment_registry_dir } else { $null }
    forward_campaign_id = if ($authorization) { [string]$authorization.forward_campaign_id } else { $null }
    forward_campaign_dir = if ($authorization) { [string]$authorization.forward_campaign_dir } else { $null }
    authorization_expires_at = if ($authorization) { [string]$authorization.expires_at } else { $null }
    task_state = if ($task) { [string]$task.State } else { $null }
    last_run_time = if ($taskInfo) { $taskInfo.LastRunTime.ToString("o") } else { $null }
    last_task_result = if ($taskInfo) { $taskInfo.LastTaskResult } else { $null }
    errors = $errors
}
$result | ConvertTo-Json -Depth 8
if ($errors.Count -gt 0) { exit 1 }
