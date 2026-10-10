"""Fail-closed guards for unverified BOTW Switch game hook offsets.

Never make an unknown game build "known" simply to allow hooks. A recognized
build still needs actual version-specific offsets verified separately.
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
WIIXL = ROOT / "WiiXLaunch"
PLAYER = WIIXL / "vendor" / "wiixlaunch-botw" / "include" / "wiixlaunch" / "botw" / "game" / "player.hpp"
MAIN = WIIXL / "src" / "main.cpp"

OLD_PLAYER = """        impl::PlayerTickHook::Install(0x873374, 0x02d67cf4);
        WIIXL_LOG("Player: per-frame tick hook installed");
        return true;"""
NEW_PLAYER = """#if WIIXL_SWITCH
        WIIXL_LOG("Player: disabled unverified Switch player tick hook");
        return false;
#else
        impl::PlayerTickHook::Install(0x873374, 0x02d67cf4);
        WIIXL_LOG("Player: per-frame tick hook installed");
        return true;
#endif"""
LEGACY_GUARD = """#if !WIIXL_SWITCH
        impl::PlayerTickHook::Install(0x873374, 0x02d67cf4);
#else
        // BotwCraft: unverified Switch PlayerTick offsets must not be installed.
#endif
        WIIXL_LOG("Player: per-frame tick hook installed");
        return true;"""

OLD_NV = """#if WIIXL_SWITCH
    NVN::Init();
#elif WIIXL_CEMU"""
NEW_NV = """#if WIIXL_SWITCH
    // BotwCraft: do not install version-specific NVN hooks into BOTW 1.0.0.
    // The host logs unknown builds. Recognition is necessary but not proof
    // of compatibility with every graphics API offset.
    if (WiiXLaunch::GameVersion::Recognised()) {
        NVN::Init();
    } else {
        WIIXL_LOG("BotwCraft: graphics hooks skipped - unrecognised BOTW build");
    }
#elif WIIXL_CEMU"""

def guard(path, original, replacement):
    if not path.is_file():
        raise RuntimeError(f"Required source file missing: {path}")
    data = path.read_text(encoding="utf-8")
    if replacement in data:
        print(f"[OK] Already guarded: {path.name}")
        return False
    legacy = path == PLAYER and LEGACY_GUARD in data
    chosen = LEGACY_GUARD if legacy else original
    if data.count(chosen) != 1:
        raise RuntimeError(f"Refusing unsafe edit: expected one unmodified anchor in {path}")
    backup = path.with_name(path.name + ".before_botwcraft_v100_guard")
    if not backup.exists():
        shutil.copy2(path, backup)
    elif not legacy:
        raise RuntimeError(f"Backup exists but guard is absent; refusing to overwrite: {backup}")
    path.write_text(data.replace(chosen, replacement, 1), encoding="utf-8")
    print(f"[OK] Protected: {path}; backup: {backup}")
    return True

def main():
    # Check both anchors before changing either file.
    for path, original, replacement in ((PLAYER, OLD_PLAYER, NEW_PLAYER),
                                        (MAIN, OLD_NV, NEW_NV)):
        if not path.is_file():
            raise RuntimeError(f"Missing: {path}")
        data = path.read_text(encoding="utf-8")
        if replacement not in data and data.count(original) != 1 and not (
            path == PLAYER and data.count(LEGACY_GUARD) == 1):
            raise RuntimeError(f"Unexpected upstream revision: {path}")
    guard(PLAYER, OLD_PLAYER, NEW_PLAYER)
    guard(MAIN, OLD_NV, NEW_NV)
    print("[BotwCraft] Switch v1.0.0 hooks fail closed; mod gameplay is NOT enabled.")

if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as exc:
        raise SystemExit(f"[ERROR] {exc}")
