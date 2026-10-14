# BotwCraft — Ryujinx adaptation

Status: **architecture / coordinate-mapping tests only; not playable**.

The upstream SkyCraft repository integrates Skyrim using SKSE and CommonLibSSE.
Neither works inside BOTW on a Switch emulator. In particular, copying
`skse/` into Ryujinx will not produce a running mod.

## Preserve vs replace

- Preserve: `fabric/` (Minecraft 26.3 mod logic), `protocol/` (shared
  memory message layout), subject to guest-specific changes and versioning.
- Replace: `skse/` with a **Ryujinx guest adapter**. Do NOT build or install
  the Skyrim DLL for BOTW.
- Keep the BOTW game running locally in the emulator. Do not redistribute
  ROMs, firmware, keys or Nintendo game assets.

## Target milestone (minimum playable walking)

1. Identify the **exact Ryujinx build** and **BOTW game version**.
2. Instrument a *locally built* Ryujinx fork with an explicit,
   versioned IPC interface to read guest player pose/collision and apply
   player state. Avoid guessing process memory offsets.
3. Find BOTW player position, facing, teleport/cell loading state and
   camera control points **for that game version**, and verify readings
   while the player moves. Record the coordinate system and scale.
4. Implement a guest adapter compatible with the existing SkyCraft
   shared-memory protocol. Translate BOTW units and axes using
   `botw/bridge_math.py`; the identity map is a test fixture, **not**
   a correct BOTW transform.
5. Export terrain and collision around Link to Minecraft's physics.
   Reconcile movement/teleport, stop both physics engines fighting,
   and handle cutscenes/load transitions.
6. Align Minecraft camera with BOTW camera; then composite the hand/HUD
   into the emulator output. Neither GPU sharing nor renderer injection
   is implemented.
7. Test walking, turning, jumping, slopes, saving/reloading, menus and
   transitions *in an actual game session*.

This work cannot legitimately be called playable until steps 1–7
are implemented and tested. More advanced block placement, combat,
destruction and VR are later milestones.

## Current development test

With Python 3.10+:

```sh
python -m unittest discover -s botw -p "test_*.py" -v
```

The test suite exercises reversibility of calibrated coordinate transforms.
It does not require or modify BOTW, Minecraft, Ryujinx or save data.

## Compatibility notes

The Minecraft Fabric half currently assumes SkyCraft's Skyrim process,
shared-memory lifecycle and naming, and may need refactoring before it
can connect to another host. Preserve upstream protocol consistency:
if struct layouts change, bump the protocol version and update
`fabric/src/main/java/dev/skycraft/link/Proto.java` together with
`protocol/skycraft_protocol.h`.

No unverified BOTW memory addresses or Ryujinx hook points are included.
