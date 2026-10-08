"""Launch/stop the BotwCraft Windows bridge, Ryujinx telemetry and controls together.

This starts transport components; the unimplemented game-side BOTW hooks and
native block rendering are not magically supplied by running this.
"""
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent

def main():
    if sys.platform != "win32":
        raise SystemExit("Windows / Ryujinx required")
    processes = []
    try:
        for name in ("host_bridge.py", "ryujinx_log_relay.py", "control_bridge.py"):
            script = ROOT / name
            if not script.is_file():
                raise FileNotFoundError(f"Missing packaged component: {script}")
            cmd = [sys.executable, "-u", str(script)]
            if name == "host_bridge.py":
                print("[BotwCraft] Starting host bridge...", flush=True)
            elif name == "ryujinx_log_relay.py":
                print("[BotwCraft] Starting Ryujinx telemetry...", flush=True)
            else:
                print("[BotwCraft] Starting Windows keyboard / virtual gamepad bridge...", flush=True)
            processes.append((name, subprocess.Popen(cmd, cwd=ROOT)))
            time.sleep(0.25)
        print("[BotwCraft] Ctrl+C stops all three processes. No Ryujinx file is modified.", flush=True)
        while True:
            for name, proc in processes:
                result = proc.poll()
                if result is not None:
                    raise RuntimeError(f"{name} terminated with code {result}")
            time.sleep(0.35)
    except KeyboardInterrupt:
        print("\n[BotwCraft] Stopping...", flush=True)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"[BotwCraft] ERROR: {exc}", file=sys.stderr, flush=True)
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
