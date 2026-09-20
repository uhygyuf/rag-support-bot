<#
    One-command demo launcher for the RAG support bot.

    Does everything the demo needs, in order:
      1. starts n8n in public mode (tunnel + WEBHOOK_URL) if it is not running, and waits
         until the editor really answers
      2. reports the tunnel / Telegram status (the Telegram shot needs the tunnel)
      3. clears the QA tickets from Supabase so the ticket table looks clean on camera
         (skip with -KeepTickets; the knowledge base is never touched)
      4. opens the demo page
      5. prints the shot list and the exact things to click

    Usage:
        demo-start.bat                 normal demo run
        demo-start.bat -KeepTickets    keep whatever is in the tickets table
        demo-start.bat -NoBrowser      do not open the browser

    Secrets (Supabase URL + service key) live OUTSIDE this repo, in
    D:\Tools\n8n\demo-secrets.json:
        { "supabaseUrl": "https://xxxx.supabase.co", "serviceKey": "sb_secret_..." }

    NOTE on the HTTP client: PowerShell 5.1's Invoke-RestMethod/Invoke-WebRequest get a
    401 for the new-style "sb_secret_..." Supabase keys (reproduced: same key and URL
    return 200 through curl.exe). So the Supabase calls here shell out to curl.exe and
    feed it the key through its config on stdin, which also keeps the key out of the
    process list.
#>
[CmdletBinding()]
param(
    [switch]$KeepTickets,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'SilentlyContinue'

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$page        = Join-Path $projectRoot 'site\index.html'
$startPublic = 'D:\Tools\n8n\start-public.bat'
$stopPublic  = 'D:\Tools\n8n\stop-public.bat'
$urlFile     = 'D:\Tools\n8n\public-url.txt'
$secretsPath = 'D:\Tools\n8n\demo-secrets.json'

function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }
function Head([string]$m) { Write-Host ''; Write-Host $m -ForegroundColor Cyan }
function Test-N8n {
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5678/home' -TimeoutSec 5 -UseBasicParsing
        return ([int]$r.StatusCode -eq 200)
    } catch { return $false }
}
function Get-PublicUrl {
    if (Test-Path -LiteralPath $urlFile) { return (Get-Content -LiteralPath $urlFile -Raw).Trim() }
    return ''
}
function Test-PublicOnline([string]$url) {
    if (-not $url) { return $false }
    $code = & curl.exe -s -o NUL -m 25 -w '%{http_code}' ($url.TrimEnd('/') + '/home')
    return ("$code" -eq '200')
}

