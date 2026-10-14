@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=D:\Program Files\Python\python.exe"
if not exist "%PY%" (
 where python >nul 2>&1
 if errorlevel 1 (
  echo [BotwCraft] Python est introuvable.
  pause
  exit /b 1
 )
 set "PY=python"
)
echo ==============================================
echo BOTWCRAFT : MODE BLOCS MINECRAFT EXPERIMENTAL
echo ==============================================
echo Ce mode utilise une instance Minecraft Fabric distincte.
echo Il ne modifie PAS BOTW ni les fichiers de mods Ryujinx.
echo.
"%PY%" "install_preview.py"
if errorlevel 1 (
 echo.
 echo [BotwCraft] Installation impossible. Verifie Prism Launcher et Internet.
 pause
 exit /b 1
)
call "PREVIEW_BLOCKS.bat"
