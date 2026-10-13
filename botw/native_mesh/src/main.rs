#[cfg(not(windows))]
fn main(){eprintln!("Requires Windows");}
#[cfg(windows)]
mod app {
use std::{ffi::c_void,io::{self,Read},mem::size_of,time::{Duration,Instant}};
const ACCESS:u32=0x438; // query + VM read/write/operation
const MAGIC:u32=0x344d4342; // BCM4, guest NVN module v4
const COOKIE:u32=0x34435742;
const CAP:usize=2048;
type H=*mut c_void;
#[repr(C)]
struct Entry {sz:u32,usage:u32,pid:u32,heap:usize,modid:u32,threads:u32,parent:u32,pri:i32,flags:u32,name:[u16;260]}
impl Default for Entry {fn default()->Self {Self{sz:size_of::<Self>() as u32,usage:0,pid:0,heap:0,modid:0,threads:0,parent:0,pri:0,flags:0,name:[0;260]}}}
#[repr(C)]
#[derive(Default)]
struct Mbi {base:usize,alloc:usize,allocprot:u32,partition:u16,pad:u16,size:usize,state:u32,prot:u32,kind:u32,pad2:u32}
#[link(name="kernel32")]
extern "system" {
fn CreateToolhelp32Snapshot(flags:u32,pid:u32)->H;
fn Process32FirstW(h:H,e:*mut Entry)->i32;
fn Process32NextW(h:H,e:*mut Entry)->i32;
fn OpenProcess(flags:u32,inherit:i32,pid:u32)->H;
fn CloseHandle(h:H)->i32;
fn VirtualQueryEx(h:H,p:*const c_void,m:*mut Mbi,len:usize)->usize;
fn ReadProcessMemory(h:H,p:*const c_void,b:*mut c_void,len:usize,done:*mut usize)->i32;
fn WriteProcessMemory(h:H,p:*mut c_void,b:*const c_void,len:usize,done:*mut usize)->i32;
}
fn pid()->Option<u32>{unsafe{
 let h=CreateToolhelp32Snapshot(2,0);if h.is_null()||h as isize==-1{return None;}
 let mut e=Entry::default();let mut id=None;
 if Process32FirstW(h,&mut e)!=0{loop{
  let n=e.name.iter().position(|x|*x==0).unwrap_or(260);
  if String::from_utf16_lossy(&e.name[..n]).eq_ignore_ascii_case("Ryujinx.exe"){id=Some(e.pid);break;}
  if Process32NextW(h,&mut e)==0{break;}
 }} CloseHandle(h);id
}}
struct Process {id:u32,h:H,mail:usize,active:u32,seq:u32}
impl Drop for Process {fn drop(&mut self){unsafe{CloseHandle(self.h);}}}
impl Process{
 fn open(id:u32)->Option<Self>{let h=unsafe{OpenProcess(ACCESS,0,id)};if h.is_null(){None}else{Some(Self{id,h,mail:0,active:0,seq:0})}}
 fn read(&self,p:usize,b:&mut[u8])->bool{
 let mut n=0;unsafe{ReadProcessMemory(self.h,p as *const _,b.as_mut_ptr() as *mut _,b.len(),&mut n)!=0&&n==b.len()}}
 fn write(&self,p:usize,b:&[u8])->bool{
 let mut n=0;unsafe{WriteProcessMemory(self.h,p as *mut _,b.as_ptr() as *const _,b.len(),&mut n)!=0&&n==b.len()}}
 fn scan(&self)->Option<usize>{
  let mut p=0x10000usize;let mut inspected=0usize;
  let mut buf=vec![0u8;1024*1024+16];
  while p<0x0000_7fff_ffff_0000usize{
   let mut m=Mbi::default();if unsafe{VirtualQueryEx(self.h,p as *const _,&mut m,size_of::<Mbi>())}==0{break;}
   let next=m.base.saturating_add(m.size);if next<=p{break;}
   let valid=m.state==0x1000&&(m.prot&0x100)==0&&matches!(m.prot&0xff,4|8|0x40|0x80);
   if valid&&m.size>0x20100{
    let mut q=m.base;
    while q<next{
     let n=(next-q).min(1024*1024);let len=(n+16).min(next-q);
     if self.read(q,&mut buf[..len]){
      for i in (0..n.saturating_sub(16)).step_by(4){
       if u32::from_le_bytes(buf[i..i+4].try_into().unwrap())!=MAGIC ||
          u32::from_le_bytes(buf[i+12..i+16].try_into().unwrap())!=COOKIE{continue;}
       let addr=q+i;let mut end=[0u8;16];
       if self.read(addr+0x10080,&mut end) {return Some(addr);}
      }
     }
     q+=n;inspected+=n;
     if inspected>12*1024*1024*1024usize{return None;}
    }
   }p=next;
  }None
 }
 fn send(&mut self,b:&[u8])->bool{
  if self.mail==0{return false;}
  let dst=1-self.active;
  let slot=self.mail+0x40+dst as usize*(CAP*32+0x40);
  if !b.is_empty()&&!self.write(slot+16,b){self.mail=0;return false;}
  self.seq=self.seq.wrapping_add(1);
  let mut meta=[0u8;8];meta[..4].copy_from_slice(&((b.len()/32) as u32).to_le_bytes());meta[4..].copy_from_slice(&self.seq.to_le_bytes());
  if !self.write(slot,&meta)||!self.write(self.mail+4,&dst.to_le_bytes()){self.mail=0;return false;}
  self.active=dst;true
 }
}
pub fn main(){
 println!("[BWC4] Rust direct-memory writer started; existing GDB bridge remains untouched");
 let mut input=io::stdin().lock();let mut process:Option<Process>=None;let mut last_scan=Instant::now()-Duration::from_secs(10);
 loop{
  let mut header=[0u8;4];if input.read_exact(&mut header).is_err(){break;}
  let len=u32::from_le_bytes(header) as usize;
  if len>CAP*32||len%96!=0{eprintln!("[BWC4] rejected invalid mesh size {len}");break;}
  let mut data=vec![0u8;len];if input.read_exact(&mut data).is_err(){break;}
  let current=pid();
  if process.as_ref().map(|p|p.id)!=current{process=current.and_then(Process::open);last_scan=Instant::now()-Duration::from_secs(10);}
  if let Some(ref mut p)=process{
   if p.mail==0&&last_scan.elapsed()>Duration::from_secs(3){
    last_scan=Instant::now();p.mail=p.scan().unwrap_or(0);
    if p.mail!=0{println!("[BWC4] guest NVN buffer found via host memory at 0x{:x}",p.mail);}
   }
   if p.mail!=0&&!p.send(&data){eprintln!("[BWC4] guest memory write failed");}
  }
 }
}
}
#[cfg(windows)]
fn main(){app::main()}
