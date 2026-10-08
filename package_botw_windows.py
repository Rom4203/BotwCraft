"""Package locally compiled WiiXLaunch BOTW host + guest and BotwCraft bridge.

The archive contains no Zelda files, Ryujinx binary, saves, Nintendo keys, or SDK.
It is an experimental package, NOT a playable Minecraft-BOTW release.
"""
import argparse
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
HOST = ROOT / "WiiXLaunch" / "build" / "switch" / "subsdk9"
GUEST_PATHS = [
    ROOT / "mod" / "botw" / "guest_mod" / "build" / "switch-mods" / "botwcraft.wxlm",
    ROOT / "botw" / "guest_mod" / "build" / "switch-mods" / "botwcraft.wxlm",
]
TARGET = "01007ef00011e000"
FILES = {
    f"ryujinx_mods/contents/{TARGET}/BotwCraft/exefs/subsdk9": HOST,
    "bridge/host_bridge.py": ROOT / "botw" / "host_bridge.py",
    "bridge/ryujinx_log_relay.py": ROOT / "botw" / "ryujinx_log_relay.py",
}

def build_zip(out: Path):
    guest = next((path for path in GUEST_PATHS if path.is_file()), None)
    if guest is None:
        raise FileNotFoundError("Missing botwcraft.wxlm: compile guest first")
    manifest = {**FILES,
        f"ryujinx_mods/contents/{TARGET}/BotwCraft/romfs/WiiXLaunch/mods/botwcraft.wxlm": guest,
        "START_BRIDGE.bat": ROOT / "packaging" / "START_BRIDGE.bat",
        "README_INSTALL.txt": ROOT / "packaging" / "README_INSTALL.txt",
    }
    missing = [str(p) for p in manifest.values() if not p.is_file()]
    if missing:
        raise FileNotFoundError("Missing build inputs:\n" + "\n".join(missing))
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in sorted(manifest.items()):
            archive.write(path, name)
    print(f"Package created: {out}")
    with zipfile.ZipFile(out) as archive:
        assert archive.testzip() is None, "Archive is corrupt"
        print("Archive integrity OK")
    return out

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "BotwCraft-experimental.zip")
    args = parser.parse_args()
    try:
        build_zip(args.output)
    except (OSError, AssertionError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
