param(
    [switch]$SkipMock
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

& $python -m quant_agents python-runtime --require-ready
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$pythonFiles = Get-ChildItem -Path quant_agents -Recurse -Filter *.py | ForEach-Object FullName
& $python -m py_compile @pythonFiles
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python -m quant_agents secret-scan
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m quant_agents source-candidate --require-reviewable
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$packetJson = (& $python -m quant_agents source-review-packet | Out-String)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$packet = $packetJson | ConvertFrom-Json
if (
    $packet.packet_created -ne $true -or
    $packet.source_baseline_authorized -ne $false -or
    -not (Test-Path -LiteralPath $packet.packet_dir -PathType Container)
) {
    throw "Source-review packet smoke test did not create a non-authorizing packet."
}

$packetVerificationJson = (& $python -m quant_agents source-review-verify --packet-dir $packet.packet_dir | Out-String)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$packetVerification = $packetVerificationJson | ConvertFrom-Json
if (
    $packetVerification.ok -ne $true -or
    $packetVerification.organization_identity_verified -ne $false -or
    $packetVerification.source_baseline_authorized -ne $false
) {
    throw "Source-review packet verification weakened a review or authorization boundary."
}

$decisionTemplateJson = (& $python -m quant_agents source-review-decision-template --packet-dir $packet.packet_dir | Out-String)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$decisionTemplate = $decisionTemplateJson | ConvertFrom-Json
if (
    $decisionTemplate.template_created -ne $true -or
    $decisionTemplate.human_fields_blank -ne $true -or
    $decisionTemplate.source_baseline_authorized -ne $false
) {
    throw "Source-review decision template smoke test did not preserve blank, non-authorizing controls."
}

$blankDecisionJson = (& $python -m quant_agents source-review-decision-verify --packet-dir $packet.packet_dir --decision $decisionTemplate.template_path | Out-String)
$blankDecisionExit = $LASTEXITCODE
if ($blankDecisionExit -ne 3) {
    throw "Blank source-review decision must block with exit code 3."
}
$blankDecision = $blankDecisionJson | ConvertFrom-Json
if (
    $blankDecision.review_claim_valid -ne $false -or
    $blankDecision.source_baseline_authorized -ne $false -or
    $blankDecision.g1_authorized -ne $false -or
    $blankDecision.real_run_authorized -ne $false
) {
    throw "Blank source-review decision incorrectly passed a governance boundary."
}

$rootScripts = @(Get-ChildItem -Path . -Filter *.ps1 -File)
foreach ($scriptFile in $rootScripts) {
    $tokens = $null
    $parseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $scriptFile.FullName, [ref]$tokens, [ref]$parseErrors
    ) | Out-Null
    if ($parseErrors -and $parseErrors.Count -gt 0) {
        throw "PowerShell parse error in $($scriptFile.Name): $($parseErrors[0].Message)"
    }
}
Write-Host ("PowerShell syntax parse: {0} scripts OK" -f $rootScripts.Count)

