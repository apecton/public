# setup_task.ps1
#
# One-time setup. Creates a single Task Scheduler entry that runs the check
# whenever the machine becomes usable again:
#   * at user logon  (cold boot / restart)
#   * on resume from sleep or hibernate
# The script itself schedules all on-time one-shot triggers while the machine
# is awake (ClaudeAutoTrigger_Next) -- no hourly polling.
#
# Run ONCE from an elevated (Administrator) PowerShell prompt:
#   powershell -ExecutionPolicy Bypass -File ".\setup_task.ps1"

#Requires -RunAsAdministrator

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptPath      = Join-Path $PSScriptRoot 'claude_auto_trigger.ps1'
$StartupTaskName = 'ClaudeAutoTrigger_Startup'
$Description     = 'Runs a Claude Code window check at logon and on resume from sleep/hibernate, then self-schedules the next trigger for exactly 5 hours later.'

if (-not (Test-Path $ScriptPath)) {
    Write-Error "Trigger script not found: $ScriptPath"
    exit 1
}
$ScriptPath = (Resolve-Path $ScriptPath).Path

$UserId = ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)

$PsArg    = "-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`""
$Action   = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $PsArg

# StartWhenAvailable lets a missed run catch up; the check is idempotent so a
# late/extra run just logs "window open" and exits.
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances  IgnoreNew `
    -StartWhenAvailable

$Principal = New-ScheduledTaskPrincipal `
    -UserId    $UserId `
    -LogonType Interactive `
    -RunLevel  Limited

# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------
# 1) At logon -- fires after a cold boot / restart, in the user's interactive
#    session (so PATH and the user token are available for `claude`).
#    Note: -AtStartup is deliberately NOT used: it fires before logon, where an
#    Interactive-logon task cannot actually run.
$LogonTrigger       = New-ScheduledTaskTrigger -AtLogOn -User $UserId
$LogonTrigger.Delay = 'PT1M'   # let network / profile settle

# 2) On resume from sleep OR hibernate -- event-based trigger on the System log,
#    Power-Troubleshooter Event ID 1 ("The system has resumed from sleep").
#    New-ScheduledTaskTrigger has no event-trigger switch, so build it via CIM.
$WakeTrigger = (Get-CimClass `
        -Namespace 'ROOT\Microsoft\Windows\TaskScheduler' `
        -ClassName 'MSFT_TaskEventTrigger') | New-CimInstance -ClientOnly
$WakeTrigger.Enabled      = $true
$WakeTrigger.Delay        = 'PT30S'
$WakeTrigger.Subscription = @'
<QueryList><Query Id="0" Path="System"><Select Path="System">*[System[Provider[@Name='Microsoft-Windows-Power-Troubleshooter'] and (EventID=1)]]</Select></Query></QueryList>
'@

Register-ScheduledTask `
    -TaskName    $StartupTaskName `
    -Action      $Action `
    -Trigger     @($LogonTrigger, $WakeTrigger) `
    -Settings    $Settings `
    -Principal   $Principal `
    -Description $Description `
    -Force | Out-Null

Write-Host "Registered: $StartupTaskName"
Write-Host "  trigger 1: at logon (cold boot / restart)"
Write-Host "  trigger 2: on resume from sleep / hibernate (Power-Troubleshooter event 1)"
Write-Host ""
Write-Host "Running initial check now (non-elevated, via Task Scheduler)..."
Start-ScheduledTask -TaskName $StartupTaskName
Write-Host ""
Write-Host "Setup complete."
Write-Host "Log:      $env:USERPROFILE\.claude_session_trigger.log"
Write-Host "Uninstall: .\remove_task.ps1"
