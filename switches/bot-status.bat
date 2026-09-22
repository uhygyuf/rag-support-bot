@echo off
rem  Report the current state without changing anything.
title Support bot - status
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0switch-bot.ps1" -Action status
echo.
echo   Press any key to close this window.
pause >NUL
