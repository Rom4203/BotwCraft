//! Windows -> Ryujinx transport for the module-owned WXLM BDP1 mailbox.
//! An inactive probe must be ACKed by WiiXLaunch's live player tick before
//! this code accepts a candidate. NEVER select a first substring match.
use std::{ffi::c_void,io,ptr,thread,time::{Duration,Instant}};
use crate::{engine::Engine,shared::DIRECT};

#[link(name="kernel32")]
extern "system"{
 fn OpenProcess(rights:u32,inherit:i32,pid:u32)->isize;
 fn CloseHandle(handle:isize)->i32;
 fn QueryFullProcessImageNameW(h:isize,flags:u32,name:*mut u16,len:*mut u32)->i32;
 fn VirtualQueryEx(h:isize,addr:*const c_void,out:*mut Mbi,size:usize)->usize;
 fn ReadProcessMemory(h:isize,addr:*const c_void,out:*mut c_void,len:usize,read:*mut usize)->i32;
 fn WriteProcessMemory(h:isize,addr:*mut c_void,src:*const c_void,len:usize,wrote:*mut usize)->i32;
}
#[link(name="psapi")]
extern "system" { fn EnumProcesses(ids:*mut u32,len:u32,used:*mut u32)->i32; }
const ACCESS:u32=0x10|0x20|0x08|0x1000;
const COMMIT:u32=0x1000;
const MARKER:&[u8]=b"BOTWCRAFT_WXLM_BDP1_LIVE_20261010";
const PACKET_OFFSET:usize=40;
const ACK_OFFSET:usize=152;
const STATE_OFFSET:usize=156;
const CHUNK:usize=1024*1024;
const SCAN_LIMIT:usize=6*1024*1024*1024;
const TOP:usize=0x00007FFF_FFFF_FFFF;

