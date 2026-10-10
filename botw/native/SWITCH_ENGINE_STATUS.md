# BOTW Switch 1.5.0: actual native engine integration status

## Implemented

`switch_camera_adapter.hpp` now calls the Switch-capable **real game camera memory accessors** from WiiXLaunch-BotW (`Camera::SetPosition`, `Camera::SetLookAt`, `Camera::SetUp`) and preserves the old camera state for restoration. It requires a verified *live camera object pointer from a game callback*. It does not find or hook that object by itself.

`flight_controller.c` consumes the absolute Minecraft pose regardless of movement mode and invokes four engine callback slots. These slots are **not bound to the running Zelda executable** by this repository. The host producer in previous ZIPs uses a BDP1 packet but doesn't guarantee that its guest mailbox is handled.

## Missing to make the requested test actually playable

1. Add the source of the currently loaded `botwcraft.wxlm` to this project, or build a replacement WiiXLaunch module from SDK sources.
2. Identify the Switch 1.5.0 **live player actor / character controller** and call a verified native warp/set-transform function. Wii U `Actor::WarpTo` and its offsets must not be copied to Switch: WiiXLaunch-BotW explicitly reports `Actor::SupportsTransform == false` on Switch.
3. Capture the active Switch camera pointer and call `SetFirstPersonCamera` from the camera update hook after the game's own update (otherwise the game may overwrite the values).
4. Implement visual hiding and collision/physics bypass without deleting Link.
5. Wire the verified BDP1 guest mailbox and common monotonic clock, test in Ryujinx 1.3.3 BOTW 1.5.0.

The presence of the code above does NOT mean that Zelda moves yet. The Rust compositor remains unchanged and is the game's separate third window.

References: https://github.com/BladesawStudios/wiixlaunch-botw/tree/main/include/wiixlaunch/botw/game
