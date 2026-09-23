@echo off
rem ============================================================
rem  Start the Harbor support bot.
rem  Turns on the two Windows services the demo runs as:
rem    n8n    - the workflow server
rem    ngrok  - the tunnel with the permanent hostname
rem  Asks for administrator rights (one Windows prompt), then
rem  reports whether the bot really answers.
rem  The real work is in switch-bot.ps1 next to this file.
rem ============================================================
title Support bot - ON
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0switch-bot.ps1" -Action on
echo.
echo   Press any key to close this window (the bot keeps running).
pause >NUL
