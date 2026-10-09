"""Locate Prism Launcher reliably on Windows; remember a one-time manual choice.

Shared by the ZIP's root installer and the bridge subprocess.
Never modifies Prism's installation or other Minecraft instances.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys

LAUNCHER_NAME = "prismlauncher.exe"
INSTANCE_NAME = "BotwCraftPreview"

def bundle_root(module_file=__file__):
    root = Path(module_file).resolve().parent
    return root.parent if root.name.lower() == "bridge" else root

def saved_location_file(module_file=__file__):
    return bundle_root(module_file) / "prism-location.txt"

def _valid_executable(candidate):
    if not candidate:
        return False
    try:
        path = Path(candidate).expanduser()
        return (path.is_file() and path.name.lower() in
                ("prismlauncher.exe", "prism launcher.exe"))
    except (OSError, ValueError):
        return False

def candidates(saved=None, env=None):
    env = os.environ if env is None else env
    seen = set()

    def offer(path):
        if not path:
            return None
        p = Path(path).expanduser()
        k = str(p).lower()
        if k in seen:
            return None
        seen.add(k)
        return p

    if saved is not None and saved.is_file():
        try:
            x = offer(saved.read_text(encoding="utf-8").strip())
            if x is not None:
                yield x
        except (OSError, UnicodeError):
            pass
    x = offer(env.get("BOTWCRAFT_PRISM"))
    if x is not None:
        yield x

    on_path = shutil.which("prismlauncher.exe") or shutil.which("PrismLauncher.exe")
    x = offer(on_path)
    if x is not None:
        yield x

    for prefix, subfolder in (
        ("LOCALAPPDATA", "Programs/PrismLauncher"),
        ("LOCALAPPDATA", "Programs/Prism Launcher"),
        ("ProgramFiles", "PrismLauncher"),
        ("ProgramFiles", "Prism Launcher"),
        ("ProgramFiles(x86)", "PrismLauncher"),
        ("ProgramFiles(x86)", "Prism Launcher"),
        ("APPDATA", "PrismLauncher"),
        ("USERPROFILE", "scoop/apps/prismlauncher/current"),
    ):
        base = env.get(prefix)
        if not base:
            continue
        for executable in ("prismlauncher.exe", "PrismLauncher.exe"):
            x = offer(Path(base) / subfolder / executable)
            if x is not None:
                yield x

def select_executable_gui():
    """Offer a native file picker instead of forcing users to edit a .bat."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        app = tk.Tk()
        app.withdraw()
        app.attributes("-topmost", True)
        try:
            selected = filedialog.askopenfilename(
                title="BotwCraft : sélectionne prismlauncher.exe (une seule fois)",
                filetypes=[("Prism Launcher", "prismlauncher.exe"),
                           ("Applications Windows", "*.exe")])
        finally:
            app.destroy()
        return Path(selected) if selected else None
    except (ImportError, OSError, RuntimeError, tk.TclError) as exc:
        print("[BotwCraft] File picker unavailable:", exc, flush=True)
        return None

def locate_prism(allow_picker=True, module_file=__file__, env=None):
    saved = saved_location_file(module_file)
    for candidate in candidates(saved, env=env):
        if _valid_executable(candidate):
            return candidate.resolve()

    if not allow_picker:
        return None

    print("[BotwCraft] Prism n'est pas dans un dossier standard.", flush=True)
    print("[BotwCraft] Une fenêtre va te demander où est prismlauncher.exe.", flush=True)
    chosen = select_executable_gui()
    if chosen is None:
        # Console fallback for a Python distribution without tkinter.
        try:
            answer = input("Chemin de prismlauncher.exe (Entrée pour annuler) : ").strip().strip('"')
            chosen = Path(answer) if answer else None
        except EOFError:
            return None
    if not _valid_executable(chosen):
        return None
    chosen = chosen.resolve()
    saved.write_text(str(chosen), encoding="utf-8")
    return chosen

def prism_data_dir(executable, env=None):
    """Resolve the same data directory Prism will use when launched.

    Prism honors -d/--dir. Its portable.txt and UserData modes are checked
    before falling back to %APPDATA%\\PrismLauncher.
    """
    env = os.environ if env is None else env
    custom = env.get("BOTWCRAFT_PRISM_DIR")
    if custom:
        return Path(custom).expanduser()
    parent = Path(executable).resolve().parent
    userdata = parent / "UserData"
    if userdata.is_dir():
        return userdata
    if (parent / "portable.txt").is_file():
        return parent
    path = env.get("APPDATA")
    if not path:
        raise EnvironmentError("APPDATA manquant : dossier de Prism inconnu")
    return Path(path) / "PrismLauncher"
