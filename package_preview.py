"""Build a no-Nintendo-assets creative preview ZIP from an actual Fabric JAR.

The archive intentionally contains NO Switch hook, exefs, romfs or WiiXLaunch
build. It can draw real Minecraft blocks on top of the BOTW window, but is
NOT a native SkyCraft-equivalent port (no BOTW geometry/depth/collisions).
"""
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parent

def choose_fabric_jar(root):
    folder = root / "fabric" / "build" / "libs"
    matches = sorted(
        [p for p in folder.glob("skycraft-*.jar")
         if all(x not in p.stem.lower() for x in ("sources", "dev", "javadoc"))],
        key=lambda p: p.stat().st_mtime_ns, reverse=True
    )
    if not matches:
        raise FileNotFoundError("Minecraft Fabric JAR missing. Build fabric/gradlew build.")
    return matches[0]

def manifest(root):
    jar = choose_fabric_jar(root)
    files = {
        "minecraft_mods/" + jar.name: jar,
        "bridge/host_bridge.py": root / "botw" / "host_bridge.py",
        "bridge/control_bridge.py": root / "botw" / "control_bridge.py",
        "bridge/hud_overlay.py": root / "botw" / "hud_overlay.py",
        "bridge/launcher.py": root / "botw" / "launcher.py",
        "INSTALL_AND_PREVIEW.bat": root / "packaging" / "INSTALL_AND_PREVIEW.bat",
        "PREVIEW_BLOCKS.bat": root / "packaging" / "PREVIEW_BLOCKS.bat",
        "install_preview.py": root / "botw" / "install_preview.py",
        "prism_template/instance.cfg": root / "tools" / "minecraft-bundle" / "Prism" / "instances" / "SkyCraft" / "instance.cfg",
        "prism_template/mmc-pack.json": root / "tools" / "minecraft-bundle" / "Prism" / "instances" / "SkyCraft" / "mmc-pack.json",
        "README_PREVIEW.txt": root / "packaging" / "README_PREVIEW.txt",
        "LICENSE": root / "LICENSE",
        "THIRD-PARTY-NOTICES.md": root / "THIRD-PARTY-NOTICES.md",
    }
    missing = [str(p) for p in files.values() if not p.is_file()]
    if missing:
        raise FileNotFoundError("Missing preview inputs: " + ", ".join(missing))
    return files

def build(out=None, root=ROOT):
    out = out or root / "dist" / "BotwCraft-Blocks-Preview.zip"
    files = manifest(root)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for path, local in sorted(files.items()):
                z.write(local, path)
        with zipfile.ZipFile(tmp, "r") as z:
            assert z.testzip() is None
            assert "INSTALL_AND_PREVIEW.bat" in z.namelist()
            assert not any("/exefs/" in x or "prod.keys" in x for x in z.namelist())
        tmp.replace(out)
    finally:
        if tmp.exists():
            tmp.unlink()
    print(f"[OK] BotwCraft creative blocks preview: {out} ({len(files)} files)")
    return out

if __name__ == "__main__":
    try:
        build()
    except (OSError, AssertionError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
