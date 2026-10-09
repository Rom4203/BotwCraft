@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=D:\Program Files\Python\python.exe"
if not exist "%PY%" (echo Python missing & pause & exit /b 1)
echo [1/3] Preparing pinned WiiXLaunch plus wiixlaunch-botw...
"%PY%" "botw\setup_wiixlaunch.py"
if errorlevel 1 (
 echo [ERROR] Unable to prepare BOTW native dependencies.
 pause
 exit /b 1
)
if not exist "botw\guard_switch_player_hook.py" (
 echo ERROR: missing v1.0.0 player-hook safety guard.
 pause
 exit /b 1
)
echo Protecting unverified game hooks; BOTW Switch 1.5.0 targeted.
"%PY%" "botw\guard_switch_player_hook.py"
if errorlevel 1 (echo Hook guard failed; refusing to compile & pause & exit /b 1)
call "build_botw_windows.bat" --no-pause
if errorlevel 1 (echo Build failed: package not created & pause & exit /b 1)
echo Building Minecraft Fabric mod from the SkyCraft-based source...
if not exist "fabric\\gradlew.bat" (
 echo [ERROR] Minecraft Gradle wrapper missing.
 pause
 exit /b 1
)
pushd "fabric"
call gradlew.bat --no-daemon build
set "MC_RC=%ERRORLEVEL%"
popd
if not "%MC_RC%"=="0" (
 echo [ERROR] Minecraft Fabric build failed. Java 25 and a network connection are required.
 pause
 exit /b 1
)
"%PY%" "package_botw_windows.py"
if errorlevel 1 (echo Packaging failed & pause & exit /b 1)
echo.
echo ZIP: dist\BotwCraft-experimental.zip
echo IMPORTANT: native graphics and player integration require runtime verification; not a playable port.
pause
