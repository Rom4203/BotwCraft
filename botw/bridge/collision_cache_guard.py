"""BotwCraft collision cache preflight: never launch silently without terrain."""
from __future__ import annotations
import os,sys,shutil,struct
from pathlib import Path

def valid_tile(p:Path)->bool:
    if p.is_symlink() or not p.is_file():return False
    try:
        with p.open('rb') as f:b=f.read(52)
        if len(b)!=52 or b[:4]!=b'BTRI':return False
        ver,x,z,count,wx,wz=struct.unpack_from('<IiiIii',b,4)
        return ver==1 and 0<=x<40 and 0<=z<32 and count<=1_000_000 and \
            (wx,wz)==(-5000+x*250,-4000+z*250) and p.stat().st_size==52+count*36
    except (OSError,ValueError,struct.error):return False

def tiles(root:Path,kind='terrain'):
    d=root/kind
    try:
        if d.is_symlink() or not d.is_dir():return []
    except OSError:return []
    return sorted(p for p in d.glob('*.btri') if valid_tile(p))

def ensure_cache(root:Path,search_parent:Path|None=None)->tuple[int,str]:
    dest=root/'terrain_cache'
    available=tiles(dest)
    if available:return len(available),'Cache BOTW valide'
    parent=search_parent or root.parent
    if not parent.is_dir():return 0,'Dossier parent inaccessible'
    candidates=[]
    # Scan only extracted BotwCraft directories. Never descend into system,
    # arbitrary user folders, or symlinks.
    for previous in parent.glob('BotwCraft*'):
        try:
            if not previous.is_dir() or previous.is_symlink() or previous.resolve()==root.resolve():continue
            source=previous/'terrain_cache'
            found=tiles(source)
            if found:candidates.append((len(found),source))
        except OSError:continue
    if not candidates:return 0,'Ancien cache introuvable : convertir le RomFS BOTW'
    _,source=max(candidates,key=lambda item:item[0])
    for kind in ('terrain','decor'):
        for p in tiles(source,kind):
            out=dest/kind/p.name
            out.parent.mkdir(parents=True,exist_ok=True)
            if not out.exists():shutil.copy2(p,out)
    return len(tiles(dest)),'Cache de collisions conserve depuis '+str(source)

def main():
    root=Path(__file__).resolve().parent.parent
    count,message=ensure_cache(root)
    print('[COLLISIONS]',message,'(tuiles:',count,')')
    if count==0:
        print('[COLLISIONS][ERREUR] Aucun terrain Zelda valide. Lance INSTALLER_COMPLET.bat')
        print('[COLLISIONS][ERREUR] Demarrage refuse plutot que collisions silencieusement absentes.')
        return 2
    return 0

if __name__=='__main__':sys.exit(main())
