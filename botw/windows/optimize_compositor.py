"""Bound compositor texture upload and WGC frame copies without changing input latency.

Install over the user's existing Rust third-window SOURCE before cargo build.
The Minecraft input ring is read/written every UI frame as before; only the
expensive 1080p RGBA texture work is rate-limited.

Python 3: python optimize_compositor.py D:\...\BotwCraft\compositor
"""
from pathlib import Path
import sys

def replace_once(content: str, before: str, after: str, label: str) -> str:
    if after in content:
        return content
    if content.count(before)!=1:
        raise ValueError(f"{label}: source layout changed; refusing unsafe patch")
    return content.replace(before,after,1)

def patch(root: Path) -> None:
    capture=root/"src"/"capture.rs"
    main=root/"src"/"main.rs"
    if not capture.is_file() or not main.is_file():
        raise FileNotFoundError("Need the original Rust compositor source directory")

    s=capture.read_text(encoding="utf-8")
    s=replace_once(s,
      "use std::sync::mpsc::SyncSender;",
      "use std::sync::mpsc::SyncSender;\nuse std::time::{Duration, Instant};",
      "capture Instant import")
    s=replace_once(s,
      "struct Capture {\n    tx: SyncSender<PixelFrame>,\n}",
      "struct Capture {\n    tx: SyncSender<PixelFrame>,\n    last_frame: Instant,\n}",
      "capture pacing field")
    s=replace_once(s,
      "Ok(Self { tx: ctx.flags })",
      "Ok(Self { tx: ctx.flags, last_frame: Instant::now() - Duration::from_millis(20) })",
      "capture initialization")
    s=replace_once(s,
      "        let width = frame.width() as usize;",
      """        // Ryujinx may render 120 Hz even when Minecraft and the WGPU
        // compositor cannot consume frames that quickly. Avoid allocating
        // and copying 8 MiB of RGBA for frames dropped by the 2-slot queue.
        // This caps copies near 60 Hz without delaying input events.
        if self.last_frame.elapsed() < Duration::from_millis(16) {
            return Ok(());
        }
        self.last_frame = Instant::now();
        let width = frame.width() as usize;""",
      "capture copy pacing")
    capture.write_text(s,encoding="utf-8")

    s=main.read_text(encoding="utf-8")
    s=replace_once(s,
      "    last_reconnect: Instant,\n",
      "    last_reconnect: Instant,\n    last_hud_upload: Instant,\n",
      "HUD pacing field")
    s=replace_once(s,
      """        if let Some(map) = self.hud_map.as_mut() {
            if let Some(next) = map.next_frame() {
                self.hud_size = (next.width, next.height);
                upload(ctx, &mut self.hud_texture, next, "minecraft-actual-hud");
            }
        }
""",
      """        // A 1080p HUD RGBA upload every 16ms competes with Minecraft's
        // actual render thread. Limit only the texture COPY to ~30 Hz.
        // Keyboard and mouse events below still run on every UI update.
        if self.last_hud_upload.elapsed() >= Duration::from_millis(33) {
            if let Some(map) = self.hud_map.as_mut() {
                if let Some(next) = map.next_frame() {
                    self.hud_size = (next.width, next.height);
                    upload(ctx, &mut self.hud_texture, next, "minecraft-actual-hud");
                }
            }
            self.last_hud_upload=Instant::now();
        }
""",
      "HUD texture upload pacing")
    s=replace_once(s,
      "        last_reconnect:Instant::now()-Duration::from_secs(2),",
      "        last_reconnect:Instant::now()-Duration::from_secs(2),\n        last_hud_upload:Instant::now()-Duration::from_secs(1),",
      "HUD pacing init")
    main.write_text(s,encoding="utf-8")
    print("Rust compositor optimized: 60Hz WGC copies, 30Hz HUD; input unchanged")

if __name__=="__main__":
    patch(Path(sys.argv[1] if len(sys.argv)>1 else "compositor"))
