//! Writes to the actual Switch guest via Ryujinx's GDB localhost stub.
//! Never probes or writes speculative Win32 host-memory copies.
use std::{fs,io::{self,Read,Write},net::{SocketAddr,TcpStream},
 path::Path,sync::{Arc,Mutex},thread,time::{Duration,Instant}};
use crate::{engine::Engine,shared::DIRECT};
const MAGIC:&[u8]=b"BOTWCRAFT_WXLM_BDP1_LIVE_20261010";
const MARKER_BYTES:usize=40;
const POSE_BYTES:usize=112;
fn other(s:&str)->io::Error{io::Error::new(io::ErrorKind::Other,s)}

fn parse_guest_addr(log:&str)->Option<usize>{
 // Reject all markers from previous Ryujinx boots.
 let cutoff=log.rfind("[LAUNCH] RYUJINX_PROCESS:")
    .or_else(||log.rfind("[LAUNCHER] Starting RYUJINX_PROCESS:"))?;
 let marker="GUEST_MAILBOX=0x";
 let tail=log[cutoff..].rsplit_once(marker)?.1;
 let hex=tail.split(|c:char|!c.is_ascii_hexdigit()).next()?;
 if hex.len()!=16{return None}
 let addr=usize::from_str_radix(hex,16).ok()?;
 (addr>=0x10000 && addr&15==0).then_some(addr)
}
fn load_addr()->Option<usize>{
 let path=std::env::var_os("BOTWCRAFT_LOG")
   .map(std::path::PathBuf::from)
   .unwrap_or_else(||Path::new("logs").join("botwcraft.log"));
 parse_guest_addr(&fs::read_to_string(path).ok()?)
}
struct Remote{stream:TcpStream}
impl Remote{
 fn connect()->io::Result<Self>{
  let address=SocketAddr::from(([127,0,0,1],22225));
  let socket=TcpStream::connect_timeout(&address,Duration::from_secs(1))?;
  socket.set_read_timeout(Some(Duration::from_secs(3)))?;
  socket.set_write_timeout(Some(Duration::from_secs(3)))?;
  let mut r=Self{stream:socket};
  let supported=r.request("qSupported")?;
  println!("[RUST_LINK] Ryujinx GDB connected: {}",supported.chars().take(100).collect::<String>());
  Ok(r)
 }
 fn request(&mut self,data:&str)->io::Result<String>{
  let sum=data.as_bytes().iter().fold(0u8,|a,b|a.wrapping_add(*b));
  let frame=format!("{}{}#{sum:02x}",'$',data);
  self.stream.write_all(frame.as_bytes())?;
  self.stream.flush()?;
  let mut current=Vec::<u8>::new();let mut phase=0u8;
  loop{
   let mut c=[0u8;1];self.stream.read_exact(&mut c)?;
   match phase{
    0=>{if c[0]==b'$'{phase=1;current.clear();}}
    1=>{if c[0]==b'#'{phase=2;}else if current.len()<0x100000 {current.push(c[0]);}
       else{return Err(other("GDB oversize response"))}}
    2=>{
     let mut last=[0u8;1];self.stream.read_exact(&mut last)?;
     let sum_hex=[c[0],last[0]];
     let expected=std::str::from_utf8(&sum_hex).ok().and_then(|s|u8::from_str_radix(s,16).ok());
     let actual=current.iter().fold(0u8,|a,b|a.wrapping_add(*b));
     if expected!=Some(actual){self.stream.write_all(b"-")?;return Err(other("GDB checksum error"))}
     self.stream.write_all(b"+")?;
     return String::from_utf8(current).map_err(|_|other("GDB invalid UTF8"))
    }
    _=>unreachable!()
   }
  }
 }
 fn read(&mut self,addr:usize,len:usize)->io::Result<Vec<u8>>{
  if len==0||len>256{return Err(other("GDB read out of bounds"))}
  let reply=self.request(&format!("m{addr:x},{len:x}"))?;
  if reply.starts_with('E') || reply.len()!=len*2{return Err(other("GDB read refused or invalid size"))}
  let mut out=Vec::with_capacity(len);
  for i in (0..reply.len()).step_by(2){
   out.push(u8::from_str_radix(&reply[i..i+2],16)
     .map_err(|_|other("GDB invalid hex bytes"))?);
  }
  Ok(out)
 }
 fn write(&mut self,addr:usize,bytes:&[u8])->io::Result<()>{
  if bytes.is_empty()||bytes.len()>POSE_BYTES{return Err(other("GDB unsafe write length"))}
  let mut cmd=format!("M{addr:x},{:x}:",bytes.len());
  for b in bytes {use std::fmt::Write as _;let _=write!(&mut cmd,"{b:02x}");}
  if self.request(&cmd)?!="OK"{return Err(other("GDB refused memory write"))}
  Ok(())
 }
 fn send(&mut self,addr:usize,pkt:&[u8])->io::Result<()>{
  if pkt.len()!=POSE_BYTES{return Err(other("BDP1 length mismatch"))}
  let seq=u32::from_le_bytes(pkt[0..4].try_into().unwrap());
  if seq&1!=0{return Err(other("BDP1 odd sequence"))}
  let at=addr+MARKER_BYTES;
  // Three requests keep the guest read seqlock consistent.
  self.write(at,&seq.wrapping_sub(1).to_le_bytes())?;
  self.write(at+4,&pkt[4..])?;
  self.write(at,&seq.to_le_bytes())?;
  Ok(())
 }
 fn authenticate(&mut self,addr:usize)->io::Result<()>{
  let m=self.read(addr,MARKER_BYTES)?;
  if !m.starts_with(MAGIC) || m[MAGIC.len()..].iter().any(|b|*b!=0){
   return Err(other("GDB guest memory is not the live WiiXLaunch mailbox"));
  }
  // An unarmed probe can never move Link or the camera.
  let mut pkt=[0u8;POSE_BYTES];let seq=0x7200BDA0u32;
  pkt[..4].copy_from_slice(&seq.to_le_bytes());
  pkt[4..8].copy_from_slice(&0x31504442u32.to_le_bytes());
  pkt[8..12].copy_from_slice(&1u32.to_le_bytes());
  self.send(addr,&pkt)?;
  let start=Instant::now();
  while start.elapsed()<Duration::from_secs(5){
   let reply=self.read(addr+152,8)?;
   let ack=u32::from_le_bytes(reply[..4].try_into().unwrap());
   if ack==seq{
    println!("[RUST_LINK] Guest core-frame ACK verified at guest 0x{addr:x}");
    return Ok(())
   }
   thread::sleep(Duration::from_millis(100));
  }
  Err(other("Core-frame tick did not ACK the unarmed GDB probe"))
 }
}
pub fn transport_loop(state:Arc<Mutex<Engine>>){
 loop{
  let result=(||->io::Result<()>{
   let addr=load_addr().ok_or_else(||other("Awaiting GUEST_MAILBOX log after current Ryujinx boot"))?;
   let mut remote=Remote::connect()?;
   remote.authenticate(addr)?;
   let mut last_seq=0u32;let mut last_report=Instant::now()-Duration::from_secs(5);
   let mut last_tick=Instant::now();
   loop{
    if load_addr()!=Some(addr){return Err(other("Ryujinx restarted; rejecting stale guest pointer"))}
    let pkt={
     let e=state.lock().map_err(|_|other("Rust bridge mutex poisoned"))?;
     e.mem.bytes(DIRECT,POSE_BYTES)
    };
    let seq=u32::from_le_bytes(pkt[..4].try_into().unwrap());
    if seq&1==0 && seq!=last_seq
       && u32::from_le_bytes(pkt[4..8].try_into().unwrap())==0x31504442u32 {
      remote.send(addr,&pkt)?;
      last_seq=seq;
    }
    if last_report.elapsed()>=Duration::from_secs(3){
     let status=remote.read(addr+152,24)?;
     let at=|n:usize|u32::from_le_bytes(status[n..n+4].try_into().unwrap());
     let camera=u64::from_le_bytes(status[8..16].try_into().unwrap());
     println!("[RUST_LINK] guest ACK={} seq={} state={} applied={} warp_method={} camera=0x{:x}",
       at(0),last_seq,at(4),at(16),at(20),camera);
     last_report=Instant::now();
    }
    let elapsed=last_tick.elapsed();
    if elapsed<Duration::from_millis(33){thread::sleep(Duration::from_millis(33)-elapsed);}
    last_tick=Instant::now();
   }
  })();
  eprintln!("[RUST_LINK] Safe GDB transport waiting: {}. No speculative memory writes.",result.unwrap_err());
  thread::sleep(Duration::from_secs(3));
 }
}
#[cfg(test)]
mod tests{
 use super::*;
 #[test]fn scoped_address(){
  let a="[LAUNCH] RYUJINX_PROCESS: first\n[BOTW_NATIVE] GUEST_MAILBOX=0x000000000b37e000\n";
  assert_eq!(parse_guest_addr(a),Some(0xb37e000));
  assert_eq!(parse_guest_addr(&(a.to_string()+"[LAUNCH] RYUJINX_PROCESS: second\n")),None);
 }
 #[test]fn reject_unscoped_and_unaligned(){
  assert_eq!(parse_guest_addr("GUEST_MAILBOX=0x000000000b37e000"),None);
  assert_eq!(parse_guest_addr("[LAUNCH] RYUJINX_PROCESS: first\nGUEST_MAILBOX=0x000000000b37e001"),None);
 }
}
