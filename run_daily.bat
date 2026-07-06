@echo off
title Weekly & Monthly Gainer Pipeline - Daily Sync
cd /d %~dp0

echo ===================================================
echo   Weekly & Monthly Gainer Data Pipeline: Daily Syncing...
echo ===================================================
echo.

:: 1. 주간 데이터 동기화
echo [INFO] Running Weekly Sync...
uv run main.py --period weekly

echo.
:: 2. 월간 데이터 동기화
echo [INFO] Running Monthly Sync...
uv run main.py --period monthly

echo.
echo ===================================================
echo   Sync Process Finished.
echo ===================================================
pause
