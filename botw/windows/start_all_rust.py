"""Isolated one-click supervisor for BotwCraft native Rust bridge test.

Uses the already-working Rust compositor third window. No Python host,
no Python direct-memory writer, no virtual controller, one combined log.
"""
from __future__ import annotations
import os,sys,subprocess,time,socket,threading,datetime,shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
LOG=ROOT/"logs"/"botwcraft.log"
RYUJINX_DEFAULT=Path(r"D:\Jeux\Emu\ryujinx\Ryujinx.exe")
log_lock=threading.Lock()

def log(tag,text):
    line=f"[{tag}] {str(text).rstrip()}"
    with log_lock:
        print(line,flush=True)
        with LOG.open("a",encoding="utf-8") as out:out.write(line+"\n")

def proc_reader(name,p):
    try:
        for line in p.stdout:log(name,line)
    except OSError as e:log("LOGGER",e)

def spawn(name,argv,cwd=ROOT):
    log("LAUNCH",f"{name}: {subprocess.list2cmdline([str(x) for x in argv])}")
    p=subprocess.Popen([str(x) for x in argv],cwd=str(cwd),
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding="utf-8",
        errors="replace",bufsize=1,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    threading.Thread(target=proc_reader,args=(name,p),daemon=True).start()
    return p

def port_ready():
    try:
        with socket.create_connection(("127.0.0.1",39847),timeout=.25):return True
    except OSError:return False

def config_path(name):
    p=ROOT/name
    if p.is_file():
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            value=line.strip().strip('"')
            if value and not value.startswith("#"):
                return Path(os.path.expandvars(value)).expanduser()
    return None

def ryujinx_running():
    try:
        result=subprocess.run(["tasklist","/FI","IMAGENAME eq Ryujinx.exe","/NH"],
            capture_output=True,text=True,timeout=4)
        return "ryujinx.exe" in result.stdout.lower()
    except (OSError,subprocess.TimeoutExpired):return False

def main():
    LOG.parent.mkdir(parents=True,exist_ok=True)
    log("LAUNCH","="*54)
    log("LAUNCH",f"Rust native BOTW session {datetime.datetime.now().isoformat(timespec='seconds')}")
    if os.name!="nt":
        log("LAUNCH","This run requires Windows/Ryujinx");return 2
    processes=[]
    try:
        exe=ROOT/"bridge"/"botwcraft-rust-bridge.exe"
        if not exe.is_file():
            log("LAUNCH","Rust bridge executable missing from distribution");return 1
        if port_ready():
            log("LAUNCH","Port 39847 already in use: stop the old Python bridge");return 1
        processes.append(("RUST_BRIDGE",spawn("RUST_BRIDGE",[exe])))
        for _ in range(60):
            if port_ready():break
            if processes[0][1].poll() is not None:
                log("LAUNCH","Rust bridge exited during startup");return 1
            time.sleep(.25)
        else:
            log("LAUNCH","Rust bridge did not open port 39847");return 1
        # Rust bridge tails ONLY positions from the current Ryujinx launch.
        # Do not run the legacy Python relay: it replayed stale positions
        # from previous append-only botwcraft.log sessions.
        log("LAUNCH","Live BOTW pose relay is integrated into the Rust bridge")
        if not ryujinx_running():
            r=config_path("ryujinx-exe-path.txt") or RYUJINX_DEFAULT
            if r.is_file():processes.append(("RYUJINX_PROCESS",spawn("RYUJINX_PROCESS",[r],r.parent)))
            else:log("LAUNCH",f"Ryujinx executable not found: {r}; start Ryujinx manually")
        comp_dir=ROOT/"compositor"
        comp_exe=None
        for name in ("botwcraft-compositor.exe","BotwCraft.exe","botwcraft.exe"):
            candidate=comp_dir/name
            if candidate.is_file():comp_exe=candidate;break
        if comp_exe is None:
            candidate=comp_dir/"target"/"release"/"botwcraft-compositor.exe"
            if candidate.is_file():comp_exe=candidate
        if comp_exe is None and (comp_dir/"Cargo.toml").is_file() and shutil.which("cargo"):
            log("LAUNCH","Compiling third-window Rust compositor")
            for args in (["cargo","build","--release","--offline"],["cargo","build","--release"]):
                result=spawn("RUST_COMPOSITOR_BUILD",args,comp_dir)
                code=result.wait()
                if code==0:break
            if code==0:
                comp_exe=comp_dir/"target"/"release"/"botwcraft-compositor.exe"
        if comp_exe is not None and comp_exe.is_file():
            processes.append(("COMPOSITOR",spawn("COMPOSITOR",[comp_exe],comp_exe.parent)))
        else:
            log("LAUNCH","Third-window compositor not installed or build failed")
        log("LAUNCH","Start Minecraft then use /botwcraft connect and /botwcraft inputs on")
        log("LAUNCH","No Enter confirmation, Python relay, or old DIRECT_LINK needed.")
        log("LAUNCH",f"Single diagnostic file: {LOG}")
        while True:
            for name,p in processes:
                if p.poll() is not None and not getattr(p,"_reported",False):
                    p._reported=True
                    log("LAUNCH",f"{name} exited with code {p.returncode}")
                    if name=="RUST_BRIDGE":return 1
            time.sleep(.4)
    except KeyboardInterrupt:
        log("LAUNCH","Stopping spawned processes")
        return 0
    finally:
        for name,p in reversed(processes):
            if p.poll() is None:
                try:p.terminate()
                except OSError:pass
        for name,p in reversed(processes):
            try:p.wait(timeout=4)
            except subprocess.TimeoutExpired:
                p.kill()

if __name__=="__main__":
    raise SystemExit(main())
