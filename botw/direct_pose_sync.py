"""Exact Minecraft-authoritative world and first-person camera target for BOTW.

This is the PRODUCER of direct transforms. No controller emulation, no
relative stick speed and no fake Link coordinate telemetry. The renderer /
BOTW engine adapter must consume the published target by applying its REAL
actor + physics transform and real camera update in the emulated guest.

The SkyCraft v11 shared mapping reserves bytes 0x18000..0x1FFFF between
the input ring and collision ring. BotwCraft uses 0x18000 for one 112-byte
seqlock record. A native host module can consume it at render cadence
without stopping Ryujinx with GDB.
"""
from __future__ import annotations
from dataclasses import dataclass
import argparse
import math
import mmap
import struct
import sys
import time
try:
    from . import host_bridge as host
except ImportError:
    import host_bridge as host

ADDRESS=0x18000
MAGIC=0x31504442  # BDP1
VERSION=1
ACTIVE=1
FPS=2
FLY=4
INPUTS=0x20000
FPS_GUI=0x10000
MC_FLY=1<<7
HEADER=struct.Struct("<4I2Q18f2I")
assert HEADER.size == 112
MAX_DELTA=128.0
MAX_STALE_MS=1000
MAX_MC_STALE_MS=1000

@dataclass(frozen=True)
class Pose:
    frame: int
    coords: tuple[float,float,float]
    yaw: float
    pitch: float
    flags: int
    eye_height: float

@dataclass(frozen=True)
class Target:
    frame: int
    position: tuple[float,float,float]
    eye: tuple[float,float,float]
    forward: tuple[float,float,float]
    yaw: float
    pitch: float
    mc_origin: tuple[float,float,float]
    botw_origin: tuple[float,float,float]
    fly: bool


def get_minecraft(memory,now_ms=None):
    if now_ms is not None:
        beat=struct.unpack_from('<Q',memory,0x18)[0]
        if not beat or not 0<=now_ms-beat<=MAX_MC_STALE_MS:
            return None
    for _ in range(4):
        a=struct.unpack_from("<I",memory,host.OFF_MC_STATE)[0]
        if a&1: continue
        flags=struct.unpack_from("<I",memory,host.OFF_MC_STATE+4)[0]
        xyz=struct.unpack_from("<3d",memory,host.OFF_MC_STATE+8)
        yaw,pitch=struct.unpack_from("<2f",memory,host.OFF_MC_STATE+0x20)
        eye=struct.unpack_from("<f",memory,host.OFF_MC_STATE+0x28)[0]
        frame=struct.unpack_from("<Q",memory,host.OFF_MC_STATE+0x38)[0]
        b=struct.unpack_from("<I",memory,host.OFF_MC_STATE)[0]
        if a==b and frame>0 and all(math.isfinite(v) and abs(v)<100000 for v in (*xyz,yaw,pitch,eye)):
            return Pose(frame,xyz,yaw,pitch,flags,eye)
    return None


def get_botw(memory, now_ms):
    """Use only REAL live Link measurements from the relay, never synthetic."""
    if struct.unpack_from("<II",memory,0)!=(host.MAGIC,host.VERSION):
        return None
    beat=struct.unpack_from("<Q",memory,16)[0]
    if not beat or not 0<=now_ms-beat<=MAX_STALE_MS:
        return None
    for _ in range(4):
        a=struct.unpack_from("<I",memory,host.OFF_SKY_STATE)[0]
        if a&1: continue
        flags=struct.unpack_from("<I",memory,host.OFF_SKY_STATE+4)[0]
        xyz=struct.unpack_from("<3d",memory,host.OFF_SKY_STATE+0x10)
        b=struct.unpack_from("<I",memory,host.OFF_SKY_STATE)[0]
        if a==b and flags&1 and xyz!=(0.,0.,0.) and all(math.isfinite(v) and abs(v)<100000 for v in xyz):
            return xyz
    return None


def ready(pose):
    return (pose is not None and
            pose.flags & (1|INPUTS|FPS_GUI) == (1|INPUTS|FPS_GUI))


