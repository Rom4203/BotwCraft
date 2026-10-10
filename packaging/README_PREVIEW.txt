BOTWCRAFT BLOCKS PREVIEW — Windows / Ryujinx
==============================================

WHAT IT DOES:
This is a first, deliberately limited, PLAYTESTABLE CREATIVE SANDBOX.
It starts Minecraft Java 26.3 (Fabric / SkyCraft-derived mod) in an isolated
Prism Launcher instance and attempts to display its actual block-world frame,
hands and HUD over the Ryujinx window. Minecraft itself handles block
placement, breaking and saves. A 21x21 starter grass platform is placed once.
SkyCraft's keyboard/mouse events are sent via the Windows bridge.

IMPORTANT LIMITATIONS:
This is NOT yet the full SkyCraft-equivalent BOTW port. The preview does not
read BOTW Link position, terrain geometry or scene depth. Blocks are drawn
in a desktop overlay, NOT as native BOTW 3D geometry. Camera/depth alignment
is approximate; the host pose is synthetic for this test mode only.
Controller integration requires vgamepad + ViGEmBus, configured in Ryujinx.
Mouse look and overlay performance need a real-Windows playtest.

MINIMAL INSTALL:
1. Have Prism Launcher installed and signed in to your Minecraft account.
   Official Prism site: https://prismlauncher.org/
2. Extract this ZIP anywhere.
3. Double-click INSTALL_AND_PREVIEW.bat, then launch BOTW in Ryujinx.
   First launch creates a separate Minecraft profile "BotwCraftPreview"
   and downloads Fabric API from Modrinth with SHA-512 verification.
4. Leave the script window running. Use Minecraft's normal creative inventory
   and mouse/buttons while Ryujinx is focused. Minecraft's creative world
   saves inside the dedicated Prism profile.

NOTES:
- Python 3.10+ is required. If available, D:\Program Files\Python\python.exe is used.
- No Nintendo files, game saves, keys or firmware are shipped or copied.
- The normal Switch mod (subsdk9 + .wxlm) is NOT installed by this preview.
  Previously observed BOTW v1.0.0 crashes cannot be fixed just by packaging.
- If Prism is installed in a non-standard location, set BOTWCRAFT_PRISM to
  the full path to prismlauncher.exe before starting.
- To uninstall, close the bridge and remove only the Prism instance
  "BotwCraftPreview" in Prism. This deletes the preview Minecraft world.
  Your existing Ryujinx Zelda saves are not modified.

SOURCE:
https://github.com/Rom4203/BotwCraft/tree/botw-ryujinx-development

Based on SkyCraft by chasmlol. SkyCraft Minecraft source is MIT licensed.
