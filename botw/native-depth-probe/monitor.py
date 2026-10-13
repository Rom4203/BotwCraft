from __future__ import annotations
import os,sys,time
from pathlib import Path

def roots():
    out=[]
    for name in ["APPDATA","LOCALAPPDATA"]:
        if os.getenv(name):out.append(Path(os.getenv(name))/"Ryujinx")
    out.extend([Path(r"D:\\Jeux\\Emu\\ryujinx\\portable"),
                Path(r"D:\\Jeux\\Emu\\ryujinx")])
    return out

def latest():
    out=[]
    for p in roots():
        for d in (p/"Logs",p/"logs"):
            if d.exists():
                out.extend(x for x in d.glob("*.log") if x.is_file())
    return max(out,key=lambda x:x.stat().st_mtime) if out else None

def main():
    print("BOTWCRAFT : MONITEUR NVN - profondeur Zelda")
    print("Lance normalement Zelda et Minecraft avec BotwCraft.")
    print("Il faut entrer dans le monde (pas rester au menu).")
    print("Le test ne modifie pas les textures ou les collisions.")
    seen=set(); start=time.monotonic(); current=None; cursor=0; had=False
    while time.monotonic()-start<180:
        chosen=latest()
        if chosen is not None:
            if chosen!=current:
                current=chosen; cursor=0
                print("Ryujinx :",chosen)
            try:
                with chosen.open("rb") as f:
                    f.seek(cursor)
                    data=f.read(1024*1024);cursor=f.tell()
                for row in data.decode("utf8","replace").splitlines():
                    if "[DEPTH_PROBE]" not in row:continue
                    had=True
                    if row not in seen:
                        print(row[-450:])
                        seen.add(row)
            except (OSError,ValueError):
                pass
        time.sleep(.4)
    if not had:
        print("Aucun message DEPTH_PROBE detecte dans les logs Ryujinx.")
        print("Cela peut signifier que le module n'est pas charge ou que les logs sont ailleurs.")
    print("Copie les lignes [DEPTH_PROBE] ou envoie le dernier log Ryujinx.")

if __name__=="__main__":main()
