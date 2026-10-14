"""Optional real-time console capture for Ryujinx launched by BotwCraft.

This is NOT an emulator patch and does not grant BOTW 1.6.0 compatibility.
It can only relay lines that Ryujinx writes to its inherited stdout/stderr.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BUNDLE = HERE.parent if HERE.name.lower() == "bridge" else HERE


def find_exe(argument=None):
    if argument:
        return Path(argument.strip('"')).expanduser()
    saved = BUNDLE / "ryujinx-exe.txt"
    if saved.is_file():
        value = saved.read_text(encoding="utf-8-sig").strip().splitlines()[0].strip('"')
        if value:
            return Path(value).expanduser()
    if sys.platform == "win32":
        try:
            from tkinter import Tk, filedialog
            dialog = Tk()
            dialog.withdraw()
            dialog.attributes("-topmost", True)
            path = filedialog.askopenfilename(
                title="BotwCraft: select your Ryujinx.exe",
                filetypes=[("Ryujinx", "*.exe")])
            dialog.destroy()
            if path:
                return Path(path)
        except Exception as exc:
            print("[BotwCraft] Windows executable picker unavailable:", exc, flush=True)
    return None


def start(executable, extra_args=()):
    exe = Path(executable).expanduser().resolve()
    if not exe.is_file() or exe.suffix.lower() != ".exe":
        raise FileNotFoundError(f"Ryujinx .exe not found: {exe}")
    log = BUNDLE / "ryujinx-live.log"
    choice = BUNDLE / "ryujinx-log-path.txt"
    if not choice.is_file():
        choice.write_text(str(log) + "\n", encoding="utf-8")
        print("[BotwCraft] Relay log path selected:", log, flush=True)
    else:
        current = choice.read_text(encoding="utf-8-sig").strip().strip('"')
        if Path(current) != log:
            print("[BotwCraft] WARNING: ryujinx-log-path.txt selects another log. "
                  "For live capture, set it to:", log, flush=True)
    (BUNDLE / "ryujinx-exe.txt").write_text(str(exe) + "\n", encoding="utf-8")
    print("[BotwCraft] Ryujinx console ->", log, flush=True)
    print("[BotwCraft] If Ryujinx does not emit stdout, this file cannot be live.", flush=True)
    args = [str(exe), *extra_args]
    captured = 0
    with log.open("a", encoding="utf-8", errors="replace", buffering=1) as out:
        out.write("\n=== BotwCraft live Ryujinx session "
                  + datetime.now().isoformat(timespec="seconds") + " ===\n")
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if sys.platform == "win32" else 0
        process = subprocess.Popen(
            args, cwd=exe.parent, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            bufsize=1, creationflags=flags)
        assert process.stdout is not None
        try:
            for line in process.stdout:
                out.write(line)
                print(line, end="", flush=True)
                captured += 1
        except KeyboardInterrupt:
            print("[BotwCraft] Capture interrupted; Ryujinx was not terminated by this script.", flush=True)
            return 0
        result = process.wait()
        print(f"[BotwCraft] Ryujinx exited ({result}); captured {captured} console lines.", flush=True)
        if not captured:
            print("[BotwCraft] This Ryujinx build did not emit redirected stdout; "
                  "the usual logs may only be available after closing it.", flush=True)
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", help="Full path to Ryujinx.exe; otherwise a file picker opens")
    parser.add_argument("args", nargs="*")
    arguments = parser.parse_args()
    try:
        exe = find_exe(arguments.exe)
        if exe is None:
            raise FileNotFoundError("Choose Ryujinx.exe to start live capture")
        return start(exe, arguments.args)
    except (OSError, ValueError) as exc:
        print(f"[BotwCraft] ERROR: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
