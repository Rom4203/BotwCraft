"""Experimental click-through Minecraft HUD overlay for the Ryujinx client area.

Consumes the actual GPU-produced SkyCraft v11 triple-buffer images. Only HUD,
items, menus and hands: NOT 3D blocks, collision/depth, or native integration.
Uses Win32 layered windows; no injection or changes to Ryujinx. Windows only.
"""
from __future__ import annotations

import argparse
import os
import ctypes
from ctypes import wintypes
import struct
import sys
import time

NAME = "Local\\SkyCraft_v1"
MAGIC, VERSION = 0x43594B53, 11
OFF_CTL, OFF_HDR, OFF_PIXELS = 0x300, 0x340, 0x20000 + (32 << 20)
SLOT_BYTES = 3840 * 2160 * 4
MAX_W, MAX_H = 3840, 2160
FILE_MAP_READ = 0x0004
ULW_ALPHA = 2
WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
DIB_RGB_COLORS = 0
SRCCOPY = 0x00CC0020
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GW_OWNER = 4
# Win32 executable basenames; titles/HTML tabs containing "Ryujinx" do NOT count.
RYUJINX_EXECUTABLES = frozenset(("ryujinx.exe", "ryujinx.ava.exe"))


def is_ryujinx_executable(path):
    """Fail closed: verify a running executable, NEVER a window title."""
    if not isinstance(path, str) or not path:
        return False
    return path.replace("/", "\\").rsplit("\\", 1)[-1].casefold() in RYUJINX_EXECUTABLES


def process_image_for_window(user32, kernel32, hwnd):
    """Resolve the actual image owning an HWND using Win32 process APIs."""
    pid = wintypes.DWORD(0)
    if not user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)) or not pid.value:
        return None
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return None  # Never fall back to matching Opera/Chrome tab titles.
    try:
        chars = wintypes.DWORD(32768)
        path = ctypes.create_unicode_buffer(chars.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(chars)):
            return path.value
        return None
    finally:
        kernel32.CloseHandle(handle)


def enable_per_monitor_dpi():
    """Avoid logical/physical coordinate mismatch when moving Ryujinx screens."""
    if sys.platform != "win32":
        return False
    try:
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.SetProcessDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
        u.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
        return bool(u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)))
    except (OSError, AttributeError):
        return False


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]

class RECT(ctypes.Structure):
    _fields_ = [(k, wintypes.LONG) for k in ("left", "top", "right", "bottom")]

class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
    ]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 1)]

def decode_slot_header(read, state):
    """Return (slot, width, height, bottom_up, frame_id); reject invalid frames."""
    slot = state & 3
    if slot >= 3:
        return None
    header = read(OFF_HDR + slot * 0x40, 0x20)
    if len(header) < 0x20:
        return None
    width, height, flags = struct.unpack_from("<III", header)
    frame_id = struct.unpack_from("<Q", header, 0x10)[0]
    if not (0 < width <= MAX_W and 0 < height <= MAX_H and frame_id > 0):
        return None
    return slot, width, height, bool(flags & 1), frame_id

def remove_void_background(pixels, width, height, tolerance=48):
    """Transparent-key a nearly uniform Minecraft void/sky background.

    Input/output RGBA8. RGB under removed pixels is zeroed. This is only an
    approximate overlay mode; actual BOTW depth-based compositing is absent.
    """
    if len(pixels) != width * height * 4 or width <= 0 or height <= 0:
        raise ValueError("invalid RGBA frame")
    points = (0, width - 1, width * (height - 1), width * height - 1)
    # Use the most common corner as the sky key, preserving terrain/blocks.
    samples = [tuple(pixels[4 * i:4 * i + 3]) for i in points]
    key = min(samples, key=lambda c: sum(
        sum(abs(c[j] - v[j]) for j in range(3)) for v in samples))
    t = max(0, min(255, int(tolerance)))
    out = bytearray(pixels)
    for i in range(0, len(out), 4):
        if max(abs(out[i + j] - key[j]) for j in range(3)) <= t:
            out[i:i + 4] = bytes(4)
    return out

