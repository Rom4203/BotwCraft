#!/usr/bin/env python3
"""BW3D: place an actual physics-enabled BOTW box in the native Hyrule world.

This is a map-unit test, NOT a screen-space render, and NOT yet the SDK for
arbitrary imported triangle meshes. It uses an existing Nintendo actor from the
user's own RomFS. The output is a stand-alone Ryujinx RomFS replacement for
one dynamic map tile, without modifying the original, saves, or BotwCraft.

Requires: pip install oead
"""
from __future__ import annotations
import argparse
import math
import pathlib
import re
import sys
import zlib

ACTORS = {"wood": "Kibako_Contain_01", "iron": "Obj_BreakBoxIron"}
MAP_PATTERN = re.compile(r"^([A-J])-(\d{1,2})_Dynamic\.smubin$")
MAX_BYTES = 48 * 1024 * 1024

def _lib():
    try:
        import oead
    except ImportError as e:
        raise RuntimeError("Module Python 'oead' absent. Installer: py -m pip install oead") from e
    return oead

def load_smubin(path, oead):
    raw = path.read_bytes()
    if not 16 <= len(raw) <= MAX_BYTES:
        raise ValueError(f"Fichier Map trop grand ou incomplet : {path}")
    compressed = raw[:4] == b"Yaz0"
    if compressed:
        uncompressed = oead.yaz0.decompress(raw)
        alignment = int(oead.yaz0.get_header(raw).data_alignment)
    else:
        uncompressed = raw
        alignment = 0
    if bytes(uncompressed[:2]) != b"YB":
        raise ValueError(f"BYML Switch little-endian invalide : {path}")
    version = int.from_bytes(bytes(uncompressed[2:4]), "little")
    if version not in (2, 3, 4):
        raise ValueError(f"BYML version inattendue : {version}")
    result = oead.byml.from_binary(uncompressed)
    if "Objs" not in result or "Rails" not in result:
        raise ValueError(f"Ce n'est pas un Map Unit Dynamic Zelda : {path}")
    return result, compressed, alignment, version