class Align:
    def __init__(self):
        self.mc_origin=None
        self.botw_origin=None
        self.last=None

    def reset(self):
        self.mc_origin=None
        self.botw_origin=None
        self.last=None

    def target(self,mc,link):
        # A transient missing game heartbeat or an opened menu must NEVER
        # reset the position anchor: re-anchoring to a physics-displaced Link
        # would silently drift the origin each time a GUI appears.
        if mc is None or link is None:
            self.last=None
            return None
        # /botwcraft inputs off is explicit opt-out; the NEXT session uses
        # a fresh anchor. An ordinary pause/menu retains the old anchor.
        if not (mc.flags & INPUTS):
            self.reset()
            return None
        if not ready(mc):
            self.last=None
            return None
        if self.mc_origin is None:
            self.mc_origin=mc.coords
            self.botw_origin=link
        if self.last is not None and mc.frame != self.last.frame:
            # Portal/respawn or teleport: refuse cross-world warp until a
            # new explicit /botwcraft inputs off/on establishes an anchor.
            delta=math.dist(mc.coords,self.last.coords)
            if delta>MAX_DELTA:
                self.reset()
                return None
        self.last=mc
        pos=tuple(self.botw_origin[i]+mc.coords[i]-self.mc_origin[i]
                  for i in range(3))
        if not all(math.isfinite(v) and abs(v)<100000 for v in pos):
            self.reset()
            return None
        theta=math.radians(mc.yaw)
        phi=math.radians(mc.pitch)
        cp=math.cos(phi)
        # Minecraft 0 yaw faces +Z; mouse up is NEGATIVE pitch.
        forward=(-math.sin(theta)*cp,-math.sin(phi),math.cos(theta)*cp)
        eye=(pos[0],pos[1]+mc.eye_height,pos[2])
        return Target(mc.frame,pos,eye,forward,mc.yaw,mc.pitch,
                      self.mc_origin,self.botw_origin,bool(mc.flags&MC_FLY))


def encode(target,sequence,now_ms):
    if sequence&1: raise ValueError("published sequence must be even")
    if target is None:
        return HEADER.pack(sequence,MAGIC,VERSION,0,0,now_ms,*([0.0]*18),0,0)
    vals=(*target.position,*target.eye,*target.forward,target.yaw,target.pitch,
          *target.mc_origin,*target.botw_origin,0.0)
    if len(vals)!=18: raise AssertionError(len(vals))
    return HEADER.pack(sequence,MAGIC,VERSION,
                       ACTIVE|FPS|(FLY if target.fly else 0),
                       target.frame,now_ms,*vals,0,0)


def publish(memory,target,sequence,now_ms):
    if len(memory)<ADDRESS+HEADER.size:
        raise ValueError("SkyCraft mapping is too short for BDP1")
    nextseq=(sequence+2)&0xfffffffe
    struct.pack_into("<I",memory,ADDRESS,(nextseq-1)&0xffffffff)
    record=encode(target,nextseq,now_ms)
    memory[ADDRESS+4:ADDRESS+HEADER.size]=record[4:]
    struct.pack_into("<I",memory,ADDRESS,nextseq)
    return nextseq


def inspect(memory,now_ms):
    a=struct.unpack_from("<I",memory,ADDRESS)[0]
    if a&1: return None
    record=HEADER.unpack_from(memory,ADDRESS)
    b=struct.unpack_from("<I",memory,ADDRESS)[0]
    if a!=b or record[1]!=MAGIC or record[2]!=VERSION:
        return None
    if not 0<=now_ms-record[5]<=MAX_STALE_MS:
        return None
    if not (record[3]&ACTIVE):
        return None
    if not all(math.isfinite(v) for v in record[6:24]):
        return None
    return record


def run(hz=60):
    if sys.platform!="win32":
        raise RuntimeError("Windows named SkyCraft memory mapping required")
    alignment=Align()
    seq=0
    laststatus=0
    print("[BotwCraft Direct] Direct Steve->Link 3D + first person TARGET producer.")
    print("[BotwCraft Direct] NO virtual controller. Requires real BOTW actor/camera "
          "executor for actual game movement; this process only publishes targets.",
          flush=True)
    with mmap.mmap(-1,host.MAPPING_BYTES,tagname=host.NAME) as memory:
        try:
            while True:
                t0=time.monotonic()
                stamp=host.uptime_ms()
                pose=get_minecraft(memory,stamp)
                link=get_botw(memory,stamp)
                target=alignment.target(pose,link)
                seq=publish(memory,target,seq,stamp)
                if t0-laststatus>=4:
                    print(f"[BotwCraft Direct] "
                          f"{'target '+str(tuple(round(x,3) for x in target.position)) if target else 'disarmed'}; "
                          f"camera={'first_person' if target else 'off'}",
                          flush=True)
                    laststatus=t0
                time.sleep(max(0,1/hz-(time.monotonic()-t0)))
        finally:
            publish(memory,None,seq,host.uptime_ms())
            print("[BotwCraft Direct] Safe disengage (BDP1 disabled).",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--hz",type=float,default=60)
    args=parser.parse_args()
    if not 10<=args.hz<=240:
        parser.error("hz must be 10..240")
    try:
        run(args.hz)
    except KeyboardInterrupt:
        pass
