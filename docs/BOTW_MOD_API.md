# BOTW Switch native mod architecture (replaces keyboard input)

**Status: interface designed, guest hooks NOT implemented. Not playable yet.**

## Choice: WiiXLaunch + BOTW game module

Research source:
- https://github.com/BladesawStudios/WiiXLaunch
- https://github.com/BladesawStudios/wiixlaunch-botw
- https://github.com/shadowninja108/exlaunch

WiiXLaunch targets Switch/AArch64 executable mods using ExLaunch, and has a
dedicated BOTW module. Unlike sending virtual controller input to Ryujinx,
game hooks can potentially read/apply Link's world-space state directly.

This is **not** a ready-made BOTW player movement API. The framework supplies
hooking/patching infrastructure; appropriate player and camera symbols and
their version-specific addresses must be verified before use.

## Intended data path

Minecraft 26.3 Fabric (unchanged game logic / input / physics)
  -> SkyCraft protocol, versioned, with game-neutral host field names
  -> Windows host bridge process (shared-memory owner + game-host IPC)
  -> Switch guest mod (WiiXLaunch / ExLaunch, BOTW 1.5/1.6)
  -> BOTW player transform/camera/collision hooks

Since guest AArch64 code and Windows Fabric can't access the same host
shared-memory object directly, a host transport bridge is required. Candidate
is a customized Ryujinx guest-service or a localhost emulated socket
transport, subject to verifying supported Switch networking in the selected
emulator. No transport has been proven yet.

The native guest-facing interface is in `botw/native/botw_adapter.hpp`.
Implementations MUST:
- Gate by known BOTW title ID, exact executable build ID and compatible update.
- Stop writes during cutscenes, loading, menus, and invalid player states.
- Read the player's feet position and local orientation on the game thread.
- Apply Minecraft's target transform *after* BOTW's own locomotion update,
  without guest/MC physics racing each other.
- Capture a collision representation to forward to MC; mere transform writes
  cause falling through terrain or desync.
- Respect the BOTW camera/cutscene ownership; don't rewrite unknown pointers.
- Never accept game-independent host pointers as guest addresses.
- Log hook success and failure without crashing or corrupting saves.

## Implementation milestones

1. Compile a WiiXLaunch BOTW guest mod against the *actual* BOTW game module
   and make it log one frame callback on Ryujinx.
2. Read Link's position + camera yaw and validate changes in-game.
3. Host/guest message transport with heartbeat, timeout and protocol version.
4. Minecraft physics drives Link using reconciled terrain collision.
5. Hide Minecraft window, composite MC GUI/hand and blocks into the emulator
   output without breaking Ryujinx rendering.
6. Exercise jump, swim, slopes, menus, fast travel, saves and reloads.

The prior `botw/controller_smoke_test.py` is a completely separate
input-only diagnostic and is *not* the selected game integration path.
The upstream `skse/` directory is Skyrim-only and must not be built
for BOTW. WiiXLaunch is GPL-3.0: review licensing if its implementation
is copied into BotwCraft; mere links/documentation do not incorporate code.

Neither a finished .nso mod, nor the host transport, nor Minecraft-to-BOTW
game integration exists in this commit. A genuine in-game test depends on
the exact Ryujinx fork and BOTW build used.
