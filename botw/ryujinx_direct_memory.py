"""Low-latency Windows->BOTW 1.5.0 DIRECT actor command transport.

Reads Steve's *absolute* position/rotation from the SkyCraft v11 map and
writes a small BDP1 seqlock into a KNOWN-owned module buffer in Ryujinx's
address space. No virtual controller, no GDB pauses, no file I/O in Zelda.

This cannot override Zelda's camera until its live camera instance/hook is
identified. The direct actor path is EXPERIMENTAL, not a verified playable
build; enable only if you've backed up game saves.
"""
from __future__ import annotations
import argparse
import ctypes as C
from ctypes import wintypes as W
import mmap
from pathlib import Path
import struct
import sys
import time

try:
    from . import host_bridge as host
    from . import direct_pose_sync as pose
except ImportError:
    import host_bridge as host
    import direct_pose_sync as pose

MARKER = b"BOTWCRAFT15_DIRECT_GUEST_XYZ_20261010\x00\x00\x00"
assert len(MARKER) == 40
TARGET_SIZE = pose.HEADER.size
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MEM_COMMIT = 0x1000
RW_PAGES = {0x04, 0x08, 0x40, 0x80}
PROCESS_RIGHTS = (PROCESS_VM_READ | PROCESS_VM_WRITE |
                  PROCESS_VM_OPERATION | PROCESS_QUERY_LIMITED_INFORMATION)
MAX_SCAN_SECONDS = 75
MAX_SCAN_BYTES = 10 << 30
BLOCK = 2 << 20
ALLOW_ACTOR_WRITE = 0x10
SYSTEM_MEMORY_MAX = 0x00007FFFFFFFFFFF


class TransportError(RuntimeError):
    pass


class MEMORY_BASIC_INFORMATION(C.Structure):
    _fields_ = [
        ("BaseAddress", C.c_void_p),
        ("AllocationBase", C.c_void_p),
        ("AllocationProtect", W.DWORD),
        ("_alignment", W.DWORD),
        ("RegionSize", C.c_size_t),
        ("State", W.DWORD),
        ("Protect", W.DWORD),
        ("Type", W.DWORD),
        ("_alignment2", W.DWORD),
    ]


def find_marker(block: bytes, value=MARKER):
    return block.find(value)


def safe_process_name(s):
    if not s:
        return False
    return s.replace("/", "\\").rsplit("\\", 1)[-1].casefold() in (
        "ryujinx.exe", "ryujinx.ava.exe")


