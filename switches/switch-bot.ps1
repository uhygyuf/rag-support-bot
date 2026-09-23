<#
    One switch to start the support bot, one to really stop it.

    A running n8n is not the whole story: the scheduled task "n8n watchdog" restarts the
    service within ~5 minutes whenever it is missing, so "stop n8n" alone is not "stop the
    bot" - it comes back. This script handles the task and the service together, which is
    the only combination that actually stays off.

    Usage (usually through the two .bat files next to this one):
        bot-on.bat        start everything and leave the watchdog enabled
        bot-off.bat       disable the watchdog, then stop n8n and the tunnel
        switch-bot.ps1 -Action status      report without changing anything

    What it deliberately does NOT do: it never reads credentials and never touches the
    database. Starting or stopping the bot cannot delete data (the demo launcher
    start-demo.bat does clear the QA tickets; this script does not).
#>
[CmdletBinding()]
param(
    [ValidateSet('on', 'off', 'status')]
    [string]$Action = 'status'
)

$ErrorActionPreference = 'Continue'

# --- where things live (edit $n8nDir if your install differs) -------------------------
if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$n8nDir        = 'D:\Tools\n8n'
$watchdogScript = Join-Path $n8nDir 'watchdog-n8n.ps1'
$watchdogConfig = Join-Path $n8nDir 'watchdog-config.json'
$startPublic   = Join-Path $n8nDir 'start-public.bat'
$urlFile       = Join-Path $n8nDir 'public-url.txt'
$backendJson   = Join-Path (Split-Path -Parent $PSScriptRoot) 'site\backend.json'
$healthUrl     = 'http://127.0.0.1:5678/healthz'
$editorUrl     = 'http://127.0.0.1:5678/home'
$taskNames     = @('n8n watchdog', 'n8n zombie cleanup')

function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }
function Head([string]$m) { Write-Host ''; Write-Host $m -ForegroundColor Cyan }

function Test-Service {
    try {
        $r = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 5 -UseBasicParsing
        return ([int]$r.StatusCode -eq 200)
    } catch { return $false }
}

function Get-TunnelUrl {
    if (Test-Path -LiteralPath $urlFile) { return (Get-Content -LiteralPath $urlFile -Raw).Trim() }
    return ''
}

function Get-TunnelCode([string]$url) {
    if (-not $url) { return '000' }
    $code = & curl.exe -s -o NUL -m 25 -w '%{http_code}' ($url.TrimEnd('/') + '/healthz')
    if (-not $code) { return '000' }
    return ([string]$code).Trim()
}

# A tunnel is reachable when the Cloudflare edge answers at all. A 502/530 means the tunnel is
# fine and the service behind it is booting or down - that is a different problem from a tunnel
# that has gone away (000), and replacing the tunnel would not fix it.
function Test-Tunnel([string]$url) {
    return ((Get-TunnelCode $url) -notin @('000', ''))
}

function Test-TunnelHealthy([string]$url) {
    return ((Get-TunnelCode $url) -eq '200')
}

function Get-PublishedBackend {
    if (-not (Test-Path -LiteralPath $backendJson)) { return '' }
    try {
        $j = Get-Content -LiteralPath $backendJson -Raw | ConvertFrom-Json
        return [string]$j.webhook
    } catch { return '' }
}

function Get-TaskState([string]$name) {
    $out = & schtasks.exe /query /tn $name /fo LIST 2>$null
    if (-not $out) { return 'missing' }
    $line = ($out | Select-String -Pattern '^\s*(Status|状态)\s*:' | Select-Object -First 1)
    if (-not $line) { return 'unknown' }
    return (($line.Line -split ':', 2)[1]).Trim()
}

function Set-Tasks([bool]$enable) {
    $verb = if ($enable) { '/enable' } else { '/disable' }
    foreach ($t in $taskNames) {
        $state = Get-TaskState $t
        if ($state -eq 'missing') {
            Say ("      task not found: {0} (not part of this install)" -f $t) Yellow
            continue
        }
        & schtasks.exe /change /tn $t $verb | Out-Null
        $now = Get-TaskState $t
        if ($enable -and $now -eq 'Ready') { Say ("      {0}: enabled (Ready)" -f $t) Green }
        elseif (-not $enable -and $now -eq 'Disabled') { Say ("      {0}: disabled" -f $t) Green }
        else { Say ("      {0}: wanted {1}, now reports {2}" -f $t, $(if ($enable) { 'Ready' } else { 'Disabled' }), $now) Red }
    }
}

