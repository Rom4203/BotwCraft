@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo ============================================================
echo BOTWCRAFT / LINK TRANSFORM DIRECT BOTW 1.5.0 [EXPERIMENTAL]
echo ============================================================
echo No virtual gamepad, no GDB memory writes each frame.
echo Source = real Minecraft physics and mouse look.
echo Target = 1.5.0 Link actor's setMtx, via Ryujinx process memory.
echo First-person camera is NOT yet connected to active CameraMgr.
echo WARNING: actor setMtx runtime has not yet been verified on YOUR 1.5.0.
echo Back up game saves and close other emulator sessions before testing.
echo.
echo 1. Run START_BRIDGE.bat in another terminal.
echo 2. Launch BOTW in Ryujinx (full 1.5.0 gameplay).
echo 3. Launch Minecraft and open a world.
echo 4. /botwcraft connect   /botwcraft hud on   /botwcraft inputs on
echo 5. Start the Rust BotwCraft game window if desired.
echo.
echo CTRL+C disengages, does NOT terminate either game.
echo ============================================================
if not exist "bridge\ryujinx_direct_memory.py" (
 echo [BotwCraft] ERROR: bridge\ryujinx_direct_memory.py missing.
 pause
 exit /b 2
)
set "PYTHON_CMD=python"
where py >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"
%PYTHON_CMD% -u "bridge\ryujinx_direct_memory.py" --apply-actor --hz 60
echo [BotwCraft] Direct Link transform exited.
pause