class SharedOverlay:
    def __init__(self, name=NAME):
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenFileMappingW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
        k32.OpenFileMappingW.restype = wintypes.HANDLE
        k32.MapViewOfFile.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                     wintypes.DWORD, ctypes.c_size_t)
        k32.MapViewOfFile.restype = ctypes.c_void_p
        k32.UnmapViewOfFile.argtypes = (ctypes.c_void_p,)
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.kernel = k32
        self.handle = k32.OpenFileMappingW(FILE_MAP_READ, False, name)
        if not self.handle:
            raise OSError("BotwCraft host bridge has not created shared memory")
        self.ptr = k32.MapViewOfFile(self.handle, FILE_MAP_READ, 0, 0, 0)
        if not self.ptr:
            k32.CloseHandle(self.handle)
            raise OSError("MapViewOfFile failed")
        if struct.unpack("<II", self.read(0, 8)) != (MAGIC, VERSION):
            self.close()
            raise ValueError("SkyCraft protocol mismatch")

    def read(self, offset, size):
        return ctypes.string_at(self.ptr + offset, size)

    def frame(self):
        state = struct.unpack("<I", self.read(OFF_CTL, 4))[0]
        info = decode_slot_header(self.read, state)
        if info is None:
            return None
        slot, w, h, bottom_up, frame_id = info
        content = self.read(OFF_PIXELS + slot * SLOT_BYTES, w * h * 4)
        # A changed control word means this buffer may have been reused; skip.
        if struct.unpack("<I", self.read(OFF_CTL, 4))[0] != state:
            return None
        return w, h, bottom_up, frame_id, content

    def close(self):
        if getattr(self, "ptr", None):
            self.kernel.UnmapViewOfFile(self.ptr)
            self.ptr = None
        if getattr(self, "handle", None):
            self.kernel.CloseHandle(self.handle)
            self.handle = None