function Stop-ServiceAndTunnel {
    $killedService = $false
    $conns = Get-NetTCPConnection -LocalPort 5678 -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
        if ($proc) { Say ("      stopping {0} (pid {1})" -f $proc.ProcessName, $proc.Id) DarkGray; Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue; $killedService = $true }
    }
    if (-not $killedService) { Say '      nothing was listening on port 5678' DarkGray }

    # the n8n launcher window and its task runner outlive the port owner; take them too
    $extra = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        ($_.Name -eq 'node.exe' -and $_.CommandLine -like "*$n8nDir*") -or
        ($_.Name -eq 'cmd.exe'  -and $_.CommandLine -like '*n8n-serve.bat*')
    }
    foreach ($p in $extra) {
        Say ("      stopping leftover {0} (pid {1})" -f $p.Name, $p.ProcessId) DarkGray
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }

    $tunnel = Get-Process -Name cloudflared -ErrorAction SilentlyContinue
    if ($tunnel) {
        Say ("      stopping the tunnel (cloudflared, pid {0})" -f ($tunnel.Id -join ',')) DarkGray
        Stop-Process -Name cloudflared -Force -ErrorAction SilentlyContinue
    } else {
        Say '      no tunnel process was running' DarkGray
    }
}

function Wait-Service([int]$seconds = 240) {
    for ($i = 1; $i -le [int]($seconds / 5); $i++) {
        Start-Sleep -Seconds 5
        Write-Host '.' -NoNewline
        if (Test-Service) { Write-Host ''; return $true }
    }
    Write-Host ''
    return $false
}

function Get-TunnelConfig {
    if (-not (Test-Path -LiteralPath $watchdogConfig)) { return $null }
    try { return (Get-Content -LiteralPath $watchdogConfig -Raw | ConvertFrom-Json).tunnel } catch { return $null }
}

function Get-TunnelUrlFromLog([string]$logPath, [string]$pattern) {
    if (-not (Test-Path -LiteralPath $logPath)) { return '' }
    $m = Select-String -LiteralPath $logPath -Pattern $pattern -ErrorAction SilentlyContinue | Select-Object -Last 1
    if ($m) { return $m.Matches.Value }
    return ''
}

function Start-FreshTunnel([string]$logPath, $tunnelCfg) {
    Get-Process -Name 'cloudflared' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    if (Test-Path -LiteralPath $logPath) { Remove-Item -LiteralPath $logPath -Force -ErrorAction SilentlyContinue }
    $args = @($tunnelCfg.args | ForEach-Object { ($_ -replace '\{port\}', '5678') -replace '\{logfile\}', $logPath })
    $exe  = ([string]$tunnelCfg.exe) -replace '/', '\'
    Say ("      starting a fresh tunnel: {0}" -f $exe) DarkGray
    Start-Process -FilePath $exe -ArgumentList $args -WindowStyle Hidden | Out-Null
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 3
        $u = Get-TunnelUrlFromLog $logPath ([string]$tunnelCfg.urlPattern)
        if ($u) {
            Set-Content -LiteralPath $urlFile -Value $u -Encoding ASCII -NoNewline
            return $u
        }
    }
    return ''
}

function Wait-Tunnel([string]$url, [int]$seconds = 150, [string]$logPath) {
    for ($i = 1; $i -le [int]($seconds / 5); $i++) {
        Start-Sleep -Seconds 5
        Write-Host '.' -NoNewline
        if (Test-TunnelHealthy $url) { Write-Host ''; return $true }
        # a slow tunnel can publish its address late; keep following the log
        if ($logPath) {
            $fresh = Get-TunnelUrlFromLog $logPath 'https://[a-z0-9-]+\.trycloudflare\.com'
            if ($fresh -and $fresh -ne $url) { Set-Content -LiteralPath $urlFile -Value $fresh -Encoding ASCII -NoNewline; return $false }
        }
    }
    Write-Host ''
    return $false
}

