@echo off
title Weekly Gainer Pipeline - Daily Sync
cd /d %~dp0

echo ===================================================
echo   Weekly Gainer Data Pipeline: Daily Syncing...
echo ===================================================
echo.

:: uv를 사용하여 main.py 실행
uv run main.py

echo.
echo ===================================================
echo   Sync Process Finished.
echo ===================================================
pause
