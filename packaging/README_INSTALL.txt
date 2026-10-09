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
   Minecraft will NOT open a mirror world before a manual connection AND
   a genuine game pose has been received.
6. Launch BOTW in Ryujinx. Only authentic Switch BOTW 1.5.0 hooks are
   currently guarded for use, and even those have not been runtime validated.

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
