@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
title BW3D - VRAIE caisse 3D dans Zelda - test Hateno
echo.
echo BW3D - OBJET PHYSIQUE DANS LE VRAI HYRULE
echo --------------------------------------
echo Aucun mod Minecraft, aucune collision BotwCraft modifiee.
echo Ce test fait apparaitre une VERITABLE CAISSE EN FER native BOTW,
echo aux coordonnees fixes de Hateno, vers les marmites.
echo Pas d'image, pas de cube qui tourne devant la camera.
echo.
set /p "ROMFS=Dossier extrait du RomFS original BOTW 1.5.0 : "
if not exist "%ROMFS%\Map\MainField\I-7\I-7_Dynamic.smubin" (
 echo.
 echo ERREUR: il faut le RomFS extrait, avec Map\MainField\I-7.
 echo Un fichier XCI ou un ZIP non extrait ne suffit pas.
 pause
 exit /b 2
)
set /p "PROFILE=Dossier des donnees Ryujinx contenant Config.json : "
if not exist "%PROFILE%\Config.json" (
 echo ERREUR: dossier Ryujinx invalide.
 pause
 exit /b 3
)
set "DEST=%PROFILE%\mods\contents\01007ef00011e000\BW3D_VRAI_CUBE"
if exist "%DEST%" (
 echo ERREUR: le test est deja present. Utilise RETIRER_TEST_CUBE.bat d'abord.
 pause
 exit /b 4
)
tasklist /FI "IMAGENAME eq Ryujinx.exe" 2>nul | find /I "Ryujinx.exe" >nul
if not errorlevel 1 (
 echo ERREUR: ferme Ryujinx avant installation.
 pause
 exit /b 5
)
py -c "import oead" >nul 2>&1
if errorlevel 1 (
 echo Installation de la bibliotheque libre oead pour BYML/Yaz0...
 py -m pip install oead
 if errorlevel 1 (echo ERREUR installation oead&pause&exit /b 6)
)
echo.
echo Ajout d'une caisse native dans la carte I-7 de Hateno...
py "%~dp0place_box.py" --romfs "%ROMFS%" --map "%ROMFS%\Map\MainField\I-7\I-7_Dynamic.smubin" --x 3457.700 --y 226.618 --z 2137.559 --kind iron --out "%DEST%"
if errorlevel 1 (echo ERREUR : aucune modification de la sauvegarde.&pause&exit /b 7)
echo.
echo TERMINE : lance Zelda BOTW 1.5.0 dans Ryujinx.
echo Va a Hateno, pres des marmites, pour voir la caisse en fer.
echo Le jeu affiche lui-meme le modele 3D, la profondeur et la physique.
echo Si elle ne se voit pas, retire ce test et donne le log Ryujinx.
pause