& $python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $SkipMock) {
    & powershell -ExecutionPolicy Bypass -File .\run_quant_agents.ps1 -Mock
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $latest = Get-ChildItem -Directory runs |
        Where-Object { $_.Name -match '^\d{8}_\d{6}_\d{3}$' } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    $state = Get-Content -Raw -Encoding UTF8 (Join-Path $latest.FullName "state.json") | ConvertFrom-Json
    if ($state.schema_version -ne 7 -or $state.success_count -ne 7 -or $state.error_count -ne 0) {
        throw "Mock acceptance failed for $($latest.FullName)"
    }
    $pythonRuntime = @(
        $state.preflight.checks |
            Where-Object { $_.name -eq "python_runtime_contract" }
    )
    $expectedLockSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath .\requirements.txt).Hash.ToLowerInvariant()
    if (
        $pythonRuntime.Count -ne 1 -or
        $pythonRuntime[0].status -ne "ok" -or
        $pythonRuntime[0].detail.ok -ne $true -or
        $pythonRuntime[0].detail.requirements_lock_sha256 -ne $expectedLockSha256
    ) {
        throw "Mock evidence is not bound to the current project Python runtime contract."
    }
    if ($state.budget_gate.status -ne "passed" -or $state.business_controls.broker_connection_enabled -ne $false) {
        throw "Operational or broker boundary gate failed for $($latest.FullName)"
    }
    if (
        $state.business_controls.research_protocol_gate.status -ne "not_evaluated_mock" -or
        $state.business_controls.research_protocol_gate.live_execution_authorized -ne $false
    ) {
        throw "Mock research-protocol gate must remain explicitly non-applicable for $($latest.FullName)"
    }
    if (
        $state.business_controls.execution_cost_gate.status -ne "not_evaluated_mock" -or
        $state.business_controls.execution_cost_gate.live_execution_ready -ne $false
    ) {
        throw "Mock execution-cost gate must remain explicitly non-applicable for $($latest.FullName)"
    }
    if (
        $state.business_controls.experiment_registry_gate.status -ne "not_evaluated_mock" -or
        $state.business_controls.experiment_registry_gate.ledger_integrity_ok -ne $false
    ) {
        throw "Mock experiment-registry gate must remain explicitly non-applicable for $($latest.FullName)"
    }
    if (
        $state.backtest_assurance.decision -ne "NOT_APPLICABLE_MOCK" -or
        $state.robustness_validation.decision -ne "NOT_APPLICABLE_MOCK" -or
        $state.robustness_validation.walk_forward.decision -ne "NOT_APPLICABLE_MOCK"
    ) {
        throw "Mock backtest gates must remain explicitly non-applicable for $($latest.FullName)"
    }
    $requiredBacktestArtifacts = @(
        "backtest\cost_ledger.json",
        "backtest\execution_policy.json",
        "backtest\robustness_validation.json",
        "backtest\backtest_assurance.json"
    )
    foreach ($relativePath in $requiredBacktestArtifacts) {
        $artifactPath = Join-Path $latest.FullName $relativePath
        if (-not (Test-Path -LiteralPath $artifactPath -PathType Leaf)) {
            throw "Required backtest artifact is missing: $artifactPath"
        }
        Get-Content -Raw -Encoding UTF8 -LiteralPath $artifactPath | ConvertFrom-Json | Out-Null
    }
    $manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $latest.FullName "run_manifest.json") | ConvertFrom-Json
    if (
        $manifest.metadata.backtest_assurance_decision -ne "NOT_APPLICABLE_MOCK" -or
        $manifest.metadata.robustness_validation_decision -ne "NOT_APPLICABLE_MOCK"
    ) {
        throw "Run manifest is not bound to the mock assurance decisions for $($latest.FullName)"
    }
    if ($manifest.metadata.execution_cost_status -ne "not_evaluated_mock") {
        throw "Run manifest is not bound to the mock execution-cost decision for $($latest.FullName)"
    }
    if ($manifest.metadata.research_protocol_status -ne "not_evaluated_mock") {
        throw "Run manifest is not bound to the mock research-protocol decision for $($latest.FullName)"
    }
    if ($manifest.metadata.experiment_registry_status -ne "not_evaluated_mock") {
        throw "Run manifest is not bound to the mock experiment-registry decision for $($latest.FullName)"
    }
    $summary = Get-Content -Raw -Encoding UTF8 (Join-Path $latest.FullName "summary.md")
    $forbidden = @("买入", "卖出", "加仓", "减仓", "止损", "止盈", "LONG", "SHORT")
    $hits = @($forbidden | Where-Object { $summary -match [regex]::Escape($_) })
    if ($hits.Count -gt 0) {
        throw "Forbidden trading terms in summary: $($hits -join ', ')"
    }

    & $python -m quant_agents verify-run --run-dir $latest.FullName
    if ($LASTEXITCODE -ne 0) { throw "Run integrity verification failed" }

    & $python -m quant_agents release-prepare --run-dir $latest.FullName
    if ($LASTEXITCODE -ne 3) {
        throw "Mock release gate must block with exit code 3"
    }
}

Write-Host "Quant pipeline verification PASSED" -ForegroundColor Green