class WinRyujinx:
    def __init__(self):
        if sys.platform != "win32":
            raise TransportError("Ryujinx process-memory transport requires Windows")
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.psapi = C.WinDLL("psapi", use_last_error=True)
        k = self.kernel
        k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        k.OpenProcess.restype = W.HANDLE
        k.CloseHandle.argtypes = [W.HANDLE]
        k.CloseHandle.restype = W.BOOL
        k.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD,
                                                 W.LPWSTR, C.POINTER(W.DWORD)]
        k.QueryFullProcessImageNameW.restype = W.BOOL
        k.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p,
                                        C.c_size_t, C.POINTER(C.c_size_t)]
        k.ReadProcessMemory.restype = W.BOOL
        k.WriteProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p,
                                         C.c_size_t, C.POINTER(C.c_size_t)]
        k.WriteProcessMemory.restype = W.BOOL
        k.VirtualQueryEx.argtypes = [W.HANDLE, C.c_void_p,
                                     C.POINTER(MEMORY_BASIC_INFORMATION), C.c_size_t]
        k.VirtualQueryEx.restype = C.c_size_t
        self.psapi.EnumProcesses.argtypes = [C.POINTER(W.DWORD), W.DWORD,
                                             C.POINTER(W.DWORD)]
        self.psapi.EnumProcesses.restype = W.BOOL
        self.handle = None
        self.pid = None
        self.mailbox = None

    def __enter__(self):
        ids = (W.DWORD * 8192)()
        used = W.DWORD(0)
        if not self.psapi.EnumProcesses(ids, C.sizeof(ids), C.byref(used)):
            raise TransportError("EnumProcesses failed")
        found = []
        for pid in ids[:used.value // C.sizeof(W.DWORD)]:
            if not pid:
                continue
            h = self.kernel.OpenProcess(PROCESS_RIGHTS, False, pid)
            if not h:
                continue
            buffer = C.create_unicode_buffer(32768)
            chars = W.DWORD(len(buffer))
            if self.kernel.QueryFullProcessImageNameW(
                    h, 0, buffer, C.byref(chars)) and safe_process_name(buffer.value):
                found.append((pid,h,buffer.value))
            else:
                self.kernel.CloseHandle(h)
        if len(found) != 1:
            for _, h, _ in found:
                self.kernel.CloseHandle(h)
            raise TransportError("Exactly one Ryujinx process must be running "
                                 "(and allow user-level Read/WriteProcessMemory); "
                                 f"found {len(found)}")
        self.pid,self.handle,image = found[0]
        print(f"[BotwCraft Direct] Ryujinx verified: {image} (pid {self.pid})",
              flush=True)
        return self

    def __exit__(self, *_):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
        self.handle = None

    def read(self,address,length):
        if not (0 < address < SYSTEM_MEMORY_MAX) or not 0 < length <= BLOCK:
            return None
        buffer = C.create_string_buffer(length)
        got = C.c_size_t(0)
        if not self.kernel.ReadProcessMemory(
                self.handle, C.c_void_p(address), buffer, length, C.byref(got)):
            return None
        return buffer.raw[:got.value]

    def write(self,address,data):
        if not self.handle or not data:
            raise TransportError("process closed or empty write")
        payload = C.create_string_buffer(data)
        used = C.c_size_t(0)
        if not self.kernel.WriteProcessMemory(self.handle,C.c_void_p(address),
                payload,len(data),C.byref(used)) or used.value!=len(data):
            raise TransportError(f"WriteProcessMemory failed at {address:x}")

    def discover(self):
        print("[BotwCraft Direct] Looking for writable 1.5.0 module-owned BDP1 "
              "mailbox (no arbitrary game memory writes)...",flush=True)
        start = time.monotonic()
        count = 0
        position = 0x10000
        candidates = []
        while position < SYSTEM_MEMORY_MAX and time.monotonic()-start < MAX_SCAN_SECONDS:
            mi = MEMORY_BASIC_INFORMATION()
            got = self.kernel.VirtualQueryEx(self.handle,C.c_void_p(position),
                                              C.byref(mi),C.sizeof(mi))
            if not got:
                position += 0x10000
                continue
            base = mi.BaseAddress or position
            stop = base + mi.RegionSize
            if stop <= position:
                raise TransportError("invalid VirtualQueryEx range")
            position = stop
            if not (mi.State == MEM_COMMIT and (mi.Protect & 0xff) in RW_PAGES
                    and not (mi.Protect & 0x100) and mi.RegionSize >= len(MARKER)):
                continue
            for offset in range(0,mi.RegionSize,BLOCK):
                if count >= MAX_SCAN_BYTES or time.monotonic()-start > MAX_SCAN_SECONDS:
                    break
                length=min(BLOCK,mi.RegionSize-offset)
                payload=self.read(base+offset,length)
                count+=length
                if payload:
                    idx=find_marker(payload)
                    if idx>=0:
                        addr=base+offset+idx
                        # Make sure writable buffer is NOT a Python string or
                        # a game data asset. Its 112B target follows marker.
                        near=self.read(addr,40+TARGET_SIZE)
                        if near is not None and len(near)==40+TARGET_SIZE and near[:40]==MARKER:
                            candidates.append(addr)
                if len(candidates)>1:
                    break
            if len(candidates)>1 or count>=MAX_SCAN_BYTES:
                break
        if len(candidates)!=1:
            raise TransportError(
                f"Found {len(candidates)} writable BDP1 mailboxes "
                f"after scanning {count>>20} MiB. Require EXACTLY one. "
                "Ensure newest BOTW 1.5.0 native module is installed and "
                "fully loaded, then restart Ryujinx.")
        self.mailbox=candidates[0]
        print(f"[BotwCraft Direct] Guest mailbox resolved to verified "
              f"Ryujinx HOST memory 0x{self.mailbox:x}",flush=True)
        return self.mailbox

    def validate(self):
        return self.mailbox is not None and self.read(self.mailbox,len(MARKER))==MARKER

    def send(self,packet):
        if self.mailbox is None or len(packet)!=TARGET_SIZE:
            raise TransportError("invalid direct position packet")
        address=self.mailbox+len(MARKER)
        sequence=struct.unpack_from("<I",packet)[0]
        if sequence & 1:
            raise TransportError("seqlock sequence must be even")
        # Guest polls while Windows runs: odd/bytes/even avoids torn commands.
        self.write(address,struct.pack("<I",(sequence-1)&0xffffffff))
        self.write(address+4,packet[4:])
        self.write(address,struct.pack("<I",sequence))


def run(hz=60,apply_actor=False):
    if not apply_actor:
        raise TransportError("Native actor writes require explicit "
                             "'--apply-actor'; this isn't an observation mode.")
    seq=0
    alignment=pose.Align()
    last_status=0.
    last_verified=0.
    with WinRyujinx() as game:
        game.discover()
        with mmap.mmap(-1,host.MAPPING_BYTES,tagname=host.NAME) as shared:
            try:
                while True:
                    now=time.monotonic()
                    stamp=host.uptime_ms()
                    mc=pose.get_minecraft(shared,stamp)
                    link=pose.get_botw(shared,stamp)
                    target=alignment.target(mc,link)
                    seq=pose.publish(shared,target,seq,stamp)
                    out=bytearray(pose.encode(target,seq,stamp))
                    if target is not None:
                        flags=struct.unpack_from("<I",out,12)[0]
                        struct.pack_into("<I",out,12,flags|ALLOW_ACTOR_WRITE)
                    if now-last_verified>0.5:
                        if not game.validate():
                            raise TransportError("Ryujinx BDP1 mailbox vanished; "
                                                 "abort to prevent writing wrong memory")
                        last_verified=now
                    game.send(bytes(out))
                    if now-last_status>4:
                        status=(tuple(round(x,3) for x in target.position)
                                if target else "disarmed")
                        print(f"[BotwCraft Direct] authoritative Link destination "
                              f"{status}, fps_camera={bool(target)}",flush=True)
                        last_status=now
                    time.sleep(max(0.,1/hz-(time.monotonic()-now)))
            finally:
                # Always disengage the game-owned mailbox if still valid.
                try:
                    if game.validate():
                        seq=(seq+2)&0xfffffffe
                        game.send(pose.encode(None,seq,host.uptime_ms()))
                except (OSError,TransportError):
                    pass
                print("[BotwCraft Direct] Link control disarmed.",flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hz",type=float,default=60)
    p.add_argument("--apply-actor",action="store_true",
                   help="Explicitly permit native BOTW Link physics writes")
    args=p.parse_args()
    if not 10<=args.hz<=120:
        p.error("hz out of 10..120")
    try:
        run(args.hz,args.apply_actor)
    except KeyboardInterrupt:
        pass
    except (TransportError,OSError,ValueError) as e:
        raise SystemExit("[BotwCraft Direct] ERROR: "+str(e))


if __name__=="__main__":
    main()
