@echo off
rem ============================================================
rem  Really stop the Harbor support bot.
rem  Stops both Windows services AND sets them to Disabled, so
rem  a reboot does not quietly bring the demo back.
rem  (Stopping n8n alone would not be enough: it starts with
rem  Windows by design.)
rem  The real work is in switch-bot.ps1 next to this file.
rem ============================================================
title Support bot - OFF
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0switch-bot.ps1" -Action off
echo.
echo   Press any key to close this window.
pause >NUL
