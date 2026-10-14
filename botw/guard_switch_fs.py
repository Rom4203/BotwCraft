"""Prevent Ryujinx fatal FS abort when Switch SD debug mount is unavailable.

Observed Ryujinx 1.3.3 BOTW 1.6.0:
  MountSdCardForDebug("sd") -> 0x320002 (not mounted)
  DirectoryExists("sd:/...") -> nn::diag::Abort ResultFsNotMounted.

WiiXLaunch's Candidate builder previously passed *explicit* sd:/ paths
through unconditionally. Reject them when SD mounting failed; allow the
already-mounted ROMFS path to continue loading .wxlm modules.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "WiiXLaunch" / "include" / "wiixlaunch" / "fs.hpp"

BEFORE = """    out[0] = path;
    out[1] = out[2] = out[3] = nullptr;
#if WIIXL_SWITCH
    // A Switch has no /vol/content."""

AFTER = """    out[0] = path;
    out[1] = out[2] = out[3] = nullptr;
#if WIIXL_SWITCH
    // Switch nn::fs does NOT return an ordinary error for file lookups
    // on a mount that was never established. It calls nn::diag::Abort
    // (ResultFsNotMounted), killing BOTW before the game can even start.
    // Ryujinx 1.3.3 can reject MountSdCardForDebug with 0x320002.
    // A path already written as sd:/ must therefore be omitted entirely
    // if the attempt to mount it failed. Explicit ROMFS paths remain valid.
    if (IsSdPath(path) && !g_FSClientReady) {
        out[0] = nullptr;
        return;
    }
    // A Switch has no /vol/content."""


def guard():
    if not SOURCE.is_file():
        raise RuntimeError("WiiXLaunch/fs.hpp absent; run setup_wiixlaunch.py")
    source = SOURCE.read_text(encoding="utf-8")
    if AFTER in source:
        print("[BotwCraft] SD mount failure guard already installed")
        return False
    if source.count(BEFORE) != 1:
        raise RuntimeError("Unexpected WiiXLaunch fs.hpp, aborting unsafe patch")
    SOURCE.write_text(source.replace(BEFORE, AFTER, 1), encoding="utf-8")
    print("[BotwCraft] Unmounted sd:/ path guard installed")
    return True


if __name__ == "__main__":
    try:
        guard()
    except (OSError, RuntimeError) as exc:
        raise SystemExit("[BotwCraft] ERROR: " + str(exc))
