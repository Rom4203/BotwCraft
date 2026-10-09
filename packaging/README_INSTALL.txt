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
* Removes the native WiiXLaunch module's ROMFS/SD frame.bin reader.
  The experimental GPU triangle-probe build uses a callback but DOES NOT render Minecraft blocks inside
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

Expected experimental native log: "BotwCraft:VISUAL_PROBE_REGISTERED"
Expected Windows log: "Minecraft export: N sections, T projected triangles".

GPU VISUAL PROBE — EXPERIMENTAL BOTW 1.5.0 BUILD
------------------------------------------------
Current experimental WiiXLaunch guest registers botw.gfx.RegisterDraw and
invokes botw.gfx.DrawMesh with ONE BUILT-IN 3-VERTEX CLIP-SPACE TRIANGLE.
This is a NATIVE Zelda NVN rendering TEST, NOT Minecraft geometry. The
older dangerous Core::GameReadFile ROMFS/SD operation is not present.

Check Ryujinx logs for:
  BotwCraft:VISUAL_PROBE_REGISTERED
  BotwCraft:VISUAL_PROBE_DRAW_CALLED result=1 vertices=3

If those appear and a triangle is visible on the Zelda image, the guest
graphics path works. It still needs a LIVE real-time bridge for the user's
actual Minecraft mesh triangles. If Ryujinx crashes, restore the previous
known-good 1.5.0 anti-crash build. Back up game saves before experiments.

The Windows bridge remains DIAGNOSTICS-ONLY for Minecraft sections, not a
working host->Switch 3D geometry transport. The earlier "renderer disabled"
note above applies to the stability build, not this visual-probe branch.

REAL MINECRAFT MESH -> ZELDA NVN: EXPERIMENTAL GDB TRANSPORT
-----------------------------------------------------------
Progress:
  Confirmed: 4 Minecraft sections, 170 triangles, valid Minecraft pose.
  Confirmed: Zelda draws a native 3-vertex triangle with WiiXLaunch NVN.
  New experimental glue: Ryujinx GDB writes bounded BWC1 packets into a
  memory buffer allocated by our own .wxlm module. No Nintendo ROMFS/SD I/O.
  Not yet confirmed in a live emulator: first genuine MC triangle on screen.

WARNING: The GDB stub pauses ALL game threads during each debugger write.
This is deliberately rate-limited to ONE mesh frame per second. Expect
stutter; this is proof-of-concept, NOT real-time SkyCraft performance.
Back up Zelda saves before enabling. Never run GDB against public hosts.

Setup:
1. Close Ryujinx and the bridge; back up your Zelda saves.
2. Install with INSTALL_NATIVE_TEST.bat (replaces WiiXLaunch botwcraft.wxlm
   with a version containing our guest-owned 16,416-byte BWC1 mailbox).
3. Use Ryujinx 1.3.3 if its Options > Debug offers "GDB Stub". Otherwise
   use a supported Ryujinx Canary build, 1.3.109+; keep your existing profile
   and saves backed up. Configure GDB Stub to listen on port 22225.
4. For native guest-address discovery Ryujinx must write LIVE console text
   to a log. Put the full path to ryujinx-live.log in ryujinx-log-path.txt
   next to START_GDB_BRIDGE.bat. START_RYUJINX_LOGGED.bat may help if your
   Ryujinx build emits redirected stdout; otherwise choose a live log.
5. Launch Zelda 1.5.0. Its log should report:
   BotwCraft:GDB_MESH_BUFFER_ADDR=0x0000............
   BotwCraft:GDB_MESH_CAPACITY=16416
   BotwCraft:VISUAL_PROBE_REGISTERED
6. Launch Minecraft manually, load a NORMAL world with Fabric SkyCraft and
   type /botwcraft connect.
7. Run START_GDB_BRIDGE.bat INSTEAD of START_BRIDGE.bat. Never run both:
   both would consume the same SkyCraft v11 render ring. If the GDB bridge
   hangs awaiting a guest address, inspect the live-log path.
8. On success, the Python bridge prints "Sent N real Minecraft triangles"
   and the guest logs "BotwCraft:GDB_MESH_FRAME_ACCEPTED". Expect projected
   Minecraft geometry to depend on the Minecraft camera: matching the
   Zelda camera and collision remains unsolved.
9. Stop the test with Ctrl+C, or disable GDB stub and restore the earlier
   known-good fixed-triangle module if necessary. Do not edit Java args.

Security/integrity:
* The ONLY guest address used is the bounded buffer announced by our module
  in a recent, version-matched 1.5.0 log. We do not scan or patch unrelated
  Zelda memory, do not open remote GDB hosts, and do not alter game saves.
* The guest validates BWC1 headers, payload length, FNV-1a hash and finite
  vertices before calling DrawMesh. Invalid data falls back to the fixed
  reference triangle.
* A fake local GDB server exercises the RSP write and guest resume protocol
  in CI. That is NOT proof the exact Ryujinx 1.3.3 stub accepts all packets.
