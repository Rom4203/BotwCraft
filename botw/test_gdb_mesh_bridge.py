"""No emulator required: fake GDB RSP server verifies guest-only BWC1 writes."""
import socket
import threading
from tempfile import TemporaryDirectory
from pathlib import Path
import time
import unittest

from botw import gdb_mesh_bridge as gdb
from botw import native_mesh_bridge as mesh


class FakeGdb:
    def __init__(self):
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.port = self.socket.getsockname()[1]
        self.socket.listen()
        self.address = 0xb3aa000
        self.memory = bytearray(gdb.MAX_PACKET)
        self.stopped = False
        self.errors = []
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def send(self, conn, reply):
        data = reply.encode()
        conn.sendall(b"$" + data + b"#" + f"{sum(data)&255:02x}".encode())

    def serve(self):
        try:
            conn, _ = self.socket.accept()
            with conn:
                conn.settimeout(3)
                while True:
                    b = conn.recv(1)
                    if not b:
                        return
                    if b == b"+":
                        continue
                    if b == b"\x03":
                        self.stopped = True
                        self.send(conn, "T02thread:1;")
                        continue
                    assert b == b"$"
                    packet = bytearray()
                    while (c := conn.recv(1)) != b"#":
                        packet.extend(c)
                    assert int(conn.recv(2),16) == sum(packet)&255
                    conn.sendall(b"+")
                    command = packet.decode()
                    if command == "?":
                        self.stopped = True
                        self.send(conn,"T05thread:1;")
                    elif command == "c":
                        self.stopped = False
                        self.send(conn, "OK")
                    elif command.startswith("M"):
                        assert self.stopped, "guest running during unsafe write"
                        coords,data = command[1:].split(":",1)
                        addr,length = (int(v,16) for v in coords.split(","))
                        chunk = bytes.fromhex(data)
                        assert len(chunk)==length
                        off=addr-self.address
                        assert 0<=off and off+length<=len(self.memory)
                        self.memory[off:off+length]=chunk
                        self.send(conn,"OK")
        except Exception as exc:
            self.errors.append(str(exc))
        finally:
            self.socket.close()


class GdbTests(unittest.TestCase):
    def test_guest_buffer_write_and_resume(self):
        v=mesh.RENDER_VERTEX.pack(0.,2.,6.,0.,0.,0xffffffff,0,0)
        packet, triangles=gdb.make_frame_packet(
            9,{(0,5,0):(0,5,0,3,v*3)},(0.,80.,0.,0.,0.))
        self.assertEqual(triangles,1)
        fake=FakeGdb()
        with gdb.RspClient(port=fake.port) as client:
            client.stop(first=True)
            client.write_memory(fake.address,packet)
            client.resume()
            client.stop()
            client.resume()
        fake.thread.join(timeout=3)
        self.assertFalse(fake.errors, fake.errors)
        self.assertFalse(fake.stopped)
        self.assertEqual(fake.memory[:len(packet)],packet)

    def test_bad_write_still_resumes_guest(self):
        fake=FakeGdb()
        with self.assertRaises(ValueError):
            with gdb.RspClient(port=fake.port) as client:
                client.stop(first=True)
                client.write_memory(fake.address,b'x'*(gdb.MAX_PACKET+1))
        fake.thread.join(timeout=3)
        self.assertFalse(fake.errors, fake.errors)
        self.assertFalse(fake.stopped)

    def test_address_requires_current_supported_game(self):
        with TemporaryDirectory() as folder:
            f=Path(folder)/"live.log"
            f.write_text("Game: build 0x6811B941\n"
                         "BotwCraft:GDB_MESH_BUFFER_ADDR=0x000000000b3aa000\n"
                         "BotwCraft:GDB_MESH_CAPACITY=16416\n")
            self.assertIsNone(gdb.read_guest_buffer_address(f))
            f.write_text(gdb.VERSION+"\n"
                         "BotwCraft:GDB_MESH_BUFFER_ADDR=0x000000000b3aa000\n"
                         "BotwCraft:GDB_MESH_CAPACITY=16416\n")
            self.assertEqual(gdb.read_guest_buffer_address(f),0xb3aa000)
            self.assertIsNone(gdb.read_guest_buffer_address(f,now=time.time()+800))

    def test_loopback_only_and_paused_only(self):
        with self.assertRaises(ValueError):
            gdb.RspClient(host="0.0.0.0")
        with self.assertRaises(gdb.RspError):
            gdb.RspClient().write_memory(0xb3aa000,b"x")
        self.assertEqual(gdb.MAX_PACKET,16352)


if __name__=="__main__":
    unittest.main()
