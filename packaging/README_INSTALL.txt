BOTWCRAFT EXPERIMENTAL BUILD - BOTW SWITCH 1.0.0
=================================================

STATUS: NOT PLAYABLE YET. This is the current prototype, not Minecraft inside BOTW.
Do not install on your only Ryujinx profile; hooks may crash BOTW.

Included:
- WiiXLaunch subsdk9, built from local sources
- BotwCraft guest .wxlm
- Windows bridge and log relay

INSTALL (ONLY AFTER THE PLAYER HOOK HAS BEEN VERIFIED FOR BOTW 1.0.0):
1. Back up your BOTW saves and Ryujinx data.
2. Copy the folder under ryujinx_mods/contents into
   %APPDATA%\Ryujinx\mods\contents, merging by title ID.
3. Start Ryujinx and BOTW.
4. Run START_BRIDGE.bat.

IMPORTANT: This package does not implement Minecraft-driven Link movement,
collision transfer or drawing Minecraft blocks inside BOTW. The currently
unverified hook is intentionally blocked by the source guard.

TO UNINSTALL:
Close Ryujinx, then MOVE the BotwCraft folder outside Ryujinx's mod search
directories (merely renaming the folder still loads the mod).

No Nintendo assets, keys, firmware or game saves are included.
