<#
    On/off switch for the demo.

    The bot is two Windows services:

        n8n     the workflow server, listening on port 5678
        ngrok   the tunnel that publishes that port under a permanent hostname

    Both start with Windows and are restarted by Windows if they crash, so there is no watchdog
    script, no republish step and no address to chase. This switch is the front end for starting
    them, stopping them and seeing what state they are in.

    Usage (usually through the .bat files next to this one):
        bot-on.bat                          start both services and report
        bot-off.bat                         stop both and keep them off across a reboot
        bot-status.bat                      report without changing anything

    Permissions, and why the first run is different from the rest:

    Windows lets only administrators start and stop a service. A service's own security descriptor
    decides this (Microsoft: "Service Security and Access Rights"; the default grants interactive
    users query and read rights, but not SERVICE_START or SERVICE_STOP). So this script does not
    fight the UAC prompt, it removes the need for it: the first time it runs elevated it appends one
    access rule to exactly these two services, giving this account the rights the PowerShell service
    cmdlets need (SERVICE_START, SERVICE_STOP, SERVICE_QUERY_STATUS, SERVICE_ENUMERATE_DEPENDENTS,
    and SERVICE_CHANGE_CONFIG, which the startup-type change needs).

    After that one prompt, every later double-click works with no prompt at all, for ever, including
    after a reboot. Microsoft warns that SERVICE_CHANGE_CONFIG lets a caller repoint a service at
    another executable; that is worth knowing, and it is why the rule is scoped to these two demo
    services and this one account, and why -Action revoke puts the original security descriptor back.
    The account in question is an administrator anyway (with Windows' usual filtered token), so the
    rule removes a prompt rather than crossing a trust boundary.

    What this script deliberately does NOT do: it never reads credentials and never touches the
    database. Starting or stopping the bot cannot delete anything.
#>
[CmdletBinding()]
param(
    [ValidateSet('on', 'off', 'status', 'grant', 'revoke')]
    [string]$Action = 'status',
    [switch]$Elevated                                   # set internally when it relaunches itself
)

$ErrorActionPreference = 'Continue'

# --- where things live ----------------------------------------------------------------
if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$n8nService    = 'n8n'
$tunnelService = 'ngrok'
$localUrl      = 'http://127.0.0.1:5678'
$publicUrl     = 'https://flyable-rekindle-disobey.ngrok-free.dev'
$demoPage      = 'https://uhygyuf.github.io/rag-support-bot/'
$backendJson   = Join-Path (Split-Path -Parent $PSScriptRoot) 'site\backend.json'
$logFile       = Join-Path $PSScriptRoot 'last-run.log'
$sddlBackup    = Join-Path $PSScriptRoot 'service-sddl-backup.txt'
$sid           = ([Security.Principal.WindowsIdentity]::GetCurrent()).User.Value

# The one rule appended to each service, in the letter order Windows itself uses:
#   DC SERVICE_CHANGE_CONFIG, LC SERVICE_QUERY_STATUS, SW SERVICE_ENUMERATE_DEPENDENTS,
#   RP SERVICE_START,         WP SERVICE_STOP
$rights        = 'DCLCSWRPWP'
$grantAce      = "(A;;$rights;;;$sid)"

$script:lines = New-Object System.Collections.ArrayList
function Say([string]$m, [string]$c = 'Gray') {
    Write-Host $m -ForegroundColor $c
    [void]$script:lines.Add($m)
}
function Head([string]$m) { Say ''; Say $m 'Cyan' }
function Flush-Log {
    try { Set-Content -LiteralPath $logFile -Value ($script:lines -join [Environment]::NewLine) -Encoding UTF8 } catch { }
}
function Show-Log([int]$tail = 40) {
    if (-not (Test-Path -LiteralPath $logFile)) { return }
    Say ''
    Say '      what the administrator window did:' DarkGray
    Get-Content -LiteralPath $logFile -Tail $tail | ForEach-Object {
        if ($_ -notmatch '^\s*$') { Say "        $_" DarkGray }
    }
}

function Test-HttpCode([string]$url, [int]$timeout = 12) {
    try {
        return [int](Invoke-WebRequest -Uri $url -TimeoutSec $timeout -UseBasicParsing -MaximumRedirection 2).StatusCode
    } catch [System.Net.WebException] {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        return 0
    } catch { return 0 }
}

function Test-Service { return ((Test-HttpCode "$localUrl/healthz") -eq 200) }
function Test-Tunnel  { return ((Test-HttpCode "$publicUrl/healthz" 25) -eq 200) }

function Wait-Service([int]$seconds = 240) {
    # n8n needs a while after a cold start; probing every 5 s tells us the moment it serves.
    for ($i = 1; $i -le [int]($seconds / 5); $i++) {
        Start-Sleep -Seconds 5
        Write-Host '.' -NoNewline
        if (Test-Service) { Write-Host ''; return $true }
    }
    Write-Host ''
    return $false
}

function Get-Svc([string]$name) {
    return (Get-Service -Name $name -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-ServiceSddl([string]$name) {
    # sc.exe can read a service's security descriptor without administrator rights.
    $out = & sc.exe sdshow $name 2>$null
    $sddl = ($out | Where-Object { $_ -match '^D:' } | Select-Object -First 1)
    if ($sddl) { return $sddl.Trim() }
    return ''
}

function Test-RulePresent([string]$name) {
    # Is the rule actually written on the service? This is the same thing Windows will look at, and it
    # deliberately does not consider the current token: an elevated run holds the rights anyway, so
    # asking "am I an administrator?" here once made a failed grant report "needs no permission prompt".
    $sddl = Get-ServiceSddl $name
    if (-not $sddl) { return $false }
    foreach ($ace in [regex]::Matches($sddl, '\(A;;([A-Z]+);;;([^)]+)\)')) {
        if ($ace.Groups[2].Value -ne $sid) { continue }
        $r = $ace.Groups[1].Value
        if ($r -match 'RP' -and $r -match 'WP') { return $true }
    }
    return $false
}

function Test-CanControl([string]$name) {
    # Will this switch need a prompt? Right now, with this token: an administrator never does.
    if (Test-Admin) { return $true }
    return (Test-RulePresent $name)
}

function Read-SddlBackup {
    # One line per service: name <tab> original security descriptor. Plain text on purpose: this
    # machine runs Windows PowerShell 5.1, where ConvertFrom-Json has no -AsHashtable.
    $map = @{}
    if (Test-Path -LiteralPath $sddlBackup) {
        foreach ($line in (Get-Content -LiteralPath $sddlBackup)) {
            $parts = $line -split "`t", 2
            if ($parts.Count -eq 2 -and $parts[0]) { $map[$parts[0]] = $parts[1] }
        }
    }
    return $map
}

function Save-SddlBackup($map) {
    $out = foreach ($k in $map.Keys) { "{0}`t{1}" -f $k, $map[$k] }
    Set-Content -LiteralPath $sddlBackup -Value $out -Encoding UTF8
}

function Add-AceToDacl([string]$sddl, [string]$ace) {
    # A service security descriptor can carry a DACL (D:) and a SACL (S:). Appending to the end of the
    # string puts the rule inside the SACL, and Windows then rejects the whole descriptor with
    # "ConvertStringSecurityDescriptorToSecurityDescriptor FAILED 1804: The specified datatype is
    # invalid" - measured on this machine, six SDDL variants, only the in-DACL form was accepted.
    # So: insert at the end of the DACL section, before any S: section.
    $depth = 0
    $split = -1
    for ($i = 0; $i -lt $sddl.Length - 1; $i++) {
        $c = $sddl[$i]
        if ($c -eq '(') { $depth++ }
        elseif ($c -eq ')') { $depth-- }
        elseif ($depth -eq 0 -and $c -eq 'S' -and $sddl[$i + 1] -eq ':') { $split = $i; break }
    }
    if ($split -gt 0) { return $sddl.Substring(0, $split) + $ace + $sddl.Substring($split) }
    return $sddl + $ace
}

function Grant-Control([string]$name) {
    # Append the one rule to the DACL. Idempotent: a second call finds it and changes nothing.
    if (-not (Get-Svc $name)) { Say ("      service {0} is not installed" -f $name) Yellow; return $false }
    $sddl = Get-ServiceSddl $name
    if (-not $sddl) { Say ("      {0,-6} could not read its security descriptor" -f $name) Red; return $false }
    if ($sddl -like "*$grantAce*") { Say ("      {0,-6} already allows this account to start and stop it" -f $name) DarkGray; return $true }

    $backup = Read-SddlBackup
    if (-not $backup.ContainsKey($name)) { $backup[$name] = $sddl; Save-SddlBackup $backup }

    $new = Add-AceToDacl $sddl $grantAce
    $out = & sc.exe sdset $name $new 2>&1
    if (($out -join ' ') -notmatch 'SUCCESS') {
        Say ("      {0,-6} could not be granted: {1}" -f $name, ($out -join ' ')) Red
        return $false
    }
    $check = Get-ServiceSddl $name
    if ($check -like "*$grantAce*") {
        Say ("      {0,-6} start/stop rights granted to this account (one time only)" -f $name) Green
        return $true
    }
    Say ("      {0,-6} the rule was written but does not read back - check services.msc" -f $name) Yellow
    return $false
}

function Revoke-Control([string]$name) {
    $backup = Read-SddlBackup
    if ($backup.ContainsKey($name)) {
        $target = $backup[$name]
    } else {
        # No saved original (fresh clone, or the file was removed): strip our own rule out of the
        # current descriptor, which leaves exactly what was there before the first grant.
        $now = Get-ServiceSddl $name
        if (-not $now -or $now -notlike "*$grantAce*") {
            Say ("      {0,-6} has no saved original rule and none of ours is present" -f $name) Yellow
            return $false
        }
        $target = $now.Replace($grantAce, '')
        Say ("      {0,-6} no saved original - removing only our own rule" -f $name) DarkGray
    }
    $out = & sc.exe sdset $name $target 2>&1
    if (($out -join ' ') -match 'SUCCESS') {
        Say ("      {0,-6} back to the Windows default" -f $name) Green
        return $true
    }
    Say ("      {0,-6} could not be restored: {1}" -f $name, ($out -join ' ')) Red
    return $false
}

function Invoke-Elevated {
    # Re-run this same script with the same action, elevated, and WAIT for it, so the result can be
    # shown in the window the user actually double-clicked (an elevated window that opens and closes
    # on its own teaches nobody anything).
    $elevArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"",
                  '-Action', $Action, '-Elevated')
    try {
        $p = Start-Process powershell -Verb RunAs -ArgumentList $elevArgs -Wait -PassThru
        return $p.ExitCode
    } catch {
        Say ''
        Say '      the Windows permission prompt was cancelled, so nothing was changed.' Yellow
        Say '      double-click again and choose "Yes" to let the switch run.' DarkGray
        return 1223
    }
}

function Enable-Service([string]$name) {
    if (-not (Get-Svc $name)) { Say ("      service {0} is not installed" -f $name) Red; return }
    Set-Service -Name $name -StartupType Automatic
    if ((Get-Svc $name).Status -ne 'Running') { Start-Service -Name $name }
    Say ("      {0,-6} {1}" -f $name, (Get-Svc $name).Status) Green
}

function Disable-Service([string]$name) {
    if (-not (Get-Svc $name)) { Say ("      service {0} is not installed" -f $name) Yellow; return }
    if ((Get-Svc $name).Status -eq 'Running') { Stop-Service -Name $name -Force }
    # Disabled, not just stopped: otherwise a reboot quietly brings the whole demo back.
    Set-Service -Name $name -StartupType Disabled
    Say ("      {0,-6} {1} (will not start by itself any more)" -f $name, (Get-Svc $name).Status) Green
}

function Get-PublishedBackend {
    if (-not (Test-Path -LiteralPath $backendJson)) { return '' }
    try { return [string]((Get-Content -LiteralPath $backendJson -Raw | ConvertFrom-Json).webhook) } catch { return '' }
}

function Show-Status {
    Head 'STATUS'
    foreach ($n in @($n8nService, $tunnelService)) {
        $svc = Get-Svc $n
        if ($svc) { Say ("      service {0,-6} {1,-9} startup: {2}" -f $n, $svc.Status, $svc.StartType) }
        else { Say ("      service {0,-6} NOT INSTALLED" -f $n) Yellow }
    }
    $free = (Test-RulePresent $n8nService) -and (Test-RulePresent $tunnelService)
    if ($free) { Say '      the switch           needs no permission prompt' Green }
    else { Say '      the switch           asks Windows once, then never again (-Action grant)' Yellow }

    if (Test-Service) { Say '      n8n service          answering on http://127.0.0.1:5678' Green }
    else { Say '      n8n service          not answering' Yellow }
    if (Test-Tunnel) { Say ("      public tunnel        online: {0}" -f $publicUrl) Green }
    else { Say ("      public tunnel        {0} does not answer" -f $publicUrl) Yellow }

    $published = Get-PublishedBackend
    if (-not $published) { Say '      published page       backend.json not found on disk' Yellow }
    elseif ($published -like "*$publicUrl*") { Say '      published page       points at the live tunnel' Green }
    else {
        Say ("      published page       points at {0}" -f ($published -replace '/webhook/.*$', '')) Red
        Say '                           that is not the tunnel above - see docs\operations.md' Yellow
    }

    Say ''
    Say '      the published page itself is hosted by GitHub and always opens;' DarkGray
    Say '      when the service above is down, a visitor sees the offline sentence.' DarkGray
    Say ("      demo page: {0}" -f $demoPage) Cyan
}

# ---------------------------------------------------------------- actions
try {

if ($Action -eq 'status') { Show-Status; exit 0 }

if (-not (Test-Admin) -and -not $Elevated) {
    if (Test-CanControl $n8nService -and (Test-CanControl $tunnelService)) {
        # Nothing to ask for: the rules are already in place, so the work happens right here.
    } else {
        Say ''
        Say '      Windows needs to allow this once: starting and stopping a service is an' Yellow
        Say '      administrator action, and this account has no rule for these two services yet.' Yellow
        Say '      The window that opens will grant it and run the action; you will not be asked again.' DarkGray
        $code = Invoke-Elevated
        Show-Log
        exit $code
    }
}

if ($Action -eq 'grant' -or $Action -eq 'revoke') {
    if (-not (Test-Admin)) {
        Say ''
        Say '      this needs administrator rights - asking Windows...' Yellow
        $code = Invoke-Elevated
        Show-Log
        exit $code
    }
    Head (("Grant start/stop rights to this account ({0})" -f $sid))
    foreach ($n in @($n8nService, $tunnelService)) {
        if ($Action -eq 'grant') { [void](Grant-Control $n) } else { [void](Revoke-Control $n) }
    }
    Show-Status
    exit 0
}

# `on` and `off`, with the rights granted first when this window is the elevated one.
if ($Elevated -or (Test-Admin)) {
    Head 'Access to the two services'
    foreach ($n in @($n8nService, $tunnelService)) { [void](Grant-Control $n) }
}

if ($Action -eq 'on') {
    Head '[1/3]  services'
    Enable-Service $n8nService          # the server first: a tunnel with nothing behind it is useless
    Enable-Service $tunnelService

    Head '[2/3]  waiting for n8n'
    Write-Host '      (a cold start takes up to a minute and a half)' -ForegroundColor DarkGray
    Write-Host '      waiting' -NoNewline -ForegroundColor DarkGray
    $serviceUp = Wait-Service 240

    Head '[3/3]  the way a visitor reaches it'
    $tunnelUp = $false
    if ($serviceUp) {
        Write-Host '      waiting' -NoNewline -ForegroundColor DarkGray
        for ($i = 1; $i -le 12; $i++) { if (Test-Tunnel) { $tunnelUp = $true; break }; Start-Sleep -Seconds 5; Write-Host '.' -NoNewline }
        Write-Host ''
    }

    Show-Status
    Say ''
    if ($serviceUp -and $tunnelUp) {
        Say '      the bot now answers, and the published page points at it' Green
        Say ("      ask it something: {0}" -f $demoPage) Cyan
    } else {
        Say '      NOT fully up. The next steps:' Yellow
        if (-not $serviceUp) {
            Say '        1. read D:\Tools\n8n\logs\n8n-service.*.log (the service writes its output there)' DarkGray
            Say '        2. services.msc: restart "n8n support bot"' DarkGray
        } else {
            Say '        1. the service answers locally, so n8n is fine; the tunnel is the slow part' DarkGray
            Say '        2. services.msc: restart "ngrok" (config: D:\Tools\ngrok\ngrok.yml)' DarkGray
        }
        Say '        3. then run bot-status.bat again' DarkGray
    }
    exit 0
}

if ($Action -eq 'off') {
    Head '[1/2]  stopping the services'
    Disable-Service $tunnelService      # close the door before stopping the server
    Disable-Service $n8nService
    Start-Sleep -Seconds 3

    Head '[2/2]  result'
    if (Test-Service) { Say '      WARNING: the service still answers - check services.msc' Red }
    else { Say '      the bot is off: nothing answers on port 5678' Green }
    Say ''
    Say '      the published page still opens (GitHub hosts it); a visitor now sees' DarkGray
    Say '      "Sorry, our assistant is offline right now".' DarkGray
    Say '      it stays off across a reboot, because both services are set to Disabled.' DarkGray
    Say '      to start again: switches\bot-on.bat' Cyan
    exit 0
}

} finally {
    Flush-Log
}
