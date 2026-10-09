"""Opt-in low-rate Minecraft->Zelda mesh proof using Ryujinx's GDB stub.

The guest module owns and announces a bounded BWC1 buffer. GDB writes ONLY
that buffer while the guest is stopped, then resumes it. This is experimental:
every update briefly pauses Zelda; it is NOT a full-speed SkyCraft IPC.
"""
from __future__ import annotations
import argparse
import ctypes
import mmap
import re
import socket
import struct
from pathlib import Path
import sys
import time

try:
    from . import native_mesh_bridge as mesh
    from . import ryujinx_log_relay as relay
except ImportError:
    import native_mesh_bridge as mesh
    import ryujinx_log_relay as relay

GUEST_ADDRESS = re.compile(r"BotwCraft:GDB_MESH_BUFFER_ADDR=0x([0-9a-fA-F]{8,16})")
VERSION = "Game: build 0xA982D2BC"
MAX_PACKET = mesh.HEADER.size + mesh.MAX_VERTICES * mesh.NATIVE_VERTEX.size
CHUNK_BYTES = 512


class RspError(RuntimeError):
    pass


class RspClient:
    """Minimal GDB remote ACK protocol. Refuse non-loopback connections."""
    def __init__(self, host="127.0.0.1", port=22225, timeout=4.0):
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("GDB mesh bridge only allows localhost")
        self.host, self.port, self.timeout = host, port, timeout
        self.sock = None
        self.stopped = False

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock.settimeout(self.timeout)
        return self

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *_):
        if self.stopped:
            try:
                self.resume()
            except (OSError, RspError):
                pass
        self.close()

    def _byte(self):
        result = self.sock.recv(1)
        if not result:
            raise RspError("GDB disconnected")
        return result

    def _reply(self):
        while True:
            c = self._byte()
            if c in (b"+", b"-"):
                continue
            if c != b"$":
                continue
            data = bytearray()
            while (ch := self._byte()) != b"#":
                if len(data) > 16_000_000:
                    raise RspError("oversized GDB response")
                data.extend(ch)
            checksum = self._byte() + self._byte()
            try:
                check = int(checksum, 16)
            except ValueError as exc:
                raise RspError("invalid GDB checksum") from exc
            if sum(data) & 255 != check:
                self.sock.sendall(b"-")
                raise RspError("corrupted GDB response")
            self.sock.sendall(b"+")
            response = data.decode("ascii", errors="replace")
            if response.startswith("O") and len(response) > 2 and response != "OK":
                continue
            return response

    def command(self, message):
        raw = message.encode("ascii")
        self.sock.sendall(b"$" + raw + b"#" +
                          f"{sum(raw) & 255:02x}".encode("ascii"))
        return self._reply()

    def stop(self, first=False):
        response = self.command("?") if first else self.interrupt()
        if not response.startswith(("T", "S")):
            raise RspError("GDB did not stop guest: " + response[:100])
        self.stopped = True

    def interrupt(self):
        self.sock.sendall(b"\x03")
        return self._reply()

    def write_memory(self, guest_address, packet):
        if not self.stopped:
            raise RspError("writing to a running guest is forbidden")
        if not 0 < guest_address < (1 << 48):
            raise ValueError("bad guest pointer")
        if len(packet) > MAX_PACKET:
            raise ValueError("BWC1 packet is larger than the guest buffer")
        for offset in range(0, len(packet), CHUNK_BYTES):
            block = packet[offset:offset + CHUNK_BYTES]
            command = f"M{guest_address + offset:x},{len(block):x}:{block.hex()}"
            response = self.command(command)
            if response != "OK":
                raise RspError(f"GDB write at offset {offset} refused: {response[:100]}")

    def resume(self):
        """In GDB RSP, 'c' receives an ACK now and a stop reply LATER.

        Never call command("c"): that waits for the next T/S stop packet,
        which does not arrive until Ctrl+C or another debugger breakpoint.
        The old implementation blocked all mesh updates at startup.
        """
        if not self.stopped:
            return
        request = b"c"
        self.sock.sendall(b"$" + request + b"#" +
                          f"{sum(request) & 255:02x}".encode("ascii"))
        ack = self._byte()
        if ack != b"+":
            raise RspError("GDB continue did not ACK request: " + repr(ack))
        self.stopped = False


def log_source(argument=None):
    result = Path(argument) if argument else relay.user_log_override()
    if result is None:
        result = relay.discover_latest_log()
    if result is not None and result.is_dir():
        result = relay.latest_log(result)
    return result


def read_guest_buffer_address(path, *, now=None, max_age=360):
    """Read only a pointer exported by OUR module during a recent 1.5.0 boot."""
    if path is None or not path.is_file():
        return None
    info = path.stat()
    if (time.time() if now is None else now) - info.st_mtime > max_age:
        return None
    with path.open("rb") as f:
        if info.st_size > (8 << 20):
            f.seek(-(8 << 20), 2)
        data = f.read().decode("utf-8", errors="replace")
    fingerprints = list(re.finditer(r"Game: build 0x[0-9A-Fa-f]{8}", data))
    if not fingerprints or fingerprints[-1].group(0) != VERSION:
        return None
    text = data[fingerprints[-1].start():]
    if "BotwCraft:GDB_MESH_CAPACITY=16416" not in text:
        return None
    values = GUEST_ADDRESS.findall(text)
    if not values:
        return None
    value = int(values[-1], 16)
    return value if 0x10000 <= value < (1 << 48) else None


