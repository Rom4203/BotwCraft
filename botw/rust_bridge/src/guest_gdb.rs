//! Writes to the actual Switch guest via Ryujinx's GDB localhost stub.
//! Never probes or writes speculative Win32 host-memory copies.
use std::{fs,io::{self,Read,Write},net::{SocketAddr,TcpStream},
 path::Path,sync::{Arc,Mutex},thread,time::{Duration,Instant}};
use crate::{engine::Engine,shared::DIRECT};
use serde_json::json;
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
  socket.set_nodelay(true)?; // prevent Nagle/ACK delays in small GDB packets
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
// A single 20-byte READ of the native guest's live Link state.
// This is intentionally not a host-process memory scan. The native
// player callback validates the actor handle and samples Actor::mMtx.
fn read_link(remote:&mut Remote,addr:usize)->io::Result<Option<(u32,[f64;3])>>{
 let buf=remote.read(addr+176,20)?;
 let tick=u32::from_le_bytes(buf[0..4].try_into().unwrap());
 let valid=u32::from_le_bytes(buf[4..8].try_into().unwrap());
 if tick==0 || valid!=1 {return Ok(None)}
 let mut pos=[0.0;3];
 for (i,x) in pos.iter_mut().enumerate(){
   *x=f32::from_le_bytes(buf[8+i*4..12+i*4].try_into().unwrap()) as f64;
 }
 if pos.iter().any(|v|!v.is_finite()||v.abs()>100000.0){return Ok(None)}
 Ok(Some((tick,pos)))
}
fn active_packet(packet:&[u8])->bool{
 if packet.len()!=POSE_BYTES{return false}
 let seq=u32::from_le_bytes(packet[0..4].try_into().unwrap());
 let magic=u32::from_le_bytes(packet[4..8].try_into().unwrap());
 let version=u32::from_le_bytes(packet[8..12].try_into().unwrap());
 let flags=u32::from_le_bytes(packet[12..16].try_into().unwrap());
 seq!=0 && seq&1==0 && magic==0x31504442 && version==1 && (flags&0x13)==0x13
}
// BDP3: after a one-time mode switch, alternate complete CRC-checked
// 112-byte slots. Exactly ONE GDB 'M' write per incoming movement pose,
// avoiding the prior selector roundtrip. Zelda tests both CRCs in its tick.
const FAST_SEL:usize=204;
const FAST_SLOT_0:usize=208;
const FAST_SLOT_1:usize=320;
fn fnv_pose(packet:&[u8;POSE_BYTES])->u32 {
    let mut hash=2166136261u32;
    for (i,v) in packet.iter().enumerate(){
        if (104..108).contains(&i){continue}
        hash=(hash ^ *v as u32).wrapping_mul(16777619u32);
    }
    hash
}
fn publish_fast(remote:&mut Remote,addr:usize,packet:&[u8],slot:&mut u32)->io::Result<()>{
    let flags=u32::from_le_bytes(packet[12..16].try_into().unwrap());
    if flags!=0 && !active_packet(packet) {
        return Err(other("Refusing invalid BDP3 packet"));
    }
    let mut pose=[0u8;POSE_BYTES];
    pose.copy_from_slice(packet);
    let crc=fnv_pose(&pose);
    pose[104..108].copy_from_slice(&crc.to_le_bytes());
    let next=if *slot==1{2u32}else{1u32};
    remote.write(addr+if next==1{FAST_SLOT_0}else{FAST_SLOT_1},&pose)?;
    *slot=next;
    Ok(())
}
fn materially_changed(a:&[u8],b:&[u8])->bool{
    // Compare inputs that affect the Zelda image (pos, eye, forward,
    // yaw, pitch) but IGNORE frame counter / clock / unused origins.
    a[12..16]!=b[12..16] || a[32..76]!=b[32..76]
}
pub fn transport_loop(state:Arc<Mutex<Engine>>){
 loop{
  let result=(||->io::Result<()>{
   let addr=load_addr().ok_or_else(||other("Awaiting current Ryujinx guest mailbox"))?;
   let mut remote=Remote::connect()?;
   // No process-memory search, and crucially no re-reading and allocating
   // the ENTIRE growing multi-megabyte log on every 60 Hz frame.
   let identity=remote.read(addr,MARKER_BYTES)?;
   if !identity.starts_with(MAGIC) || identity[MAGIC.len()..].iter().any(|b|*b!=0){
    return Err(other("GDB guest mailbox marker mismatch; no memory writes"));
   }
   println!("[RUST_LINK] Guest mailbox matched; read-only until Zelda and Minecraft are active.");
   let mut authenticated=false;
   let mut selected=0u32;
   let mut last_guest_tick=0u32;
   let mut last_link:Option<([f64;3],Instant)>=None;
   let mut last_report=Instant::now()-Duration::from_secs(5);
   let mut last_read=Instant::now()-Duration::from_secs(1);
   let mut last_tx=Instant::now()-Duration::from_secs(1);
   let mut last_pose:Option<[u8;POSE_BYTES]>=None;
   let mut latency_sum=0u128;
   let mut latency_count=0u64;
   loop{
    // Player XYZ is sampled every 100ms, NOT at every transmitted Minecraft
    // frame. That avoids a 4th GDB roundtrip on the critical camera path.
    if last_read.elapsed()>=Duration::from_millis(100){
      if let Some((tick,pos))=read_link(&mut remote,addr)?{
       if tick!=last_guest_tick{
        last_guest_tick=tick;
        last_link=Some((pos,Instant::now()));
        let mut engine=state.lock().map_err(|_|other("bridge mutex poisoned"))?;
        engine.command(json!({"type":"pose","x":pos[0],"y":pos[1],"z":pos[2],
            "yaw":0.0,"pitch":0.0,"world":1}));
       }
      }
      last_read=Instant::now();
    }
    let pose={
      let engine=state.lock().map_err(|_|other("bridge mutex poisoned"))?;
      let raw=engine.mem.bytes(DIRECT,POSE_BYTES);
      let mut out=[0u8;POSE_BYTES];out.copy_from_slice(&raw);out
    };
    let native_live=last_link.as_ref().is_some_and(|(_,stamp)|stamp.elapsed()<Duration::from_millis(900));
    let armed=native_live && active_packet(&pose);
    if armed {
      if !authenticated{
       // The legacy mailbox probe stays as a one-time handshake.
       // Reset to legacy before authenticating if another bridge was used.
       remote.write(addr+FAST_SEL,&0u32.to_le_bytes())?;
       remote.authenticate(addr)?;
       // One-time transition to CRC-verified double-buffer mode.
       // The NX150 mod never reads a half-updated slot.
       remote.write(addr+FAST_SEL,&3u32.to_le_bytes())?;
       authenticated=true;
       selected=0;
       last_pose=None;
       println!("[RUST_LINK] Authenticated; BDP3 one-write double-buffer mode");
      }
      let change=last_pose.as_ref().is_none_or(|p|materially_changed(p,&pose));
      // Keepalive even while still, so native stale detection can disarm.
      let refresh=last_tx.elapsed()>=Duration::from_millis(300);
      if change || refresh{
       let started=Instant::now();
       publish_fast(&mut remote,addr,&pose,&mut selected)?;
       latency_sum+=started.elapsed().as_micros();
       latency_count+=1;
       last_pose=Some(pose);
       last_tx=Instant::now();
      }
    } else if authenticated {
       // Exactly one disarm is sent through BDP3, not to an unused
       // legacy slot. Then stop writing while Minecraft is inactive.
       let mut off=pose;
       let seq=u32::from_le_bytes(off[0..4].try_into().unwrap())&!1;
       off[0..4].copy_from_slice(&seq.to_le_bytes());
       off[12..16].fill(0);
       publish_fast(&mut remote,addr,&off,&mut selected)?;
       authenticated=false;
       last_pose=None;
       println!("[RUST_LINK] Disarmed once. Read-only until active input.");
    }
    if last_report.elapsed()>=Duration::from_secs(5){
      let status=remote.read(addr+196,8).unwrap_or_default();
      let (fps,hidden)=if status.len()==8{
        (u32::from_le_bytes(status[0..4].try_into().unwrap()),
         u32::from_le_bytes(status[4..8].try_into().unwrap()))
      }else{(0,0)};
      let mean=if latency_count>0{latency_sum/latency_count as u128}else{0};
      println!("[RUST_LINK] LinkTick={} FPS_MATRIX_FRAMES={} LINK_HIDDEN={} active={} BDP3_rtt_us={} samples={} still_refresh=300ms",
         last_guest_tick,fps,hidden,armed,mean,latency_count);
      latency_sum=0;latency_count=0;
      last_report=Instant::now();
    }
    // The stream uses the most recent Minecraft pose, never a queue of
    // past frames. 2ms poll is low overhead; GDB requests self-throttle.
    thread::sleep(Duration::from_millis(if armed{2}else{60}));
   }
  })();
  eprintln!("[RUST_LINK] Guest transport paused: {}",result.unwrap_err());
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
 #[test]fn no_disarmed_packet_is_ever_streamed(){
   let mut p=[0u8;POSE_BYTES];
   p[0..4].copy_from_slice(&2u32.to_le_bytes());
   p[4..8].copy_from_slice(&0x31504442u32.to_le_bytes());
   p[8..12].copy_from_slice(&1u32.to_le_bytes());
   assert!(!active_packet(&p));
   p[12..16].copy_from_slice(&0x13u32.to_le_bytes());
   assert!(active_packet(&p));
   p[12..16].copy_from_slice(&0x3u32.to_le_bytes());
   assert!(!active_packet(&p));
 }
 #[test]fn checksum_ignores_only_reserved_crc_field(){
   let mut a=[0u8;POSE_BYTES];
   let h=fnv_pose(&a);
   a[104..108].copy_from_slice(&h.to_le_bytes());
   assert_eq!(fnv_pose(&a),h);
   a[36]=1;
   assert_ne!(fnv_pose(&a),h);
 }
 #[test]fn material_change_ignores_frame_counter_but_not_camera(){
   let a=[0u8;POSE_BYTES];
   let mut b=a;
   b[16]=1;
   assert!(!materially_changed(&a,&b));
   b[32]=1;assert!(materially_changed(&a,&b));
 }
 #[test]fn reject_unscoped_and_unaligned(){
  assert_eq!(parse_guest_addr("GUEST_MAILBOX=0x000000000b37e000"),None);
  assert_eq!(parse_guest_addr("[LAUNCH] RYUJINX_PROCESS: first\nGUEST_MAILBOX=0x000000000b37e001"),None);
 }
}
