@echo off
title Stop Telegram Bot
echo ========================================================
echo   Stopping any running Telegram Bot instances...
echo ========================================================
powershell -Command "Get-CimInstance Win32_Process -Filter \"Name like 'python%' and CommandLine like '%bot.py%'\" | Stop-Process -Force"
echo Done! All existing bot instances have been closed.
pause

