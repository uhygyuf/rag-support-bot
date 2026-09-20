@echo off
rem ============================================================
rem  Harbor RAG support bot - one-command demo launcher.
rem  Starts n8n (public mode), clears the QA tickets, opens the page
rem  and prints the 60-second shot list. Real work: demo\demo-start.ps1
rem  Switches:  start-demo.bat -KeepTickets   |  -NoBrowser
rem ============================================================
title Harbor RAG support bot - DEMO launcher
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0demo\demo-start.ps1" %*
echo.
echo   Press any key to close this window.
pause >NUL
