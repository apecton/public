# remove_task.ps1
# Removes all ClaudeAutoTrigger scheduled tasks and optionally cleans up state files.
# Run from an elevated (Administrator) PowerShell prompt.

#Requires -RunAsAdministrator

Set-StrictMode -Version Latest
$ErrorActionPreference = 'SilentlyContinue'

foreach ($name in @('ClaudeAutoTrigger_Startup', 'ClaudeAutoTrigger_Next')) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "Removed: $name"
    } else {
        Write-Host "Not found (already removed): $name"
    }
}

Write-Host ""
foreach ($f in @("$env:USERPROFILE\.claude_session_trigger", "$env:USERPROFILE\.claude_session_trigger.log")) {
    if (Test-Path $f) {
        $choice = Read-Host "Delete $f ? [y/N]"
        if ($choice -match '^[Yy]$') {
            Remove-Item $f -Force
            Write-Host "Deleted: $f"
        }
    }
}

Write-Host "Done."
