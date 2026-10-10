# Native BOTW bridge — host process (work in progress)

Run on Windows using `py botw/host_bridge.py`. This allocates SkyCraft's
version 11 Windows named shared-memory mapping and exposes a localhost-only
NDJSON command transport on port 39847 for a **future native BOTW game mod**.

Example diagnostic client packet (values must already be Minecraft-space):
`{"type":"pose","x":0,"y":64,"z":0,"yaw":0,"pitch":0,"world":1}`

The server replies with Minecraft's current published player state. It does
not read Ryujinx memory, inject code, manipulate the controller, or write to
BOTW. A real WiiXLaunch guest mod and a verified guest->host transport are
still required. It is not playable and should not be presented as such.

IMPORTANT: The Fabric half may depend on additional Skyrim-specific
initialization besides the shared mapping; successful mapping creation alone
does NOT prove that Minecraft will connect. The mapping is large (~197 MiB)
because the original SkyCraft overlay buffers are retained for compatibility.

The existing `skse/` plugin is not relevant for Ryujinx. Avoid launching
this server alongside Skyrim SkyCraft, because the shared-memory name would
conflict. Use a different `--mapping` and `-Dskycraft.link=...` if needed.

BOTW update/firmware identifiers differ: `17.0.1` is commonly a Switch
system firmware version, **not** a Ryujinx emulator build number.
