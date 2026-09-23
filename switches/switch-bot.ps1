<#
    On/off switch for the demo.

    The bot is two Windows services now:

        n8n     the workflow server, listening on port 5678
        ngrok   the tunnel that publishes that port under a permanent hostname

    Both start with Windows and are restarted by Windows if they crash, so there is no watchdog
    script, no republish step and no address to chase. This switch is the friendly front end for
    starting them, stopping them, and seeing what state they are in.

    Usage (usually through the .bat files next to this one):
        bot-on.bat                          start both services and report
        bot-off.bat                         stop both and stop them coming back
        switch-bot.ps1 -Action status       report without changing anything

    Starting and stopping a service needs administrator rights, so the script asks for them
    itself (one Windows prompt). -Action status never does.

    What it deliberately does NOT do: it never reads credentials and never touches the database.
    Starting or stopping the bot cannot delete data (the demo launcher start-demo.bat does clear
    the QA tickets; this script does not).
#>
[CmdletBinding()]
param(
    [ValidateSet('on', 'off', 'status')]
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

function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }
function Head([string]$m) { Write-Host ''; Write-Host $m -ForegroundColor Cyan }

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

function Invoke-Elevated {
    # Re-run this same script with the same action, this time elevated. The elevated window closes
    # on its own when the script finishes.
    $elevArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"",
                  '-Action', $Action, '-Elevated')
    Start-Process powershell -Verb RunAs -ArgumentList $elevArgs | Out-Null
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
    if (Test-Service) { Say '      n8n service            answering on http://127.0.0.1:5678' Green }
    else { Say '      n8n service            not answering' Yellow }
    if (Test-Tunnel) { Say ("      public tunnel          online: {0}" -f $publicUrl) Green }
    else { Say ("      public tunnel          {0} does not answer" -f $publicUrl) Yellow }

    $published = Get-PublishedBackend
    if (-not $published) { Say '      published page         backend.json not found on disk' Yellow }
    elseif ($published -like "*$publicUrl*") { Say '      published page         points at the live tunnel' Green }
    else {
        Say ("      published page         points at {0}" -f ($published -replace '/webhook/.*$', '')) Red
        Say '                             that is not the tunnel above - see docs\operations.md' Yellow
    }

    Say ''
    Say '      the published page itself is hosted by GitHub and always opens;' DarkGray
    Say '      when the service above is down, a visitor sees the offline sentence.' DarkGray
    Say ("      demo page: {0}" -f $demoPage) Cyan
}

# ---------------------------------------------------------------- actions
if ($Action -eq 'status') { Show-Status; exit 0 }

if (-not (Test-Admin) -and -not $Elevated) {
    Write-Host 'Starting and stopping the bot needs administrator rights - asking Windows...' -ForegroundColor Yellow
    Invoke-Elevated
    Write-Host 'The result is in the window that just opened.' -ForegroundColor Gray
    Start-Sleep -Seconds 3
    exit 0
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
