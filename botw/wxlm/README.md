# BotwCraft WiiXLaunch native module

This is the start of a standalone WiiXLaunch SDK module for BOTW Switch 1.5.0. It registers a **real guest player-tick callback** through the `botw.player` surface and owns a BDP1 mailbox in its guest BSS.

**IMPORTANT: This does not move Link or change the camera yet.** The source intentionally logs that the required transform hook is not installed. Do not replace the existing `botwcraft.wxlm` in your game with this experiment.

Build against https://github.com/BladesawStudios/WiiXLaunch/sdk using its `build_mod.py` and devkitA64. The build script in this directory is a convenience wrapper.

Required next native implementation:
1. Bind `g_BotwCraftGameMailbox` address to the host producer (current Python producer still writes into a *different* subsdk9 BDP1 buffer); validate guest memory mapping and synchronization.
2. Capture an actual Link actor pointer via `botw.player`; trace BOTW Switch 1.5.0 character-controller transform setter in native game code. Do not assume Wii U vtable offsets or treat cached position fields as setters.
3. Locate the active `LookAtCamera` pointer during game camera update and call camera setter *after* game update.
4. Mask Link rendering and bypass local physics updates while Minecraft is authoritative. Restore on disconnect.
5. Retain the Rust compositor and Minecraft bridge; evolve collisions only after no-collision movement is verified.

The Python host packet layout is `<4I2Q18f2I` / 112 bytes. This file's `Pose` matches that layout. Multiple copies of an unrelated BDP1 marker in Ryujinx memory **do not prove** a guest module is receiving data.
