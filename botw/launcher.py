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


def build_commands(preview_blocks=False, gdb_port=None, world_gdb_port=None):
    scripts = [("host_bridge.py", ["--preview-blocks"] if preview_blocks else [])]
    if not preview_blocks:
        scripts.append(("ryujinx_log_relay.py", []))
        if world_gdb_port is not None:
            scripts.append(("world_gdb_bridge.py", ["--port", str(world_gdb_port)]))
        elif gdb_port is not None:
            scripts.append(("gdb_mesh_bridge.py", ["--port", str(gdb_port)]))
        else:
            scripts.append(("native_mesh_bridge.py", []))
    return scripts


def main():
    if sys.platform != "win32":
        raise SystemExit("Windows / Ryujinx required")
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview-blocks", action="store_true",
                    help="Explicit standalone preview; NEVER claims Link telemetry.")
    ap.add_argument("--gdb-port", type=int, default=None,
                    help="EXPERIMENTAL: replace diagnostic mesh reader with Ryujinx GDB writer")
    ap.add_argument("--world-gdb-port", type=int, default=None,
                    help="BWC2 real-world Hyrule 3D channel, separate from 2D GDB")
    args = ap.parse_args()
    if args.world_gdb_port is not None and not (1 <= args.world_gdb_port <= 65535):
        ap.error("invalid world GDB port")
    if args.world_gdb_port is not None and args.gdb_port is not None:
        ap.error("select only one GDB render-ring consumer")
    if args.gdb_port is not None and not (1 <= args.gdb_port <= 65535):
        ap.error("invalid GDB port")
    if args.preview_blocks and (args.gdb_port is not None or
                                args.world_gdb_port is not None):
        ap.error("preview mode cannot be combined with native GDB")
    processes = []
    try:
        print("[BotwCraft] Bridge only: Minecraft and Ryujinx are NOT started or modified.", flush=True)
        print("[BotwCraft] Launch Minecraft manually; type /botwcraft connect in its chat.", flush=True)
        print("[BotwCraft] No Java arguments, Prism profile changes or automatic worlds.", flush=True)
        for name, extra in build_commands(args.preview_blocks, args.gdb_port,
                                                  args.world_gdb_port):
            script = ROOT / name
            if not script.is_file():
                raise FileNotFoundError(f"Missing packaged component: {script}")
            print(f"[BotwCraft] Starting {name}", flush=True)
            processes.append((name, subprocess.Popen(
                [sys.executable, "-u", str(script), *extra], cwd=ROOT)))
            time.sleep(0.25)
        print("[BotwCraft] Ctrl+C stops only bridge services.", flush=True)
        warned_mesh = False
        while True:
            for name, proc in processes:
                code = proc.poll()
                if code is not None:
                    if name == "native_mesh_bridge.py":
                        if not warned_mesh:
                            print("[BotwCraft] WARNING: mesh rendering process stopped "
                                  f"(exit {code}). Link log relay and host bridge remain running. "
                                  "See mesh bridge error above for the real cause.", flush=True)
                            warned_mesh = True
                        continue
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
