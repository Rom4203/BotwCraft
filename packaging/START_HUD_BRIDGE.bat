@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo [BotwCraft HUD] Premier test du HUD original Minecraft sur Zelda.
echo [BotwCraft HUD] Minecraft recoit clavier/souris; superposition NON native NVN.
echo [BotwCraft HUD] CTRL+C ferme bridge et HUD, pas les jeux.
echo [BotwCraft HUD] Dans Minecraft : /botwcraft connect puis /botwcraft hud on
echo [BotwCraft HUD] La fenetre Minecraft ne sera ni fermee ni masquee automatiquement.
set "BOTWCRAFT_HUD_OVERLAY=1"
call "%~dp0START_BRIDGE.bat"
