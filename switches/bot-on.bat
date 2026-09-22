@echo off
rem ============================================================
rem  Start the Harbor support bot.
rem  Enables the self-healing task, starts n8n (+ the public
rem  tunnel) if needed and reports what is up.
rem  The real work is in switch-bot.ps1 next to this file.
rem ============================================================
title Support bot - ON
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0switch-bot.ps1" -Action on
echo.
echo   Press any key to close this window (the bot keeps running).
pause >NUL
