# claude_auto_trigger.Tests.ps1
# Pester v5 tests for claude_auto_trigger.ps1
#
# Run from the repo root:
#   Invoke-Pester .\tests\claude_auto_trigger.Tests.ps1 -Output Detailed
#
# Requires Pester >= 5.0:
#   Install-Module Pester -Force -Scope CurrentUser

BeforeAll {
    # Dot-source the script to load functions without executing Invoke-Main
    # ($MyInvocation.InvocationName will be '.' so the guard fires)
    . (Join-Path $PSScriptRoot '..' 'claude_auto_trigger.ps1')

    # Redirect state files to PesterDrive so tests don't touch real files
    $Script:TimestampFile = Join-Path $TestDrive 'trigger_timestamp.txt'
    $Script:LogFile       = Join-Path $TestDrive 'trigger.log'
    $Script:ScriptPath    = Join-Path $PSScriptRoot '..' 'claude_auto_trigger.ps1'
}

# ---------------------------------------------------------------------------
# Read-LastTriggerTime
# ---------------------------------------------------------------------------
Describe 'Read-LastTriggerTime' {
    Context 'no timestamp file exists' {
        BeforeEach {
            if (Test-Path $Script:TimestampFile) { Remove-Item $Script:TimestampFile -Force }
        }
        It 'returns null' {
            Read-LastTriggerTime | Should -BeNullOrEmpty
        }
    }

    Context 'valid ISO-8601 timestamp' {
        BeforeEach {
            $refTime = (Get-Date).AddHours(-3)
            Set-Content $Script:TimestampFile -Value $refTime.ToString('o') -Encoding UTF8
        }
        It 'returns a DateTime' {
            Read-LastTriggerTime | Should -BeOfType [DateTime]
        }
        It 'returns a time approximately 3 hours ago' {
            $result  = Read-LastTriggerTime
            $elapsed = (Get-Date) - $result
            $elapsed.TotalHours | Should -BeGreaterThan 2.9
            $elapsed.TotalHours | Should -BeLessThan    3.1
        }
    }

    Context 'corrupted timestamp file' {
        BeforeEach {
            Set-Content $Script:TimestampFile -Value 'not-a-date' -Encoding UTF8
        }
        It 'returns null' {
            Read-LastTriggerTime | Should -BeNullOrEmpty
        }
        It 'writes a WARN entry to the log' {
            Read-LastTriggerTime | Out-Null
            (Get-Content $Script:LogFile -Raw) | Should -Match 'WARN'
        }
    }

    Context 'empty timestamp file' {
        BeforeEach {
            Set-Content $Script:TimestampFile -Value '' -Encoding UTF8
        }
        It 'returns null' {
            Read-LastTriggerTime | Should -BeNullOrEmpty
        }
    }
}

# ---------------------------------------------------------------------------
# Save-TriggerTime
# ---------------------------------------------------------------------------
Describe 'Save-TriggerTime' {
    It 'writes an ISO-8601 string that round-trips back to the same time' {
        $now = Get-Date
        Save-TriggerTime $now
        $read = Read-LastTriggerTime
        [Math]::Abs(($read - $now).TotalSeconds) | Should -BeLessThan 1
    }
}

# ---------------------------------------------------------------------------
# Invoke-Main — trigger-decision logic
# ---------------------------------------------------------------------------
Describe 'Invoke-Main trigger decisions' {
    BeforeEach {
        if (Test-Path $Script:TimestampFile) { Remove-Item $Script:TimestampFile -Force }
        Mock Invoke-ClaudeSession  { return $true }
        Mock Register-NextTask     { }
        Mock Test-NextTaskExists   { return $true }
    }

    Context 'no prior session on record' {
        It 'triggers a session' {
            Invoke-Main
            Should -Invoke Invoke-ClaudeSession -Times 1 -Exactly
        }
        It 'schedules the next task' {
            Invoke-Main
            Should -Invoke Register-NextTask -Times 1 -Exactly
        }
    }

    Context 'last trigger was 6 hours ago (window fully elapsed)' {
        BeforeEach { Save-TriggerTime (Get-Date).AddHours(-6) }
        It 'triggers a session' {
            Invoke-Main
            Should -Invoke Invoke-ClaudeSession -Times 1 -Exactly
        }
        It 'schedules the next task' {
            Invoke-Main
            Should -Invoke Register-NextTask -Times 1 -Exactly
        }
    }

    Context 'last trigger was exactly 5 hours ago (boundary)' {
        BeforeEach { Save-TriggerTime (Get-Date).AddHours(-5).AddSeconds(-1) }
        It 'triggers a session' {
            Invoke-Main
            Should -Invoke Invoke-ClaudeSession -Times 1 -Exactly
        }
    }

    Context 'last trigger was 3 hours ago (window still open)' {
        BeforeEach { Save-TriggerTime (Get-Date).AddHours(-3) }
        It 'does NOT trigger a session' {
            Invoke-Main
            Should -Invoke Invoke-ClaudeSession -Times 0 -Exactly
        }
        It 'checks whether the _Next task exists' {
            Invoke-Main
            Should -Invoke Test-NextTaskExists -Times 1 -Exactly
        }
        It 'does NOT re-create _Next when it already exists' {
            Invoke-Main
            Should -Invoke Register-NextTask -Times 0 -Exactly
        }
    }

    Context '_Next task is missing while window is still open' {
        BeforeEach {
            Save-TriggerTime (Get-Date).AddHours(-3)
            Mock Test-NextTaskExists { return $false }
        }
        It 'does NOT trigger a session' {
            Invoke-Main
            Should -Invoke Invoke-ClaudeSession -Times 0 -Exactly
        }
        It 're-creates the _Next task' {
            Invoke-Main
            Should -Invoke Register-NextTask -Times 1 -Exactly
        }
    }

    Context 'timestamp is in the future (clock skew)' {
        BeforeEach { Save-TriggerTime (Get-Date).AddHours(2) }
        It 'skips without triggering' {
            Invoke-Main
            Should -Invoke Invoke-ClaudeSession -Times 0 -Exactly
        }
        It 'writes a WARN log entry' {
            Invoke-Main
            (Get-Content $Script:LogFile -Raw) | Should -Match 'WARN'
        }
    }

    Context 'claude invocation fails' {
        BeforeEach {
            Mock Invoke-ClaudeSession { return $false }
        }
        It 'does NOT save a new timestamp' {
            if (Test-Path $Script:TimestampFile) { Remove-Item $Script:TimestampFile -Force }
            Invoke-Main
            Test-Path $Script:TimestampFile | Should -Be $false
        }
        It 'does NOT schedule the next task' {
            Invoke-Main
            Should -Invoke Register-NextTask -Times 0 -Exactly
        }
    }
}

