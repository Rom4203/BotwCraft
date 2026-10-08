# BotwCraft prototype: Ryujinx telemetry relay

This is a **read-only integration experiment**, NOT a playable BOTW + Minecraft build.

## What it implements

The experimental Switch guest prints measured position in Ryujinx's normal log:

```
[BotwCraft:v100] position X=... Y=... Z=...
```

`botw/ryujinx_log_relay.py` follows the newest Ryujinx log and forwards actual telemetry as JSON over `127.0.0.1:39847` to `botw/host_bridge.py`. The host bridge writes the existing SkyCraft v11 named shared-memory mapping that the Fabric code can read. This is a one-way path: BOTW **to** Minecraft.

There is deliberately **no synthetic pose** if the Switch hook isn't running. Yaw/pitch are zero placeholders. This log transport will also be too slow/jittery for final gameplay.

## How to run the relay on Windows

In the repository directory with Python at `D:\Program Files\Python\python.exe`, run `start_botw_prototype.bat`. It runs the relay tests, opens the host bridge, then follows Ryujinx logs. No Ryujinx files are changed.

To validate without a game, test using `python -m unittest botw.test_ryujinx_log_relay`. For log inspection only, run `python botw/ryujinx_log_relay.py --dry-run --from-start`.

## Remaining hard blockers before a game is playable

* Confirm the exact 1.0.0 hook actually receives the live **Link** actor, not an unrelated actor; no game-side evidence yet. An invalid hook can crash Ryujinx.
* Add a safe BOTW transform setter, with authoritative physics/collision handling. The current `player.hpp` explicitly has no verified Switch setter.
* Implement **Minecraft -> Ryujinx** transport, not just read-only logs. A logfile cannot control Link.
* Feed BOTW world geometry/collisions to Minecraft, and integrate rendering, blocks, UI and interactions.
* Test all components in a live Ryujinx/BOTW session, with backed-up saves.

Do not install unverified game hooks on a stable Ryujinx profile. The build script compiles only.
