"""Install a DEDICATED non-preview SkyCraft Fabric instance for BOTW.

The preview profile is deliberately never reused; it contains a synthetic
world flag and cannot be the authoritative Zelda game link. Existing
Minecraft worlds and profiles are left unchanged.
"""
from __future__ import annotations

from pathlib import Path
import shutil

try:
    from .prism_discovery import locate_prism, prism_data_dir, prism_instance_dir, prism_minecraft_dir
    from .install_preview import download_fabric_api
except ImportError:
    from prism_discovery import locate_prism, prism_data_dir, prism_instance_dir, prism_minecraft_dir
    from install_preview import download_fabric_api

NATIVE_NAME = "BotwCraftNative"
JAVA_FLAGS = (
    "--enable-native-access=ALL-UNNAMED",
    "-Dskycraft.quitWithSkyrim=false",
    "-Dskycraft.startHidden=false",
    "-Dskycraft.showWindow=true",
    "-Dbotwcraft.experimentalBlocks=false",
)


def native_instance_cfg(source):
    """Preserve chosen memory/Java settings while adding native link flags."""
    lines = source.splitlines()
    if "[General]" not in lines:
        lines.insert(0, "[General]")
    for i, line in enumerate(lines):
        if line.startswith("name="):
            lines[i] = "name=" + NATIVE_NAME
        if line.startswith("OverrideJavaArgs="):
            lines[i] = "OverrideJavaArgs=true"
    idx = next((i for i, line in enumerate(lines)
                if line.startswith("JvmArgs=")), None)
    if idx is None:
        lines.append("JvmArgs=" + " ".join(JAVA_FLAGS))
    else:
        before = lines[idx].partition("=")[2].split()
        before = [x for x in before if not x.startswith((
            "-Dskycraft.startHidden=",
            "-Dskycraft.quitWithSkyrim=",
            "-Dskycraft.showWindow=",
            "-Dbotwcraft.experimentalBlocks=",
        ))]
        for value in JAVA_FLAGS:
            if value not in before:
                before.append(value)
        lines[idx] = "JvmArgs=" + " ".join(before)
    if not any(x.startswith("OverrideJavaArgs=") for x in lines):
        lines.append("OverrideJavaArgs=true")
    if not any(x.startswith("name=") for x in lines):
        lines.append("name=" + NATIVE_NAME)
    return "\n".join(lines) + "\n"


def install_native_minecraft(bundle, prism=None, skip_fabric_download=False):
    bundle = Path(bundle)
    prism = Path(prism) if prism is not None else locate_prism(allow_picker=True)
    if prism is None or not prism.is_file():
        raise FileNotFoundError(
            "Prism Launcher introuvable. Choisis prismlauncher.exe.")
    data_dir = prism_data_dir(prism)
    minecraft_jar = list((bundle / "minecraft_mods").glob("skycraft-*.jar"))
    minecraft_jar = [
        p for p in minecraft_jar
        if not any(x in p.stem.lower() for x in ("sources", "dev", "javadoc"))
    ]
    if len(minecraft_jar) != 1:
        raise FileNotFoundError("Le ZIP doit contenir un seul mod SkyCraft Fabric compilé")
    template = bundle / "prism_template"
    if not (template / "mmc-pack.json").is_file():
        raise FileNotFoundError("Prism template mmc-pack.json missing")
    if not (template / "instance.cfg").is_file():
        raise FileNotFoundError("Prism template instance.cfg missing")
    profile = prism_instance_dir(data_dir, NATIVE_NAME)
    profile.mkdir(parents=True, exist_ok=True)
    cfg_file = profile / "instance.cfg"
    initial = (cfg_file.read_text(encoding="utf-8") if cfg_file.exists()
               else (template / "instance.cfg").read_text(encoding="utf-8"))
    updated = native_instance_cfg(initial)
    if updated != initial:
        cfg_file.write_text(updated, encoding="utf-8")
    pack = profile / "mmc-pack.json"
    if not pack.exists():
        shutil.copy2(template / "mmc-pack.json", pack)
    game_dir = prism_minecraft_dir(profile)
    game_dir.mkdir(exist_ok=True)
    # A leftover preview marker would turn this into the rejected sandbox.
    preview_marker = game_dir / "botwcraft.preview"
    if preview_marker.exists():
        raise RuntimeError(f"BotwCraftNative contains a preview-only marker: {preview_marker}. "
                           "Remove it only if this really is the native instance.")
    print(f"[BotwCraft] Actual Minecraft game directory: {game_dir}", flush=True)
    mods = game_dir / "mods"
    mods.mkdir(exist_ok=True)
    for old in mods.glob("skycraft-*.jar"):
        if old.name != minecraft_jar[0].name:
            old.unlink()
    shutil.copy2(minecraft_jar[0], mods / minecraft_jar[0].name)
    if not skip_fabric_download:
        download_fabric_api(mods)
    print(f"[BotwCraft] Minecraft natif configuré : {profile}")
    return profile
