<#
.SYNOPSIS
  Create (or remove) the Windows scheduled task that runs the monthly refresh.

.DESCRIPTION
  Registers "INR fair value - monthly refresh" for the current user. It runs
  scripts\monthly_refresh.cmd on the given day of each month, and catches up at the next
  logon if the PC was off. Each run writes a log to outputs\refresh_logs and commits
  data/raw and reports/ to the local git repository (no push).

  The task runs only while you are logged on and needs no password or admin rights.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\schedule_monthly_refresh.ps1
  powershell -ExecutionPolicy Bypass -File scripts\schedule_monthly_refresh.ps1 -Day 16 -Time 10:30
  powershell -ExecutionPolicy Bypass -File scripts\schedule_monthly_refresh.ps1 -Remove
#>
param(
    [ValidateRange(1, 31)][int]$Day = 15,
    [string]$Time = "09:00",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$name = "INR fair value - monthly refresh"

if ($Remove) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "Removed scheduled task '$name'."
    } else {
        Write-Host "No scheduled task named '$name'."
    }
    return
}

$root = Split-Path -Parent $PSScriptRoot
$cmd = Join-Path $PSScriptRoot "monthly_refresh.cmd"
$python = (Get-Command python -ErrorAction Stop).Source
& $python -c "import inrfv" 2>$null
if ($LASTEXITCODE -ne 0) { throw "inrfv is not importable with $python; run 'pip install -e .' in $root first." }

# Task Scheduler XML: a monthly calendar trigger, catch-up after missed runs, and the
# interpreter found now pinned, so the task does not depend on PATH at run time.
$esc = { param($s) [System.Security.SecurityElement]::Escape($s) }
$user = "$env:USERDOMAIN\$env:USERNAME"
$start = (Get-Date "$((Get-Date).ToString('yyyy-MM-dd')) $Time").ToString("s")
$months = "<January/><February/><March/><April/><May/><June/><July/><August/><September/><October/><November/><December/>"
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>$(& $esc "Runs python -m inrfv.refresh --commit in $root (logs in outputs\refresh_logs). No push.")</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>$start</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByMonth>
        <DaysOfMonth><Day>$Day</Day></DaysOfMonth>
        <Months>$months</Months>
      </ScheduleByMonth>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$(& $esc $user)</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>cmd.exe</Command>
      <Arguments>$(& $esc "/c set INRFV_PYTHON=$python&& `"$cmd`"")</Arguments>
      <WorkingDirectory>$(& $esc $root)</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@
Register-ScheduledTask -TaskName $name -Xml $xml -Force | Out-Null

$next = (Get-ScheduledTaskInfo -TaskName $name).NextRunTime
Write-Host "Scheduled '$name': day $Day of each month at $Time. Next run: $next"
Write-Host "Logs: $root\outputs\refresh_logs   Remove with: -Remove   Run now: Start-ScheduledTask -TaskName '$name'"
