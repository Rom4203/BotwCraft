# BotwCraft Rust scene relay — source, not a playable renderer

This Rust crate reads the actual Minecraft (SkyCraft v11) render ring and
preserves the complete block atlas, UV coordinates, face colors, lighting
values, triangle ordering and 16-block section coordinates.

It exports BWC2 packets in WORLD coordinates. It intentionally does not
project Minecraft geometry using a guessed Zelda FOV, replace the existing
Rust compositor executable, or write to Ryujinx's guest memory. Zelda-native
camera and depth composition still require a verified BOTW 1.5.0 render hook.

## Why this exists

The ZIP used for the Windows session included compositor/Cargo.toml and
botwcraft-compositor.exe, but NO compositor/src/*.rs; therefore the binary
cannot safely be rebuilt from that package. This is a new, separate Rust
module, added on an experimental branch rather than replacing the existing
working input/collision bridge.

The existing botw/native_world_scene.hpp already defines BWC2. This crate
encodes that precise 56-byte header and 32-byte vertex format. It does not
replace the BWC2 guest API or invent a Zelda camera matrix.

## Build and tests

cd botw/rust-scene-relay
cargo test
cargo build --release

On Windows, run the bridge and the Minecraft mod FIRST. The relay is a
diagnostic module and must be the ONLY reader of the SkyCraft render ring:
do not run bridge/blocks_overlay.py or native_mesh_bridge.py simultaneously.

With no arguments the executable prints scene/atlas diagnostics only.
To produce a debug packet, pass both a calibrated 4x4 affine world transform
and an output directory:

botwcraft-rust-scene-relay --transform calibrated-minecraft-to-hyrule.txt --out debug

The matrix file contains four rows of four finite floats, ROW-major; the last
row must be 0 0 0 1. It must be MEASURED, not guessed from FOV. For safety,
debug output is never sent to Ryujinx by this tool.

## Next integration work

1. Recover or recreate the source of the Windows compositor (only the binary
   was present in the uploaded 2026-10-12 ZIP).
2. Separate GUI/HUD commands from the Minecraft scene at Gui/GuiGraphics
   rendering time and capture the HUD on a transparent render target.
   Do NOT key black pixels out of a completed Minecraft screenshot.
3. Supply Zelda's actual view/projection and depth. Project WORLD meshes on
   the GPU using that matrix, and depth-test against Zelda's scene.
4. Keep the Minecraft window rendering normally when connected. Blend the
   separate hand and GUI targets AFTER world geometry.
5. Integrate and validate in Ryujinx 1.3.3 with BOTW 1.5.0. The existing
   native SD/ROMFS read path previously caused guest crashes; do not enable
   it by default.

No Nintendo assets or game binaries are distributed in this source crate.
