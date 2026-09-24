# claude_auto_trigger.ps1
#
# Fires `claude -p "hello"` at the precise moment the 5-hour usage window resets.
# After each successful trigger it registers a one-shot Task Scheduler entry for
# exactly now+5h, so the next session starts at the right time -- not at the next
# arbitrary hourly tick.
#
# Invoked by Task Scheduler (startup trigger + self-scheduled one-shot).
# Do NOT run with elevated (Administrator) rights.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Script:ScriptPath    = if ($MyInvocation.MyCommand.Path) { $MyInvocation.MyCommand.Path } else { $PSCommandPath }
$Script:ProjectRoot   = Split-Path $Script:ScriptPath -Parent
$Script:TimestampFile = Join-Path $Script:ProjectRoot '.claude_session_trigger'
$Script:LogFile       = Join-Path $Script:ProjectRoot '.claude_session_trigger.log'
$Script:WindowHours   = 5
$Script:StartupHour   = 6   # default startup hour (0-23)
$Script:NextTaskName  = 'ClaudeAutoTrigger_Next'
$Script:MaxLogLines   = 1000

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $entry = '{0}  {1,-5}  {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    try {
        Add-Content -Path $Script:LogFile -Value $entry -Encoding UTF8
        $lines = Get-Content $Script:LogFile -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($lines -and $lines.Count -gt $Script:MaxLogLines) {
            $lines | Select-Object -Last $Script:MaxLogLines | Set-Content $Script:LogFile -Encoding UTF8
        }
    } catch { <# never let a log write kill the script #> }
}

# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------
function Read-LastTriggerTime {
    if (-not (Test-Path $Script:TimestampFile)) { return $null }
    $raw = Get-Content $Script:TimestampFile -Encoding UTF8 -Raw -ErrorAction SilentlyContinue
    if (-not $raw) { return $null }
    try {
        return [DateTime]::Parse($raw.Trim(), [System.Globalization.CultureInfo]::InvariantCulture)
    } catch {
        Write-Log "Unreadable timestamp '$($raw.Trim())' -- treating as first run" 'WARN'
        return $null
    }
}

function Save-TriggerTime {
    param([DateTime]$Time)
    Set-Content -Path $Script:TimestampFile -Value ($Time.ToString('o')) -Encoding UTF8
}


# ---------------------------------------------------------------------------
# Helper: adjust next trigger time to preferred startup hour window
# ---------------------------------------------------------------------------
function Get-AdjustedNextTime {
    param([DateTime]$BaseTime)
    $intervalHours = $Script:WindowHours
    $startupHour   = $Script:StartupHour

    # Calculate raw next time based on interval
    $rawNext = $BaseTime.AddHours($intervalHours)

    # Determine how many hours before the startup hour the rawNext time is (on a 24‑hour circle)
    $hoursBeforeStartup = ($startupHour - $rawNext.TimeOfDay.TotalHours + 24) % 24
    # Use -le to include the exact boundary (e.g., exactly 5h before 6AM = 1AM should round up)
    if ($hoursBeforeStartup -le $intervalHours) {
        # rawNext lies within the interval before the startup hour → round up to the next startup hour
        $adjusted = $rawNext.Date.AddHours($startupHour)
        if ($adjusted -lt $rawNext) {
            $adjusted = $adjusted.AddDays(1)
        }
        return $adjusted
    }
    else {
        return $rawNext
    }
}

# ---------------------------------------------------------------------------
# Task Scheduler helpers
# ---------------------------------------------------------------------------
function Test-NextTaskExists {
    $out = & schtasks /query /tn $Script:NextTaskName 2>&1
    if ($LASTEXITCODE -eq 0) {
        return $true
    } else {
        return $false
    }
}