function Start-ServiceWithUrl([string]$url, [string]$launcher) {
    Get-NetTCPConnection -LocalPort 5678 -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    $extra = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        ($_.Name -eq 'node.exe' -and $_.CommandLine -like "*$n8nDir*")
    }
    foreach ($p in $extra) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 4
    # the service reads its public address from this variable at boot; without it the
    # Telegram/Gmail webhooks register an address that no longer exists
    $env:WEBHOOK_URL = $url
    Start-Process -FilePath $launcher -WindowStyle Minimized | Out-Null
    Write-Host '      waiting for the service' -NoNewline -ForegroundColor DarkGray
    return (Wait-Service 240)
}

function Publish-Backend([string]$url) {
    $script = Join-Path (Split-Path -Parent $PSScriptRoot) 'demo\publish-backend-url.ps1'
    if (-not (Test-Path -LiteralPath $script)) {
        Say ("      {0} is missing - the published page keeps its old address" -f $script) Yellow
        return $false
    }
    Say '      publishing the current address to the hosted page' DarkGray
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script | Out-Host
    $published = Get-PublishedBackend
    return ($published -and $url -and $published -like "*$($url.TrimEnd('/'))*")
}

function Show-Status {
    Head 'STATUS'
    foreach ($t in $taskNames) {
        $state = Get-TaskState $t
        $colour = if ($state -eq 'Ready') { 'Green' } elseif ($state -eq 'Disabled') { 'Yellow' } else { 'Red' }
        Say ("      scheduled task {0,-22} {1}" -f $t, $state) $colour
    }
    if (Test-Service) { Say '      n8n service            answering on http://127.0.0.1:5678' Green }
    else { Say '      n8n service            not answering' Yellow }

    $url = Get-TunnelUrl
    if (-not $url) { Say '      public tunnel          no address recorded' Yellow }
    elseif (Test-Tunnel $url) { Say ("      public tunnel          online: {0}" -f $url) Green }
    else { Say ("      public tunnel          {0} does not answer" -f $url) Yellow }

    $published = Get-PublishedBackend
    if (-not $published) { Say '      published page         backend.json not found on disk' Yellow }
    elseif ($url -and $published -like "*$($url.TrimEnd('/'))*") { Say '      published page         points at the live tunnel' Green }
    else {
        Say ("      published page         STALE - it points at {0}" -f $published) Red
        Say '                             run bot-on.bat: it republishes the current address' Yellow
    }

    Say ''
    Say '      the published page itself is hosted by GitHub and always opens;' DarkGray
    Say '      when the service above is down, a visitor sees the offline sentence.' DarkGray
}

