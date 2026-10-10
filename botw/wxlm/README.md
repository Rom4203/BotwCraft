# BotwCraft NX150 — native actor and first-person camera

This folder contains the standalone `bwc_pose.wxlm` AArch64 module,
compiled by `.github/workflows/botw-native-switch.yml`.
It runs alongside the original `botwcraft.wxlm`/subsdk9.

## What is implemented

1. WiiXLaunch `botw.player` player-tick and module-owned BDP1 mailbox (no NVN gfx overlay registration or per-frame GPU injection).
   The guest writes an acknowledgment proving that the actual game frame
   consumes the Minecraft-authoritative input. The Windows bridge remains **read-only** while Link is not spawned or Minecraft is inactive; it no longer sends thousands of disarmed packets via GDB.
2. On a live `botw.player` tick, exposes Link's measured NX150 Actor::mMtx position as a 20-byte read-only guest snapshot at mailbox offsets 176–195. Rust reads this snapshot via Ryujinx GDB rather than relying on stale log relay positions.
3. Link placement through the public `botw.actor` `SetMtx` / `WarpTo`
   interfaces, with an experimental NX150 actor-virtual fallback if they
   return unsupported. The fallback checks the player actor's **NX150
   `+0x398` matrix** against real Link telemetry before calling virtual
   `setMtx` (#85). It uses the Wii U setMtx ABI as a hypothesis, **not
   a verified Switch callable signature**.
4. Model-only hiding by shrinking `gsys::Model` scale at `+0x88`
   (actor's model pointer is NX150 `+0x4E0`) and restoring on disarm.
5. NX150 native camera hook at `sead::LookAtCamera::doUpdateMatrix`
   (module-relative `0x00B1BE7C`). The actual address comes from
   `wiixl.call.ResolveTarget`, **not** `wiixl.core.ImageBase()`,
   which is zero on Switch. It applies Minecraft eye and forward to Zelda's
   active `LookAtCamera` before Zelda computes the final view matrix.
   The hook filters out cameras far away from Link.
6. Guest result codes accessible from Windows Rust bridge:
   `state=4` means not fully applied; `state=5` means Link transform
   called; `state=6` means camera called; `state=7` means both were
   called. `warp_method=3` is the NX150 vtable fallback.

## Build

Use WiiXLaunch's Switch SDK with devkitPro devkitA64:

```
python3 sdk/scripts/build_mod.py --source botw/wxlm --target switch --wiixlaunch sdk
```

The official GitHub Actions job builds and publishes the binary automatically.
The Windows Rust test overlay is built in the dependent CI packaging job.

## Runtime limitations

**Successful compilation does not establish playability.** The virtual
`setMtx` ABI, camera hook and model scaling have NOT been tested against
a real Ryujinx BOTW 1.5.0 session. This module may crash the game; back up
the Zelda save, and test only in a disposable session.

For now, Zelda collisions are not fed back into Minecraft. Minecraft
positions remain authoritative and the actor transform is reapplied on
each guest player tick, to keep a creative-mode flight test possible even
without collision integration.

Sources for NX150 layout and function addresses:
- https://github.com/zeldaret/botw/blob/master/src/KingSystem/ActorSystem/actActor.h
- https://github.com/zeldaret/botw/blob/master/lib/gsys/include/gsys/gsysModel.h
- https://github.com/zeldaret/botw/blob/master/data/uking_functions.csv
- https://github.com/BladesawStudios/WiiXLaunch/tree/main/sdk

## Ryujinx 2026-10-10 second crash investigation

User's `botwcraft(4).log` got beyond the old unmounted-SD filesystem abort and successfully loaded WiiXLaunch and the module, but crashed after 1:23 with a Ryujinx JIT `System.AccessViolationException` in `SignalMemoryTrackingImpl/WriteGuest`.
At crash time host logs still showed `BDP1 disarmed`, `LinkTelemetry=false`, `applied=0`, and hundreds of extra `WiiXLaunch: Injected frame #...` events. **No actor warp was executed.**

Mitigations: do not install the NVN graphics callback at all; register the already-installed player tick instead. Additionally Rust now reads Link XYZ from guest mailbox without writing until both real Link and Minecraft are alive. On leaving gameplay, send a single disarm instead of endless disabled frames. This addresses documented potentially unsafe behavior but cannot prove a specific root cause or eliminate unrelated Ryujinx bugs without a real runtime test.
