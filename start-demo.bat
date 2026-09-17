@echo off
title Harbor RAG support bot - DEMO launcher
echo.
echo   Harbor Coffee - RAG support bot
echo   ================================
echo.
echo   [1/2] checking n8n on http://127.0.0.1:5678 ...
curl -s -o NUL -m 4 http://127.0.0.1:5678/home
if errorlevel 1 (
  echo         n8n is NOT running - starting it in a separate window...
  start "n8n server (keep this window open)" /min "D:\Tools\n8n\n8n-serve.bat"
  echo         waiting 30 seconds for n8n to boot...
  ping -n 31 127.0.0.1 >NUL
) else (
  echo         n8n is running.
)
echo.
echo   [2/2] opening the demo website ...
start "" "E:\Hermes\Projects\rag-support-bot\site\index.html"
echo.
echo   n8n editor ..... http://127.0.0.1:5678
echo   workflow ....... "Support Bot (RAG) - full"   (must show Published)
echo   demo website ... site\index.html  (click the "Need coffee help?" button)
echo.
echo   To STOP n8n later: close the window titled "n8n server",
echo   or double-click D:\Tools\n8n\stop-n8n.bat
echo.
ping -n 16 127.0.0.1 >NUL
