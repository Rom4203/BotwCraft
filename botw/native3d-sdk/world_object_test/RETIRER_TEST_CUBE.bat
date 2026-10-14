@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
title BW3D - Retirer uniquement le cube de test
echo.
set /p "PROFILE=Dossier donnees Ryujinx contenant Config.json : "
if not exist "%PROFILE%\Config.json" (echo ERREUR dossier Ryujinx invalide&pause&exit /b 2)
set "DEST=%PROFILE%\mods\contents\01007ef00011e000\BW3D_VRAI_CUBE"
if not exist "%DEST%\romfs\Map\MainField\I-7\I-7_Dynamic.smubin" (
 echo Aucun mod BW3D VRAI CUBE a cet emplacement.
 pause
 exit /b 0
)
tasklist /FI "IMAGENAME eq Ryujinx.exe" 2>nul | find /I "Ryujinx.exe" >nul
if not errorlevel 1 (echo Ferme Ryujinx avant le retrait.&pause&exit /b 3)
echo Suppression uniquement de "%DEST%" ...
rmdir /s /q "%DEST%"
if exist "%DEST%" (echo ERREUR suppression inachevee&pause&exit /b 4)
echo Caisse de test retiree. BotwCraft et les sauvegardes sont inchanges.
pause
