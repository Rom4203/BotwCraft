"""Install verified ARM64 BotwCraft binaries for an isolated BOTW 1.5.0 test.

The Nintendo game is not bundled. Requires an existing legitimate Ryujinx data
folder. This installer never modifies game saves, firmware or unrelated mods.
The user must back up saves and have BOTW Switch 1.5.0 installed separately.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import struct
import sys
import time

TITLE_ID = "01007ef00011e000"
TITLE_ID_UPPER = TITLE_ID.upper()
MOD_NAME = "BotwCraft"


def find_ryujinx_root(explicit=None):
    if explicit:
        candidate = Path(explicit).expanduser()
        if not candidate.is_dir():
            raise FileNotFoundError(f"Ryujinx dossier introuvable : {candidate}")
        return candidate.resolve()

    candidates = []
    override = os.environ.get("BOTWCRAFT_RYUJINX_DATA")
    if override:
        candidates.append(Path(override))
    for envvar in ("APPDATA", "LOCALAPPDATA"):
        directory = os.environ.get(envvar)
        if directory:
            candidates.append(Path(directory) / "Ryujinx")
    for candidate in candidates:
        if (candidate / "mods" / "contents").is_dir() and candidate.is_dir():
            return candidate.resolve()

    if sys.platform == "win32":
        try:
            import tkinter as tk
            from tkinter import filedialog
            app = tk.Tk()
            app.withdraw()
            app.attributes("-topmost", True)
            selected = filedialog.askdirectory(
                title="BotwCraft : choisir le dossier de données Ryujinx (mods et sdcard)")
            app.destroy()
            if selected:
                return find_ryujinx_root(selected)
        except Exception as exc:
            print("[BotwCraft] Sélection graphique impossible :", exc)
    raise FileNotFoundError(
        "Dossier Ryujinx non trouvé : définir BOTWCRAFT_RYUJINX_DATA")


def source_paths(bundle):
    exefs = (bundle / "ryujinx_mods" / "contents" / TITLE_ID /
             MOD_NAME / "exefs" / "subsdk9")
    wxlm = (bundle / "ryujinx_sdcard" / "WiiXLaunch" / "mods" /
            TITLE_ID_UPPER / "botwcraft.wxlm")
    for path in (exefs, wxlm):
        if not path.is_file() or path.stat().st_size < 100:
            raise FileNotFoundError(
                f"Module Switch absent/incomplet dans l'archive : {path}")
    return exefs, wxlm


def _copy_atomically(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".botwcraft-tmp")
    try:
        shutil.copy2(source, temp)
        temp.replace(destination)
    finally:
        if temp.exists():
            temp.unlink()


def install(bundle, ryujinx_root, backup_root=None):
    source_exefs, source_guest = source_paths(bundle)
    root = Path(ryujinx_root).resolve()
    # Both directories are needed. Do not accidentally install into a game
    # folder, an emulator executable folder or a newly created fake profile.
    if not (root / "mods" / "contents").is_dir():
        raise ValueError(f"Ce dossier ne contient pas mods/contents : {root}")
    if not (root / "sdcard").is_dir():
        raise ValueError(f"Ce dossier ne contient pas sdcard : {root}")
    mods = root / "mods" / "contents" / TITLE_ID / MOD_NAME
    guest = root / "sdcard" / "WiiXLaunch" / "mods" / TITLE_ID_UPPER / "botwcraft.wxlm"
    new_exefs = mods / "exefs" / "subsdk9"
    new_romfs_guest = mods / "romfs" / "WiiXLaunch" / "mods" / "botwcraft.wxlm"
    new_romfs_probe = mods / "romfs" / "WiiXLaunch" / "mods" / "botwcraft" / "frame.bin"
    backup_root = Path(backup_root or bundle / "backups")
    backup = backup_root / time.strftime("%Y%m%d-%H%M%S")
    items = []
    if mods.exists():
        items.append((mods, backup / "old_BotwCraft_mod"))
    if guest.exists():
        items.append((guest, backup / "old_botwcraft.wxlm"))
    if items:
        backup.mkdir(parents=True, exist_ok=True)
        for original, saved in items:
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(original), str(saved))
            print(f"[BotwCraft] Sauvegarde de l'ancien mod : {saved}")
    _copy_atomically(source_exefs, new_exefs)
    # Ryujinx 1.3.3 may refuse Switch MountSdCardForDebug. WiiXLaunch
    # then reads modules from the title's mounted ROMFS instead.
    _copy_atomically(source_guest, new_romfs_guest)
    _copy_atomically(source_guest, guest)
    # Valid empty BWC1 frame available through game-mounted ROMFS *at boot*.
    # The Switch guest probes this path; it cannot rely on the SD debug mount.
    # It does not modify Zelda game files or save data.
    new_romfs_probe.parent.mkdir(parents=True, exist_ok=True)
    new_romfs_probe.write_bytes(struct.pack("<8I", 0x31435742, 1, 0, 0,
                                            2166136261, 0, 0, 0))
    print("[BotwCraft] Module natif 1.5.0 installé :")
    print("  ExeFS:", new_exefs)
    print("  RomFS (fallback quand la SD est inaccessible):", new_romfs_guest)
    print("  SD   :", guest)\n    print("  ROMFS BWC1 probe (at boot):", new_romfs_probe)\n    print("[BotwCraft] ROMFS live file updates still require Ryujinx validation.")
    print("[BotwCraft] Aucune sauvegarde Zelda modifiée.")
    print("[BotwCraft] Le lancement et le fonctionnement en jeu restent à vérifier.")
    return new_exefs, guest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ryujinx-data", help="Ryujinx data folder containing mods/ and sdcard/")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("Ce programme d'installation nécessite Windows.")
    bundle = Path(__file__).resolve().parent
    try:
        root = find_ryujinx_root(args.ryujinx_data)
        install(bundle, root)
        (bundle / "ryujinx-data.txt").write_text(str(root) + "\n", encoding="utf-8")
        # Leave Prism, Java arguments, Minecraft instances and worlds untouched.
        print("[BotwCraft] Minecraft not modified. Install the Fabric JAR manually if needed.")
        print("[BotwCraft] Start Minecraft yourself and use /botwcraft connect.")
    except (OSError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"[BotwCraft] ERREUR installation : {exc}")


if __name__ == "__main__":
    main()
