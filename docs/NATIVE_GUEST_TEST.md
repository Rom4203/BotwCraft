# Compile the first actual BOTW guest module (Switch)

The repository now includes a minimal **native WiiXLaunch .wxlm module** at
`botw/guest_mod/`. Its sole behavior is to log when the game-side loader
calls the module entry point. **It does not yet read Link's position or
connect Minecraft.** It is a real Switch/AArch64 module source file, not
a keyboard injector.

## Build prerequisites

- A working WiiXLaunch host and SDK targeting Switch. The upstream
  WiiXLaunch docs report that the Switch host and mods work in Ryujinx:
  https://github.com/BladesawStudios/WiiXLaunch/blob/main/docs/overview.md
- devkitPro with devkitA64 and Python.
- BOTW Switch game executable build supported by the host. **Do not assume**
  the prebuilt host supports v0 (1.0.0). Check its game target and build ID.

## Compile

Using a WiiXLaunch checkout with its SDK:

```powershell
python path\to\WiiXLaunch\sdk\scripts\build_mod.py --source botw\guest_mod --target switch
```

Expected module output (path may depend on SDK revision):
`botw/guest_mod/build/switch-mods/botwcraft.wxlm`.

## Deploy only with a verified compatible host

For BOTW title ID `01007EF00011E000`, WiiXLaunch's documented LayeredFS
mod location is:

```
<ryujinx-mod-folder>/romfs/WiiXLaunch/mods/botwcraft.wxlm
```

A `.wxlm` cannot operate without the WiiXLaunch Switch **host loader**,
which is distributed/built separately. The host must be compatible with
the exact game executable. Do not randomly install an NSO replacement
built for a newer BOTW revision: it can crash or corrupt running state.

## What success looks like

A host loader log line confirming that `botwcraft` loaded, followed by:

`BotwCraft: Switch native module loaded; waiting for v0 player hooks`

This checks that our AArch64 code executes *inside BOTW*. It is **not**
a position-reading test; there is no verified Switch v0 player position
address to read yet. WiiXLaunch's BOTW feature table says
`Player::SupportsPosition == false` on Switch.

## Next genuine milestone

Determine the BOTW v0 NSO Build ID, resolve the player's actual live
transform and per-tick function, and implement a guest hook against that
verified build. Then implement the guest/host transport and wire it into
SkyCraft Fabric. The host-side Python bridge is separate and is not
yet reached by this guest module.

Source: https://github.com/BladesawStudios/WiiXLaunch/blob/main/docs/sdk/getting-started.md