class OverlayWindow:
    def __init__(self):
        u, g = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("gdi32", use_last_error=True)
        self.u, self.g = u, g
        hwnd = ctypes.c_void_p
        u.CreateWindowExW.argtypes = (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
            wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            hwnd, hwnd, hwnd, ctypes.c_void_p)
        u.CreateWindowExW.restype = hwnd
        u.GetWindowTextW.argtypes = (hwnd, wintypes.LPWSTR, ctypes.c_int)
        u.GetWindowTextW.restype = ctypes.c_int
        u.GetClientRect.argtypes = (hwnd, ctypes.POINTER(RECT))
        u.ClientToScreen.argtypes = (hwnd, ctypes.POINTER(POINT))
        u.IsWindowVisible.argtypes = (hwnd,)
        u.IsIconic.argtypes = (hwnd,)
        u.GetForegroundWindow.argtypes = ()
        u.GetForegroundWindow.restype = hwnd
        u.GetWindowThreadProcessId.argtypes = (hwnd, ctypes.POINTER(wintypes.DWORD))
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.GetWindow.argtypes = (hwnd, wintypes.UINT)
        u.GetWindow.restype = hwnd
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD,
                                                  wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
        k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        k32.CloseHandle.restype = wintypes.BOOL
        self.kernel = k32
        self.last_target = None
        u.EnumWindows.argtypes = (ctypes.c_void_p, wintypes.LPARAM)
        u.UpdateLayeredWindow.argtypes = (hwnd, hwnd, ctypes.POINTER(POINT), ctypes.POINTER(SIZE),
            hwnd, ctypes.POINTER(POINT), wintypes.DWORD, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD)
        u.UpdateLayeredWindow.restype = wintypes.BOOL
        g.CreateCompatibleDC.argtypes = (hwnd,)
        g.CreateCompatibleDC.restype = hwnd
        g.CreateDIBSection.argtypes = (hwnd, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                                       ctypes.POINTER(ctypes.c_void_p), hwnd, wintypes.DWORD)
        g.CreateDIBSection.restype = hwnd
        g.SelectObject.argtypes = (hwnd, hwnd)
        g.SelectObject.restype = hwnd
        g.DeleteObject.argtypes = (hwnd,)
        g.DeleteObject.restype = wintypes.BOOL
        g.DeleteDC.argtypes = (hwnd,)
        g.DeleteDC.restype = wintypes.BOOL
        u.ShowWindow.argtypes = (hwnd, ctypes.c_int)
        u.DestroyWindow.argtypes = (hwnd,)
        g.StretchBlt.argtypes = (hwnd, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                hwnd, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.DWORD)
        self.hwnd = u.CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            "STATIC", "BotwCraft HUD", WS_POPUP, 0, 0, 1, 1, None, None, None, None)
        if not self.hwnd:
            raise OSError("Unable to create layered overlay window")
        self.src_dc, self.dst_dc = g.CreateCompatibleDC(None), g.CreateCompatibleDC(None)
        self.src_bitmap = self.dst_bitmap = None
        self.src_bits = self.dst_bits = None
        self.src_size = self.dst_size = None
        self.visible = False

    def find_game(self):
        """Only track the real Ryujinx process, never an unrelated browser tab.

        Hide HUD whenever Ryujinx isn't foreground: a WS_EX_TOPMOST overlay
        must not draw on Opera/Discord while the user switches applications.
        """
        foreground = self.u.GetForegroundWindow()
        if not foreground:
            self.last_target = None
            return None
        image = process_image_for_window(self.u, self.kernel, foreground)
        if not is_ryujinx_executable(image):
            self.last_target = None
            return None

        result = []
        CALLBACK = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p,
                                     wintypes.LPARAM)

        def check(hwnd, _):
            if hwnd == self.hwnd or not self.u.IsWindowVisible(hwnd):
                return True
            if self.u.IsIconic(hwnd) or self.u.GetWindow(hwnd, GW_OWNER):
                return True
            exe = process_image_for_window(self.u, self.kernel, hwnd)
            if not is_ryujinx_executable(exe):
                return True
            rect = RECT()
            if not self.u.GetClientRect(hwnd, ctypes.byref(rect)):
                return True
            w, h = rect.right - rect.left, rect.bottom - rect.top
            if w < 320 or h < 240:
                return True
            pos = POINT(0, 0)
            if self.u.ClientToScreen(hwnd, ctypes.byref(pos)):
                result.append((hwnd == foreground, w * h,
                               (pos.x, pos.y, w, h), exe))
            return True

        callback = CALLBACK(check)
        self.u.EnumWindows(callback, 0)
        if not result:
            self.last_target = None
            return None
        selected = max(result, key=lambda x: (x[0], x[1]))
        if selected[3] != self.last_target:
            self.last_target = selected[3]
            print("[BotwCraft HUD] Processus cible verifie :",
                  selected[3], flush=True)
        return selected[2]

    def new_dib(self, dc, width, height):
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height  # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bits = ctypes.c_void_p()
        bmp = self.g.CreateDIBSection(dc, ctypes.byref(bmi), DIB_RGB_COLORS,
                                      ctypes.byref(bits), None, 0)
        if not bmp or not bits.value:
            raise OSError("Unable to allocate overlay bitmap")
        self.g.SelectObject(dc, bmp)
        return bmp, bits

    def draw(self, frame, location, rgba=True, key_background=False):
        x, y, output_w, output_h = location
        w, h, bottom_up, _, pixels = frame
        if self.src_size != (w, h):
            old_bitmap = self.src_bitmap
            self.src_bitmap, self.src_bits = self.new_dib(self.src_dc, w, h)
            if old_bitmap: self.g.DeleteObject(old_bitmap)
            self.src_size = (w, h)
        if self.dst_size != (output_w, output_h):
            old_bitmap = self.dst_bitmap
            self.dst_bitmap, self.dst_bits = self.new_dib(self.dst_dc, output_w, output_h)
            if old_bitmap: self.g.DeleteObject(old_bitmap)
            self.dst_size = (output_w, output_h)
        # Minecraft's RGBA framebuffer -> Win32 layered-window BGRA.
        if key_background:
            if not rgba:
                raise ValueError("void background removal expects RGBA source")
            pixels = remove_void_background(pixels, w, h)
        converted = bytearray(pixels)
        if rgba:
            converted[0::4], converted[2::4] = pixels[2::4], pixels[0::4]
        if bottom_up:
            stride = w * 4
            converted = b"".join(converted[i*stride:(i+1)*stride]
                                 for i in range(h - 1, -1, -1))
        ctypes.memmove(self.src_bits, bytes(converted), len(converted))
        if not self.g.StretchBlt(self.dst_dc, 0, 0, output_w, output_h,
                                 self.src_dc, 0, 0, w, h, SRCCOPY):
            return False
        p, size = POINT(x, y), SIZE(output_w, output_h)
        origin = POINT(0, 0)
        blend = BLENDFUNCTION(0, 0, 255, 1)  # source per-pixel alpha
        ok = self.u.UpdateLayeredWindow(self.hwnd, None, ctypes.byref(p),
            ctypes.byref(size), self.dst_dc, ctypes.byref(origin), 0,
            ctypes.byref(blend), ULW_ALPHA)
        if ok and not self.visible:
            self.u.ShowWindow(self.hwnd, 4)
            self.visible = True
        return bool(ok)

    def hide(self):
        if self.visible:
            self.u.ShowWindow(self.hwnd, 0)
            self.visible = False

    def close(self):
        self.hide()
        for bitmap in (self.src_bitmap, self.dst_bitmap):
            if bitmap: self.g.DeleteObject(bitmap)
        for dc in (self.src_dc, self.dst_dc):
            if dc: self.g.DeleteDC(dc)
        if self.hwnd: self.u.DestroyWindow(self.hwnd)

