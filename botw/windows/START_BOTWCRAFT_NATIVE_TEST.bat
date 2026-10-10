@echo off
setlocal
cd /d "%~dp0"
echo BOTWCRAFT - Nintendo BOTW 1.5.0 direct native Rust test
echo =====================================================
echo [1] Installing the experimental WiiXLaunch module alongside the working mod...
where py >nul 2>nul
if not errorlevel 1 (
  set "PY=py -3"
) else (
  set "PY=python"
)
%PY% install_native_experimental.py
if errorlevel 1 (
  echo [BOTWCRAFT] Could not install native module. Nothing was launched.
  pause
  exit /b 1
)
echo [2] Starting Rust bridge, Ryujinx log relay and third Rust compositor...
%PY% bridge\start_all_rust.py
pause
