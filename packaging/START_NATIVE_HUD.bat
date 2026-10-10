@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo [BotwCraft NVN] VRAIE texture du HUD Minecraft dans le rendu Zelda.
echo [BotwCraft NVN] Experience a image FIXE reduite 128x72, PAS encore un HUD anime.
echo [BotwCraft NVN] Nouveau mod WiiXLaunch installe via INSTALL_NATIVE_TEST.bat obligatoire.
echo [BotwCraft NVN] Ryujinx: serveur GDB actif sur 127.0.0.1:22225.
echo [BotwCraft NVN] A NE PAS lancer avec START_HUD_BRIDGE.bat.
echo [BotwCraft NVN] Dans Minecraft: /botwcraft connect puis /botwcraft hud on.
set "BOTWCRAFT_NATIVE_HUD_PORT=22225"
call "%~dp0START_BRIDGE.bat"
