"""Install BotwCraft's isolated Prism Minecraft creative-preview instance.

No modifications to BOTW, Ryujinx, existing SkyCraft instances, games or saves.
Requires an existing Prism Launcher installation and a Microsoft Minecraft login.
Downloads Fabric API from Modrinth and validates the published SHA-512 hash.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request

try:
    from .prism_discovery import locate_prism, prism_data_dir
except ImportError:
    from prism_discovery import locate_prism, prism_data_dir

INSTANCE = "BotwCraftPreview"
MC = "26.3"
USER_AGENT = "BotwCraft/0.1 (https://github.com/Rom4203/BotwCraft)"

def modrinth_fabric_version(versions):
    if not isinstance(versions, list):
        raise ValueError("invalid Fabric API version response")
    for entry in sorted(versions, key=lambda v: v.get("date_published", ""), reverse=True):
        for file in entry.get("files", []):
            if file.get("primary") and file.get("filename", "").endswith(".jar"):
                return file
    for entry in versions:
        for file in entry.get("files", []):
            if file.get("filename", "").endswith(".jar"):
                return file
    raise ValueError(f"No compatible Fabric API file for Minecraft {MC}")

def download_fabric_api(mods):
    endpoint = "https://api.modrinth.com/v2/project/P7dR8mSH/version?"
    query = urllib.parse.urlencode({
        "loaders": json.dumps(["fabric"]),
        "game_versions": json.dumps([MC]),
    })
    req = urllib.request.Request(endpoint + query, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=25) as response:
        versions = json.loads(response.read(2_000_000))
    metadata = modrinth_fabric_version(versions)
    url = metadata.get("url", "")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ("cdn.modrinth.com", "cdn.modrinth.com.cn"):
        raise ValueError("Fabric API download URL is not a recognized HTTPS Modrinth CDN")
    filename = metadata["filename"]
    if Path(filename).name != filename or not filename.lower().endswith(".jar"):
        raise ValueError("invalid Fabric API filename")
    expected = metadata.get("hashes", {}).get("sha512")
    if not isinstance(expected, str) or len(expected) != 128:
        raise ValueError("Fabric API lacks an expected SHA-512 integrity hash")
    target = mods / filename
    if target.exists() and hashlib.sha512(target.read_bytes()).hexdigest() == expected.lower():
        print("[BotwCraft] Fabric API already installed and verified")
        return target
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as response:
        content = response.read(45_000_000)
    if len(content) >= 45_000_000 or hashlib.sha512(content).hexdigest() != expected.lower():
        raise ValueError("Fabric API integrity check failed or download too large")
    # Only manage Fabric API packages in this dedicated preview instance.
    for old in mods.glob("fabric-api-*.jar"):
        if old.name != filename:
            old.unlink()
    target.write_bytes(content)
    print("[BotwCraft] Fabric API downloaded with SHA-512 verification:", filename)
    return target

def preview_jvm_config(content):
    """Enable the standalone Minecraft preview in an existing Prism instance.

    Older ZIPs only set JVM flags on first install. Manually created Prism
    profiles (the common user case) silently lacked botwcraft.experimentalBlocks
    and sat on the vanilla title screen. Preserve other instance settings.
    """
    flags = (
        "-Dbotwcraft.experimentalBlocks=true",
        "-Dskycraft.quitWithSkyrim=false",
        "-Dskycraft.showWindow=true",
        "-Dskycraft.startHidden=false",
    )
    lines = content.splitlines()
    if "[General]" not in lines:
        lines.insert(0, "[General]")
    jvm_index = next((i for i, line in enumerate(lines)
                      if line.startswith("JvmArgs=")), None)
    if jvm_index is None:
        lines.append("JvmArgs=--enable-native-access=ALL-UNNAMED " + " ".join(flags))
    else:
        old = lines[jvm_index].partition("=")[2]
        for key in ("botwcraft.experimentalBlocks", "skycraft.quitWithSkyrim",
                    "skycraft.showWindow", "skycraft.startHidden"):
            old = re.sub(r"(?<!\\S)-D" + re.escape(key) + r"=\\S+", "", old)
        lines[jvm_index] = "JvmArgs=" + " ".join((old.strip(), *flags)).strip()
    override = next((i for i, line in enumerate(lines)
                     if line.startswith("OverrideJavaArgs=")), None)
    if override is not None:
        lines[override] = "OverrideJavaArgs=true"
    else:
        lines.append("OverrideJavaArgs=true")
    return "\\n".join(lines) + "\\n"

def install(root, instance_root):
    jar_dir = root / "minecraft_mods"
    jars = [p for p in jar_dir.glob("skycraft-*.jar")
            if all(s not in p.stem for s in ("sources", "dev", "javadoc"))]
    if len(jars) != 1:
        raise FileNotFoundError("Preview ZIP must contain exactly one compiled SkyCraft Fabric JAR")
    template = root / "prism_template"
    if not (template / "instance.cfg").is_file() or not (template / "mmc-pack.json").is_file():
        raise FileNotFoundError("Prism instance template missing from preview ZIP")

    instance_root.mkdir(parents=True, exist_ok=True)
    cfg_path = instance_root / "instance.cfg"
    if cfg_path.exists():
        cfg = cfg_path.read_text(encoding="utf-8")
    else:
        cfg = (template / "instance.cfg").read_text(encoding="utf-8")
        cfg = cfg.replace("name=SkyCraft", f"name={INSTANCE}")
    corrected = preview_jvm_config(cfg)
    if corrected != cfg:
        cfg_path.write_text(corrected, encoding="utf-8")
        print("[BotwCraft] Profil Prism mis à jour : monde automatique + fenêtre visible")
    pack = instance_root / "mmc-pack.json"
    if not pack.exists():
        shutil.copy2(template / "mmc-pack.json", pack)

    mods = instance_root / ".minecraft" / "mods"
    mods.mkdir(parents=True, exist_ok=True)
    # Preserve other mods and world saves; update only our SkyCraft-derived JAR.
    for old in mods.glob("skycraft-*.jar"):
        if old.name != jars[0].name:
            old.unlink()
    shutil.copy2(jars[0], mods / jars[0].name)
    download_fabric_api(mods)
    print("[BotwCraft] Creative preview installed in:", instance_root)
    print("[BotwCraft] Your existing Zelda and Minecraft worlds were not touched.")
    return instance_root

def main():
    if sys.platform != "win32":
        raise SystemExit("Windows required")
    root = Path(__file__).resolve().parent
    prism = locate_prism(allow_picker=True)
    if prism is None:
        raise SystemExit("Prism Launcher not found. Select prismlauncher.exe.")
    profile = prism_data_dir(prism) / "instances" / INSTANCE
    try:
        install(root, profile)
    except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
        raise SystemExit("[BotwCraft] Setup failed: " + str(exc))

if __name__ == "__main__":
    main()
