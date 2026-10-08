"""Build a local distribution ZIP from already compiled BOTW + Minecraft mods.

Never packages Nintendo files, Ryujinx executable, saves, firmware, devkitPro,
or user credentials. This is NOT yet a playable SkyCraft-equivalent port.
"""
import argparse
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
TARGET = "01007ef00011e000"

def find_minecraft_jar(root):
    folder = root / "fabric" / "build" / "libs"
    matches = sorted(
        (p for p in folder.glob("*.jar")
         if p.is_file() and p.name.lower().startswith("skycraft-")
         and not any(word in p.stem.lower() for word in ("sources", "dev", "javadoc"))),
        key=lambda p: p.stat().st_mtime_ns,
        reverse=True,
    )
    if not matches:
        raise FileNotFoundError(
            "Minecraft Fabric mod missing. Build fabric/gradlew.bat remapJar using Java 25 first."
        )
    return matches[0]

def archive_manifest(root):
    guest_options = (
        root / "mod" / "botw" / "guest_mod" / "build" / "switch-mods" / "botwcraft.wxlm",
        root / "botw" / "guest_mod" / "build" / "switch-mods" / "botwcraft.wxlm",
    )
    guest = next((p for p in guest_options if p.is_file()), None)
    if guest is None:
        raise FileNotFoundError("BOTW guest .wxlm missing: compile BOTW guest first")
    prefix = f"ryujinx_mods/contents/{TARGET}/BotwCraft"
    manifest = {
        f"{prefix}/exefs/subsdk9": root / "WiiXLaunch" / "build" / "switch" / "subsdk9",
        f"{prefix}/romfs/WiiXLaunch/mods/botwcraft.wxlm": guest,
        "minecraft_mods/" + find_minecraft_jar(root).name: find_minecraft_jar(root),
        "bridge/host_bridge.py": root / "botw" / "host_bridge.py",
        "bridge/ryujinx_log_relay.py": root / "botw" / "ryujinx_log_relay.py",
        "START_BRIDGE.bat": root / "packaging" / "START_BRIDGE.bat",
        "README_INSTALL.txt": root / "packaging" / "README_INSTALL.txt",
        "THIRD-PARTY-NOTICES.md": root / "THIRD-PARTY-NOTICES.md",
        "LICENSE": root / "LICENSE",
    }
    missing = [str(p) for p in manifest.values() if not p.is_file()]
    if missing:
        raise FileNotFoundError("Missing build inputs:\n" + "\n".join(missing))
    return manifest

def build_zip(out, root=ROOT):
    manifest = archive_manifest(root)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Atomic publication: never leave a misleading half-built release.
    tmp = out.with_suffix(out.suffix + ".tmp")
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, path in sorted(manifest.items()):
                archive.write(path, name)
        with zipfile.ZipFile(tmp) as archive:
            broken = archive.testzip()
            if broken:
                raise OSError(f"ZIP integrity failure: {broken}")
        tmp.replace(out)
        print(f"[OK] Archive: {out}")
        print(f"[OK] {len(manifest)} files, including BOTH host/guest and Minecraft Fabric JAR")
    finally:
        if tmp.exists():
            tmp.unlink()
    return out

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "BotwCraft-experimental.zip")
    args = parser.parse_args()
    try:
        build_zip(args.output)
    except (OSError, AssertionError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
