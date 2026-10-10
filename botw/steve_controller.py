"""Move Link and turn BOTW camera from Minecraft via a virtual XInput pad.

Prototype: this drives BOTW's NORMAL controller/physics in Ryujinx, not a
teleport nor a true 1st-person camera hook. Requires vgamepad/ViGEmBus and
the virtual Xbox controller manually mapped to Player 1 in Ryujinx.
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

FPS = 0x10000
INPUTS = 0x20000


@dataclass(frozen=True)
class McPose:
    frame: int
    x: float
    y: float
    z: float
    yaw: float
    pitch: float
    flags: int


@dataclass(frozen=True)
class Sticks:
    left_x: float = 0.0
    left_y: float = 0.0
    right_x: float = 0.0
    right_y: float = 0.0


def clip(v):
    return max(-1.0,min(1.0,v))


def mc_state(memory):
    for _ in range(4):
        a = struct.unpack_from("<I",memory,host.OFF_MC_STATE)[0]
        if a&1:
            continue
        flags = struct.unpack_from("<I",memory,host.OFF_MC_STATE+4)[0]
        xyz = struct.unpack_from("<ddd",memory,host.OFF_MC_STATE+8)
        yaw,pitch = struct.unpack_from("<ff",memory,host.OFF_MC_STATE+0x20)
        frame = struct.unpack_from("<Q",memory,host.OFF_MC_STATE+0x38)[0]
        b = struct.unpack_from("<I",memory,host.OFF_MC_STATE)[0]
        if a==b and frame and all(math.isfinite(v) and abs(v)<100000
                                 for v in (*xyz,yaw,pitch)):
            return McPose(frame,*xyz,yaw,pitch,flags)
    return None


def engaged(pose):
    return (pose is not None and
            pose.flags & (1|FPS|INPUTS) == (1|FPS|INPUTS))


def real_link_live(memory,now_ms):
    if struct.unpack_from("<II",memory,0)!=(host.MAGIC,host.VERSION):
        return False
    heartbeat=struct.unpack_from("<Q",memory,0x10)[0]
    if not heartbeat or not 0<=now_ms-heartbeat<1500:
        return False
    a=struct.unpack_from("<I",memory,host.OFF_SKY_STATE)[0]
    flags=struct.unpack_from("<I",memory,host.OFF_SKY_STATE+4)[0]
    xyz=struct.unpack_from("<ddd",memory,host.OFF_SKY_STATE+0x10)
    b=struct.unpack_from("<I",memory,host.OFF_SKY_STATE)[0]
    return a==b and not a&1 and bool(flags&1) and xyz!=(0.,0.,0.)


def convert(before,after,dt,walk_speed=4.32,camera_speed=120.0):
    if not engaged(before) or not engaged(after) or not 0.001<=dt<=0.5:
        return Sticks()
    dx,dz=after.x-before.x,after.z-before.z
    if abs(dx)>12 or abs(dz)>12 or abs(after.y-before.y)>12:
        return Sticks() # MC teleport, not player input
    yaw=math.radians(after.yaw)
    side=(dx*math.cos(yaw)+dz*math.sin(yaw))/(walk_speed*dt)
    forward=(-dx*math.sin(yaw)+dz*math.cos(yaw))/(walk_speed*dt)
    mag=math.hypot(side,forward)
    if mag>1:
        side/=mag
        forward/=mag
    yaw_delta=(after.yaw-before.yaw+180)%360-180
    pitch_delta=after.pitch-before.pitch
    return Sticks(clip(side),clip(forward),
                  clip(-yaw_delta/dt/camera_speed),
                  clip(-pitch_delta/dt/camera_speed))


class Driver:
    def __init__(self,walk_speed=4.32,camera_speed=120.):
        self.last=None
        self.last_time=0.
        self.last_new_frame=0.
        self.out=Sticks()
        self.walk_speed=walk_speed
        self.camera_speed=camera_speed

    def step(self,pose,link_live,now):
        if not link_live or not engaged(pose):
            self.last=None
            self.out=Sticks()
            return self.out
        if self.last is None:
            self.last=pose
            self.last_time=now
            self.last_new_frame=now
        elif pose.frame!=self.last.frame:
            self.out=convert(self.last,pose,now-self.last_time,
                             self.walk_speed,self.camera_speed)
            self.last=pose
            self.last_time=now
            self.last_new_frame=now
        elif now-self.last_new_frame>0.25:
            self.out=Sticks()  # watchdog: never leave a stick held
        return self.out


def run(args,gamepad=None):
    if sys.platform!="win32" and gamepad is None:
        raise RuntimeError("Windows/virtual XInput device required")
    if gamepad is None:
        try:
            import vgamepad as vg
            gamepad=vg.VX360Gamepad()
        except (ImportError,OSError) as e:
            raise RuntimeError(
                "vgamepad/ViGEmBus absent. Run 'py -3 -m pip install vgamepad', "
                "then select virtual Xbox controller in Ryujinx > Input > Player 1.") from e
    print("[BotwCraft Link] Virtual Xbox created. Bind it to Ryujinx Player 1.",
          flush=True)
    print("[BotwCraft Link] Steve movement -> left stick; Steve mouse -> right "
          "stick. Native 1st person/coordinate teleport not implemented.",
          flush=True)
    driver=Driver(args.walk_speed,args.camera_speed)
    last_log=0.
    with mmap.mmap(-1,host.MAPPING_BYTES,tagname=host.NAME) as shared:
        try:
            while True:
                now=time.monotonic()
                state=driver.step(mc_state(shared),
                                  real_link_live(shared,host.uptime_ms()),now)
                gamepad.left_joystick_float(x_value_float=state.left_x,
                                           y_value_float=state.left_y)
                gamepad.right_joystick_float(x_value_float=state.right_x,
                                            y_value_float=state.right_y)
                gamepad.update()
                if now-last_log>5:
                    print(f"[BotwCraft Link] left={state.left_x:+.2f},"
                          f"{state.left_y:+.2f} right={state.right_x:+.2f},"
                          f"{state.right_y:+.2f}",flush=True)
                    last_log=now
                time.sleep(max(0.,1/args.hz-(time.monotonic()-now)))
        finally:
            gamepad.reset()
            gamepad.update()
            print("[BotwCraft Link] Controller neutral, stopped.",flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hz",type=float,default=60)
    p.add_argument("--walk-speed",type=float,default=4.32)
    p.add_argument("--camera-speed",type=float,default=120.)
    a=p.parse_args()
    if not 10<=a.hz<=120 or not .1<=a.walk_speed<=40 or not 10<=a.camera_speed<=720:
        p.error("invalid rates")
    try:
        run(a)
    except KeyboardInterrupt:
        pass
    except (RuntimeError,OSError,ValueError) as exc:
        raise SystemExit("[BotwCraft Link] ERROR: "+str(exc))


if __name__=="__main__":
    main()
