param(
    [ValidateRange(1, 10)]
    [int]$TrialsPerSkill = 3,
    [string]$OutputRoot = "drill_reports"
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

function Get-TextSha256([string]$Text) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $utf8NoBom.GetBytes($Text)
        $hash = $algorithm.ComputeHash($bytes)
        return ([BitConverter]::ToString($hash)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $algorithm.Dispose()
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

if (-not $env:DEEPSEEK_API_KEY) {
    throw "DEEPSEEK_API_KEY is required for real Pi skill acceptance"
}

& $python -m quant_agents skills-audit | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Pi skills supply-chain audit failed"
}

$piCli = (Resolve-Path -LiteralPath "pi_runtime\node_modules\@earendil-works\pi-coding-agent\dist\cli.js").Path
$outputDirectory = Join-Path $OutputRoot ("pi_skills_acceptance_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$outputDirectory = (Resolve-Path -LiteralPath $outputDirectory).Path

$cases = @(
    [ordered]@{
        name = "quant-agent-evaluation"
        prompt = 'Load and apply the explicitly supplied quant-agent-evaluation skill and its referenced evaluation contract. Return this exact JSON object using native JSON booleans: {"skill_name":"quant-agent-evaluation","production_skills_enabled":false,"mock_is_real_evidence":false,"deterministic_grading_first":true,"real_trading_advice_allowed":false}'
    },
    [ordered]@{
        name = "quant-backtest-assurance"
        prompt = 'Load and apply the explicitly supplied quant-backtest-assurance skill and its A-share execution reference. Return this exact JSON object using native JSON booleans: {"skill_name":"quant-backtest-assurance","decision_values":["PASS","CONDITIONAL","BLOCKED"],"calculations_owner":"Python","same_bar_close_fill_allowed":false,"real_trading_advice_allowed":false}'
    }
)

$trials = @()
foreach ($case in $cases) {
    $skillPath = (Resolve-Path -LiteralPath (Join-Path ".pi\skills" $case.name)).Path
    foreach ($trialNumber in 1..$TrialsPerSkill) {
        $lines = $case.prompt | & node $piCli `
            --mode json `
            --provider deepseek `
            --model deepseek-v4-pro `
            --thinking off `
            --no-session `
            --tools read `
            --no-extensions `
            --no-skills `
            --skill $skillPath `
            --no-prompt-templates `
            --no-themes `
            --no-context-files `
            --no-approve `
            --offline `
            --system-prompt "You are an isolated operator-skill acceptance agent. Load the supplied skill and requested reference. Your entire assistant response must be exactly one JSON object: first character {, last character }, no reasoning, preface, fence, or trailing text."
        $exitCode = $LASTEXITCODE
        $raw = ($lines -join "`n") + "`n"
        $rawPath = Join-Path $outputDirectory ($case.name + "_" + $trialNumber + ".jsonl")
        [IO.File]::WriteAllText($rawPath, $raw, $utf8NoBom)

        $events = @()
        $eventsValid = $true
        try {
            foreach ($line in ($raw -split "`r?`n")) {
                if ($line.Trim()) {
                    $events += ($line | ConvertFrom-Json -ErrorAction Stop)
                }
            }
        }
        catch {
            $eventsValid = $false
        }

        $toolStarts = @($events | Where-Object { $_.type -eq "tool_execution_start" })
        $badTools = @(
            $toolStarts | Where-Object {
                $_.toolName -ne "read" -or
                -not ([IO.Path]::GetFullPath([string]$_.args.path).StartsWith(
                    $skillPath,
                    [StringComparison]::OrdinalIgnoreCase
                ))
            }
        )
        $messageEnds = @(
            $events | Where-Object {
                $_.type -eq "message_end" -and $_.message.role -eq "assistant"
            }
        )
        $final = if ($messageEnds.Count) { $messageEnds[-1].message } else { $null }
        $assistantText = if ($null -ne $final) {
            (($final.content | Where-Object { $_.type -eq "text" } | ForEach-Object { $_.text }) -join "")
        }
        else {
            ""
        }

        $parsed = $null
        $parseError = ""
        try {
            $parsed = $assistantText | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            $parseError = $_.Exception.Message
        }
        $strictJson = (
            $null -ne $parsed -and
            $assistantText.Trim().StartsWith("{") -and
            $assistantText.Trim().EndsWith("}")
        )
        $commonContract = (
            $exitCode -eq 0 -and
            $eventsValid -and
            $null -ne $final -and
            $final.provider -eq "deepseek" -and
            $final.model -eq "deepseek-v4-pro" -and
            $final.stopReason -eq "stop" -and
            $toolStarts.Count -ge 2 -and
            $badTools.Count -eq 0 -and
            $strictJson -and
            $parsed.skill_name -eq $case.name -and
            ($parsed.real_trading_advice_allowed -is [bool]) -and
            $parsed.real_trading_advice_allowed -eq $false
        )
        if ($case.name -eq "quant-agent-evaluation" -and $strictJson) {
            $caseContract = (
                ($parsed.production_skills_enabled -is [bool]) -and
                $parsed.production_skills_enabled -eq $false -and
                ($parsed.mock_is_real_evidence -is [bool]) -and
                $parsed.mock_is_real_evidence -eq $false -and
                ($parsed.deterministic_grading_first -is [bool]) -and
                $parsed.deterministic_grading_first -eq $true
            )
        }
        elseif ($strictJson) {
            $caseContract = (
                $parsed.calculations_owner -eq "Python" -and
                ($parsed.same_bar_close_fill_allowed -is [bool]) -and
                $parsed.same_bar_close_fill_allowed -eq $false -and
                (@($parsed.decision_values) -join ",") -eq "PASS,CONDITIONAL,BLOCKED"
            )
        }
        else {
            $caseContract = $false
        }
        $passed = $commonContract -and $caseContract

        $trials += [pscustomobject][ordered]@{
            skill = $case.name
            trial = $trialNumber
            status = if ($passed) { "passed" } else { "failed" }
            exit_code = $exitCode
            strict_json = $strictJson
            parse_error = $parseError
            provider = if ($null -ne $final) { $final.provider } else { "" }
            model = if ($null -ne $final) { $final.model } else { "" }
            session_id = if ($eventsValid -and @($events | Where-Object { $_.type -eq "session" }).Count) {
                @($events | Where-Object { $_.type -eq "session" })[0].id
            }
            else {
                ""
            }
            tool_count = $toolStarts.Count
            only_skill_local_reads = ($badTools.Count -eq 0)
            assistant_text_sha256 = Get-TextSha256 $assistantText
            usage = if ($null -ne $final) { $final.usage } else { $null }
            raw_sha256 = (Get-FileHash -LiteralPath $rawPath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
}

$failedTrials = @($trials | Where-Object { $_.status -ne "passed" })
$tokenValues = @(
    $trials | Where-Object { $null -ne $_.usage } | ForEach-Object { [int64]$_.usage.totalTokens }
)
$costValues = @(
    $trials | Where-Object { $null -ne $_.usage } | ForEach-Object { [double]$_.usage.cost.total }
)
$report = [ordered]@{
    schema_version = 1
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    status = if ($failedTrials.Count -eq 0) { "passed" } else { "failed" }
    scope = "operator_skills_contract_only_not_market_research"
    production_runtime_skills_enabled = $false
    allowed_acceptance_tool = "read"
    skills_lock_sha256 = (Get-FileHash -LiteralPath "governance\pi_skills.lock.json" -Algorithm SHA256).Hash.ToLowerInvariant()
    trials_per_skill = $TrialsPerSkill
    passed_trials = $trials.Count - $failedTrials.Count
    total_trials = $trials.Count
    strict_json_pass_rate = if ($trials.Count) {
        [math]::Round(($trials.Count - $failedTrials.Count) / $trials.Count, 4)
    }
    else {
        0
    }
    trials = $trials
    total_tokens = ($tokenValues | Measure-Object -Sum).Sum
    total_cost_usd = ($costValues | Measure-Object -Sum).Sum
    not_covered = @(
        "Production market-analysis quality",
        "Licensed Tushare data quality",
        "Human semantic review",
        "Release approval"
    )
    disclaimer = "Operator skills acceptance only; not market research or real trading advice."
}
$reportPath = Join-Path $outputDirectory "acceptance_report.json"
$reportJson = $report | ConvertTo-Json -Depth 12
[IO.File]::WriteAllText($reportPath, $reportJson + "`n", $utf8NoBom)
$reportJson
Write-Host "Acceptance report: $reportPath"

if ($failedTrials.Count) {
    exit 1
}
