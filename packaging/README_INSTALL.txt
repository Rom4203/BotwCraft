BOTWCRAFT - EXPERIMENTAL MANUAL CONNECTION / SWITCH 1.5.0
============================================================

THIS IS NOT YET A PLAYABLE MINECRAFT-IN-HYRULE RELEASE.

NEW WORKFLOW (NO AUTOMATIC LAUNCHES, NO JAVA FLAG OVERRIDES)
-----------------------------------------------------------
1. Back up your Zelda saves. Close both games before installing/updating.
2. Run INSTALL_NATIVE_TEST.bat to install ONLY the Switch mod into Ryujinx.
   It no longer installs/edits Prism profiles or Java arguments.
3. In your preferred, existing Prism instance with Minecraft 26.3 + Fabric
   Loader + Fabric API, manually add minecraft_mods/skycraft-*.jar via
   Prism > Edit instance > Mods > Add File.
   Remove any older skycraft-*.jar to avoid duplicate mod IDs.
   Your world saves are NOT removed. You decide which world to use.
4. Start START_BRIDGE.bat. It now starts ONLY Python bridge processes.
   It does not start Prism, Minecraft, Java or Zelda.
5. Launch Minecraft yourself with no BotwCraft-specific JVM arguments.
   Join or create the world you want to use. In Minecraft chat, type:
     /botwcraft connect       Allow the SkyCraft v11 link
     /botwcraft status        Check for real BOTW position telemetry
     /botwcraft disconnect    Disconnect without stopping Minecraft
   Minecraft will NEVER open a mirror world or teleport your character.
   The /botwcraft connect command is TELEMETRY-ONLY: real Link coordinates
   are received and Minecraft's existing world is exported for diagnostics.
   This is a test and does not synchronize gameplay or collision.
6. Launch BOTW 1.5.0 in Ryujinx. Native Link position telemetry has now
   been observed in actual user logs. Graphics file transport is unresolved.

BOTW 1.6.0 IS NOT SUPPORTED
---------------------------
Your Ryujinx logs confirmed version 1.6.0 and unknown fingerprint 0x6811B941.
The native module detects this and refuses all unsafe graphics and Link hooks.
This avoids the prior crash but prevents position updates and Zelda-side meshes.
A log reader, Python bridge or local web server CANNOT invent those missing
guest-side hooks. Simply accepting the 1.6.0 fingerprint is unsafe.

To select 1.5.0, in Ryujinx right-click Zelda > Manage Title Updates, choose
your LEGITIMATE existing 1.5.0 update and Save. If it is missing, Ryujinx
cannot create it from 1.6.0; use an older update backed up from your own game.
Do not relabel 1.6.0 content as 1.5.0.

LOG CAPTURE
-----------
Some Ryujinx versions create files only at exit. If normal logfile paths
are missing, START_RYUJINX_LOGGED.bat can start Ryujinx and attempt to capture
its stdout to ryujinx-live.log. This is optional and may not work with builds
that do not emit redirected stdout.
Logs contain BOTW startup/version information; without supported native hooks
they cannot supply genuine per-frame Link positions.

TECHNICAL TRANSPORT
-------------------
Fabric SkyCraft v11 -> Windows named shared memory Local\SkyCraft_v1
Windows host bridge -> TCP 127.0.0.1:39847 (validated JSON messages)
Native mesh bridge -> virtual SD BWC1 frame.bin (experimental)
WiiXLaunch Switch subsdk9 and botwcraft.wxlm (BOTW 1.5.0 only)

Old SkyCraft labels may still appear in debug output because the protocol is
derived from SkyCraft. This does NOT mean Skyrim is actually running.

NO NINTENDO GAME FILES, KEYS, ROMS OR FIRMWARE ARE DISTRIBUTED.

Repository: https://github.com/Rom4203/BotwCraft

OCTOBER 9 TELEMETRY MILESTONE AND RUNTIME SAFETY FIX
---------------------------------------------------
Actual BOTW 1.5.0 native logs include:
  BotwCraft:NATIVE_POSITION_MILLI x=-1125660 y=237270 z=1903970
Windows relay confirms these are forwarded into the SkyCraft v11 host.
The former Fabric code automatically teleported its player to this Link
position, despite having no Hyrule collision/terrain in the Minecraft
world. The same Skyrim-only mode suppressed level rendering and mouse
capture, leading to a black world, deaths and an unlocked mouse.

THIS BUILD DISABLES ALL THREE BEHAVIORS COMPLETELY.
  /botwcraft connect      Activate telemetry only.
  /botwcraft status       Show the measured Link X/Y/Z, if fresh.
  /botwcraft disconnect   Disconnect, leaving both games and saves alone.
Any existing Minecraft world remains the user's own. The mod does not
change its rules, inventory, spawn, movement, pause handling or options.
DO NOT enable old experimentalBlocks JVM flags or old preview marker.

Known native graphics issue: WiiXLaunch repeatedly reports that the
Ryujinx guest filesystem cannot open sd:/WiiXLaunch/.../frame.bin.
Host output files alone do not prove that the guest SD filesystem is
mounted. Without a supported live guest-readable channel, no native
Minecraft mesh rendering is validated. Do not force a mount with
unverified FS hooks; a previous unsupported path aborted Ryujinx.

CRASH GUARD - BOTW 1.5.0 / RYUJINX 1.3.3 (2026-10-09)
----------------------------------------------------
A real Ryujinx crash log confirmed ResultSvcInvalidCurrentMemory (0xD401)
while the experimental ROMFS Minecraft mesh reader called
nn::fs::ReadFile on the game's main thread. It crashed ~6 seconds after
launch. Do NOT reinstall the previous ROMFS diagnostic test.

THIS BUILD:
* Removes the native WiiXLaunch module's ROMFS/SD frame.bin reader and
  native mesh draw callback. It DOES NOT render Minecraft blocks inside
  Zelda. Link pose is still read natively by the WiiXLaunch 1.5.0 host
  after game startup; the Python log relay forwards those genuine poses.
* The Python native_mesh_bridge is NOW DIAGNOSTICS-ONLY. It reports
  Minecraft section/triangle counts and never writes Ryujinx mod files
  while the game is running. No misleading "writable again" message.
* Fabric /botwcraft connect remains under user control. Minecraft world
  export continues even while Zelda is loading: the Windows shared-memory
  transport being present is no longer confused with having a live
  Link pose. Minecraft player, mouse and world remain unchanged.
* The installer stops creating the experimental ROMFS frame.bin. It
  backs up and replaces ONLY the previous BotwCraft mod directory.
* Don't run Ryujinx mod ROMFS file updates while the game is running.
  Ryujinx's modded ROMFS is assembled at launch, not a supported live IPC.
* A future real-time guest-render transport is a separate development
  task. Success of Python or ARM64 builds does not prove 3D rendering.

Expected native log: "BotwCraft:MESH_DISABLED"
Expected Windows log: "Minecraft export: N sections, T projected triangles".
