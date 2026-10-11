//! Windows owner of the SkyCraft v11 named shared memory.
//! Exact layout retained so Minecraft Fabric and the Rust compositor work unchanged.
use std::{ffi::c_void,io,ptr, sync::atomic::{fence,Ordering}};
const NAME:&str="Local\\SkyCraft_v1";
pub const MAGIC:u32=0x43594b53;
pub const VERSION:u32=11;
pub const SKY:usize=0x100;
pub const MC:usize=0x200;
pub const DIRECT:usize=0x18000;
const RING:usize=0x20000;
const SLOT:usize=3840*2160*4;
pub const SIZE:usize=RING+(32<<20)+3*SLOT+(64<<20);
const READWRITE:u32=0x04;
const MAP_ALL:u32=0x0002|0x0004;
const ALREADY_EXISTS:u32=183;

#[link(name="kernel32")]
extern "system" {
 fn CreateFileMappingW(file:isize,security:*mut c_void,protect:u32,hi:u32,lo:u32,name:*const u16)->isize;
 fn MapViewOfFile(handle:isize,access:u32,hi:u32,lo:u32,length:usize)->*mut c_void;
 fn UnmapViewOfFile(addr:*const c_void)->i32;
 fn CloseHandle(handle:isize)->i32;
 fn GetLastError()->u32;
 fn GetTickCount64()->u64;
}
pub fn clock()->u64 { unsafe{GetTickCount64()} }
pub struct SharedMap{handle:isize,base:*mut u8}
// The map is protected by Mutex in the bridge. Minecraft and the compositor
// independently use the existing per-record sequence and ring protocols.
unsafe impl Send for SharedMap {}
impl Drop for SharedMap{
 fn drop(&mut self){unsafe{
  if !self.base.is_null(){UnmapViewOfFile(self.base.cast());}
  if self.handle!=0 {CloseHandle(self.handle);}
 }}
}
impl SharedMap{
 pub fn create()->io::Result<Self>{
  let name:Vec<u16>=NAME.encode_utf16().chain([0]).collect();
  let h=unsafe{CreateFileMappingW(-1,ptr::null_mut(),READWRITE,(SIZE as u64>>32) as u32,SIZE as u32,name.as_ptr())};
  if h==0{return Err(io::Error::last_os_error());}
  let exists=unsafe{GetLastError()}==ALREADY_EXISTS;
  if exists {unsafe{CloseHandle(h);}return Err(io::Error::new(io::ErrorKind::AlreadyExists,"SkyCraft_v1 already owned by another bridge: stop the old Python bridge")); }
  let base=unsafe{MapViewOfFile(h,MAP_ALL,0,0,SIZE).cast::<u8>()};
  if base.is_null(){let e=io::Error::last_os_error();unsafe{CloseHandle(h);}return Err(e);}
  let mut m=Self{handle:h,base};
  m.u32_set(0,MAGIC);m.u32_set(4,VERSION);m.u64_set(16,0);
  println!("[RUST_BRIDGE] Shared map created: {} bytes",SIZE);
  Ok(m)
 }
 fn check(offset:usize,len:usize){assert!(offset<=SIZE && len<=SIZE-offset);}
 pub fn bytes(&self,offset:usize,len:usize)->Vec<u8>{
  Self::check(offset,len);
  let mut b=vec![0;len];
  unsafe{ptr::copy_nonoverlapping(self.base.add(offset),b.as_mut_ptr(),len);}
  b
 }
 pub fn u32(&self,o:usize)->u32{u32::from_le_bytes(self.bytes(o,4).try_into().unwrap())}
 pub fn u64(&self,o:usize)->u64{u64::from_le_bytes(self.bytes(o,8).try_into().unwrap())}
 pub fn f64(&self,o:usize)->f64{f64::from_le_bytes(self.bytes(o,8).try_into().unwrap())}
 pub fn f32(&self,o:usize)->f32{f32::from_le_bytes(self.bytes(o,4).try_into().unwrap())}
 pub fn write(&mut self,o:usize,buf:&[u8]){
  Self::check(o,buf.len());
  unsafe{ptr::copy_nonoverlapping(buf.as_ptr(),self.base.add(o),buf.len());}
 }
 pub fn u32_set(&mut self,o:usize,v:u32){self.write(o,&v.to_le_bytes())}
 pub fn u64_set(&mut self,o:usize,v:u64){self.write(o,&v.to_le_bytes())}
 pub fn f32_set(&mut self,o:usize,v:f32){self.write(o,&v.to_le_bytes())}
 pub fn f64_set(&mut self,o:usize,v:f64){self.write(o,&v.to_le_bytes())}
 pub fn sequence_begin(&mut self,o:usize,next:u32){self.u32_set(o,next.wrapping_sub(1));fence(Ordering::Release);}
 pub fn sequence_end(&mut self,o:usize,next:u32){fence(Ordering::Release);self.u32_set(o,next);}
}
