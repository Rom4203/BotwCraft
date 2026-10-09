"""Start only BotwCraft bridge services; Minecraft and Ryujinx remain user-owned.

Open Prism and Ryujinx yourself. Minecraft connects with /botwcraft connect
when actual game telemetry arrives. No Java flags, GUI launches or world changes.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def build_commands(preview_blocks=False):
    scripts = [("host_bridge.py", ["--preview-blocks"] if preview_blocks else [])]
    if not preview_blocks:
        scripts.extend([("ryujinx_log_relay.py", []), ("native_mesh_bridge.py", [])])
    # Input capture is separately opt-in: do not steal Minecraft keyboard/mouse.
    return scripts


def main():
    if sys.platform != "win32":
        raise SystemExit("Windows / Ryujinx required")
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview-blocks", action="store_true",
                    help="Explicit standalone preview; NEVER claims Link telemetry.")
    args = ap.parse_args()
    processes = []
    try:
        print("[BotwCraft] Bridge only: Minecraft and Ryujinx are NOT started or modified.", flush=True)
        print("[BotwCraft] Launch Minecraft manually; type /botwcraft connect in its chat.", flush=True)
        print("[BotwCraft] No Java arguments, Prism profile changes or automatic worlds.", flush=True)
        for name, extra in build_commands(args.preview_blocks):
            script = ROOT / name
            if not script.is_file():
                raise FileNotFoundError(f"Missing packaged component: {script}")
            print(f"[BotwCraft] Starting {name}", flush=True)
            processes.append((name, subprocess.Popen(
                [sys.executable, "-u", str(script), *extra], cwd=ROOT)))
            time.sleep(0.25)
        print("[BotwCraft] Ctrl+C stops only bridge services.", flush=True)
        while True:
            for name, proc in processes:
                code = proc.poll()
                if code is not None:
                    raise RuntimeError(f"{name} exited unexpectedly ({code})")
            time.sleep(0.35)
    except KeyboardInterrupt:
        print("\n[BotwCraft] Stopping bridges, leaving both games untouched.", flush=True)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"[BotwCraft] ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
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
