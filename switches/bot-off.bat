@echo off
rem ============================================================
rem  Really stop the Harbor support bot.
rem  Disables the self-healing task FIRST, then stops n8n and
rem  the public tunnel. Stopping n8n alone is not enough: the
rem  task would start it again within about five minutes.
rem  The real work is in switch-bot.ps1 next to this file.
rem ============================================================
title Support bot - OFF
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0switch-bot.ps1" -Action off
echo.
echo   Press any key to close this window.
pause >NUL
