# BotwCraft native BOTW 1.5.0 rendering pipeline

This is **in-game NVN rendering code**, not a Windows overlay. Source is
MIT-licensed SkyCraft (Fabric) plus WiiXLaunch BOTW (Switch 1.5.0).

## Actual program flow

1. Original SkyCraft Fabric game produces **RenSection** packets containing
   Minecraft block triangles in protocol v11's 64 MiB RenderRing.
2. `botw/native_mesh_bridge.py` consumes the real ring, caches block-section
   data, projects up to 170 triangles against Minecraft's current camera
   and packs at most 510 vertices into a bounded, checksummed `BWC1` frame.
3. The Python bridge writes `frame.bin` via an atomic replacement into
   Ryujinx's virtual SD card, at:
   `sdcard/WiiXLaunch/mods/01007EF00011E000/botwcraft/frame.bin`.
4. The native WiiXLaunch BOTW guest (AArch64) imports
   `wiixl.core::GameReadFile` and `botw.gfx::RegisterDraw/DrawMesh`.
   It registers a **native NVN draw callback**, polls `frame.bin` about
   5 times per second, verifies version, payload size, triangle count, hash
   and finite positions, and draws the validated vertices using BOTW's own
   native NVN command buffer. Invalid packets cannot alter the previous
   verified GPU vertex buffer.
5. A stale Minecraft heartbeat clears the geometry from the native renderer,
   and clean Python exit writes an empty frame.

The code remains useful when the 1.5.0 Link camera/physics interface is ported.
It is separate from the old `hud_overlay.py` experiment.

## Binary BWC1 (little-endian)

```text
offset  size  meaning
0x00     4    BWC1 magic (0x31435742)
0x04     4    version = 1
0x08     4    frame ID (monotonic u32)
0x0c     4    vertices (0..510, multiple of 3)
0x10     4    FNV-1a u32 over the following vertex bytes
0x14    12    reserved/zero
0x20    n*32  n vertices (x,y,z,w,nx,ny,nz,nw; float32 each)
```

A vertex stream is untextured native normals-shader geometry, not yet
Minecraft's textured material/atlas pipeline.

## Critical limitations before this is actually playable

**BOTW Switch 1.5.0 player position is unsupported in the current WiiXLaunch
`botw.player` surface.** Its `SupportsPosition()` returns false; even though
WiiXLaunch recognises build 1.5.0, it cannot yet emit reliable Link poses.
The Java Minecraft world can only follow Zelda when the native guest provides
its actual state to the existing host bridge. There is currently no real
Link-to-Minecraft pose feed on that Switch build.

**Projection currently uses Minecraft's pose, NOT Zelda's view-projection and
depth buffer.** A rendered block will be part of the native Zelda NVN frame,
but alignment/occlusion is not guaranteed. This is not SkyCraft-level block
rendering yet. Switch guest reading Ryujinx's SD file and BOTW 1.5.0 gameplay
must still be verified in an actual emulator session.

The needed next steps are:

- Resolve/validate the Link player singleton and transform on Switch 1.5.0;
  do not reuse any 1.0.0 or Wii U address.
- Feed authoritative Link pose and terrain collision into Fabric, and use
  Minecraft physics to update Link in the game engine.
- Supply Zelda's actual view-projection/depth matrices to the native renderer,
  and load SkyCraft's block atlas/textures rather than normals only.
- Confirm correct SD mounting and mod installation on Ryujinx 1.3.3.

## Developer execution

The normal native ZIP includes the Python script as
`bridge/native_mesh_bridge.py`. `bridge/launcher.py` starts it with the
shared-memory host and log relay.

Ryujinx usually uses `%APPDATA%\\Ryujinx\\sdcard`; when its data directory is
portable/custom, set `BOTWCRAFT_SDROOT` to the actual virtual SD folder. The
script refuses an absent folder rather than creating a fake Ryujinx data tree.

To inspect the fully automated native and protocol tests:
`https://github.com/Rom4203/BotwCraft/actions`

No Nintendo game binaries, encryption keys, copyrighted textures or assets
are included.
