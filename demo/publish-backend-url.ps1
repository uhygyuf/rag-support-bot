# publish-backend-url.ps1: point the hosted demo page at the backend n8n is reachable at right now.
#
# The quick tunnel gets a new hostname every time it restarts, so the hosted copy of the demo
# site (GitHub Pages) needs to be told the current address. This script:
#   1. reads the live tunnel URL from the watchdog's url file
#   2. builds the chat webhook URL and ASKS THE BOT A QUESTION to prove it really answers
#   3. writes site/backend.json and pushes it (Pages redeploys automatically)
#
# Usage:  powershell -ExecutionPolicy Bypass -File demo\publish-backend-url.ps1
#         ... -NoPush     (write the file only, do not commit)
#         ... -SkipCheck  (publish without the live answer check)

param(
  [switch]$NoPush,
  [switch]$SkipCheck
)

$ErrorActionPreference = 'Stop'

# This script is also run unattended (from the watchdog), where a git credential prompt would hang
# until the caller kills it. Fail fast instead: credentials must already be stored.
$env:GIT_TERMINAL_PROMPT = '0'

$repo    = 'E:\Hermes\Projects\rag-support-bot'
$urlFile = 'D:\Tools\n8n\public-url.txt'
$index   = Join-Path $repo 'site\index.html'
$target  = Join-Path $repo 'site\backend.json'

if (-not (Test-Path $urlFile))   { throw "no tunnel URL file at $urlFile - is the tunnel running?" }
$base = (Get-Content $urlFile -Raw).Trim()
if (-not $base)                  { throw "the tunnel URL file is empty ($urlFile)" }
if ($base -notmatch '^https://') { throw "unexpected tunnel URL: $base" }

$html = Get-Content $index -Raw
if ($html -notmatch 'data-local-webhook="http://127\.0\.0\.1:5678(/webhook/[^"]+)"') {
  throw "could not find the chat webhook path in $index"
}
$webhook = "$base$($Matches[1])"
Write-Host "backend: $webhook"

if (-not $SkipCheck) {
  $body = '{"action":"sendMessage","sessionId":"publish-check","chatInput":"How long does US shipping take?"}'
  try {
    $answer = Invoke-RestMethod -Uri $webhook -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 60
  } catch {
    throw "the backend did not answer at $webhook ($($_.Exception.Message)) - not publishing a dead address"
  }
  if (-not $answer.output) { throw "the backend answered without an 'output' field - not publishing" }
  Write-Host "live check: OK - $($answer.output)"
}

$payload = [ordered]@{
  webhook = $webhook
  updated = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ssK')
  note    = 'Address of the live n8n backend for this demo page. Quick-tunnel URLs change whenever the tunnel restarts - refresh this file by running demo/publish-backend-url.ps1 on the machine that runs n8n.'
}
$json = ($payload | ConvertTo-Json) + "`n"
# UTF8 without BOM - a BOM would make some JSON readers choke, and no BOM is what the browser expects
[System.IO.File]::WriteAllText($target, $json, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "wrote $target"

Push-Location $repo
try {
  git add site/backend.json
  git diff --cached --quiet
  if ($LASTEXITCODE -eq 0) {
    Write-Host 'backend.json unchanged - nothing to commit'
  } else {
    git commit -m "demo: point the hosted page at the live backend ($base)" | Write-Host
    if (-not $NoPush) {
      git push origin HEAD | Write-Host
      Write-Host 'pushed - GitHub Pages redeploys automatically'
    } else {
      Write-Host 'committed locally (-NoPush)'
    }
  }
} finally {
  Pop-Location
}
