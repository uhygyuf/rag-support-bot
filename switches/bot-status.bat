@echo off
rem ============================================================
rem  What is the bot doing right now?
rem  Read only: no administrator rights needed, changes nothing.
rem ============================================================
title Support bot - STATUS
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0switch-bot.ps1" -Action status
echo.
echo   Press any key to close this window.
pause >NUL
