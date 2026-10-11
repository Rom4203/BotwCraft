"""BotwCraft self-contained clean installer for Ryujinx BOTW Switch 1.5.0.

Correctif installation Windows: pas de chemin temporaire precharge. Version test20 low-latency. Copy-only: never touches Nintendo game dumps or saves.
Keeps rollback backups and verifies SHA256 on every installed native binary.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
TITLE = '01007ef00011e000'
UPPER = TITLE.upper()
MOD_NAME = 'BotwCraft'
BACKUPS = ROOT / 'backups'
MANIFEST = ROOT / 'installation.json'
NATIVE = {'exefs/subsdk9': ROOT/'native/subsdk9',
          'romfs/WiiXLaunch/mods/bwc_pose.wxlm': ROOT/'native/bwc_pose.wxlm'}


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda:f.read(1048576), b''):h.update(part)
    return h.hexdigest()


def process_running():
    if os.name != 'nt':return False
    try:
        p=subprocess.run(['tasklist','/FI','IMAGENAME eq Ryujinx.exe','/NH'],
                         capture_output=True,text=True,timeout=7)
        return 'ryujinx.exe' in p.stdout.lower()
    except (OSError,subprocess.TimeoutExpired):
        return True  # do not risk touching files while process state unknown


def _ryujinx_profile(candidate):
    """Resolve an explicit data folder or Ryujinx executable folder.

    Ryujinx may store Config.json in %%APPDATA%%\Ryujinx or in a portable
    sibling folder.  Do not use a folder unless Config.json really exists.
    """
    text=str(candidate).strip().strip('"').strip("'")
    if not text:return None
    root=Path(os.path.expandvars(text)).expanduser()
    if root.is_file() and root.name.lower()=='config.json':
        root=root.parent
    elif root.is_file() and root.name.lower()=='ryujinx.exe':
        root=root.parent
    for p in [root,root/'portable',root/'Ryujinx',root/'Ryujinx'/'portable']:
        if (p/'Config.json').is_file():
            return p.resolve()
    return None


def ryujinx_root(override: str|None, interactive:bool=False):
    """Never trust ryujinx-data.txt blindly: older archives accidentally
    shipped a /tmp test-profile path.  Validate it and auto-fallback.
    """
    if override:
        resolved=_ryujinx_profile(override)
        if not resolved:
            raise RuntimeError('Profil Ryujinx invalide : Config.json introuvable a : '+str(override))
        return resolved

    candidates=[]
    saved=ROOT/'ryujinx-data.txt'
    if saved.is_file():
        try:
            entry=saved.read_text(encoding='utf-8-sig').strip()
            if entry:candidates.append(('ancien chemin memorise',entry))
        except OSError:
            pass
    appdata=os.environ.get('APPDATA')
    if appdata:candidates.append(('%APPDATA%\\Ryujinx',str(Path(appdata)/'Ryujinx')))
    local=os.environ.get('LOCALAPPDATA')
    if local:candidates.append(('%LOCALAPPDATA%\\Ryujinx',str(Path(local)/'Ryujinx')))
    # Portable Ryujinx may sit beside this extracted ZIP or one level above.
    for parent in [ROOT, ROOT.parent, ROOT.parent.parent]:
        candidates.extend([
            ('Ryujinx portable',str(parent/'Ryujinx'/'portable')),
            ('Ryujinx portable',str(parent/'ryujinx'/'portable')),
            ('Ryujinx portable',str(parent/'portable')),
        ])
    selected=None
    for label,item in candidates:
        profile=_ryujinx_profile(item)
        if profile is not None:
            selected=profile
            print(f'[RYUJINX] Profil candidat ({label}) : {selected}')
            break
        if label=='ancien chemin memorise':
            print('[RYUJINX] Ancien chemin invalide ignore :',item)

    if interactive and sys.stdin.isatty():
        print('')
        print('Dossier de DONNEES Ryujinx : celui qui contient Config.json.')
        print('Si Ryujinx est PORTABLE, indique le dossier Ryujinx\\portable.')
        if selected is not None:
            print('Profil propose :',selected)
            response=input('Entree = utiliser ce profil ; autre chemin = saisir ici : ').strip().strip('"')
        else:
            response=input('Chemin du profil Ryujinx (contient Config.json) : ').strip().strip('"')
        if response:
            chosen=_ryujinx_profile(response)
            if chosen is None:
                raise RuntimeError('Le chemin indique ne contient pas de Config.json : '+response)
            selected=chosen
    if selected is None:
        raise RuntimeError(
            'Aucun profil Ryujinx valide detecte. Indique le dossier qui contient Config.json '
            '(ou le dossier Ryujinx.exe avec un sous-dossier portable) : '
            'python install_clean.py --ryujinx "C:\\...\\Ryujinx"')
    return selected


def destinations(profile):
    return (profile/'mods'/'contents'/TITLE/MOD_NAME,
            profile/'sdcard'/'WiiXLaunch'/'mods'/UPPER)


def validate_native():
    for name,source in NATIVE.items():
        if not source.is_file() or source.stat().st_size<1024:
            raise RuntimeError(f'Fichier natif absent ou incomplet : {source}')
    if not (ROOT/'bridge/botwcraft-rust-bridge.exe').is_file():
        raise RuntimeError('Exécutable Rust du bridge absent')
    if not (ROOT/'compositor/Cargo.toml').is_file():
        raise RuntimeError('Sources de la fenêtre Rust absents')
    if not (ROOT/'minecraft_mods/skycraft-0.1.2.jar').is_file():
        raise RuntimeError('Mod Minecraft absent du projet')


def verify(profile):
    mod, sd=destinations(profile)
    if not mod.is_dir():raise RuntimeError(f'Mod Ryujinx pas installé : {mod}')
    for part,source in NATIVE.items():
        path=mod/part
        if not path.is_file():raise RuntimeError(f'Fichier absent dans Ryujinx : {path}')
        if sha(path)!=sha(source):
            raise RuntimeError(f'Fichier incorrect (hash différent) : {path}')
    modules=list((mod/'romfs/WiiXLaunch/mods').glob('*.wxlm'))
    if sorted(x.name.lower() for x in modules)!=['bwc_pose.wxlm']:
        raise RuntimeError(f'Mélange de modules BOTW : {[x.name for x in modules]}')
    if (sd/'botwcraft.wxlm').exists():
        raise RuntimeError(f'Ancien botwcraft.wxlm toujours présent sur SD : {sd}')
    if not (sd/'bwc_pose.wxlm').is_file() or sha(sd/'bwc_pose.wxlm')!=sha(NATIVE['romfs/WiiXLaunch/mods/bwc_pose.wxlm']):
        raise RuntimeError('Fichier .wxlm SD incorrect')
    print('[OK] 1 seul module actif pour BotwCraft : bwc_pose.wxlm')
    print('[OK] Correct subsdk9 et bwc_pose.wxlm dans RomFS (SHA256 identiques)')
    print('[OK] Copie SD du module cohérente, ancien botwcraft.wxlm supprimé')
    print('[OK] Profil Ryujinx :',profile)


def backup_files(profile):
    oldmod,oldsd=destinations(profile)
    stamp=dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    bak=BACKUPS/stamp
    bak.mkdir(parents=True,exist_ok=False)
    if oldmod.exists():
        if oldmod.is_symlink():raise RuntimeError('Refus de modifier un ancien mod symbolic link')
        shutil.copytree(oldmod,bak/'ancien_mod_Ryujinx')
    if oldsd.exists():
        if oldsd.is_symlink():raise RuntimeError('Refus de modifier un dossier SD symbolic link')
        shutil.copytree(oldsd,bak/'ancien_mod_SD')
    return bak


def install(profile):
    if process_running():
        raise RuntimeError('Ferme complètement Ryujinx avant installation (Ryujinx.exe encore actif).')
    validate_native()
    mod,sd=destinations(profile)
    print('[1/4] Sauvegarde de tes anciens modules (et non des sauvegardes BOTW)...')
    backup=backup_files(profile)
    print('      Sauvegarde:',backup)
    try:
        print('[2/4] Installation propre du mod Ryujinx : AUCUN ancien botwcraft.wxlm...')
        stage=mod.parent/(MOD_NAME+'.installing')
        if stage.exists():shutil.rmtree(stage)
        for part,source in NATIVE.items():
            target=stage/part
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target)
        if mod.exists():shutil.rmtree(mod)
        stage.rename(mod)
        print('[3/4] Nettoyage des 2 vieux modules SD, puis installation du nouveau...')
        sd.mkdir(parents=True,exist_ok=True)
        for file in ('botwcraft.wxlm','bwc_pose.wxlm'):
            old=sd/file
            if old.is_file():old.unlink()
        shutil.copy2(NATIVE['romfs/WiiXLaunch/mods/bwc_pose.wxlm'],sd/'bwc_pose.wxlm')
        print('[4/4] Vérification SHA256, présence et doublons...')
        verify(profile)
        MANIFEST.write_text(json.dumps({
            'ryujinx_profile':str(profile),
            'created_at':dt.datetime.now().isoformat(),
            'backup':str(backup),
            'native_hashes':{part:sha(source) for part,source in NATIVE.items()},
            'version':'2026-10-10-lowlatency-bdp2-v7',
        },indent=2,ensure_ascii=False),encoding='utf-8')
        (ROOT/'ryujinx-data.txt').write_text(str(profile)+'\n',encoding='utf-8')
        print('\n[INSTALLATION REUSSIE] Ton jeu et tes sauvegardes ne sont pas modifiés.')
        print('[INSTALLATION REUSSIE] Lance START_BOTWCRAFT.bat pour démarrer.')
    except Exception:
        print('[ERREUR] Tentative de restauration automatique des fichiers précédents...',file=sys.stderr)
        restore_files(profile,backup)
        raise


def restore_files(profile, backup):
    if process_running():raise RuntimeError('Ferme Ryujinx avant restauration.')
    mod,sd=destinations(profile)
    # The installer knows exactly which two locations it touched.
    old=backup/'ancien_mod_Ryujinx'
    if mod.exists():shutil.rmtree(mod)
    if old.exists():
        mod.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(old,mod)
    old=backup/'ancien_mod_SD'
    if sd.exists():
        (sd/'bwc_pose.wxlm').unlink(missing_ok=True)
        (sd/'botwcraft.wxlm').unlink(missing_ok=True)
    if old.exists():
        if sd.exists():shutil.rmtree(sd)
        sd.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(old,sd)
    print('[OK] Retour à la configuration précédente réalisé depuis',backup)


def minecraft_copy(path):
    dest=Path(os.path.expandvars(path)).expanduser()
    if not dest.is_dir():raise RuntimeError('Dossier Minecraft mods introuvable : '+str(dest))
    target=dest/'skycraft-0.1.2.jar'
    if target.exists() and sha(target)!=sha(ROOT/'minecraft_mods/skycraft-0.1.2.jar'):
        backup=BACKUPS/('minecraft_'+dt.datetime.now().strftime('%Y%m%d_%H%M%S'))
        backup.mkdir(parents=True,exist_ok=True)
        shutil.copy2(target,backup/target.name)
        print('[MC] Ancien mod Minecraft sauvegardé :',backup/target.name)
    shutil.copy2(ROOT/'minecraft_mods/skycraft-0.1.2.jar',target)
    if sha(target)!=sha(ROOT/'minecraft_mods/skycraft-0.1.2.jar'):
        raise RuntimeError('Copie Minecraft invalide')
    print('[MC] skycraft-0.1.2.jar installé dans',target)


def main():
    p=argparse.ArgumentParser(description='Installer BotwCraft clean pour BOTW 1.5.0 sur Ryujinx')
    p.add_argument('--ryujinx',help='Dossier de profil Ryujinx, celui qui contient Config.json')
    action=p.add_mutually_exclusive_group()
    action.add_argument('--verify',action='store_true',help='Vérification uniquement, aucune écriture')
    action.add_argument('--restore',action='store_true',help='Restaure les mods de la dernière installation')
    p.add_argument('--minecraft-mods',help='Dossier mods de TON instance Minecraft/Prism à alimenter')
    a=p.parse_args()
    profile=ryujinx_root(a.ryujinx, interactive=not (a.verify or a.restore))
    if a.restore:
        if not MANIFEST.is_file():raise RuntimeError('Aucune installation enregistrée à restaurer')
        state=json.loads(MANIFEST.read_text(encoding='utf-8'))
        if Path(state['ryujinx_profile'])!=profile:raise RuntimeError('Profil installé différent : renseigne --ryujinx')
        restore_files(profile,Path(state['backup']))
        MANIFEST.unlink(missing_ok=True)
    elif a.verify:
        validate_native();verify(profile)
    else:
        install(profile)
        if a.minecraft_mods:
            minecraft_copy(a.minecraft_mods)
        elif sys.stdin.isatty():
            print('\nMinecraft : si le mod est déjà dans Prism, appuie Entrée.')
            print('Sinon, copie le chemin du dossier « mods » de TON instance Minecraft.')
            try: value=input('Chemin Minecraft mods (Entrée = ne pas changer) : ').strip().strip('"')
            except EOFError:value=''
            if value:minecraft_copy(value)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('\n[BOTWCRAFT][ERREUR]',exc,file=sys.stderr)
        raise SystemExit(1)