def dist_to_map(objects, x, z):
    """Infer only an existing map's region from its real placed object coordinates.
    Never invent a tile index or a world origin to force a fake placement.
    """
    points=[]
    for obj in objects:
        p=obj.get("Translate")
        if p and len(p)==3:
            try:
                q=[float(v) for v in p]
                if all(math.isfinite(v) for v in q):
                    points.append((q[0],q[2]))
            except (ValueError,TypeError):
                continue
    if not points:
        return float("inf"),float("inf")
    xs=sorted(q[0] for q in points)
    zs=sorted(q[1] for q in points)
    # A map tile may contain a few decorative props spanning its border.
    def distance(p,values):
        return 0.0 if values[0] <= p <= values[-1] else min(abs(p-values[0]),abs(p-values[-1]))
    distance=math.hypot(distance(x,xs),distance(z,zs))
    midx=xs[len(xs)//2]
    midz=zs[len(zs)//2]
    return distance,math.hypot(x-midx,z-midz)

def choose_map(romfs,x,z,oead,requested=None):
    if requested:
        p=pathlib.Path(requested).resolve()
        if not p.is_file() or not MAP_PATTERN.fullmatch(p.name):
            raise ValueError("Préciser un fichier *_Dynamic.smubin original du RomFS BOTW.")
        root,compressed,alignment,version=load_smubin(p,oead)
        d,center=dist_to_map(root["Objs"],x,z)
        if d>600 or center>1200:
            raise ValueError("Les coordonnées sont trop éloignées de cette région de la carte.")
        return p,root,compressed,alignment,version
    base=romfs/"Map"/"MainField"
    if not base.is_dir():
        raise FileNotFoundError("Dossier RomFS absent : "+str(base))
    candidates=[]
    for p in sorted(base.glob("*/*_Dynamic.smubin")):
        if not MAP_PATTERN.fullmatch(p.name):
            continue
        try:
            root,compressed,alignment,version=load_smubin(p,oead)
            d,center=dist_to_map(root["Objs"],x,z)
            if d <= 350 and center < 1000:
                candidates.append(((d,center),p,root,compressed,alignment,version))
        except (ValueError, OSError):
            continue
    if not candidates:
        raise RuntimeError("Aucune région correspondant à XYZ. Essayer --map avec un fichier original.")
    candidates.sort(key=lambda c:c[0])
    best=candidates[0]
    if len(candidates)>1 and best[0][0]>100 and abs(candidates[1][0][0]-best[0][0])<20:
        raise RuntimeError("Position ambiguë entre deux régions. Préciser --map.")
    return best[1:]

def make_object(root,x,y,z,actor,oead):
    old=root["Objs"]
    hashes={int(obj.get("HashId",0)) for obj in old}
    # Fixed and reproducible ID. Hash must not collide with ANY in-game object.
    seed=f"BW3D native crate|{actor}|{x:.3f}|{y:.3f}|{z:.3f}".encode()
    new_hash=zlib.crc32(seed)&0xffffffff
    while new_hash in hashes or new_hash==0:
        new_hash=(new_hash+1)&0xffffffff
    item=oead.byml.Hash({
        "HashId":oead.U32(new_hash),
        "SRTHash":oead.S32(0),
        "Translate":oead.byml.Array([oead.F32(x),oead.F32(y),oead.F32(z)]),
        "Rotate":oead.F32(0.),
        "IsStatic":False,
        "UnitConfigName":actor,
    })
    old.append(item)
    # Dynamic map unit search is indexed by HashId.
    old.sort(key=lambda v:int(v["HashId"]))
    return new_hash,len(old)

def build(romfs,xyz,out,kind="wood",map_file=None):
    oead=_lib()
    romfs=pathlib.Path(romfs).expanduser().resolve()
    out=pathlib.Path(out).expanduser().resolve()
    if not romfs.is_dir():
        raise FileNotFoundError("Dossier RomFS original introuvable : "+str(romfs))
    if out==romfs or romfs in out.parents:
        raise ValueError("La sortie doit être HORS du dump RomFS original.")
    x,y,z=map(float,xyz)
    if not all(math.isfinite(v) and -10000.<v<10000. for v in (x,y,z)):
        raise ValueError("XYZ invalide.")
    file,root,compressed,alignment,version=choose_map(romfs,x,z,oead,map_file)
    hash_id,count=make_object(root,x,y,z,ACTORS[kind],oead)
    binary=bytes(oead.byml.to_binary(root,big_endian=False,version=version))
    # Re-read BEFORE touching the output. Check all original actors remained.
    check=oead.byml.from_binary(binary)
    if len(check["Objs"])!=count or sum(
      int(a["HashId"])==hash_id for a in check["Objs"])!=1:
        raise RuntimeError("Invalid BYML roundtrip. No file emitted.")
    data=bytes(oead.yaz0.compress(binary,data_alignment=alignment)) if compressed else binary
    relative=file.relative_to(romfs)
    dst=out/"romfs"/relative
    if dst.exists():
        raise FileExistsError("La destination existe déjà : "+str(dst))
    dst.parent.mkdir(parents=True,exist_ok=True)
    temp=dst.with_suffix(dst.suffix+".new")
    temp.write_bytes(data)
    temp.replace(dst)
    return dst,hash_id

def main(argv=None):
    parser=argparse.ArgumentParser(description="Placer une vraie caisse 3D physique dans BOTW (pas un overlay).")
    parser.add_argument("--romfs",required=True,help="Dossier RomFS de votre propre dump BOTW Switch")
    parser.add_argument("--x",type=float,required=True,help="Coordonnée X absolue Hyrule")
    parser.add_argument("--y",type=float,required=True,help="Coordonnée Y du SOL Hyrule")
    parser.add_argument("--z",type=float,required=True,help="Coordonnée Z absolue Hyrule")
    parser.add_argument("--out",required=True,help="Dossier distinct pour le mod Ryujinx")
    parser.add_argument("--kind",choices=sorted(ACTORS),default="wood")
    parser.add_argument("--map",dest="map_file",help="Fichier Dynamic original si la détection automatique est ambiguë")
    args=parser.parse_args(argv)
    try:
        dst,hid=build(args.romfs,(args.x,args.y,args.z),args.out,args.kind,args.map_file)
    except (ValueError, RuntimeError, FileNotFoundError, FileExistsError, OSError) as e:
        parser.exit(2,"[BW3D] ERREUR : "+str(e)+"\n")
    print("[BW3D] OBJET PHYSIQUE AJOUTÉ : ",ACTORS[args.kind])
    print("[BW3D] POSITION HYRULE : ",args.x,args.y,args.z)
    print("[BW3D] HASHID : ",hex(hid))
    print("[BW3D] FICHIER MOD (ne modifie pas le jeu original) : ",dst)
    print("[BW3D] Copier le contenu du dossier de sortie dans le dossier du mod RomFS Ryujinx.")
    return 0

if __name__=="__main__":
    sys.exit(main())
