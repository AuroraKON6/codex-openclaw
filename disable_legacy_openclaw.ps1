[CmdletBinding(SupportsShouldProcess)]
param(
    [string[]]$TaskNames = @(
        "OpenClaw Gateway",
        "OpenClaw Gateway (quant-research)",
        "OpenClaw Gateway Watchdog (quant-research)"
    ),
    [int[]]$LegacyPorts = @(18789, 18790)
)

$ErrorActionPreference = "Stop"
$results = @()
foreach ($taskName in $TaskNames) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if (-not $task) {
        $results += [ordered]@{ task_name = $taskName; found = $false; disabled = $true }
        continue
    }
    $actionError = $null
    if ($task.State -ne "Disabled" -and $PSCmdlet.ShouldProcess($taskName, "Stop and disable legacy task")) {
        try {
            if ($task.State -eq "Running") {
                Stop-ScheduledTask -TaskName $taskName
            }
            Disable-ScheduledTask -TaskName $taskName | Out-Null
        } catch {
            $actionError = $_.Exception.Message
        }
    }
    $current = Get-ScheduledTask -TaskName $taskName
    $results += [ordered]@{
        task_name = $taskName
        found = $true
        disabled = $current.State -eq "Disabled"
        state = [string]$current.State
        error = $actionError
    }
}

Start-Sleep -Seconds 2
$listeners = @(
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in $LegacyPorts }
)
$report = [ordered]@{
    schema_version = 1
    checked_at = [DateTimeOffset]::UtcNow.ToString("o")
    tasks = $results
    legacy_ports = $LegacyPorts
    legacy_port_listening = $listeners.Count -gt 0
    listeners = @($listeners | ForEach-Object {
        [ordered]@{
            local_address = $_.LocalAddress
            local_port = $_.LocalPort
            owning_process = $_.OwningProcess
        }
    })
    all_tasks_disabled = @($results | Where-Object { -not $_.disabled }).Count -eq 0
    action = if ($WhatIfPreference) { "preview" } else { "disabled" }
}
$report | ConvertTo-Json -Depth 6

if (-not $WhatIfPreference -and (-not $report.all_tasks_disabled -or $report.legacy_port_listening)) {
    Write-Error "Legacy runtime shutdown requires manual review; no process was force-killed"
    exit 2
}
