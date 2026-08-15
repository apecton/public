# claude_auto_trigger

Windows utility that fires a Claude Code session at the precise moment the usage window resets (default 5‑hour window), with optional alignment to a preferred startup hour (default 7 AM) to maximise available quota without guessing.

## How it works

Claude Code's usage limit is a **rolling window** (default 5 hours) that starts with your first message. Once that window expires, sending any message opens a fresh window.

This utility tracks when the last session was started and schedules the next trigger for `last_trigger + WindowHours`, then, if that time falls within the interval before the configured `StartupHour`, it rounds the trigger up to the next occurrence of the startup hour.

It runs the check on three signals, so the window is never left to drift:

- **While the machine is awake** — a one-shot `_Next` task fires exactly at `last_trigger + WindowHours` (adjusted for startup hour if needed).
- **At logon** (cold boot / restart) — the check runs as soon as you log in.
- **On resume from sleep or hibernate** — an event-based trigger (Power-Troubleshooter event 1) runs the check the moment the machine wakes.

The check itself is idempotent: it triggers a session only if the window has elapsed (after adjustment), otherwise it just re-confirms the schedule and exits. So firing it on every logon/wake is cheap and safe.

```
Boot, log in at 7:15
  └─ logon task fires ~7:16 → claude -p "hello" → schedules _Next for 12:16

Machine running at 12:16
  └─ _Next fires → claude -p "hello" → schedules _Next for 17:16

Machine asleep at 17:16, wakes at 18:00
  └─ wake trigger fires → window elapsed → claude -p "hello" → schedules _Next for 23:00
```

No polling. No arbitrary hourly ticks.

## Requirements

- Windows 10 / 11
- PowerShell 5.1+ (built in)
- [Claude Code](https://claude.ai/code) installed and `claude` on your PATH
- Pester 5+ (for tests only): `Install-Module Pester -Force -Scope CurrentUser`

## Configuration

The script defines two variables at the top of `claude_auto_trigger.ps1`:

- `$Script:WindowHours` – length of the usage window in hours (default **5**).
- `$Script:StartupHour` – preferred start‑of‑day hour in 24‑hour format (default **7** for 7 AM).

When the next calculated trigger time falls within the interval before the startup hour, the script rounds the trigger up to the next occurrence of the startup hour. This aligns sessions with your working day while still respecting the window length.

Example (defaults): if the last session ended at 2 AM, the raw next trigger would be at 7 AM (2 + 5). Since 7 AM is the startup hour, it stays at 7 AM. If the last session ended at 10 PM, raw next is 3 AM, which lies within the 2‑hour‑to‑7 AM window, so the script pushes the trigger to 7 AM.

## Install

Double-click **`setup_task.cmd`** (or run it from any prompt). It requests UAC elevation automatically and bypasses the PowerShell execution policy — no manual flags needed.

```
setup_task.cmd
```

`setup_task.ps1` registers the logon + wake tasks and immediately runs an initial check. From that point on, the script manages its own schedule — no further setup needed.

## Files

| File | Purpose |
|---|---|
| `claude_auto_trigger.ps1` | Main script — checks elapsed time, triggers session, self-schedules next run |
| `setup_task.ps1` | One-time admin setup — registers the logon + wake Task Scheduler entry |
| `setup_task.cmd` | Launcher for `setup_task.ps1` — handles UAC elevation + execution-policy bypass |
| `remove_task.ps1` | Uninstall — removes all tasks and optionally deletes state files |
| `remove_task.cmd` | Launcher for `remove_task.ps1` — handles UAC elevation + execution-policy bypass |
| `tests/claude_auto_trigger.Tests.ps1` | Pester v5 unit tests |

## State files (in the project folder)

| File | Contents |
|---|---|
| `.claude_session_trigger` | ISO-8601 timestamp of last trigger |
| `.claude_session_trigger.log` | Rolling log (capped at 1000 lines) |

Both files are git-ignored.

## Task Scheduler entries

| Task | Trigger | Notes |
|---|---|---|
| `ClaudeAutoTrigger_Startup` | At user logon (60s delay) **and** on resume from sleep/hibernate (Power-Troubleshooter event 1, 30s delay) | Created by `setup_task.ps1`, never deleted |
| `ClaudeAutoTrigger_Next` | One-shot at `last_trigger + WindowHours` (adjusted for startup hour) | Created/overwritten by the script after each trigger |

## Manual test

```powershell
# Run immediately (skips if window hasn't elapsed yet)
powershell -ExecutionPolicy Bypass -File ".\claude_auto_trigger.ps1"

# Check the log
Get-Content "$PSScriptRoot\.claude_session_trigger.log" -Tail 20
```

To force a trigger on the next run, delete the timestamp file:

```powershell
Remove-Item "$PSScriptRoot\.claude_session_trigger" -Force
```

## Run tests

```powershell
# From the claude_auto_trigger directory
Invoke-Pester .\tests\claude_auto_trigger.Tests.ps1 -Output Detailed
```

## Uninstall

Double-click **`remove_task.cmd`** (or run it from any prompt). It will ask whether to delete the state files.

```
remove_task.cmd
```

## Troubleshooting

**`claude` not found on PATH**
Claude Code must be on your system PATH. Open a new PowerShell window and run `claude --version` to verify.

**Task never fires**
Check Task Scheduler (`taskschd.msc`) under `Task Scheduler Library` for `ClaudeAutoTrigger_Startup` and `ClaudeAutoTrigger_Next`. The Last Run Result column shows any errors.

**`_Next` task missing after a trigger**
The startup task re-creates it automatically at the next logon. You can also run the script manually to force re-creation.

**Doesn't fire on logon or after waking**
Re-run `setup_task.cmd` to (re)register the triggers, then confirm both are present:

```powershell
(Get-ScheduledTask -TaskName ClaudeAutoTrigger_Startup).Triggers |
    ForEach-Object { $_.CimClass.CimClassName }
# Expect: MSFT_TaskLogonTrigger  and  MSFT_TaskEventTrigger
```

If you see only `MSFT_TaskBootTrigger`, you're on an older registration — re-run the setup. The wake trigger relies on Power-Troubleshooter **event ID 1** in the System log; confirm your machine logs it after a real sleep/resume cycle:

```powershell
Get-WinEvent -FilterHashtable @{ LogName='System'; ProviderName='Microsoft-Windows-Power-Troubleshooter'; Id=1 } -MaxEvents 3
```