def run(name=NAME, rgba=True, fps=60, key_background=False):
    if sys.platform != "win32":
        raise RuntimeError("Windows required")
    enable_per_monitor_dpi()
    win = OverlayWindow()
    shm = None
    last_id = 0
    last_frame_at = 0.0
    last_location = None
    last_frame = None
    try:
        print("[BotwCraft HUD] Waiting for Minecraft overlay; Ctrl+C to stop", flush=True)
        while True:
            if shm is None:
                try:
                    shm = SharedOverlay(name)
                except (OSError, ValueError):
                    win.hide()
                    time.sleep(1)
                    continue
            where = win.find_game()
            now = time.monotonic()
            if where:
                frame = shm.frame()
                changed = frame is not None and frame[3] != last_id
                if changed:
                    last_id, last_frame_at = frame[3], now
                    last_frame = frame
                # Refresh on *either* a new Minecraft frame or game-window
                # relocation. Never assume the game rectangle stays fixed.
                if last_frame and now - last_frame_at <= 1.0:
                    if changed or where != last_location:
                        if win.draw(last_frame, where, rgba=rgba,
                                    key_background=key_background):
                            last_location = where
                else:
                    win.hide()
                    last_location = None
            else:
                win.hide()
                last_location = None
            time.sleep(1 / fps)
    except KeyboardInterrupt:
        pass
    finally:
        if shm: shm.close()
        win.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default=NAME)
    parser.add_argument("--pixel-format", choices=("rgba", "bgra"), default="rgba")
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--key-background", action="store_true",
                        help="Experimental 3D Minecraft preview: key out sky pixels (no BOTW depth)")
    args = parser.parse_args()
    if not 1 <= args.fps <= 60:
        parser.error("--fps must be 1..60")
    try:
        run(args.name, args.pixel_format == "rgba", args.fps, args.key_background)
    except (OSError, RuntimeError) as exc:
        raise SystemExit(f"[BotwCraft HUD] {exc}")
