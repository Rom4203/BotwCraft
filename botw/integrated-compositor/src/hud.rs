//! Original SkyCraft v11 named shared-memory RGBA HUD, no screenshot or GDB.
use std::ffi::c_void;
use std::ptr;
use std::sync::atomic::{AtomicU64, Ordering};
use crate::capture::PixelFrame;

const MAGIC: u32 = 0x43594B53;
const VERSION: u32 = 11;
const OFF_CTL: usize = 0x300;
const OFF_HDR: usize = 0x340;
const OFF_PIXELS: usize = 0x20000 + (32 << 20);
const SLOT_BYTES: usize = 3840 * 2160 * 4;

#[link(name = "kernel32")]
unsafe extern "system" {
    fn OpenFileMappingW(access: u32, inherit: i32, name: *const u16) -> isize;
    fn MapViewOfFile(handle: isize, access: u32, hi: u32, lo: u32, bytes: usize) -> *mut c_void;
    fn UnmapViewOfFile(base: *const c_void) -> i32;
    fn CloseHandle(handle: isize) -> i32;
}
const FILE_MAP_READ: u32 = 4;
const FILE_MAP_WRITE: u32 = 2;
const OFF_INPUT_RING: usize = 0x1000;
const INPUT_CAPACITY: usize = 4096;

pub struct SharedHud {
    handle: isize,
    base: *const u8,
    latest_id: u64,
}

impl SharedHud {
    pub fn open() -> Option<Self> {
        let wide: Vec<u16> = "Local\\SkyCraft_v1".encode_utf16().chain(Some(0)).collect();
        // SAFETY: Win32 owns the named mapping; the bridge keeps it alive while
        // running. We map read-only and bounds-check all protocol fields.
        unsafe {
            let handle = OpenFileMappingW(FILE_MAP_READ | FILE_MAP_WRITE, 0, wide.as_ptr());
            if handle == 0 { return None; }
            let base = MapViewOfFile(handle, FILE_MAP_READ | FILE_MAP_WRITE, 0, 0, 0) as *const u8;
            if base.is_null() {
                CloseHandle(handle);
                return None;
            }
            let mut result = Self { handle, base, latest_id: 0 };
            if result.read_u32(0) != MAGIC || result.read_u32(4) != VERSION {
                result.close();
                return None;
            }
            Some(result)
        }
    }

    fn read_u32(&self, offset: usize) -> u32 {
        // SAFETY: offsets are constant and inside the mapping header/slots.
        unsafe { ptr::read_unaligned(self.base.add(offset).cast::<u32>()) }
    }
    fn read_u64(&self, offset: usize) -> u64 {
        unsafe { ptr::read_unaligned(self.base.add(offset).cast::<u64>()) }
    }
    /// Stable Fabric McState flags: skip virtual FPS lock while a Minecraft
    /// screen (inventory, pause, chat) is visible. Bit 17 means the player
    /// explicitly enabled /botwcraft inputs on; bit 16 means no GUI screen.
    pub fn inputs_enabled(&self) -> bool {
        const OFF_MC_STATE: usize = 0x200;
        let seq1=self.read_u32(OFF_MC_STATE);
        if seq1 & 1 != 0 { return false; }
        let flags=self.read_u32(OFF_MC_STATE+4);
        seq1==self.read_u32(OFF_MC_STATE) && flags & 0x20000 != 0
    }

    pub fn is_gameplay_mouse(&self) -> bool {
        const OFF_MC_STATE: usize = 0x200;
        let seq1=self.read_u32(OFF_MC_STATE);
        if seq1 & 1 != 0 { return false; }
        let flags=self.read_u32(OFF_MC_STATE+4);
        let seq2=self.read_u32(OFF_MC_STATE);
        seq1==seq2 && (flags & 0x30000)==0x30000
    }

    pub fn next_frame(&mut self) -> Option<PixelFrame> {
        let state = self.read_u32(OFF_CTL);
        if state & 4 == 0 { return None; }
        let slot = (state & 3) as usize;
        if slot >= 3 { return None; }
        let header = OFF_HDR + slot * 0x40;
        let w = self.read_u32(header) as usize;
        let h = self.read_u32(header + 4) as usize;
        let flags = self.read_u32(header + 8);
        let id = self.read_u64(header + 0x10);
        if w == 0 || h == 0 || w > 3840 || h > 2160 || id == 0 || id == self.latest_id {
            return None;
        }
        let len = w.checked_mul(h)?.checked_mul(4)?;
        if len > SLOT_BYTES { return None; }
        let mut data = vec![0u8; len];
        unsafe { ptr::copy_nonoverlapping(self.base.add(OFF_PIXELS + slot * SLOT_BYTES), data.as_mut_ptr(), len); }
        if state != self.read_u32(OFF_CTL) { return None; }
        if flags & 1 != 0 {
            let row_bytes = w * 4;
            for row in 0..h/2 {
                let (left, right) = data.split_at_mut((h - 1 - row) * row_bytes);
                left[row * row_bytes..(row + 1)*row_bytes].swap_with_slice(&mut right[..row_bytes]);
            }
        }
        self.latest_id = id;
        Some(PixelFrame { width: w, height: h, data })
    }
    /// Writes SkyCraft v11's actual IN_KEY/IN_MOUSE/IN_CURSOR input ring.
    /// One writer (this compositor), one reader (Fabric's InputBridge).
    /// The host bridge must already own the mapping; never guess memory.
    pub fn push_input(&mut self, kind: u16, code: u16, a: i32, b: i32, c: i32) -> bool {
        unsafe {
            let head = &*(self.base.add(OFF_INPUT_RING).cast::<AtomicU64>());
            let tail = &*(self.base.add(OFF_INPUT_RING + 0x40).cast::<AtomicU64>());
            let index = head.load(Ordering::Relaxed);
            if index.wrapping_sub(tail.load(Ordering::Acquire)) >= INPUT_CAPACITY as u64 {
                return false;
            }
            let addr = self.base.add(OFF_INPUT_RING + 0x80 + (index as usize & (INPUT_CAPACITY-1)) * 16)
                as *mut u8;
            ptr::write_unaligned(addr.cast::<u16>(), kind);
            ptr::write_unaligned(addr.add(2).cast::<u16>(), code);
            ptr::write_unaligned(addr.add(4).cast::<i32>(), a);
            ptr::write_unaligned(addr.add(8).cast::<i32>(), b);
            ptr::write_unaligned(addr.add(12).cast::<i32>(), c);
            head.store(index + 1, Ordering::Release);
        }
        true
    }

    fn close(&mut self) {
        unsafe {
            if !self.base.is_null() { UnmapViewOfFile(self.base.cast()); self.base = ptr::null(); }
            if self.handle != 0 { CloseHandle(self.handle); self.handle = 0; }
        }
    }
}
impl Drop for SharedHud { fn drop(&mut self) { self.close(); } }
