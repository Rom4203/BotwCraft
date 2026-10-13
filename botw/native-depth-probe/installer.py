from __future__ import annotations
import os, subprocess, shutil, sys
from pathlib import Path

TITLE="01007EF00011E000"
PROBE="bwc_depth_probe.wxlm"
MOD_NAME="BotwCraft-NVN-Depth-Diagnostic"
ROOT=Path(__file__).resolve().parent

def profile():
    paths=[]
    if (x:=os.getenv("APPDATA")): paths.append(Path(x)/"Ryujinx")
    if (x:=os.getenv("LOCALAPPDATA")): paths.append(Path(x)/"Ryujinx")
    paths += [Path(r"D:\\Jeux\\Emu\\ryujinx\\portable"),Path(r"D:\\Jeux\\Emu\\ryujinx")]
    for candidate in paths:
        if (candidate/"Config.json").is_file():return candidate
    print("Profil Ryujinx introuvable automatiquement.")
    p=Path(input("Dossier qui contient Config.json : ").strip().strip('"'))
    if not (p/"Config.json").is_file():raise RuntimeError("Config.json absent")
    return p

def main():
    if os.name!="nt":raise RuntimeError("Windows uniquement")
    p=subprocess.run(["tasklist","/FI","IMAGENAME eq Ryujinx.exe","/NH"],capture_output=True,text=True)
    if "ryujinx.exe" in p.stdout.lower():raise RuntimeError("Ferme Ryujinx avant l'installation")
    base=profile()
    stable=base/"mods"/"contents"/TITLE.lower()/"BotwCraft"/"romfs"/"WiiXLaunch"/"mods"/"bwc_pose.wxlm"
    # Windows is case-insensitive, so TITLE.lower() matches the stock installer.
    if not stable.is_file():
        raise RuntimeError("Installe d'abord ton BotwCraft habituel, module bwc_pose introuvable : "+str(stable))
    # A separate Ryujinx content mod: no modification to the user's working BotwCraft.
    mod=base/"mods"/"contents"/TITLE/MOD_NAME
    path=mod/"romfs"/"WiiXLaunch"/"mods"/PROBE
    sd=base/"sdcard"/"WiiXLaunch"/"mods"/TITLE/PROBE
    if len(sys.argv)>1 and sys.argv[1]=="--disable":
        path.unlink(missing_ok=True)
        sd.unlink(missing_ok=True)
        print("[OK] Diagnostic desac tive ; installation BotwCraft conservee")
        return
    file=ROOT/PROBE
    if not file.is_file():raise RuntimeError("Module compile absent : "+str(file))
    print("Profil :",base)
    print("Module additionnel :",path)
    print("AUCUN module BotwCraft, Minecraft ou subsdk9 existant n'est remplace.")
    if input("Installer le diagnostic experimental ? (O/N) : ").strip().lower()!="o":
        print("Annule");return
    for dst in (path,sd):
        if dst.exists() and dst.read_bytes()!=file.read_bytes():
            raise RuntimeError("Un autre module diagnostique existe deja : "+str(dst))
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(file,dst)
    print("[OK] Diagnostic de profondeur installe.")
    print("Lance ton BotwCraft habituel. Si Ryujinx plante, ferme-le puis relance")
    print("INSTALLER_COMPLET.bat et choisis la desactivation.")
if __name__=="__main__":
    try:main()
    except Exception as e:print("[ERREUR]",e);sys.exit(1)
