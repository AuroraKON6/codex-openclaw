param(
    [switch]$IncludeFullRegression
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

function Invoke-CapturedProcess {
    param(
        [Parameter(Mandatory)] [string]$FilePath,
        [Parameter(Mandatory)] [string]$ArgumentLine
    )
    $startInfo = New-Object Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FilePath
    $startInfo.Arguments = $ArgumentLine
    $startInfo.WorkingDirectory = $scriptDir
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = $utf8NoBom
    $startInfo.StandardErrorEncoding = $utf8NoBom
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $startInfo
    if (-not $process.Start()) { throw "Could not start $FilePath" }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    [pscustomobject]@{
        ExitCode = $process.ExitCode
        Text = $stdout + $stderr
    }
    $process.Dispose()
}

$reportDir = Join-Path $scriptDir ("drill_reports\operational_drill_{0:yyyyMMdd_HHmmss}" -f (Get-Date))
New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
$patterns = @(
    "test_operations.py",
    "test_release.py",
    "test_scheduling.py",
    "test_governance.py",
    "test_cli.py",
    "test_pi_client.py",
    "test_orchestrator.py"
)
$testResults = @()
$status = "passed"
$failure = $null
foreach ($pattern in $patterns) {
    $logPath = Join-Path $reportDir ($pattern.Replace(".py", ".log"))
    $capture = Invoke-CapturedProcess `
        -FilePath $python `
        -ArgumentLine "-m unittest discover -s tests -p $pattern -v"
    $exitCode = $capture.ExitCode
    $text = $capture.Text
    [IO.File]::WriteAllText($logPath, $text, $utf8NoBom)
    Write-Host $text
    $testResults += [ordered]@{
        pattern = $pattern
        exit_code = $exitCode
        passed = $exitCode -eq 0
        log = $logPath
    }
    if ($exitCode -ne 0) {
        $status = "failed"
        $failure = "Fault drill failed for $pattern"
        break
    }
}
$fullRegression = $null
if ($IncludeFullRegression -and $status -eq "passed") {
    $logPath = Join-Path $reportDir "full_regression.log"
    $capture = Invoke-CapturedProcess `
        -FilePath (Get-Command powershell.exe).Source `
        -ArgumentLine "-NoProfile -ExecutionPolicy Bypass -File `"$scriptDir\verify_quant_pipeline.ps1`""
    $exitCode = $capture.ExitCode
    $text = $capture.Text
    [IO.File]::WriteAllText($logPath, $text, $utf8NoBom)
    Write-Host $text
    $fullRegression = [ordered]@{
        exit_code = $exitCode
        passed = $exitCode -eq 0
        log = $logPath
    }
    if ($exitCode -ne 0) {
        $status = "failed"
        $failure = "Full regression failed during drill"
    }
}

$report = [ordered]@{
    schema_version = 1
    status = $status
    executed_at = [DateTimeOffset]::UtcNow.ToString("o")
    runtime = "test_and_mock_only"
    real_llm_called = $false
    drills = @(
        "run_lock_contention_and_stale_reclaim",
        "request_idempotency_and_explicit_retry",
        "event_chain_tamper_detection",
        "stale_run_recovery",
        "production_monitor_excludes_mock_and_stale_runs",
        "archive_tamper_path_traversal_and_restore_verification",
        "retention_and_legal_hold_plan",
        "release_block_on_mock_or_tamper",
        "schedule_cutoff_and_stable_request_id",
        "data_license_evidence_validation",
        "pi_version_model_json_tool_and_timeout_failures",
        "source_preflight_dependency_and_budget_blocking"
    )
    test_results = $testResults
    full_regression = $fullRegression
    failure = $failure
    evidence_dir = $reportDir
    production_files_modified = $false
    disclaimer = "Operational drill only; not market research or real trading advice."
}
$reportPath = Join-Path $reportDir "drill_report.json"
[IO.File]::WriteAllText(
    $reportPath,
    (($report | ConvertTo-Json -Depth 12) + [Environment]::NewLine),
    $utf8NoBom
)
$report | ConvertTo-Json -Depth 12
if ($status -ne "passed") { throw $failure }
