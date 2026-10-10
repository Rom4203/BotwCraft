@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo [BotwCraft] Diagnostique : enregistrer une image du VRAI HUD SkyCraft.
echo [BotwCraft] D'abord, /botwcraft connect puis /botwcraft hud on dans Minecraft.
if exist "D:\Program Files\Python\python.exe" (
 "D:\Program Files\Python\python.exe" -u "bridge\hud_snapshot.py" --out "minecraft-hud-test.png"
) else (
 where py >nul 2>&1
 if not errorlevel 1 (
  py -3 -u "bridge\hud_snapshot.py" --out "minecraft-hud-test.png"
 ) else (
  python -u "bridge\hud_snapshot.py" --out "minecraft-hud-test.png"
 )
)
pause