# ---------------------------------------------------------------- actions
switch ($Action) {

    'on' {
        $cfg = $null
        if (Test-Path -LiteralPath $watchdogConfig) {
            try { $cfg = Get-Content -LiteralPath $watchdogConfig -Raw | ConvertFrom-Json } catch { $cfg = $null }
        }
        $tunnelCfg = if ($cfg) { $cfg.tunnel } else { $null }
        $tunnelLog = if ($tunnelCfg -and $tunnelCfg.logFile) { ([string]$tunnelCfg.logFile) -replace '/', '\' } else { Join-Path $n8nDir 'cloudflared.log' }
        $launcher  = if ($cfg -and $cfg.service.launcher) { ([string]$cfg.service.launcher) -replace '/', '\' } else { Join-Path $n8nDir 'n8n-serve.bat' }

        Head '[1/4]  leave the watchdog enabled'
        Set-Tasks $true

        Head '[2/4]  service'
        if (Test-Service) {
            Say '      n8n is already running' Green
        } else {
            Say '      n8n is not running - starting it' Yellow
            if (-not (Test-Path -LiteralPath $watchdogScript)) {
                Say ("      ERROR: {0} not found; start n8n manually and re-run" -f $watchdogScript) Red
                exit 1
            }
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $watchdogScript -Config $watchdogConfig | Out-Null
            Write-Host '      waiting for the service' -NoNewline -ForegroundColor DarkGray
            if (-not (Wait-Service 240)) {
                Say '      n8n did not answer within 4 minutes - open the "n8n public" window and read it' Red
                Show-Status
                exit 1
            }
        }

        Head '[3/4]  public tunnel (the published page needs a reachable one)'
        $url = Get-TunnelUrl
        $tunnelOk = $false
        if ($url -and (Test-TunnelHealthy $url)) {
            Say ("      online: {0}" -f $url) Green
            $tunnelOk = $true
        } else {
            if ($url) {
                Say ("      {0} answers with {1} - giving it 30 seconds" -f $url, (Get-TunnelCode $url)) Yellow
                Write-Host '      waiting for the service through the tunnel' -NoNewline -ForegroundColor DarkGray
                $tunnelOk = [bool](Wait-Tunnel $url 30 $null)
            }
            if (-not $tunnelOk -and $url -and (Test-Tunnel $url)) {
                # the edge answers, so the tunnel exists; a 502/530 here is the service booting
                # behind it, and replacing the tunnel would only add a new hostname to chase
                Say '      the tunnel itself is up - the service behind it is the slow part' Yellow
                Write-Host '      waiting for the service' -NoNewline -ForegroundColor DarkGray
                $tunnelOk = [bool](Wait-Tunnel $url 150 $null)
            }
            if (-not $tunnelOk -and -not (Test-Tunnel $url)) {
                if (-not $tunnelCfg) {
                    Say '      no tunnel settings in watchdog-config.json - cannot restart it here' Red
                } else {
                    Say '      replacing the tunnel (the edge does not answer for this address at all)' Yellow
                    $url = Start-FreshTunnel $tunnelLog $tunnelCfg
                    if (-not $url) {
                        Say '      no new address appeared in the tunnel log within 90 seconds' Red
                    } else {
                        Say ("      new address: {0} - restarting n8n so it knows it" -f $url) Yellow
                        if (-not (Start-ServiceWithUrl $url $launcher)) {
                            Say '      n8n did not answer after the restart' Red
                            Show-Status
                            exit 1
                        }
                        Say '      n8n is up again' Green
                        Write-Host '      waiting for the tunnel to answer' -NoNewline -ForegroundColor DarkGray
                        $tunnelOk = [bool](Wait-Tunnel $url 150 $tunnelLog)
                        $url = Get-TunnelUrl
                    }
                }
            }
        }
        if ($tunnelOk) { Say '      the tunnel answers' Green } else { Say '      the tunnel still does not answer - the published page will stay offline' Red }

        Head '[4/4]  published page'
        $published = Get-PublishedBackend
        $publishedOk = ($url -and $published -and ($published -like "*$($url.TrimEnd('/'))*"))
        if ($publishedOk) {
            Say '      already points at the live tunnel' Green
        } elseif ($tunnelOk) {
            $publishedOk = Publish-Backend $url
            if ($publishedOk) { Say '      published (Pages redeploys in ~1 minute)' Green }
            else { Say '      publishing failed - run demo\publish-backend-url.ps1 by hand' Yellow }
        } else {
            Say '      skipped: there is no reachable address to publish' Yellow
        }

        Show-Status
        Say ''
        if ($tunnelOk -and $publishedOk) {
            Say '      the bot now answers, and the published page points at it' Green
            Say '      demo page: https://uhygyuf.github.io/rag-support-bot/' Cyan
        } else {
            Say '      NOT fully up. The next steps:' Yellow
            Say '        1. run this switch again in a minute (the tunnel sometimes needs a second try)' DarkGray
            Say '        2. if it still fails: D:\Tools\n8n\start-public.bat, read its window, then rerun' DarkGray
        }
    }

    'off' {
        Head '[1/3]  disable the watchdog first'
        Say '      (otherwise the task restarts n8n within ~5 minutes)' DarkGray
        Set-Tasks $false

        Head '[2/3]  stop the service and the tunnel'
        Stop-ServiceAndTunnel
        Start-Sleep -Seconds 3

        Head '[3/3]  result'
        if (Test-Service) { Say '      WARNING: the service still answers - check the n8n window' Red }
        else { Say '      n8n is stopped' Green }
        if (Get-Process -Name cloudflared -ErrorAction SilentlyContinue) { Say '      WARNING: a tunnel process is still running' Red }
        else { Say '      the tunnel is stopped' Green }
        Say ''
        Say '      the published page still opens (GitHub hosts it); a visitor now sees' DarkGray
        Say '      "Sorry, our assistant is offline right now".' DarkGray
        Say '      to start again: switches\bot-on.bat' Cyan
    }

    'status' {
        Show-Status
    }
}