def make_frame_packet(frame, sections, pose):
    if pose is None:
        return None, 0
    vertices = mesh.sections_to_mesh(sections, pose)
    if not vertices:
        return None, 0
    return mesh.encode_mesh(frame, vertices), len(vertices) // 3


def run(args):
    if sys.platform != "win32":
        raise RuntimeError("Run this experimental bridge on Windows")
    print("[BotwCraft GDB] Enabling game GDB writes briefly pauses BOTW.",
          "[Ryujinx] Options > Debug > Enable GDB Stub, port", args.port, flush=True)
    print("[BotwCraft GDB] Start this script INSTEAD of the diagnostic mesh reader.",
          flush=True)
    guest_log = log_source(args.log)
    print(f"[BotwCraft GDB] Current Ryujinx log source: "
          f"{guest_log or 'NOT FOUND'}", flush=True)
    kernel = ctypes.windll.kernel32
    kernel.GetTickCount64.restype = ctypes.c_uint64
    with mmap.mmap(-1, mesh.MAPPING_BYTES, tagname=mesh.MAPPING_NAME) as shared:
        while True:
            updated_log = log_source(args.log)
            if updated_log != guest_log:
                guest_log = updated_log
                print(f"[BotwCraft GDB] Ryujinx log changed: "
                      f"{guest_log or 'NOT FOUND'}", flush=True)
            address = read_guest_buffer_address(guest_log)
            if address:
                break
            print("[BotwCraft GDB] Waiting for fresh BOTW 1.5.0 GDB_MESH_BUFFER_ADDR "
                  "in Ryujinx live log...", flush=True)
            time.sleep(3)
        print(f"[BotwCraft GDB] Guest-owned buffer at 0x{address:x}", flush=True)
        sections, frame, last_send, last_result = {}, 1, 0.0, None
        print(f"[BotwCraft GDB] Connecting to local debugger on port {args.port}...",
              flush=True)
        with RspClient(port=args.port) as gdb:
            print("[BotwCraft GDB] Connected. Checking guest stop/resume...",
                  flush=True)
            gdb.stop(first=True)
            gdb.resume()
            print("[BotwCraft GDB] Game resumed; waiting for actual Minecraft "
                  "section packets...", flush=True)
            waiting_printed = 0.0
            while True:
                if struct.unpack_from("<II", shared) != (
                        mesh.PROTOCOL_MAGIC, mesh.PROTOCOL_VERSION):
                    time.sleep(0.15)
                    continue
                events, _ = mesh.decode_render_ring(shared)
                for kind, data in events:
                    if kind == "clear":
                        sections.clear()
                    elif data[3] == 0:
                        sections.pop(data[:3], None)
                    else:
                        sections[data[:3]] = data
                pose = (mesh.read_minecraft_pose(shared)
                        if mesh.minecraft_heartbeat_is_live(
                            shared, int(kernel.GetTickCount64())) else None)
                now = time.monotonic()
                if (pose is None or not sections) and now - waiting_printed > 12:
                    print(f"[BotwCraft GDB] Waiting for Minecraft export: "
                          f"sections={len(sections)}, "
                          f"pose={'present' if pose is not None else 'absent'}. "
                          "Open a world and type /botwcraft connect.",
                          flush=True)
                    waiting_printed = now
                if pose is not None and sections and now - last_send >= 1/args.hz:
                    packet, count = make_frame_packet(frame, sections, pose)
                    if packet:
                        gdb.stop()
                        try:
                            gdb.write_memory(address, packet)
                        finally:
                            gdb.resume()
                        last_send = now
                        frame = (frame + 1) & 0xffffffff
                        result = (len(sections), count)
                        if last_result != result or frame % 10 == 0:
                            print(f"[BotwCraft GDB] Sent {count} real Minecraft "
                                  f"triangles ({len(packet)} bytes) into Zelda's "
                                  "native BWC1 mailbox", flush=True)
                            last_result = result
                time.sleep(0.03)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=22225)
    ap.add_argument("--log", type=Path)
    ap.add_argument("--hz", type=float, default=1.0)
    args = ap.parse_args()
    if not (1 <= args.port <= 65535 and 0.2 <= args.hz <= 2.0):
        ap.error("port must be 1..65535; hz must be between 0.2 and 2.0")
    try:
        run(args)
    except KeyboardInterrupt:
        print("[BotwCraft GDB] Stopped. Both games remain user-controlled.")
    except (OSError, RspError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"[BotwCraft GDB] ERROR: {exc}")


if __name__ == "__main__":
    main()
