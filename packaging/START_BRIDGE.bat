@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
if not exist "bridge\launcher.py" (
 echo [BotwCraft] ERROR: bridge\launcher.py introuvable.
 pause
 exit /b 1
)
if exist "ryujinx-data.txt" (
 set "BOTWCRAFT_RYUJINX_DATA="
 set /p BOTWCRAFT_RYUJINX_DATA=<"ryujinx-data.txt"
 if defined BOTWCRAFT_RYUJINX_DATA set "BOTWCRAFT_SDROOT=!BOTWCRAFT_RYUJINX_DATA!\sdcard"
)
if defined BOTWCRAFT_SDROOT (
 echo [BotwCraft] Ryujinx SD: !BOTWCRAFT_SDROOT!
) else (
 echo [BotwCraft] Attention: chemin SD non configure. Verifier ryujinx-data.txt.
)
if exist "ryujinx-log-path.txt" (
 set "BOTWCRAFT_RYUJINX_LOG="
 set /p BOTWCRAFT_RYUJINX_LOG=<"ryujinx-log-path.txt"
 if defined BOTWCRAFT_RYUJINX_LOG echo [BotwCraft] Source journal: !BOTWCRAFT_RYUJINX_LOG!
)
echo [BotwCraft] Bridge experimental BOTW 1.5.0 - Ryujinx se lance separement.
echo [BotwCraft] Ctrl+C pour arreter.
set "BOTWCRAFT_EXTRA="
if defined BOTWCRAFT_WORLD_GDB_PORT (
 set "BOTWCRAFT_EXTRA=--world-gdb-port !BOTWCRAFT_WORLD_GDB_PORT!"
 echo [BotwCraft] BWC2 Hyrule world geometry GDB port !BOTWCRAFT_WORLD_GDB_PORT!
)
if defined BOTWCRAFT_GDB_PORT (
 set "BOTWCRAFT_EXTRA=--gdb-port !BOTWCRAFT_GDB_PORT!"
 echo [BotwCraft] GDB mesh transfer EXPERIMENTAL enabled, port !BOTWCRAFT_GDB_PORT!
)
rem A Python variable including "py -3" cannot be quoted as one executable.
if exist "D:\Program Files\Python\python.exe" (
 "D:\Program Files\Python\python.exe" -u "bridge\launcher.py" !BOTWCRAFT_EXTRA!
) else (
 where py >nul 2>&1
 if not errorlevel 1 (
  py -3 -u "bridge\launcher.py" !BOTWCRAFT_EXTRA!
 ) else (
  python -u "bridge\launcher.py" !BOTWCRAFT_EXTRA!
 )
)
if errorlevel 1 echo [BotwCraft] Le bridge s'est arrete avec une erreur.
pause
