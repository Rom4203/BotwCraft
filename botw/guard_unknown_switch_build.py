"""Do not install any filesystem/game hooks on an unknown Switch build.

Ryujinx 1.3.3 log 2026-10-09: BOTW is actually v1.6.0, CRC 0x6811B941.
WiiXLaunch was built for 1.5.0 CRC 0xA982D2BC. The game-module loader
must therefore skip even its filesystem hooks on this unexpected build.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "WiiXLaunch" / "src" / "switch_entry.cpp"

INCLUDE_FROM = "#include <wiixlaunch/generated_host.hpp>"
INCLUDE_TO = INCLUDE_FROM + "\n#include <wiixlaunch/game_version.hpp>"
FN_FROM = '''extern "C" void WiiXLaunch_SwitchLoadPoint() {
    // Before either load point, so a game that mounts romfs before its first'''
FN_TO = '''extern "C" void WiiXLaunch_SwitchLoadPoint() {
    // The game version gate protects everything, not just the renderer.
    // Even nn::fs hooks and file lookups require a verified Switch executable.
    if (!WiiXLaunch::GameVersion::Recognised()) {
        WIIXL_LOG("BotwCraft: unsupported BOTW build, skipping native hooks and module load");
        return;
    }
    // Before either load point, so a game that mounts romfs before its first'''


def guard():
    if not MAIN.is_file():
        raise RuntimeError("WiiXLaunch src/switch_entry.cpp missing")
    text = MAIN.read_text(encoding="utf-8")
    if FN_TO in text:
        if INCLUDE_TO not in text:
            raise RuntimeError("Unsupported game guard present without version include")
        print("[BotwCraft] Unsupported Switch game guard already installed")
        return False
    if text.count(FN_FROM) != 1 or text.count(INCLUDE_FROM) != 1:
        raise RuntimeError("Switch entry changed: refusing an unverified game-hook patch")
    text = text.replace(INCLUDE_FROM, INCLUDE_TO, 1).replace(FN_FROM, FN_TO, 1)
    MAIN.write_text(text, encoding="utf-8")
    print("[BotwCraft] Unsupported Switch build will NOT enter game loader")
    return True


if __name__ == "__main__":
    try:
        guard()
    except (OSError, RuntimeError) as exc:
        raise SystemExit("[BotwCraft] ERROR: " + str(exc))
