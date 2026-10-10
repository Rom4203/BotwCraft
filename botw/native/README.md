# BOTW 1.5.0 native creative flight (work in progress)

This directory implements a **real native consumer** for BDP1 absolute Minecraft flight poses. It is intentionally isolated from SkyCraft's Skyrim plugin.

## Behavior

- Reads the 112-byte little-endian BDP1 record using a sequence check.
- Rejects stale/invalid data (older than 1000 ms), unarmed sessions and non-flying poses.
- On a valid frame: disables BOTW player physics, sets the absolute Link transform, points the real camera from Minecraft's eye along Minecraft's forward vector, hides Link's model.
- On disengage: restores player visibility and physics. No virtual gamepad input or stick emulation.

## What is still missing

**Not yet playable.** The current shipped `botwcraft.wxlm` reports `BOTW_NATIVE_UNSUPPORTED: player position API absent` and `no Link pose hook installed`.

A *source-based* BOTW 1.5.0 WiiXLaunch engine adapter must implement these four callbacks:
- `set_player_transform`: Link actor transform + associated physics position
- `set_camera_lookat`: actual active LookAtCamera state, not an overlay/projection trick
- `set_player_visible`: hide player mesh while keeping actor alive
- `set_player_physics_enabled`: bypass collision/gravity for Minecraft creative flight

Wire `bwc_flight_tick` into the engine update hook (after guest BDP1 mailbox has been mapped and host/guest clock alignment is validated). Provide an actual mailbox address derived from the loaded module, not an arbitrary scanned host-memory marker.

**Important:** host `host_uptime_ms` and guest time must share the same clock domain or be translated in the adapter before calling tick.

Do not replace the compositor: the separate Rust window remains the gameplay window. Never deploy until callbacks are verified for the exact BOTW v1.5.0 build. Back up saves.

## Protocol

Header: `flight_controller.h`. Implementation: `flight_controller.c`. Both are portable C11 (apart from Nintendo Switch-specific hook implementations to be supplied).

This is the native execution layer, **not** a compiled `.wxlm` or modified `subsdk9`.