# Supabase over curl.exe (see the note above). The key travels on stdin, never in argv.
function Invoke-Supabase {
    param([string]$Method, [string]$Path, [string]$Key, [string]$Base)
    $curlCfg = @(
        ('url = "{0}{1}"' -f $Base, $Path),
        ('request = {0}' -f $Method),
        ('header = "apikey: {0}"' -f $Key),
        ('header = "Authorization: Bearer {0}"' -f $Key),
        'silent',
        'write-out = "\n%{http_code}"'
    ) -join "`n"
    # curl needs its config in a file (older builds refuse -K -); the temp file is removed
    # right away so the key never sits in argv or on disk.
    $tmpCfg = Join-Path $env:TEMP ('demo-curl-' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.cfg')
    $raw = @()
    try {
        Set-Content -LiteralPath $tmpCfg -Value $curlCfg -Encoding ASCII
        $raw = @(& curl.exe -K $tmpCfg)
    } finally {
        Remove-Item -LiteralPath $tmpCfg -Force -ErrorAction SilentlyContinue
    }
    if ($raw.Count -eq 0) { return @{ status = 0; body = '' } }
    $text = ($raw -join "`n").Trim()
    if (-not $text) { return @{ status = 0; body = '' } }
    # curl appends "\n<status>" via write-out; with an empty body (204, or "[]" reads)
    # there may be no body at all, so handle both shapes.
    $split = $text.LastIndexOf("`n")
    $statusText = $text
    $bodyText = ''
    if ($split -ge 0) { $statusText = $text.Substring($split + 1).Trim(); $bodyText = $text.Substring(0, $split) }
    $status = 0
    try { $status = [int]$statusText } catch { $status = 0; $bodyText = $text }
    return @{ status = $status; body = $bodyText }
}
function ConvertTo-Rows([string]$body) {
    # a JSON array of one row stays an array in some PowerShell versions; flatten it
    $rows = @()
    if (-not $body -or -not $body.Trim()) { return $rows }
    try {
        foreach ($r in @($body | ConvertFrom-Json)) { $rows += $r }
    } catch { }
    return $rows
}

# ---------------------------------------------------------------- 1. the service
Head '[1/4]  n8n service'
if (Test-N8n) {
    Say '      already running on http://127.0.0.1:5678' Green
} else {
    Say '      not running - starting n8n in public mode (tunnel + WEBHOOK_URL)' Yellow
    if (-not (Test-Path -LiteralPath $startPublic)) {
        Say "      ERROR: $startPublic not found - start n8n manually and rerun." Red
        Read-Host 'press enter to exit' | Out-Null
        exit 1
    }
    Start-Process -FilePath $startPublic -WindowStyle Minimized | Out-Null
    $ready = $false
    for ($i = 1; $i -le 36; $i++) {
        Start-Sleep -Seconds 5
        Write-Host '.' -NoNewline
        if (Test-N8n) { $ready = $true; break }
    }
    Write-Host ''
    if ($ready) { Say '      n8n is up' Green } else { Say '      n8n did not answer within 3 minutes - check the n8n window' Red }
}

# ---------------------------------------------------------------- 2. the tunnel
Head '[2/4]  public tunnel (needed for the Telegram shot)'
$url = Get-PublicUrl
if ($url -and (Test-PublicOnline $url)) {
    Say "      online: $url" Green
} else {
    Say '      tunnel is not answering - the Telegram notification will NOT fire live.' Yellow
    Say '      options:' Yellow
    Say '        * the "n8n watchdog" task repairs this within ~5 min:' DarkGray
    Say '            powershell -File D:\Tools\n8n\watchdog-n8n.ps1 -Config D:\Tools\n8n\watchdog-config.json' DarkGray
    Say '        * or film that shot from the alert already in the Telegram bot chat (message_id 35/36)' DarkGray
}

# ---------------------------------------------------------------- 3. clean tickets
Head '[3/4]  demo data'
if ($KeepTickets) {
    Say '      -KeepTickets: leaving the tickets table untouched' Yellow
} elseif (-not (Test-Path -LiteralPath $secretsPath)) {
    Say "      no $secretsPath - skipping the ticket cleanup (the table keeps its old rows)" Yellow
    Say '      create it with: { "supabaseUrl": "https://<project>.supabase.co", "serviceKey": "<secret key>" }' DarkGray
} else {
    try {
        $cfg = Get-Content -LiteralPath $secretsPath -Raw | ConvertFrom-Json
        $base = ([string]$cfg.supabaseUrl).TrimEnd('/')
        $key = [string]$cfg.serviceKey
        if (-not $base -or -not $key) { throw 'demo-secrets.json is missing supabaseUrl or serviceKey' }

        $read = Invoke-Supabase -Method 'GET' -Path '/rest/v1/tickets?select=id,question&order=id.asc' -Key $key -Base $base
        if ($read.status -ne 200) { throw "Supabase refused the read (HTTP $($read.status)): $($read.body)" }
        $rows = ConvertTo-Rows $read.body

        if ($rows.Count -eq 0) {
            Say '      tickets table is already empty' Green
        } else {
            Say "      removing $($rows.Count) QA ticket(s):" Yellow
            foreach ($r in $rows) {
                $q = [string]$r.question
                if ($q.Length -gt 60) { $q = $q.Substring(0, 60) + '...' }
                Say ("        #{0}  {1}" -f $r.id, $q) DarkGray
            }
            $del = Invoke-Supabase -Method 'DELETE' -Path '/rest/v1/tickets?id=gte.0' -Key $key -Base $base
            if ($del.status -lt 200 -or $del.status -ge 300) { throw "delete failed (HTTP $($del.status)): $($del.body)" }
            $left = Invoke-Supabase -Method 'GET' -Path '/rest/v1/tickets?select=id' -Key $key -Base $base
            $leftRows = ConvertTo-Rows $left.body
            if ($leftRows.Count -eq 0) { Say '      tickets table cleared - the next escalation will be the only row' Green }
            else { Say "      cleanup incomplete: $($leftRows.Count) row(s) left" Red }
        }
        Say '      (knowledge base documents were NOT touched)' DarkGray
    } catch {
        Say "      cleanup failed: $($_.Exception.Message)" Red
        Say '      the demo still works, the ticket table just keeps its old rows' DarkGray
    }
}

# ---------------------------------------------------------------- 4. the page
Head '[4/4]  demo page'
if (Test-Path -LiteralPath $page) {
    if ($NoBrowser) { Say "      -NoBrowser: open it yourself -> $page" Yellow }
    else {
        Start-Process $page | Out-Null
        Say '      opened in your default browser' Green
    }
} else {
    Say "      ERROR: $page not found" Red
}

# ---------------------------------------------------------------- shot list
Head 'SHOT LIST - 60 seconds'
Say '   0-8 s   click "Need coffee help?" -> welcome + quick options      caption: answers from YOUR docs'
Say '   8-20 s  ask: Do you ship to Canada?        -> answer + [faq.md]     caption: source shown'
Say '  20-32 s  ask: Can you sponsor our hackathon? -> passed to our team   caption: never invents'
Say '  32-40 s  Supabase tickets table -> the new row                         caption: unanswered -> ticket'
Say '  40-48 s  phone: Telegram notification                                  caption: team pinged in seconds'
Say '  48-60 s  end card: Your docs / Honest answers / Human handoff'
Say ''
Say '   widget endpoint : http://127.0.0.1:5678/webhook/b45b0144-db0e-41f0-bef0-380d3d675f2c/chat'
Say '   n8n editor      : http://127.0.0.1:5678   (workflow must be Published)'
Say '   tickets table   : Supabase dashboard -> Table editor -> tickets'
Say ''
Say '   record with Win+Alt+R (Xbox Game Bar). When you are done:'
Say "     stop the tunnel/instance:  $stopPublic"
Say ''