#[repr(C)]
#[derive(Default)]
struct Mbi {
 base:usize,allocation:usize,allocation_protect:u32,pad:u32,
 len:usize,state:u32,protect:u32,kind:u32,pad2:u32
}
fn writable(p:u32)->bool{p&0x100==0 && matches!(p&0xff,0x04|0x08|0x40|0x80)}
fn failure(s:&str)->io::Error{io::Error::new(io::ErrorKind::Other,s)}
struct Process { handle:isize,pid:u32 }
impl Drop for Process{fn drop(&mut self){unsafe{CloseHandle(self.handle);}}}
impl Process{
 fn attach()->io::Result<Self>{
  let mut pids=[0u32;8192];
  let mut used=0u32;
  if unsafe{EnumProcesses(pids.as_mut_ptr(),std::mem::size_of_val(&pids) as u32,&mut used)}==0{
   return Err(io::Error::last_os_error());
  }
  let mut found=Vec::new();
  for pid in pids[..(used as usize/4).min(pids.len())].iter().copied().filter(|v|*v!=0){
   let h=unsafe{OpenProcess(ACCESS,0,pid)};
   if h==0{continue}
   let mut buf=[0u16;32768];let mut n=buf.len() as u32;
   let match_name=unsafe{QueryFullProcessImageNameW(h,0,buf.as_mut_ptr(),&mut n)}!=0 &&
    String::from_utf16_lossy(&buf[..n as usize])
     .rsplit(['\\','/']).next()
     .is_some_and(|s|s.eq_ignore_ascii_case("Ryujinx.exe") ||
                    s.eq_ignore_ascii_case("Ryujinx.Ava.exe"));
   if match_name{found.push((h,pid));}else{unsafe{CloseHandle(h);}}
  }
  if found.len()!=1{
   for (h,_) in found{unsafe{CloseHandle(h);}}
   return Err(failure("Expected exactly one verified Ryujinx process"));
  }
  let (handle,pid)=found.remove(0);
  println!("[RUST_LINK] Ryujinx PID={pid}");
  Ok(Self{handle,pid})
 }
 fn query(&self,addr:usize)->Option<Mbi>{
  let mut info=Mbi::default();
  let read=unsafe{VirtualQueryEx(self.handle,addr as *const c_void,
                               &mut info,std::mem::size_of::<Mbi>())};
  (read==std::mem::size_of::<Mbi>()).then_some(info)
 }
 fn read(&self,addr:usize,len:usize)->io::Result<Vec<u8>>{
  if len==0 || len>CHUNK{return Err(failure("invalid ReadProcessMemory length"))}
  let mut out=vec![0u8;len];let mut read=0usize;
  let ok=unsafe{ReadProcessMemory(self.handle,addr as *const c_void,
    out.as_mut_ptr().cast(),len,&mut read)};
  if ok==0 || read!=len{return Err(io::Error::last_os_error())}
  Ok(out)
 }
 fn write(&self,addr:usize,data:&[u8])->io::Result<()>{
  if data.is_empty() || data.len()>112{return Err(failure("invalid memory write size"))}
  let region=self.query(addr).ok_or_else(||failure("destination page unavailable"))?;
  if region.state!=COMMIT || !writable(region.protect)
    || addr.checked_add(data.len()).is_none_or(|end|end>region.base+region.len){
   return Err(failure("unwritable / crossing boundary Ryujinx memory page"))
  }
  let mut written=0usize;
  let ok=unsafe{WriteProcessMemory(self.handle,addr as *mut c_void,
    data.as_ptr().cast(),data.len(),&mut written)};
  if ok==0 || written!=data.len(){return Err(io::Error::last_os_error())}
  Ok(())
 }
 fn candidates(&self)->io::Result<Vec<usize>>{
  let mut out=Vec::new();let mut cursor=0x10000usize;
  let mut scanned=0usize;let began=Instant::now();
  while cursor<TOP && scanned<SCAN_LIMIT && began.elapsed()<Duration::from_secs(60){
   let Some(r)=self.query(cursor)else{cursor=cursor.saturating_add(0x10000);continue};
   let end=r.base.saturating_add(r.len);
   if end<=cursor{break}
   cursor=end;
   if r.state!=COMMIT || !writable(r.protect){continue}
   let mut offset=0usize;
   while offset<r.len && scanned<SCAN_LIMIT{
    let size=(r.len-offset).min(CHUNK);
    scanned+=size;
    if let Ok(data)=self.read(r.base+offset,size){
     // Scan all hits, then verify the complete 40-byte null-padded marker.
     let mut at=0;
     while let Some(n)=data[at..].windows(MARKER.len()).position(|w|w==MARKER){
      let index=at+n;
      let addr=r.base+offset+index;
      if let Ok(bytes)=self.read(addr,40){
       if bytes[..MARKER.len()]==*MARKER &&
          bytes[MARKER.len()..].iter().all(|b|*b==0) &&
          self.query(addr+STATE_OFFSET).is_some_and(|p|p.state==COMMIT&&writable(p.protect)){
        if !out.contains(&addr){out.push(addr);}
       }
      }
      at=index+MARKER.len();
      if at>=data.len(){break}
     }
    }
    // Overlap marker size at boundaries.
    if size<=MARKER.len(){break}
    offset+=size-MARKER.len();
   }
   if out.len()>32{return Err(failure("Too many candidate WXLM markers"))}
  }
  println!("[RUST_LINK] WXLM marker candidates={} scanned={} MiB",out.len(),scanned>>20);
  Ok(out)
 }
 fn send(&self,mailbox:usize,pkt:&[u8])->io::Result<()>{
  if pkt.len()!=112{return Err(failure("BDP1 packet must be exactly 112 bytes"))}
  let seq=u32::from_le_bytes(pkt[..4].try_into().unwrap());
  if seq&1!=0{return Err(failure("BDP1 odd published sequence"))}
  let address=mailbox+PACKET_OFFSET;
  self.write(address,&seq.wrapping_sub(1).to_le_bytes())?;
  self.write(address+4,&pkt[4..])?;
  self.write(address,&seq.to_le_bytes())
 }
 fn authenticated(&self,candidates:&[usize])->io::Result<usize>{
  let mut approved=Vec::new();
  for (i,&address) in candidates.iter().enumerate(){
   // Flags=0: never move Link during mailbox discovery.
   let seq=0x72000000u32.wrapping_add(i as u32*2);
   let mut probe=[0u8;112];
   probe[0..4].copy_from_slice(&seq.to_le_bytes());
   probe[4..8].copy_from_slice(&0x31504442u32.to_le_bytes());
   probe[8..12].copy_from_slice(&1u32.to_le_bytes());
   if self.send(address,&probe).is_err(){continue}
   let deadline=Instant::now()+Duration::from_millis(1500);
   while Instant::now()<deadline{
    if let Ok(reply)=self.read(address+ACK_OFFSET,8){
     let seen=u32::from_le_bytes(reply[..4].try_into().unwrap());
     let state=u32::from_le_bytes(reply[4..8].try_into().unwrap());
     if seen==seq && matches!(state,1|2|4){
      println!("[RUST_LINK] Guest player-tick ACK from 0x{address:x}");
      approved.push(address);break
     }
    }
    thread::sleep(Duration::from_millis(20));
   }
  }
  if approved.len()!=1{return Err(failure("No unique guest-confirmed WXLM mailbox; refusing writes"))}
  Ok(approved[0])
 }
}

pub fn transport_loop(state:std::sync::Arc<std::sync::Mutex<Engine>>){
 loop{
  let result=(||->io::Result<()>{
   let process=Process::attach()?;
   let addresses=process.candidates()?;
   let mailbox=process.authenticated(&addresses)?;
   println!("[RUST_LINK] Confirmed live guest mailbox {mailbox:#x}; transport active");
   let mut last_seq=0u32;
   loop{
    let pkt={
     let e=state.lock().map_err(|_|failure("Rust bridge mutex poisoned"))?;
     e.mem.bytes(DIRECT,112)
    };
    let seq=u32::from_le_bytes(pkt[..4].try_into().unwrap());
    if seq&1==0 && seq!=last_seq &&
       u32::from_le_bytes(pkt[4..8].try_into().unwrap())==0x31504442{
      process.send(mailbox,&pkt)?;
      last_seq=seq;
    }
    // No process memory writing without an authenticated guest ACK.
    if process.query(mailbox).is_none(){return Err(failure("Mailbox mapping vanished"))}
    thread::sleep(Duration::from_millis(16));
   }
  })();
  eprintln!("[RUST_LINK] Transport disconnected: {}; retry after Ryujinx / Zelda is ready",
       result.unwrap_err());
  thread::sleep(Duration::from_secs(3));
 }
}
