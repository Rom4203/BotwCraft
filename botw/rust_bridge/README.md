# BotwCraft Rust host bridge

A native Rust replacement for the Python **host + Minecraft position producer**.
It is **not** a separate Minecraft server, and does not change the Minecraft
Fabric mod or the independent Rust gameplay window.

## Compatible paths

- Owns \`Local\SkyCraft_v1\` (SkyCraft v11) with the original layout.
- Receives Ryujinx measured player position from local TCP JSON lines on 127.0.0.1:39847.
- Reads real Minecraft pose from the shared memory; maps it to the anchored BOTW
  coordinate system and publishes a 112-byte BDP1 seqlock record at 0x18000.
- Publishes only while Minecraft and BOTW telemetry are fresh and the Minecraft
  world, FPS and input flags permit gameplay; does not require creative fly mode.
- Retains the compositor as the single writer of the keyboard/mouse input ring,
  rather than introducing concurrent writers or inventing a controller.
- Logs periodic diagnostics with \`[RUST_BRIDGE]\`.

## Build

From \`botw/rust_bridge\` on Windows:

\`\`\`
cargo build --release
target\release\botwcraft-rust-bridge.exe
\`\`\`

**Do not run the old Python \`host_bridge.py\` simultaneously**: only one process
may own the shared memory mapping and TCP port.

The current Python \`ryujinx_log_relay.py\` can still post genuine Zelda
positions to the Rust bridge; it should be retained until its log parsing is
ported. Likewise, the real AArch64 WiiXLaunch engine hook that actually warps
Link and updates LookAtCamera remains unfinished. Moving the host producer to
Rust does **not** make the incomplete BOTW mod playable by itself.

## Incoming line protocol

\`\`\`json
{"type":"pose","x":100.0,"y":250.0,"z":-20.0,"yaw":90.0,"pitch":0.0,"world":1}
\`\`\`

\`{"type":"minecraft"}\` returns the latest Minecraft state. Responses are
newline-delimited JSON. Game pose packets must be real, measured BOTW telemetry.
The former \`type=input\` TCP command is intentionally refused while the compositor
owns the input ring; only one writer may push input events.
