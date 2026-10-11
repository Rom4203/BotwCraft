#!/usr/bin/env python3
"""Install ONLY the patched exact-test20 Minecraft JAR in a selected instance.
Does not edit Ryujinx, shaders, saves, Prism instance settings, gameplay mods
or any archive automatically. Preserves everything it replaces as a backup.
"""
from pathlib import Path
import hashlib,sys,shutil,time
ROOT=Path(__file__).resolve().parent
SRC=ROOT/'minecraft_mods'/'skycraft-0.1.2.jar'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    if not SRC.exists():raise RuntimeError('JAR BotwCraft absent')
    print('Entre le CHEMIN DU DOSSIER mods de ton INSTANCE Prism.')
    if len(sys.argv)>1: destination=Path(sys.argv[1].strip('"'))
    else: destination=Path(input('Dossier mods : ').strip().strip('"'))
    if not destination.is_dir():raise ValueError('Ce dossier mods est introuvable : '+str(destination))
    # Never install if Minecraft itself is using the JAR.
    target=destination/'skycraft-0.1.2.jar'
    stamp=time.strftime('%Y%m%d_%H%M%S')
    backup=ROOT/'backups'/('Minecraft_Avant_Correctif_'+stamp)
    candidates=[p for p in destination.iterdir()
        if p.is_file() and p.suffix.lower()=='.jar' and p.name.lower().startswith('skycraft')]
    backup.mkdir(parents=True,exist_ok=True)
    for p in candidates: shutil.copy2(p,backup/p.name)
    temp=destination/'skycraft-0.1.2.jar.installing'
    try:
        shutil.copy2(SRC,temp)
        if sha(temp)!=sha(SRC):raise RuntimeError('Echec verification de copie SHA256')
        for p in candidates: p.unlink()
        temp.replace(target)
        assert sha(target)==sha(SRC)
    except BaseException:
        temp.unlink(missing_ok=True)
        if not target.exists():
            for p in backup.iterdir():shutil.copy2(p,destination/p.name)
        raise
    print('[OK] Un seul SkyCraft :',target)
    print('[OK] SHA256 :',sha(target))
    print('[OK] Sauvegardes :',backup)
    print('Le composant Zelda et la camera premiere personne ne sont PAS modifies.')
if __name__=='__main__':
    try:main()
    except Exception as e:
        print('[ERREUR]',e,file=sys.stderr)
        raise SystemExit(1)
