"""Remove unsafe version-mismatched BOTW player tick install from Switch host builds.

This deliberately disables player tick on *all* Switch versions pending a verified
build-specific hook. It does not implement movement and does not touch Ryujinx.
"""
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
PLAYER = ROOT / "WiiXLaunch" / "wiixlaunch-botw" / "include" / "wiixlaunch" / "botw" / "game" / "player.hpp"
OLD = "        impl::PlayerTickHook::Install(0x873374, 0x02d67cf4);"
NEW = """#if !WIIXL_SWITCH
        impl::PlayerTickHook::Install(0x873374, 0x02d67cf4);
#else
        // BOTW Switch tick addresses are not verified for v1.0.0.
        // Never patch the v1.5.0/Wii U address into Switch v1.0.0.
#endif"""
def main():
    if not PLAYER.is_file():
        raise SystemExit(f"Cannot find WiiXLaunch player header: {PLAYER}")
    source = PLAYER.read_text(encoding="utf-8")
    if NEW in source:
        print("[BotwCraft] Guard already installed; no change")
        return
    if source.count(OLD) != 1:
        raise SystemExit("[BotwCraft] Expected tick install not found exactly once; no change")
    backup = PLAYER.with_suffix(".hpp.before_botwcraft_v100_guard")
    if backup.exists():
        raise SystemExit(f"[BotwCraft] Backup already exists without guard; refusing to overwrite: {backup}")
    shutil.copy2(PLAYER, backup)
    PLAYER.write_text(source.replace(OLD, NEW), encoding="utf-8")
    print(f"[BotwCraft] Unsafe Switch PlayerTick hook disabled: {PLAYER}")
    print(f"[BotwCraft] Original saved: {backup}")
    print("[BotwCraft] Rebuild the HOST. This is a crash guard, NOT a playable mod.")
if __name__ == "__main__":
    main()