# ---------------------------------------------------------------------------
# Invoke-ClaudeSession — PATH guard
# ---------------------------------------------------------------------------
Describe 'Invoke-ClaudeSession' {
    Context 'claude binary not on PATH' {
        BeforeEach {
            Mock Get-Command { $null } -ParameterFilter { $Name -eq 'claude' }
        }
        It 'returns false' {
            Invoke-ClaudeSession | Should -Be $false
        }
        It 'logs an ERROR entry' {
            Invoke-ClaudeSession | Out-Null
            (Get-Content $Script:LogFile -Raw) | Should -Match 'ERROR'
        }
    }

    Context 'claude is on PATH and exits 0' {
        BeforeEach {
            Mock Get-Command { [pscustomobject]@{ Name = 'claude'; Source = 'C:\fake\claude.cmd' } } `
                -ParameterFilter { $Name -eq 'claude' }
            Mock Invoke-ClaudeCommand { 'Hello! How can I help?'; $global:LASTEXITCODE = 0 }
        }
        It 'returns true' {
            Invoke-ClaudeSession | Should -Be $true
        }
    }

    Context 'claude is on PATH but exits non-zero' {
        BeforeEach {
            Mock Get-Command { [pscustomobject]@{ Name = 'claude' } } `
                -ParameterFilter { $Name -eq 'claude' }
            Mock Invoke-ClaudeCommand { 'error output'; $global:LASTEXITCODE = 1 }
        }
        It 'still returns true (invocation succeeded, non-zero is a warning)' {
            Invoke-ClaudeSession | Should -Be $true
        }
        It 'logs a WARN entry' {
            Invoke-ClaudeSession | Out-Null
            (Get-Content $Script:LogFile -Raw) | Should -Match 'WARN'
        }
    }
}

# ---------------------------------------------------------------------------
# Register-NextTask — scheduling math
# ---------------------------------------------------------------------------
Describe 'Register-NextTask' {
    BeforeEach {
        Mock Register-ScheduledTask { }
        Mock New-ScheduledTaskAction  { [pscustomobject]@{ Execute = 'powershell.exe' } }
        Mock New-ScheduledTaskTrigger { [pscustomobject]@{ At = $At } }
        Mock New-ScheduledTaskSettingsSet { [pscustomobject]@{} }
        Mock New-ScheduledTaskPrincipal   { [pscustomobject]@{} }
    }

    It 'calls Register-ScheduledTask with the correct task name' {
        Register-NextTask (Get-Date).AddHours(5)
        Should -Invoke Register-ScheduledTask -Times 1 -Exactly `
            -ParameterFilter { $TaskName -eq 'ClaudeAutoTrigger_Next' }
    }

    It 'bumps a past target time to near-immediate' {
        $past = (Get-Date).AddMinutes(-10)
        # Should not throw; should adjust time and call Register-ScheduledTask
        { Register-NextTask $past } | Should -Not -Throw
        Should -Invoke Register-ScheduledTask -Times 1 -Exactly
    }

    It 'logs a WARN when target is in the past' {
        Register-NextTask (Get-Date).AddMinutes(-10)
        (Get-Content $Script:LogFile -Raw) | Should -Match 'WARN'
    }
}
