"""Relay actual BotwCraft Ryujinx telemetry to the existing SkyCraft host bridge.

Read-only bridge: does not invent positions, modify Ryujinx, or move Link.
Start host_bridge.py separately, then run this relay.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import socket
import time

PATTERN = re.compile(
    r'\[BotwCraft:v100\]\s*(?:position\s*)?X\s*=\s*([-+]?\d+(?:\.\d+)?)'
    r'\s+Y\s*=\s*([-+]?\d+(?:\.\d+)?)\s+Z\s*=\s*([-+]?\d+(?:\.\d+)?)',
    re.IGNORECASE,
)

def parse_pose(line):
    match = PATTERN.search(line)
    if not match:
        return None
    xyz = tuple(float(v) for v in match.groups())
    if not all(math.isfinite(v) and abs(v) < 1000000 for v in xyz):
        return None
    return dict(type="pose", x=xyz[0], y=xyz[1], z=xyz[2],
                yaw=0.0, pitch=0.0, world=1)

def default_log_dir():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA missing; use --log")
    root = Path(appdata) / "Ryujinx"
    for folder in ("Logs", "logs"):
        p = root / folder
        if p.is_dir():
            return p
    raise FileNotFoundError(f"No Ryujinx logs directory in {root}")

def latest_log(folder):
    files = [p for p in folder.iterdir()
             if p.is_file() and p.suffix.lower() in (".log", ".txt")]
    return max(files, key=lambda p: p.stat().st_mtime_ns) if files else None

def forward_pose(pose, port=39847):
    packet = (json.dumps(pose, separators=(",", ":")) + "\n").encode("ascii")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.75) as sock:
            sock.settimeout(0.75)
            sock.sendall(packet)
            response = sock.makefile("rb").readline(4096)
        return bool(response and json.loads(response).get("ok") is True)
    except (OSError, ValueError):
        return False

def relay(path=None, port=39847, interval=0.2, from_start=False, dry_run=False):
    folder = default_log_dir() if path is None or path.is_dir() else None
    current = None
    offset = 0
    print("[BotwCraft relay] Read-only telemetry bridge; Ctrl+C to stop", flush=True)
    while True:
        candidate = latest_log(folder) if folder else path
        if candidate is None or not candidate.is_file():
            time.sleep(interval)
            continue
        if candidate != current:
            current = candidate
            offset = 0 if from_start else candidate.stat().st_size
            print(f"[BotwCraft relay] Watching {candidate}", flush=True)
        if candidate.stat().st_size < offset:
            offset = 0
        with candidate.open("r", encoding="utf-8", errors="replace") as stream:
            stream.seek(offset)
            while True:
                line = stream.readline()
                if not line:
                    break
                offset = stream.tell()
                pose = parse_pose(line)
                if pose is None:
                    continue
                ok = dry_run or forward_pose(pose, port)
                state = "dry-run" if dry_run else ("sent" if ok else "host bridge unavailable")
                print(f"[BotwCraft relay] {state}: {pose['x']}, {pose['y']}, {pose['z']}", flush=True)
        time.sleep(interval)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log", type=Path, help="Ryujinx log file/directory")
    ap.add_argument("--port", type=int, default=39847)
    ap.add_argument("--interval", type=float, default=0.2)
    ap.add_argument("--from-start", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not (0.05 <= args.interval <= 30.0 and 1 <= args.port <= 65535):
        ap.error("Invalid --interval or --port")
    try:
        relay(args.log, args.port, args.interval, args.from_start, args.dry_run)
    except KeyboardInterrupt:
        print("\n[BotwCraft relay] stopped")
    except (OSError, RuntimeError) as exc:
        raise SystemExit(f"[BotwCraft relay] ERROR: {exc}")

if __name__ == "__main__":
    main()
