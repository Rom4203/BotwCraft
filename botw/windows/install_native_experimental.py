"""Install ONLY the experimental bwc_pose.wxlm alongside existing BotwCraft.
Keep subsdk9 and the original botwcraft.wxlm unmodified.
"""
from pathlib import Path
import shutil,sys,time

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from install_native import find_ryujinx_root, _copy_atomically

TITLE="01007ef00011e000"
UPPER=TITLE.upper()

def main():
    src=ROOT/"ryujinx_sdcard"/"WiiXLaunch"/"mods"/UPPER/"bwc_pose.wxlm"
    if not src.is_file() or src.stat().st_size<256:
        raise FileNotFoundError("The compiled experimental bwc_pose.wxlm is missing.")
    saved=ROOT/"ryujinx-data.txt"
    data=(saved.read_text(encoding="utf-8").strip() if saved.is_file() else None)
    try:
        ryroot=find_ryujinx_root(data)
    except (OSError,ValueError):
        ryroot=find_ryujinx_root(None)
    if not (ryroot/"mods"/"contents").is_dir() or not (ryroot/"sdcard").is_dir():
        raise ValueError("Ryujinx profile must contain mods/contents AND sdcard")
    targets=[
      ryroot/"mods"/"contents"/TITLE/"BotwCraft"/"romfs"/"WiiXLaunch"/"mods"/"bwc_pose.wxlm",
      ryroot/"sdcard"/"WiiXLaunch"/"mods"/UPPER/"bwc_pose.wxlm",
    ]
    stamp=time.strftime("%Y%m%d-%H%M%S")
    for target in targets:
        if target.is_file():
            backup=ROOT/"backups"/stamp/(target.name+"-"+str(len(str(target))))
            backup.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(target,backup)
            print(f"[NATIVE] Backed up existing experimental mod: {backup}")
        _copy_atomically(src,target)
        print(f"[NATIVE] Installed: {target}")
    saved.write_text(str(ryroot)+"\n",encoding="utf-8")
    print("[NATIVE] Original subsdk9 and botwcraft.wxlm preserved; saves untouched.")

if __name__=="__main__":
    try:main()
    except (OSError,ValueError) as e:
        print("[NATIVE] Installation failed:",e,file=sys.stderr)
        raise SystemExit(1)
