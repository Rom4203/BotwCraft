//! Writes to the actual Switch guest via Ryujinx's GDB localhost stub.
//! Never probes or writes speculative Win32 host-memory copies.
use std::{fs,io::{self,Read,Write},net::{SocketAddr,TcpStream},
 path::Path,sync::{Arc,Mutex},thread,time::{Duration,Instant}};
use crate::{engine::Engine,shared::DIRECT,terrain::TerrainRelay,static_terrain::STATIC_ACTIVE};
use serde_json::json;
use std::sync::atomic::Ordering;
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
// GDB packets are 2x hex-encoded. Reading the socket one byte at a time
// previously required thousands of kernel calls per 16-tile terrain batch.
struct Remote{
 stream:TcpStream,
 buffer:[u8;8192],
 at:usize,
 end:usize,
}
impl Remote{
 fn next_byte(&mut self)->io::Result<u8>{
  if self.at==self.end {
   self.end=self.stream.read(&mut self.buffer)?;
   self.at=0;
   if self.end==0{return Err(other("GDB socket closed"))}
  }
  let b=self.buffer[self.at];self.at+=1;Ok(b)
 }

 fn connect()->io::Result<Self>{
  let address=SocketAddr::from(([127,0,0,1],22225));
  let socket=TcpStream::connect_timeout(&address,Duration::from_secs(1))?;
  socket.set_nodelay(true)?; // prevent Nagle/ACK delays in small GDB packets
  socket.set_read_timeout(Some(Duration::from_secs(3)))?;
  socket.set_write_timeout(Some(Duration::from_secs(3)))?;
  let mut r=Self{stream:socket,buffer:[0;8192],at:0,end:0};
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
   let c=self.next_byte()?;
   match phase{
    0=>{if c==b'$'{phase=1;current.clear();}}
    1=>{if c==b'#'{phase=2;}else if current.len()<0x100000 {current.push(c);}
       else{return Err(other("GDB oversize response"))}}
    2=>{
     let sum_hex=[c,self.next_byte()?];
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
  if len==0||len>1008{return Err(other("GDB read out of bounds"))}
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
    a[12..16]!=b[12..16] || a[32..76]!=b[32..76] || a[100..104]!=b[100..104]
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
   let mut last_optical_read=Instant::now()-Duration::from_secs(1);
   let mut optical_seq=0u32;
   let mut optical_reported=false;
   let mut last_pose:Option<[u8;POSE_BYTES]>=None;
   let mut latency_sum=0u128;
   let mut latency_count=0u64;
   let mut terrain=TerrainRelay::default();
   let mut terrain_static_guest=false;
   let mut last_terrain=Instant::now()-Duration::from_secs(1);
   let mut terrain_ring_read=0u32;
   let mut terrain_ring_available=false;
   let mut terrain_ring_checked=false;
   let mut terrain_ring_lost=0u32;
   let mut terrain_gdb_max_tiles=16usize;
   let mut terrain_disarmed_at:Option<Instant>=None;
   let mut ever_havok=false;
   let mut last_havok_warning=Instant::now()-Duration::from_secs(10);
   let mut last_havok_diagnostic=Instant::now()-Duration::from_secs(10);
   let mut terrain_stats_received=0usize;
   let mut terrain_stats_accepted=0usize;
   let mut terrain_stats_read_us=0u128;
   let mut terrain_stats_mesh_us=0u128;
   let mut terrain_stats_batches=0u128;
   loop{
    // Player XYZ is sampled every 100ms, NOT at every transmitted Minecraft
    // frame. That avoids a 4th GDB roundtrip on the critical camera path.
    if last_read.elapsed()>=Duration::from_millis(250){
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
      let refresh=last_tx.elapsed()>=Duration::from_millis(250);
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
    // Zelda optical VIEW captured AFTER sead::LookAtCamera::doUpdateMatrix.
    // Use the EXISTING GDB connection: never start another debugger client.
    if armed && authenticated && last_optical_read.elapsed()>=Duration::from_millis(10) {
      if let Ok(view)=remote.read(addr+4084,84){
        let magic=u32::from_le_bytes(view[0..4].try_into().unwrap());
        let seq=u32::from_le_bytes(view[4..8].try_into().unwrap());
        let game_tick=u32::from_le_bytes(view[8..12].try_into().unwrap());
        let valid=magic==0x31575642 && seq!=0 && seq&1==0 && game_tick!=0 &&
          view[12..84].chunks_exact(4).all(|x| {
            let f=f32::from_le_bytes(x.try_into().unwrap());
            f.is_finite() && f.abs()<100000.0
          });
        if valid {
          if let Ok(mut engine)=state.lock(){
            let base=0x980usize; // reserved SkyCraft-v11 shared memory header
            optical_seq=optical_seq.wrapping_add(2)&!1;
            engine.mem.sequence_begin(base+4,optical_seq);
            engine.mem.u32_set(base,0x31575642); // BVW1
            engine.mem.u64_set(base+8,crate::shared::clock());
            engine.mem.u32_set(base+16,game_tick);
            engine.mem.u32_set(base+20,1);
            engine.mem.write(base+24,&view[12..84]); // eye + forward + native view
            engine.mem.write(base+96,&pose[76..100]); // 3 MC + 3 BOTW anchors
            engine.mem.sequence_end(base+4,optical_seq);
            if !optical_reported {
              println!("[RUST_LINK] Native Zelda optical view BVW1 ready; Minecraft FOV never used for blocks");
              optical_reported=true;
            }
          }
        }
      }
      last_optical_read=Instant::now();
    }
    // Static physical mesh bypass: stop spending Havok CPU on raycasts when
    // the exact user-owned collision file is already present on disk.
    let static_active=STATIC_ACTIVE.load(Ordering::Acquire);
    if authenticated && static_active!=terrain_static_guest {
      remote.write(addr+4080,&(if static_active{1u32}else{0u32}).to_le_bytes())?;
      terrain_static_guest=static_active;
      if static_active { ever_havok=false; }
      println!("[TERRAIN] Guest Havok scan {} (direct BTRI mode)",if static_active{"suspended"}else{"resumed"});
    }
    // V2 mailbox: 64-slot independent terrain mesh ring at guest +496.
    // No 56-byte tile can be overwritten before Rust has 64 newer tiles,
    // even when the emulator's GDB debugger pauses for an input refresh.
    // 10ms polling is deliberately bounded; never delay the BDP3 camera
    // with an unbounded while-loop or hundreds of Havok read requests.
    if armed && authenticated && !static_active && last_terrain.elapsed()>=Duration::from_millis(10){
      terrain_disarmed_at=None;
      if !terrain_ring_checked {
        match remote.read(addr+488,8){
          Ok(h)=>{
            terrain_ring_available=u32::from_le_bytes(h[4..8].try_into().unwrap())==0x32525254;
            terrain_ring_checked=true;
            println!("[TERRAIN] native 0.68m tile ring: {}",if terrain_ring_available{"64 grid slots, 10ms poll, batched"}else{"not installed; legacy fallback"});
          },
          Err(_)=>{} // wait until a valid player frame produces the ring marker
        }
      }
      if terrain_ring_available {
        match remote.read(addr+488,8){
          Ok(h)=>{
            let write=u32::from_le_bytes(h[0..4].try_into().unwrap());
            let pending=write.wrapping_sub(terrain_ring_read);
            if pending>64 {
              let dropped=pending-64;
              terrain_ring_lost=terrain_ring_lost.saturating_add(dropped);
              terrain_ring_read=write.wrapping_sub(64);
              eprintln!("[TERRAIN] GDB ring fell behind, skipped {} old tiles (total lost={}); BDP3 still active",dropped,terrain_ring_lost);
            }
            // Read up to sixteen contiguous 56-byte terrain tiles per GDB
            // request. The guest ring can wrap at index 63; split only there.
            // Save the whole group before touching the expensive Minecraft
            // collider map, so the repeated 8-block region mesh is sent once.
            let mut samples=Vec::with_capacity(32*56);
            let mut consumed=0u32;
            let started=Instant::now();
            while terrain_ring_read!=write && consumed<32 {
              let index=(terrain_ring_read%64) as usize;
              let count=(write.wrapping_sub(terrain_ring_read) as usize)
                .min(64-index).min(terrain_gdb_max_tiles).min(32-consumed as usize);
              let location=addr+496+index*56;
              match remote.read(location,count*56){
                Ok(bytes)=>{
                  let mut accepted=0usize;
                  for sample in bytes.chunks_exact(56){
                    let seq=u32::from_le_bytes(sample[0..4].try_into().unwrap());
                    if seq==0 || seq&1!=0 {break}
                    samples.extend_from_slice(sample);
                    accepted+=1;
                  }
                  terrain_ring_read=terrain_ring_read.wrapping_add(accepted as u32);
                  consumed+=accepted as u32;
                  if accepted!=count{break}
                }
                Err(e)=>{
                  // Some Ryujinx GDB builds cap each memory-read packet to
                  // 256 bytes. Fall back to four 56-byte tiles (224 bytes),
                  // rather than losing ALL terrain on those emulator builds.
                  if count>4 {
                    terrain_gdb_max_tiles=4;
                    eprintln!("[TERRAIN] GDB large reads unsupported ({e}); using 4-tile burst reads");
                    continue;
                  }
                  if last_havok_warning.elapsed()>=Duration::from_secs(5){
                    eprintln!("[TERRAIN] GDB burst read failed ({e}), BDP3 remains active");
                    last_havok_warning=Instant::now();
                  }
                  break;
                }
              }
            }
            let read_us=started.elapsed().as_micros();
            if !samples.is_empty(){
              let mesh_start=Instant::now();
              let mut engine=state.lock().map_err(|_|other("bridge mutex poisoned"))?;
              let count=terrain.ingest_batch(&samples,&pose,&mut engine.mem);
              let mesh_us=mesh_start.elapsed().as_micros();
              if count>0 {ever_havok=true}
              terrain_stats_received+=samples.len()/56;
              terrain_stats_accepted+=count;
              terrain_stats_read_us+=read_us;
              terrain_stats_mesh_us+=mesh_us;
              terrain_stats_batches+=1;
            }
          }
          Err(e)=>{
            if last_havok_warning.elapsed()>=Duration::from_secs(5){
              eprintln!("[TERRAIN] Havok ring header unavailable ({e}); gameplay link kept alive");
              last_havok_warning=Instant::now();
            }
          }
        }
      }else{
        // Backward-compatible stream, only when a previous Zelda module
        // doesn't implement the new ring protocol.
        if let Ok(sample)=remote.read(addr+432,56){
          let mut engine=state.lock().map_err(|_|other("bridge mutex poisoned"))?;
          if terrain.ingest(&sample,&pose,&mut engine.mem){ever_havok=true}
        }
      }
      if last_havok_diagnostic.elapsed()>=Duration::from_secs(10){
        if terrain_ring_available {
          println!("[TERRAIN] fine ring consumed={} lost={} batches={} received={} accepted={} GDB_read_avg_us={} mesh_avg_us={} (batched regions)",terrain_ring_read,terrain_ring_lost,terrain_stats_batches,terrain_stats_received,terrain_stats_accepted,
            terrain_stats_read_us/terrain_stats_batches.max(1),terrain_stats_mesh_us/terrain_stats_batches.max(1));
          terrain_stats_received=0;terrain_stats_accepted=0;
          terrain_stats_read_us=0;terrain_stats_mesh_us=0;terrain_stats_batches=0;
        }
        last_havok_diagnostic=Instant::now();
      }
      last_terrain=Instant::now();
    }else if !armed && ever_havok && !static_active{
      // Do not discard every real collider on one lost 1-FPS frame / BDP3
      // handshake. Preserve it for 3 seconds; still clear on disconnect.
      let since=terrain_disarmed_at.get_or_insert_with(Instant::now);
      if since.elapsed()>=Duration::from_secs(3){
        let mut engine=state.lock().map_err(|_|other("bridge mutex poisoned"))?;
        terrain.clear(&mut engine.mem);
        ever_havok=false;
        terrain_disarmed_at=None;
      }
    }
    if last_report.elapsed()>=Duration::from_secs(5){
      let status=remote.read(addr+196,8).unwrap_or_default();
      let (fps,hidden)=if status.len()==8{
        (u32::from_le_bytes(status[0..4].try_into().unwrap()),
         u32::from_le_bytes(status[4..8].try_into().unwrap()))
      }else{(0,0)};
      let mean=if latency_count>0{latency_sum/latency_count as u128}else{0};
      println!("[RUST_LINK] LinkTick={} FPS_MATRIX_FRAMES={} LINK_HIDDEN={} active={} BDP3_rtt_us={} samples={} still_refresh=250ms",
         last_guest_tick,fps,hidden,armed,mean,latency_count);
      latency_sum=0;latency_count=0;
      last_report=Instant::now();
    }
    // The stream uses the most recent Minecraft pose, never a queue of
    // past frames. 2ms poll is low overhead; GDB requests self-throttle.
    thread::sleep(Duration::from_millis(if armed{1}else{30}));
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