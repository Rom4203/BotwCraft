# BotwCraft — Windows transport & HUD prototype

**Status: not a playable Minecraft-in-BOTW port.** This branch implements real
pieces of the bridge, but it does not yet have verified BOTW Switch 1.0.0
player/physics/game-world hooks or a native block renderer.

## Components now implemented

- **Native Switch modules:** `subsdk9` host and `botwcraft.wxlm` guest, compiled
  with WiiXLaunch. The old Wii U / different-game-version PlayerTick and NVN
  hooks are prevented from installing in an *unrecognised* BOTW v1.0.0 executable.
  The protected `Player::Init` returns **false** instead of pretending to work.
- **SkyCraft v11 shared memory:** `botw/host_bridge.py` owns
  `Local\\SkyCraft_v1`, accepts validated pose and input packets, forwards
  16-byte keyboard/mouse events into the existing Minecraft Fabric input ring,
  and reports the real `McState` coordinates, rotation and frame number.
  The heartbeat uses Windows `GetTickCount64` and expires if game poses stop.
- **Windows input:** `botw/control_bridge.py` captures keys only when Ryujinx
  is in focus, mirrors key/button transitions into Minecraft, and can drive a
  ViGEm X360 virtual controller. If Minecraft sends fresh in-world positions,
  planar velocity becomes camera-relative left-stick intent (with teleport
  rejection); otherwise it falls back to regular keyboard joystick mapping.
  A virtual controller requires **vgamepad + ViGEmBus**, selected as Player 1.
- **Windows HUD:** `botw/hud_overlay.py` reads Minecraft's actual shared-memory
  GPU overlay image (HUD, held items, menus) and attempts to draw it in a
  transparent, click-through Win32 window aligned over Ryujinx. It hides stale
  frames. This is **not** a replacement for native depth-tested 3D blocks.
  It has no in-game Windows verification yet.
- **Lifecycle:** `botw/launcher.py` starts and stops the bridge, Ryujinx log
  relay, optional HUD overlay and controller together; all via
  `START_BRIDGE.bat` in the packaged ZIP.
- **ZIP:** `BUILD_AND_PACKAGE.bat` compiles WiiXLaunch and SkyCraft/Fabric,
  and `package_botw_windows.py` archives both mods, the bridge and HUD.

## Actual program flow

```
Ryujinx log with verified BOTW pose (not yet available on 1.0.0)
  -> ryujinx_log_relay.py
  -> host_bridge.py
  -> SkyCraft v11 shared memory
  -> Fabric Minecraft reads host pose, reads keyboard, runs its own physics
  -> SkyCraft McState/overlay/render ring
  -> host_bridge.py <- control_bridge.py (reads McState)
  -> virtual X360 controller -> Ryujinx player input (optional)

MC overlay pixels -> hud_overlay.py -> desktop window above Ryujinx
```

The **host ↔ Fabric** transport is implemented and unit-tested. The **guest
BOTW ↔ host** game-state interface is NOT implemented. WiiXLaunch's
`wiixl.net` surface explicitly is unavailable on Switch, so the host cannot
simply open a TCP connection from the guest module. On the actual logged BOTW
1.0.0 build the player tick patch crashed at `U-King.nss+0x873378`; its
0x873374 address was from another target, so it has been disabled.

## Remaining work to reach a genuinely playable SkyCraft-grade port

1. Reverse engineer and validate exact BOTW Switch 1.0.0 **player/physics
   addresses and game-thread update phase**, gated by executable fingerprint.
2. Implement reliable Switch guest-to-Windows pose/collision export and
   Windows-to-Switch **movement or transform**. Controller emulation is only
   an interim input workaround, not an authoritative transform setter.
3. Extract true terrain/building collision geometry for Minecraft physics.
4. Render Minecraft **world meshes** with occlusion/depth in BOTW's NVN renderer
   and map placed/broken blocks to game world / saves.
5. Test in a real Ryujinx/BOTW/MC session (including saves, teleports, menus).

Without these, this is an SDK/protocol/UI demonstration, NOT a playable release.

## Tests and safety

Run `python -m unittest discover -s botw -p 'test_*.py' -v`; GitHub Actions
runs the protocol and packaging tests. The executable scripts will **never
install themselves into Ryujinx**; back up saves, use a separate test profile
and move the mod folder completely out of Ryujinx's mods path to disable it.

No Nintendo assets, firmware, decryption keys or emulator binaries are included.
SkyCraft gameplay code remains attributed to chasmlol under its MIT license.
