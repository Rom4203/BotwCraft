# BotwCraft Switch rendering: safe Rust implementation

The stable user ZIP has a **compiled-only** Rust bridge and compositor.
This code is a new isolated graphics foundation, **not yet a playable
in-game block renderer**. Neither the stable ZIP's existing executable nor
the original Skyrim/SkyCraft integration is replaced.

Minecraft already publishes its actual meshes/UVs/atlas in the SkyCraft_v11
render ring. The Rust world cache decodes these messages, retains mesh
sections, uses distance culling, and uploads **only changed sections** to
GPU buffers. The shader applies nearest-neighbor atlas sampling, AO/tint and
block lighting. It uses a real depth-tested triangle pipeline rather than
generating PNGs or a per-block bitmap.

Integrating this into *Zelda's frame* still requires a Ryujinx Vulkan or BOTW
NVN host that makes **both the scene color target and game depth target**
accessible. A separate transparent Windows window cannot guarantee correct
occlusion and should not be used as the final solution.

The existing bridge, player collision, installer, saves and GDB path must be
kept intact. In particular, only **one** consumer can advance the render-ring
tail, and a second GDB client cannot be introduced without refactoring the
existing Rust bridge.

Commands (in a Windows Rust environment):
`cargo test --manifest-path botw/rust_world/Cargo.toml`
`cargo check --manifest-path botw/rust_world/Cargo.toml --features gpu`

The source-only crate is not auto-launched by the stable distribution.
