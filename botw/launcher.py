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
    from .prism_discovery import locate_prism, prism_data_dir
except ImportError:  # Standalone ZIP bridge/launcher.py
    from prism_discovery import locate_prism, prism_data_dir

ROOT = Path(__file__).resolve().parent

def start_minecraft(preview_blocks=False):
    if not preview_blocks:
        return None
    prism = locate_prism(allow_picker=True)
    if prism is None:
        raise RuntimeError("Prism Launcher introuvable : sélectionne prismlauncher.exe "
                           "dans la fenêtre de recherche")
    data_dir = prism_data_dir(prism)
    expected_instance = data_dir / "instances" / "BotwCraftPreview"
    if not expected_instance.is_dir():
        raise RuntimeError(
            "L'instance Minecraft BotwCraftPreview n'existe pas dans "
            f"{data_dir}. Relance INSTALL_AND_PREVIEW.bat.")
    env = os.environ.copy()
    opts = env.get("JAVA_TOOL_OPTIONS", "")
    opts += (" -Dbotwcraft.experimentalBlocks=true"
             " -Dskycraft.startHidden=false -Dskycraft.showWindow=true"
             " -Dskycraft.quitWithSkyrim=false")
    env["JAVA_TOOL_OPTIONS"] = opts.strip()
    print(f"[BotwCraft] Launching Minecraft through {prism}", flush=True)
    return subprocess.Popen(
        [str(prism), "--dir", str(data_dir), "--launch", "BotwCraftPreview"],
        env=env, cwd=prism.parent)

def build_commands(preview_blocks=False):
    scripts = [
        ("host_bridge.py", ["--preview-blocks"] if preview_blocks else []),
    ]
    if not preview_blocks:
        scripts.append(("ryujinx_log_relay.py", []))
    scripts.extend([
        ("hud_overlay.py", ["--key-background", "--fps", "8"] if preview_blocks else []),
        ("control_bridge.py", []),
    ])
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
        minecraft = start_minecraft(args.preview_blocks)
        print("[BotwCraft] Ctrl+C stops Windows bridge processes. "
              "Ryujinx files untouched.", flush=True)
        if args.preview_blocks:
            print("[BotwCraft] Preview: Minecraft creative blocks OVER the BOTW window, "
                  "without native game collision, Link position or depth.", flush=True)
        while True:
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
