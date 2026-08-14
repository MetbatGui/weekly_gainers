@echo off
title Weekly & Monthly Gainer Pipeline - Daily Sync
cd /d %~dp0

echo ===================================================
echo   Weekly & Monthly Gainer Data Pipeline: Daily Syncing...
echo ===================================================
echo.

:: 주간+월간 데이터 동기화 (단일 오케스트레이터)
echo [INFO] Running Sync...
uv run main.py

echo.
echo ===================================================
echo   Sync Process Finished.
echo ===================================================
pause