* The return to native real-time Zelda 3D requires a supported guest-side
  shared-memory or emulator integration and proper Zelda camera transform.

SKYCRAFT -> BOTW REAL WORLD-SPACE BACKEND (BWC2, DEVELOPMENT)
------------------------------------------------------------
This is an INCREMENTAL core-engine port, not a playable release.
User-approved priorities: camera, 3D block world rendering, Minecraft
physics/collision, Minecraft keyboard/mouse and HUD. Defer saves,
Zelda-mob interactions and mining/destroying Zelda terrain.

BWC1 (legacy) is screen-space, uses the Minecraft camera and produces
the large cyan rectangle over the Zelda picture. DO NOT treat this as
equivalent to SkyCraft.

New BWC2:
* botw/world_space.py keeps actual block/world coordinates from SkyCraft
  v11, UV atlas coordinates, ARGB shading, Minecraft lighting and
  transparency/normal flags. They are anchored once to Link's real
  world position, NEVER re-centered on every Minecraft-camera change.
* botw/native_world_scene.hpp validates checksummed bounded BWC2
  packets and computes actual 3D clip-space from Zelda camera
  position/target/up and the current native projection focal.
* botw/world_gdb_bridge.py writes BWC2 3D geometry into a guest-owned
  buffer using the local Ryujinx debugger, separate from BWC1.
* botw/guest_mod/mod.cpp provides separate BWC2 and BWC1 buffers.
  The native world renderer WILL NOT draw a fake 2D rectangle when BWC2
  is received without a real BOTW camera. Real camera/depth hookups are
  required, and still in development.
* START_WORLD_BRIDGE.bat is DEVELOPMENT ONLY. It will not make the world
  appear until the live BOTW camera matrix/depth path is wired. Users who
  just want Link telemetry should keep START_BRIDGE.bat.

Next source modules being implemented: native BOTW camera hook,
matching NVN world depth attachment, streaming Minecraft texture atlas,
Hyrule Havok/physics collision to Fabric, then controls/HUD capture.
Automated builds validate packet and math; do not interpret them as
proving camera, collision or real-time interaction inside the game.

MINECRAFT HUD FIRST / KEYBOARD + MOUSE OWNED BY MINECRAFT
--------------------------------------------------------
This test is the first stage of the revised SkyCraft parity roadmap:
1. Original MC HUD in the Zelda display.
2. Minecraft camera/mouse and configurable BOTW-specific keys.
3. MC creative flight / first-person world movement, no collisions yet.
4. BOTW world collision and walking.
5. World-anchored Minecraft block place/break and 3D display.
Defer BOTW mobs, terrain destruction and persistence for now.

START_HUD_BRIDGE.bat runs host_bridge + Ryujinx position relay +
diagnostic native mesh component + the existing click-through Win32
hud_overlay.py. It NEVER starts either game or captures any keyboard or
mouse itself. minecraft_mods/skycraft-*.jar now enables the ORIGINAL
SkyCraft FrameExporter, with the same asynchronous GPU staging buffers
and original protocol v11 shared-memory RGBA triple buffer.

Quick test:
* Have Zelda 1.5.0 running in Ryujinx, and Minecraft 26.3 open to a world.
* Run START_HUD_BRIDGE.bat instead of START_BRIDGE.bat.
* From the Minecraft chat issue /botwcraft connect, then
  /botwcraft hud on.
* In this explicit HUD mode, Minecraft's world rendering is suppressed
  ONLY in Minecraft's own framebuffer capture, leaving its real hand,
  hotbar, hearts, inventory and menus. Minecraft continues to tick and
  receives physical keyboard/mouse input.
* A non-activating, mouse-click-through Windows layer displays these
  ORIGINAL RGBA GUI pixels over Ryujinx's client area. This is a
  diagnostic Windows window compositor, not a finished native NVN
  texture pipeline. It requires Ryujinx to run in windowed/borderless
  mode and does NOT unify window focus yet. On a single monitor, keep
  both windows visible for this first test.
* If no HUD appears, run CHECK_HUD.bat; it saves minecraft-hud-test.png
  from the actual shared-memory RGBA buffer. If that file contains the
  MC interface, then the GUI producer works and the remaining problem
  is the Ryujinx Windows overlay placement/alpha.
* Use /botwcraft hud off to restore normal Minecraft world rendering,
  or /botwcraft disconnect to end the session.
* Do not use the old /botwcraft hud command with the old Fabric JAR;
  replace it with the new one, manually, via Prism > Mods.

IMPORTANT: This patch does NOT yet route Minecraft player movement or
mouse yaw to Zelda, take over camera or install real world collisions.
For complete one-window parity, the next stage requires pinning Ryujinx
as a non-activating display surface while Minecraft keeps SDL focus,
with carefully isolated BOTW action key mappings. Do not let both
windows process the same keyboard/mouse events. Savegame backups
recommended before all experimental native Switch updates.
