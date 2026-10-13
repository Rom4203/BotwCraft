from __future__ import annotations
import os, subprocess, shutil, sys, struct
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
    valid=[p for p in paths if (p/"Config.json").is_file()]
    # Prefer the profile that actually contains the working BotwCraft,
    # not an old unused AppData profile when Ryujinx is in portable mode.
    for p in valid:
        stable=p/"mods"/"contents"/TITLE.lower()/"BotwCraft"/"romfs"/"WiiXLaunch"/"mods"/"bwc_pose.wxlm"
        if stable.is_file():return p
    if len(valid)==1:return valid[0]
    print("Profil BotwCraft Ryujinx introuvable automatiquement.")
    p=Path(input("Dossier qui contient Config.json : ").strip().strip('"'))
    if not (p/"Config.json").is_file():raise RuntimeError("Config.json absent")
    return p

def main():
    if os.name!="nt":raise RuntimeError("Windows uniquement")
    p=subprocess.run(["tasklist","/FI","IMAGENAME eq Ryujinx.exe","/NH"],capture_output=True,text=True)
    if "ryujinx.exe" in p.stdout.lower():raise RuntimeError("Ferme Ryujinx avant l'installation")
    base=profile()
    # A separate Ryujinx content mod: do not change the working BotwCraft.
    mod=base/"mods"/"contents"/TITLE/MOD_NAME
    path=mod/"romfs"/"WiiXLaunch"/"mods"/PROBE
    sd=base/"sdcard"/"WiiXLaunch"/"mods"/TITLE/PROBE
    if len(sys.argv)>1 and sys.argv[1]=="--disable":
        path.unlink(missing_ok=True)
        sd.unlink(missing_ok=True)
        print("[OK] Diagnostic desactive ; installation BotwCraft conservee")
        return
    stable=base/"mods"/"contents"/TITLE.lower()/"BotwCraft"/"romfs"/"WiiXLaunch"/"mods"/"bwc_pose.wxlm"
    if not stable.is_file():
        raise RuntimeError("Installe d'abord ton BotwCraft habituel, module bwc_pose introuvable : "+str(stable))
    file=ROOT/PROBE
    if not file.is_file():raise RuntimeError("Module compile absent : "+str(file))
    expected=file.read_bytes()
    if not (expected[:4]==b"MLXW" and expected[12:27]==b"bwc_depth_probe"):
        raise RuntimeError("Paquet compile invalide (en-tete WiiXLaunch incorrect)")
    expected_crc=struct.unpack_from("<I",expected,40)[0]
    print("[VERIF] Module du ZIP :",len(expected),"octets ; CRC attendu dans Ryujinx : 0x%08X"%expected_crc)
    print("Profil :",base)
    print("Module additionnel :",path)
    print("AUCUN module BotwCraft, Minecraft ou subsdk9 existant n'est remplace.")
    if input("Installer le diagnostic experimental ? (O/N) : ").strip().lower()!="o":
        print("Annule");return
    for dst in (path,sd):
        # Users may already have our older NDP1 probe. Upgrade only a known
        # WiiXLaunch module with the exact bwc_depth_probe identity.
        if dst.exists() and dst.read_bytes()!=file.read_bytes():
            old=dst.read_bytes()
            if not (old.startswith(b"MLXW") and old[12:27]==b"bwc_depth_probe"):
                raise RuntimeError("Refus de remplacer un module inconnu : "+str(dst))
            print("[MAJ] Ancienne sonde diagnostique remplacee :",dst)
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(file,dst)
    for dst in (path,sd):
        if not dst.is_file() or dst.read_bytes()!=expected:
            raise RuntimeError("Verification installation impossible : "+str(dst))
    print("[OK] Nouveau diagnostic installe et verifie.")
    print("[VERIF] Dans logs/botwcraft.log, repere :")
    print("        [loader:bwc_depth_probe] integrity OK (crc32 0x%08X"%expected_crc)
    print("       Si tu lis un autre CRC, Ryujinx charge encore une ancienne sonde.")
    print("Lance ton BotwCraft habituel. Si Ryujinx plante, ferme-le puis relance")
    print("INSTALLER_COMPLET.bat et choisis la desactivation.")
if __name__=="__main__":
    try:main()
    except Exception as e:print("[ERREUR]",e);sys.exit(1)
