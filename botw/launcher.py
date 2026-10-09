"""One-process supervisor for SkyCraft/BotwCraft Windows components.

The optional block-building preview is Minecraft rendered as a desktop overlay;
it is NOT integrated BOTW collision or native graphics.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

try:
    from .prism_discovery import locate_prism, prism_data_dir, prism_instance_dir, prism_minecraft_dir
except ImportError:  # Standalone ZIP bridge/launcher.py
    from prism_discovery import locate_prism, prism_data_dir, prism_instance_dir, prism_minecraft_dir

ROOT = Path(__file__).resolve().parent

def inspect_prism_instance(profile):
    """Do not mistake a Prism GUI window for a running Minecraft game."""
    for file in (profile / "instance.cfg", profile / "mmc-pack.json"):
        if not file.is_file():
            raise RuntimeError(f"Prism instance incomplete or absent: {file}; "
                               "re-run INSTALL_NATIVE_TEST.bat")
    game_dir = prism_minecraft_dir(profile)
    mods = game_dir / "mods"
    if not list(mods.glob("skycraft-*.jar")):
        raise RuntimeError(f"Minecraft SkyCraft mod missing from {mods}; "
                           "re-run INSTALL_NATIVE_TEST.bat")
    if not list(mods.glob("fabric-api-*.jar")):
        print(f"[BotwCraft] WARNING: Fabric API missing in {mods}", flush=True)


def minecraft_started(profile, after):
    latest = prism_minecraft_dir(profile) / "logs" / "latest.log"
    try:
        return latest.is_file() and latest.stat().st_mtime >= after - 3
    except OSError:
        return False


def start_minecraft(preview_blocks=False):
    prism = locate_prism(allow_picker=True)
    if prism is None:
        raise RuntimeError("Prism Launcher introuvable : selectionne prismlauncher.exe")
    data_dir = prism_data_dir(prism)
    profile_name = "BotwCraftPreview" if preview_blocks else "BotwCraftNative"
    profile = prism_instance_dir(data_dir, profile_name)
    inspect_prism_instance(profile)
    env = os.environ.copy()
    opts = env.get("JAVA_TOOL_OPTIONS", "")
    if not preview_blocks:
        # A previously launched preview may have left this JVM property in the environment.
        opts = " ".join(part for part in opts.split()
                        if not part.startswith("-Dbotwcraft.experimentalBlocks="))
        cfg = (profile / "instance.cfg").read_text(encoding="utf-8", errors="replace")
        if "-Dbotwcraft.experimentalBlocks=true" in cfg:
            raise RuntimeError("Native Prism profile still enables experimentalBlocks=true. "
                               "Re-run INSTALL_NATIVE_TEST.bat from the updated build.")
        marker = prism_minecraft_dir(profile) / "botwcraft.preview"
        if marker.is_file():
            raise RuntimeError(f"Native profile has preview marker: {marker}")
    if preview_blocks:
        opts += " -Dbotwcraft.experimentalBlocks=true"
    opts += (" -Dskycraft.startHidden=false -Dskycraft.showWindow=true"
             " -Dskycraft.quitWithSkyrim=false")
    env["JAVA_TOOL_OPTIONS"] = opts.strip()
    print(f"[BotwCraft] Prism: {prism}", flush=True)
    print(f"[BotwCraft] Instance: {profile}", flush=True)
    print(f"[BotwCraft] Minecraft game directory: {prism_minecraft_dir(profile)}", flush=True)
    print(f"[BotwCraft] Command: --dir {data_dir} --launch {profile_name}", flush=True)
    start_time = time.time()
    process = subprocess.Popen([str(prism), "--dir", str(data_dir),
                                "--launch", profile_name], env=env, cwd=prism.parent)
    return process, profile, start_time


def build_commands(preview_blocks=False):
    scripts = [
        ("host_bridge.py", ["--preview-blocks"] if preview_blocks else []),
    ]
    if not preview_blocks:
        scripts.append(("ryujinx_log_relay.py", []))
        scripts.append(("native_mesh_bridge.py", []))
    if preview_blocks:
        scripts.append(("hud_overlay.py", ["--key-background", "--fps", "8"]))
    # Real BOTW mode renders blocks with native NVN via WiiXLaunch; do not
    # overlay a second, unregistered, Windows-side Minecraft framebuffer.
    scripts.append(("control_bridge.py", []))
    return scripts

def main():
    if sys.platform != "win32":
        raise SystemExit("Windows / Ryujinx required")
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview-blocks", action="store_true",
                    help="Synthetic Minecraft creative preview; NOT actual BOTW world integration")
    args = ap.parse_args()
    processes = []
    minecraft = None
    try:
        for name, extra in build_commands(args.preview_blocks):
            script = ROOT / name
            if not script.is_file():
                raise FileNotFoundError(f"Missing packaged component: {script}")
            print(f"[BotwCraft] Starting {name}", flush=True)
            processes.append((name, subprocess.Popen([sys.executable, "-u", str(script), *extra], cwd=ROOT)))
            time.sleep(0.25)
        minecraft, profile, minecraft_start = start_minecraft(args.preview_blocks)
        mc_confirmed = False
        mc_warned = False
        print("[BotwCraft] Ctrl+C stops Windows bridge processes. "
              "Ryujinx files untouched.", flush=True)
        if args.preview_blocks:
            print("[BotwCraft] Preview: Minecraft creative blocks OVER the BOTW window, "
                  "without native game collision, Link position or depth.", flush=True)
        while True:
            if not mc_confirmed and minecraft_started(profile, minecraft_start):
                mc_confirmed = True
                print("[BotwCraft] Minecraft started: latest.log was updated.", flush=True)
            if not mc_confirmed and not mc_warned and time.time() - minecraft_start >= 30:
                mc_warned = True
                print("[BotwCraft] WARNING: Prism started, but Minecraft launch was not confirmed.", flush=True)
                print("[BotwCraft] Open Prism, double-click BotwCraftNative and check its console.", flush=True)
                print(f"[BotwCraft] Minecraft log: {prism_minecraft_dir(profile) / 'logs' / 'latest.log'}", flush=True)
            if minecraft.poll() not in (None, 0):
                raise RuntimeError(f"Prism exited with an error ({minecraft.returncode})")
            for name, proc in processes:
                result = proc.poll()
                if result is not None:
                    if name == "hud_overlay.py":
                        continue  # Optional renderer; don't interrupt native game.
                    raise RuntimeError(f"{name} stopped unexpectedly (code {result})")
            time.sleep(0.35)
    except KeyboardInterrupt:
        print("\n[BotwCraft] Stopping...", flush=True)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"[BotwCraft] ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        # Do not kill Minecraft itself; player may want to save their creative world.
        for _, proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
        for _, proc in reversed(processes):
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
