"""Reproducible BotwCraft Switch dependencies: pinned WiiXLaunch + BOTW module.

Keeps the WiiXLaunch and wiixlaunch-botw sources together as their upstream
intended. Supports both git clones (WiiXLaunch is a git submodule) and
GitHub's source ZIPs (which omit git submodule content). Never copies an
incompatible version or replaces an existing modified checkout.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
HOST = ROOT / "WiiXLaunch"
HOST_REMOTE = "https://github.com/BladesawStudios/WiiXLaunch.git"
BOTW_REMOTE = "https://github.com/BladesawStudios/wiixlaunch-botw.git"
# The host's gitlink is the authority, these pins double-check its nested dep.
HOST_COMMIT = "30e0502ff2abb76b1816e8271d4126e0a95ac9fc"
BOTW_COMMIT = "49e07a6acd6d675a98cba3bb8fc244c39bce8790"


def call(*args, cwd=None):
    subprocess.run(["git", *map(str, args)], cwd=cwd, check=True)


def result(*args, cwd=None):
    return subprocess.run(["git", *map(str, args)], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def prepare():
    if not HOST.is_dir() or not (HOST / "build_switch.bat").is_file():
        if (ROOT / ".git").exists():
            print("[BotwCraft] Initialising pinned WiiXLaunch Git submodule", flush=True)
            call("submodule", "update", "--init", "WiiXLaunch", cwd=ROOT)
        else:
            # Downloaded ZIP: gitlinks do not contain the actual host files.
            print("[BotwCraft] GitHub ZIP: retrieving pinned WiiXLaunch", flush=True)
            if HOST.exists() and any(HOST.iterdir()):
                raise RuntimeError("WiiXLaunch exists but is incomplete; "
                                   "will not overwrite it")
            call("clone", "--no-checkout", "--depth", "1", HOST_REMOTE, HOST,
                 cwd=ROOT)
            call("fetch", "--depth", "1", "origin", HOST_COMMIT, cwd=HOST)
            call("checkout", "--detach", HOST_COMMIT, cwd=HOST)

    actual_host = result("rev-parse", "HEAD", cwd=HOST)
    if actual_host != HOST_COMMIT:
        dirty = result("status", "--porcelain", cwd=HOST)
        if dirty:
            raise RuntimeError("Existing WiiXLaunch has local changes or a "
                               "different version. Refusing to discard them: "
                               + actual_host)
        print("[BotwCraft] Pinning WiiXLaunch release", flush=True)
        call("fetch", "--depth", "1", "origin", HOST_COMMIT, cwd=HOST)
        call("checkout", "--detach", HOST_COMMIT, cwd=HOST)

    # The host itself uses nested gitlinks: do not flatten or copy the fork.
    # The old TKVSC-Team URL is a redirect; use the requested BladesawStudios
    # fork, which also contains the *newer* pinned commit.
    call("config", "submodule.vendor/wiixlaunch-botw.url", BOTW_REMOTE, cwd=HOST)
    call("submodule", "update", "--init", "--recursive", cwd=HOST)
    nested = HOST / "vendor" / "wiixlaunch-botw"
    if not nested.is_dir():
        raise RuntimeError("wiixlaunch-botw was not checked out")
    actual_botw = result("rev-parse", "HEAD", cwd=nested)
    if actual_botw != BOTW_COMMIT:
        raise RuntimeError("Wrong BOTW modding version: " + actual_botw +
                           " (expected " + BOTW_COMMIT + ")")
    if not (nested / "include" / "wiixlaunch" / "botw" / "graphics" / "nvn.hpp").is_file():
        raise RuntimeError("NVN rendering module absent from WiiXLaunch")
    print("[BotwCraft] WiiXLaunch:", actual_host, flush=True)
    print("[BotwCraft] wiixlaunch-botw:", actual_botw, flush=True)
    print("[BotwCraft] Dependencies ready for BOTW Switch 1.5.0 builds.",
          flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        prepare()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        raise SystemExit("[BotwCraft] Native dependency setup failed: " + str(exc))


if __name__ == "__main__":
    main()
