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

# Actual native WiiXLaunch guest telemetry (fixed-point to avoid freestanding
# printf/floating-point formatting inside the Switch .wxlm).
NATIVE_POSITION = re.compile(
    r'BotwCraft:NATIVE_POSITION_MILLI\s+x=([-+]?\d+)'
    r'\s+y=([-+]?\d+)\s+z=([-+]?\d+)'
)

def parse_pose(line):
    native = NATIVE_POSITION.search(line)
    if native:
        integers = tuple(int(v) for v in native.groups())
        if any(abs(v) > 100000000 for v in integers):
            return None
        x, y, z = (v / 1000.0 for v in integers)
        return dict(type="pose", x=x, y=y, z=z,
                    yaw=0.0, pitch=0.0, world=1)
    match = PATTERN.search(line)
    if not match:
        return None
    xyz = tuple(float(v) for v in match.groups())
    if not all(math.isfinite(v) and abs(v) < 1000000 for v in xyz):
        return None
    return dict(type="pose", x=xyz[0], y=xyz[1], z=xyz[2],
                yaw=0.0, pitch=0.0, world=1)

def user_log_override():
    """Optional file/directory path; not the virtual SD card path."""
    for name in ("BOTWCRAFT_RYUJINX_LOG", "RYUJINX_LOG_PATH"):
        value = os.environ.get(name, "").strip().strip('"')
        if value:
            return Path(value).expanduser()
    here = Path(__file__).resolve().parent
    for file in (here.parent / "ryujinx-log-path.txt",
                 here / "ryujinx-log-path.txt"):
        try:
            if file.is_file():
                value = file.read_text(encoding="utf-8-sig").strip().splitlines()[0].strip().strip('"')
                if value:
                    return Path(value).expanduser()
        except (OSError, IndexError):
            pass
    return None


def candidate_log_directories():
    roots = []
    saved = os.environ.get("BOTWCRAFT_RYUJINX_DATA")
    if saved:
        roots.append(Path(saved))
    here = Path(__file__).resolve().parent
    for config in (here.parent / "ryujinx-data.txt",
                   here / "ryujinx-data.txt"):
        try:
            if config.is_file():
                roots.append(Path(config.read_text(encoding="utf-8-sig").strip().splitlines()[0]))
        except (OSError, IndexError):
            pass
    for key in ("APPDATA", "LOCALAPPDATA"):
        if os.environ.get(key):
            roots.append(Path(os.environ[key]) / "Ryujinx")
    roots += [Path.home() / "AppData/Roaming/Ryujinx",
              Path.home() / "AppData/Local/Ryujinx"]
    exe = os.environ.get("BOTWCRAFT_RYUJINX_EXE")
    if exe:
        roots.append(Path(exe).parent)
    roots += [Path.cwd() / "Ryujinx", Path.cwd() / "portable"]
    seen = set()
    for root in roots:
        for base in (root, root / "portable", root / "Portable"):
            for name in ("Logs", "logs"):
                directory = base / name
                key = os.path.normcase(str(directory.absolute()))
                if key not in seen:
                    seen.add(key)
                    yield directory


def default_log_dir():
    """Return an existing logs folder, without aborting while Ryujinx starts."""
    return next((p for p in candidate_log_directories() if p.is_dir()), None)


def latest_log(folder):
    try:
        files = [p for p in folder.iterdir()
                 if p.is_file() and p.suffix.lower() in (".log", ".txt")]
        return max(files, key=lambda p: p.stat().st_mtime_ns) if files else None
    except (OSError, ValueError):
        return None


def discover_latest_log():
    files = [latest_log(p) for p in candidate_log_directories() if p.is_dir()]
    files = [p for p in files if p is not None]
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
    explicit = Path(path).expanduser() if path is not None else user_log_override()
    current = None
    offset = 0
    notice = 0.0
    warned_version = False
    print("[BotwCraft relay] Waiting for Ryujinx log; Ctrl+C to stop", flush=True)
    if explicit is not None:
        print(f"[BotwCraft relay] Source: {explicit}", flush=True)
    else:
        print("[BotwCraft relay] If no logs are found, create ryujinx-log-path.txt "
              "beside START_BRIDGE.bat with a log file or Logs directory.", flush=True)
    while True:
        if explicit is None:
            candidate = discover_latest_log()
        elif explicit.is_file() or explicit.suffix.lower() in (".log", ".txt"):
            candidate = explicit if explicit.is_file() else None
        else:
            candidate = latest_log(explicit) if explicit.is_dir() else None
        if candidate is None or not candidate.is_file():
            now = time.monotonic()
            if not notice or now - notice > 20:
                print("[BotwCraft relay] Log not found yet; waiting for Ryujinx.", flush=True)
                notice = now
            time.sleep(interval)
            continue
        try:
            stat = candidate.stat()
            if candidate != current:
                current = candidate
                offset = 0 if from_start or time.time() - stat.st_mtime < 120 else stat.st_size
                warned_version = False
                print(f"[BotwCraft relay] Watching {candidate}", flush=True)
            elif stat.st_size < offset:
                offset = 0
            with candidate.open("r", encoding="utf-8", errors="replace") as stream:
                stream.seek(offset)
                while True:
                    line = stream.readline()
                    if not line:
                        break
                    offset = stream.tell()
                    if not warned_version and "unsupported BOTW build, skipping native hooks" in line:
                        warned_version = True
                        print("[BotwCraft relay] BOTW 1.6.0 incompatible: "
                              "native Link positions are disabled.", flush=True)
                    pose = parse_pose(line)
                    if pose is None:
                        continue
                    ok = dry_run or forward_pose(pose, port)
                    state = ("dry-run" if dry_run else
                             ("sent" if ok else "host bridge unavailable"))
                    print(f"[BotwCraft relay] {state}: "
                          f"{pose['x']}, {pose['y']}, {pose['z']}", flush=True)
        except (OSError, UnicodeError) as exc:
            print(f"[BotwCraft relay] Log unavailable: {exc}", flush=True)
            current = None
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
