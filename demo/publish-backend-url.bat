@echo off
title Publish the demo backend URL
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish-backend-url.ps1" %*
echo.
pause