function Register-NextTask {
    param([DateTime]$At)

    if ($At -le (Get-Date)) {
        $At = (Get-Date).AddSeconds(30)
        Write-Log "Next trigger was in the past -- bumped to $($At.ToString('HH:mm:ss'))" 'WARN'
    }

    $psArg = "-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Script:ScriptPath`""

    $Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $psArg
    $Trigger = New-ScheduledTaskTrigger -Once -At $At
    $Settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
        -MultipleInstances IgnoreNew `
        -StartWhenAvailable
    $UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $Principal = New-ScheduledTaskPrincipal `
        -UserId $UserId `
        -LogonType Interactive `
        -RunLevel Limited

    try {
        Register-ScheduledTask `
            -TaskName $Script:NextTaskName `
            -Action $Action `
            -Trigger $Trigger `
            -Settings $Settings `
            -Principal $Principal `
            -Description 'One-shot trigger for next Claude Code window reset' `
            -Force | Out-Null
        Write-Log "Scheduled '$($Script:NextTaskName)' for $($At.ToString('yyyy-MM-dd HH:mm'))"
    } catch {
        Write-Log "FAILED to schedule next task: $_" 'ERROR'
    }
}

# ---------------------------------------------------------------------------
# Claude invocation (isolated so Pester can mock it)
# ---------------------------------------------------------------------------
function Invoke-ClaudeCommand {
    # Local Continue so $ErrorActionPreference = 'Stop' (script scope) doesn't
    # promote claude's stderr output to a terminating error via 2>&1.
    # Empty-string stdin skips the 3-second "no stdin data" wait.
    $ErrorActionPreference = 'Continue'
    return ('' | & claude -p 'hello') 2>&1
}

function Invoke-ClaudeSession {
    if (-not (Get-Command 'claude' -ErrorAction SilentlyContinue)) {
        Write-Log "'claude' not found on PATH -- is Claude Code installed?" 'ERROR'
        return $false
    }
    try {
        $null     = Invoke-ClaudeCommand
        $exitCode = $LASTEXITCODE
        if ($exitCode -eq 0) {
            Write-Log 'Session started OK (exit 0)'
        } else {
            Write-Log "claude exited $exitCode" 'WARN'
        }
        return $true
    } catch {
        Write-Log "Exception invoking claude: $_" 'ERROR'
        return $false
    }
}

# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------
function Invoke-Main {
    $lastTrigger   = Read-LastTriggerTime
    $now           = Get-Date
    $shouldTrigger = $false

    if ($null -eq $lastTrigger) {
        Write-Log 'No prior session on record -- triggering now'
        $shouldTrigger = $true
    } else {
        $elapsed = $now - $lastTrigger

        if ($elapsed.TotalSeconds -lt 0) {
            Write-Log "Timestamp is in the future ($lastTrigger) -- possible clock skew. Skipping." 'WARN'
            return
        }

        if ($elapsed.TotalHours -ge $Script:WindowHours) {
            Write-Log ("Window elapsed ({0}h {1}m) -- triggering" -f [int]$elapsed.Hours, [int]$elapsed.Minutes)
            $shouldTrigger = $true
        } else {
            $rawNextTime = $lastTrigger.AddHours($Script:WindowHours)
            $nextTime    = Get-AdjustedNextTime -BaseTime $lastTrigger
            $remaining   = $nextTime - $now
            Write-Log ("Window open -- {0}h {1}m remaining (next: {2:HH:mm:ss})" -f `
                [int]$remaining.Hours, [int]$remaining.Minutes, $nextTime)

            # Safety net: re-create _Next if it was accidentally deleted
            if (-not (Test-NextTaskExists)) {
                Write-Log "Task '$($Script:NextTaskName)' missing -- re-creating for $($nextTime.ToString('HH:mm:ss'))" 'WARN'
                Register-NextTask $nextTime
            }
        }
    }

    if ($shouldTrigger) {
        $ok = Invoke-ClaudeSession
        if ($ok) {
            $triggerTime = Get-Date
            Save-TriggerTime $triggerTime
            $nextTrigger = Get-AdjustedNextTime -BaseTime $triggerTime
            Register-NextTask $nextTrigger
        }
    }
}

# Don't run when dot-sourced by Pester
if ($MyInvocation.InvocationName -ne '.') {
    Invoke-Main
}