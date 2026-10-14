# Target: BOTW Switch cartridge v0 (base game 1.0.0)

Status: **not playable / reverse engineering required**.

Owner provided an XCI dump named `The Legend of Zelda_ Breath of the Wild v0 (01007EF00011E000)`. The base game's content/title identifier is 01007EF00011E000. Do not guess the executable's **Build ID** from the title ID; determine the actual NSO build ID before applying any hooks.

## Preconditions
- Ryujinx fork and binary version must be recorded, independently of Nintendo Switch system firmware (17.0.1 is a firmware number).
- Personal `prod.keys` are generally necessary to run XCI content in Ryujinx. Do not place keys, decrypted NSOs, XCI, Nintendo assets or firmware in this public repository.
- User owns physical BOTW cartridge. No update or DLC is required just to define a target; no assumption that WiiXLaunch Switch offsets support game v0.
- Capture Ryujinx emulator log, game version and NSO build ID locally before enabling guest hooks.

## Native integration plan
1. Verify whether WiiXLaunch BOTW supports exact Switch v0 executable build ID. Do not use offsets from 1.5/1.6 blindly.
2. Build a minimal ExLaunch/WiiXLaunch BOTW mod that logs a hook invocation. Compile specifically for AArch64 Nintendo Switch guest, load via Atmosphere-style game mod directory in Ryujinx if fork supports it.
3. Find v0's Link player transform, update ordering, and loading/cutscene checks. WiiXLaunch explicitly marks `Player::SupportsPosition` **false** on Switch; implement and validate this missing functionality.
4. Implement native guest-to-host transport. A Windows named mapping is **not directly visible** to guest AArch64. The bridge must transport data via an emulator-supported guest facility (or a carefully scoped emulator modification).
5. Add guest collision -> Minecraft Fabric voxel shapes. Movement must originate in Minecraft physics, with BOTW player puppet synchronized.
6. Add Minecraft camera and HUD/hand rendering. Do not claim playable until tested with real BOTW and Minecraft clients.

## Current source locations
- `fabric/`: existing SkyCraft Fabric logic (still Skyrim-dependent in places)
- `protocol/`: existing SkyCraft shared memory
- `botw/native/botw_adapter.hpp`: native guest integration interface (unimplemented)
- `botw/host_bridge.py`: host transport endpoint (guest is not connected)
- `docs/BOTW_MOD_API.md`: WiiXLaunch integration design

## Known external references
- https://github.com/BladesawStudios/WiiXLaunch
- https://github.com/BladesawStudios/wiixlaunch-botw
- https://docs.ryujinx.app/guides/setup-guide/
- https://zeldamods.org/wiki/Help:Using_mods

No direct keyboard/gamepad injection is part of the chosen architecture. The prior `controller_smoke_test.py` is a separate diagnostic only.
