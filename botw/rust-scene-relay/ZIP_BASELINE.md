# Recovered executable baseline (uploaded ZIP, 12 October 2026)

The user's original archive is botwcraftlastwork.zip. The latest visually
modified archive is BotwCraft_correctif_visuel_v2.zip. Both were inspected,
not blindly merged into the active BOTW branch.

## Verified byte-for-byte identical between both archives

- compositor/botwcraft-compositor.exe
  - 9,562,112 bytes
  - SHA256 55129bbff86892b71f96e2d152e17638e2f8d62cc75fde95e4c1b9fb6eeb74b9
- bridge/botwcraft-rust-bridge.exe
  - 636,928 bytes
  - SHA256 21ce1163286b68713133870330cb16c13d0b71d23e45cbbf1b1e7faea775ad60

Therefore the latest ZIP did not update either Rust executable. It changed
the Minecraft JAR and introduced the Python rendering overlay.

## Minecraft JAR versions

- botwcraftlastwork.zip: 249,110 bytes, SHA256
  ccc03c9eac4a7a2d62e349b82cdde02f64fa6fe24d436bc4709fa66005fc2cf2
- BotwCraft_correctif_visuel_v2.zip: 252,764 bytes, SHA256
  88d47ff549c3337db97859793642d2028cbedc4153d765f869e7f30db5a02cf1

The last JAR includes independently patched Java classes (BotwHudCleaner,
BotwCameraState). Those are NOT the desired true Minecraft GUI-layer export.
BotwHudCleaner masks rectangular zones of the captured final frame, and
may still corrupt the picture. Do not treat that mask as the final solution.

The user's final compositor/Cargo.toml specifies:
- eframe 0.33 with WGPU and default fonts;
- wgpu 27 with Vulkan and DX12;
- windows-capture 2.0.1.

However no actual Rust src/main.rs was included in either ZIP, and the
searched BOTW GitHub branches did not expose that compositor source at the
tested locations.

## Do not break the working session

- Keep the original native guest modules, player movement, collisions and
  Rust bridge executable intact until a drop-in compositor is built and tested.
- New Rust scene relay runs separately; do not launch alongside Python's
  blocks_overlay.py or native_mesh_bridge.py because each drains the same
  RenderRing tail.
- This branch currently contains source and tests, NOT a replacement executable
  or a directly installable release.
