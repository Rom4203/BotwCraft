# BOTW 1.5.0 Minecraft-authoritative movement sync (work in progress)

**Scope: every Minecraft movement mode**, not a creative-flight feature. Minecraft is the authoritative simulation for walking, sprinting, jumps, falling, swimming, crawling, riding and flying. Zelda renders Hyrule, its actors and its camera. The independent Rust compositor remains the gameplay window.

## First milestone (no BOTW collisions)

- Read fresh absolute Minecraft player position, eye and look direction from BDP1, without requiring a creative/fly flag.
- Maintain a calibrated world-origin mapping from Minecraft to BOTW instead of copying incompatible absolute coordinates blindly.
- Send transforms to Link's actor via a verified in-game BOTW hook (never a gamepad) and render from Minecraft's actual first-person eye and look vector.
- Hide Link's model, **not** the actor itself. Temporarily disable Zelda character physics/collision enforcement so Minecraft's movements remain authoritative.
- Keep the last safe in-game state when the packet is stale or Minecraft disconnects; restore normal game visibility/physics when disarming.

## Intended SkyCraft-style integration later

- Read Zelda geometry and dynamic collider contacts and feed them into Minecraft's collision simulation.
- Minecraft continues computing motion and deciding contacts. Zelda does not take over movement.
- Sync block placement/destruction, rendering, interactions and combat in later phases, using dedicated protocols rather than overloading player-position packets.

## What is actually implemented now

`flight_controller.c` is a transport-independent, guarded **all-mode pose consumer** (the historical filename predates the scope correction). It does not require flying. It requests camera, actor transform, visibility and temporary physics-bypass callbacks. It is **not a complete game mod**.

The existing `botwcraft.wxlm` reports `BOTW_NATIVE_UNSUPPORTED: player position API absent` and `no Link pose hook installed`. To make this real, WiiXLaunch BOTW 1.5.0 native sources and verified bindings for `set_player_transform`, `set_camera_lookat`, `set_player_visible`, `set_player_physics_enabled` are needed. The host must also publish matching BDP1 packets and map the correct guest mailbox. Validate actual packet structure, ownership and clock alignment before deployment; do not write to memory just because a marker matches.

This directory does not compile or install `.wxlm`; SkyCraft on `main` is unaffected.
