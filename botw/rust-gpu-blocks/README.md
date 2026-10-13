# BotwCraft Rust GPU block renderer

Experimental, separate Windows GPU layer. Does not replace the
working botwcraft-compositor.exe or botwcraft-rust-bridge.exe.

Features:
- SkyCraft v11 REN_SECTION geometry and REN_ATLAS pixels, including animated sprites.
- Actual Minecraft atlas UV, colors, alpha-cutouts and textures on the GPU (WGPU).
- Camera reading through a seqlock; actual GameRenderer FOV and eye position.
- Dynamic viewport matching the existing BotwCraft composite window.
- 24-bit depth buffer for Minecraft blocks, perspective-correct rasterization.
- Click-through, transparent, non-activating Windows overlay (no mouse grab).
- Displays nothing until Minecraft enables BotwCraft's compositor-input flag.
- No guessed Nintendo memory addresses or game modification.

Limitations:
- The renderer is a true GPU 3D rasterizer, but it is still an overlay. It cannot
  depth-test against Zelda terrain, cliffs, buildings or trees without an actual
  Zelda depth texture from the compositor or the native BOTW render pipeline.
- The live exported Minecraft camera FOV can differ from BOTW's visual camera;
  matching both requires a real BOTW camera matrix provider.
- It cannot display below the Minecraft HUD until the mod exports GUI separately
  and the original compositor supplies a separate HUD layer.
- The Python blocks_overlay.py must be disabled when this runs; otherwise both
  applications compete for the same render ring.
- Compile tests run in GitHub Actions; actual Ryujinx output needs local testing.

Build:
  cd botw/rust-gpu-blocks
  cargo build --release

Deployment:
  Set BOTWCRAFT_RUST_BLOCKS=1 before starting the BotwCraft supervisor.
  Install the executable at BotwCraft/compositor/botwcraft-rust-gpu-blocks.exe.
  Supervisor launches the Rust renderer instead of the Python block overlay.

The process never modifies Ryujinx ROMFS/ExeFS or Switch memory.
No Nintendo game assets or copyrighted block texture assets are distributed.

For correct Zelda-native compositing later:
1. Acquire live BOTW view-projection and scene depth from a verified guest hook.
2. Feed both into the Rust renderer's GPU projection and depth interface.
3. Render the Minecraft world between Zelda opaque draw and Minecraft HUD.
