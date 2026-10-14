use crate::shared::{self,SharedMap,SKY,MC,DIRECT};
use serde_json::{Value,json};

const ACTIVE:u32=1;
const FPS:u32=2;
const FLY:u32=4;
const INPUTS:u32=0x20000;
const FPS_GUI:u32=0x10000;
const MC_FLY:u32=1<<7;
const STALE:u64=1000;
// Keep test20 FPS freeze recovery: avoid repeated BDP disarm in 1-FPS stalls.
const MC_STALE:u64=6000;
const MAX_TELEPORT:f64=128.0;

#[derive(Clone,Copy)]
struct McPose{
 frame:u64,pos:[f64;3],yaw:f32,pitch:f32,flags:u32,eye:f32,fov:f32,
 // Actual Minecraft render eye for this frame; F5 can move it off-player.
 // Read only after the Fabric producer sets CAM_VALID.
 camera:Option<([f64;3],u32)>
}
const CAM_VALID:u32=0x40000;

/// Camera math follows SkyCraft's Game.cpp:
/// one common render eye, yaw+180 and inverted pitch in F5 front,
/// and exactly the observed Minecraft camera distance in F5 rear.
/// No smoothing or interpolated guesses across unrelated frames.
fn view_for(m:McPose,botw_feet:[f64;3])->([f64;3],[f64;3],f64,f64){
 let mut yaw=m.yaw as f64;
 let mut pitch=m.pitch as f64;
 let camera=if let Some((eye,mode))=m.camera {
   if mode==2 {yaw+=180.0; pitch=-pitch;}
   [
     botw_feet[0]+(eye[0]-m.pos[0]),
     botw_feet[1]+(eye[1]-m.pos[1]),
     botw_feet[2]+(eye[2]-m.pos[2]),
   ]
 }else {
   let h=if (0.05..=64.0).contains(&m.eye){m.eye as f64}else{1.72};
   [botw_feet[0],botw_feet[1]+h,botw_feet[2]]
 };
 let (sy,cy)=yaw.to_radians().sin_cos();
 let (sp,cp)=pitch.to_radians().sin_cos();
 let forward=[-sy*cp,-sp,cy*cp];
 (camera,forward,yaw,pitch)
}
fn finite(v:f64)->bool{v.is_finite() && v.abs()<100000.0}

pub struct Engine{
 pub mem:SharedMap,
 game_stamp:Option<u64>,game_seq:u32,last_world:Option<u32>,teleport_seq:u32,
 bdp_seq:u32,mc_anchor:Option<[f64;3]>,botw_anchor:Option<[f64;3]>,
 last_mc:Option<McPose>,last_status:u64
}
impl Engine{
 pub fn new()->std::io::Result<Self>{
  Ok(Self{mem:SharedMap::create()?,game_stamp:None,game_seq:0,
    last_world:None,teleport_seq:0,bdp_seq:0,mc_anchor:None,
    botw_anchor:None,last_mc:None,last_status:0})
 }
 fn mc(&self,now:u64)->Option<McPose>{
  let beat=self.mem.u64(24);
  if beat==0 || now<beat || now-beat>MC_STALE{return None}
  for _ in 0..5 {
   let seq=self.mem.u32(MC);
   if seq&1!=0 {continue}
   let flags=self.mem.u32(MC+4);
   let pos=[self.mem.f64(MC+8),self.mem.f64(MC+16),self.mem.f64(MC+24)];
   let yaw=self.mem.f32(MC+32);
   let pitch=self.mem.f32(MC+36);
   let eye=self.mem.f32(MC+40);
   let fov=self.mem.f32(MC+64); // McState FOV relative offset 0x40
   let frame=self.mem.u64(MC+56);
   let camera=if flags&CAM_VALID!=0 {
     let eye=[
       self.mem.f64(MC+0x50),
       self.mem.f64(MC+0x58),
       self.mem.f64(MC+0x60),
     ];
     let mode=self.mem.u32(MC+0xC0);
     // Reject broken/stale/out-of-range camera telemetry rather than
     // snapping Zelda to a bogus position. Minecraft's normal F5 <= 12m.
     let dist2=(0..3).map(|i|(eye[i]-pos[i]).powi(2)).sum::<f64>();
     if mode<=2 && eye.iter().all(|v|finite(*v)) &&
          dist2.is_finite() && dist2<=1024.0 {
       Some((eye,mode))
     }else {None}
   }else {None};
   if seq==self.mem.u32(MC) && frame!=0
      && pos.iter().all(|x|finite(*x)) && finite(yaw as f64)
      && finite(pitch as f64) && finite(eye as f64) && finite(fov as f64){
    return Some(McPose{frame,pos,yaw,pitch,flags,eye,fov,camera});
   }
  }
  None
 }
 fn game(&self,now:u64)->Option<[f64;3]>{
  let beat=self.mem.u64(16);
  if beat==0 || now<beat || now-beat>STALE{return None}
  for _ in 0..5{
   let seq=self.mem.u32(SKY);
   if seq&1!=0{continue}
   let flags=self.mem.u32(SKY+4);
   let pos=[self.mem.f64(SKY+16),self.mem.f64(SKY+24),self.mem.f64(SKY+32)];
   if seq==self.mem.u32(SKY) && flags&1!=0
       && pos!=[0.;3] && pos.iter().all(|x|finite(*x)){
    return Some(pos)
   }
  }
  None
 }
 /// Read-only pose/anchor snapshot for collision streaming. Incomplete or
 /// stale sessions cannot publish fake ground, and Minecraft is never moved.
 pub fn collision_frame(&self)->Option<([f64;3],[f64;3],[f64;3])>{
  let now=shared::clock();
  let mc=self.mc(now)?;
  if mc.flags&(ACTIVE|INPUTS)!=(ACTIVE|INPUTS){return None}
  self.game(now)?;
  Some((mc.pos,self.mc_anchor?,self.botw_anchor?))
 }
 fn reset_anchor(&mut self){
  self.mc_anchor=None;self.botw_anchor=None;self.last_mc=None;
 }
 pub fn tick(&mut self){
  let now=shared::clock();
  let alive=self.game_stamp.is_some_and(|stamp|now>=stamp && now-stamp<STALE);
  // Follow the Python host behavior exactly: no fabricated BOTW pose.
  self.mem.u64_set(16,if alive{now}else{0});
  self.mem.u32_set(SKY+4,if alive{1}else{0});

  let mc=self.mc(now);let game=self.game(now);
  let mut out=[0u8;112];
  self.bdp_seq=self.bdp_seq.wrapping_add(2)&!1;
  out[0..4].copy_from_slice(&self.bdp_seq.to_le_bytes());
  out[4..8].copy_from_slice(&0x31504442u32.to_le_bytes());
  out[8..12].copy_from_slice(&1u32.to_le_bytes());
  out[24..32].copy_from_slice(&now.to_le_bytes());
  let mut enabled=false;
  if let Some(m)=mc{
   if m.flags&INPUTS==0{
    self.reset_anchor();
   }else // Third Rust gameplay window holds focus; Minecraft client FPS GUI may be off.
   if (m.flags&(ACTIVE|INPUTS))==(ACTIVE|INPUTS){
    if let Some(p)=game{
     if self.mc_anchor.is_none(){
      self.mc_anchor=Some(m.pos);self.botw_anchor=Some(p);
     }
     let teleport=self.last_mc.is_some_and(|old|m.frame!=old.frame &&
       (0..3).map(|i|(m.pos[i]-old.pos[i]).powi(2)).sum::<f64>().sqrt()>MAX_TELEPORT);
     if teleport{self.reset_anchor();}
     else if let (Some(ma),Some(ga))=(self.mc_anchor,self.botw_anchor){
      self.last_mc=Some(m);
      let pos=[ga[0]+m.pos[0]-ma[0],ga[1]+m.pos[1]-ma[1],ga[2]+m.pos[2]-ma[2]];
      let (eye,forward,render_yaw,render_pitch)=view_for(m,pos);
      // The player stays at the same feet position. ONLY Zelda's real
      // render camera follows Minecraft's camera in F5 and first person.
      let vals=[pos[0],pos[1],pos[2],eye[0],eye[1],eye[2],
        forward[0],forward[1],forward[2],render_yaw,render_pitch,
        ma[0],ma[1],ma[2],ga[0],ga[1],ga[2],
        if (30.0..=130.0).contains(&m.fov){m.fov as f64}else{70.0}]; // Pose.reserved FOV
      if vals.iter().all(|v|finite(*v)){
       enabled=true;
       // Explicitly authorize the native WXLM actuator only while MC is ready.
       let flags=ACTIVE|FPS|0x10|if m.flags&MC_FLY!=0{FLY}else{0};
       out[12..16].copy_from_slice(&flags.to_le_bytes());
       out[16..24].copy_from_slice(&m.frame.to_le_bytes());
       for (i,v) in vals.iter().enumerate(){
        out[32+i*4..36+i*4].copy_from_slice(&(*v as f32).to_le_bytes());
       }
      }
     }
    }
   }
  }
  // One writer, seqlock commit; the guest transport reads this exact 112B.
  self.mem.sequence_begin(DIRECT,self.bdp_seq);
  self.mem.write(DIRECT+4,&out[4..]);
  self.mem.sequence_end(DIRECT,self.bdp_seq);
  if now-self.last_status>=4000{
   println!("[RUST_BRIDGE] BDP1 {} | Minecraft={} LinkTelemetry={}",
     if enabled{"armed"}else{"disarmed"},mc.is_some(),game.is_some());
   self.last_status=now;
  }
 }
 pub fn command(&mut self,v:Value)->Value{
  match v.get("type").and_then(Value::as_str){
   Some("pose")=>{
    let mut xyz=[0f64;5];
    for (i,name) in ["x","y","z","yaw","pitch"].iter().enumerate(){
     let Some(n)=v.get(name).and_then(Value::as_f64) else{return json!({"error":format!("missing {name}")});};
     if !finite(n){return json!({"error":format!("invalid {name}")});}
     xyz[i]=n;
    }
    let world=v.get("world").and_then(Value::as_u64).unwrap_or(1);
    if world>u32::MAX as u64{return json!({"error":"invalid world"})}
    if self.last_world!=Some(world as u32){
     self.teleport_seq=self.teleport_seq.wrapping_add(1);
     self.last_world=Some(world as u32);
    }
    self.game_seq=self.game_seq.wrapping_add(2)&!1;
    self.mem.sequence_begin(SKY,self.game_seq);
    self.mem.u32_set(SKY+4,1);
    self.mem.u32_set(SKY+8,world as u32);
    self.mem.u32_set(SKY+12,self.teleport_seq);
    for i in 0..3{self.mem.f64_set(SKY+16+8*i,xyz[i]);}
    self.mem.f32_set(SKY+40,xyz[3] as f32);
    self.mem.f32_set(SKY+44,xyz[4] as f32);
    self.mem.u32_set(SKY+48,self.teleport_seq);
    self.mem.u32_set(SKY+52,1280);
    self.mem.u32_set(SKY+56,720);
    self.mem.f32_set(SKY+60,12.0);
    self.mem.sequence_end(SKY,self.game_seq);
    self.game_stamp=Some(shared::clock());
    json!({"ok":true,"minecraft":self.status()})
   }
   Some("minecraft")=>json!({"ok":true,"minecraft":self.status()}),
   Some("input")=>json!({"error":"Input ring has one writer: Rust compositor (not TCP bridge)"}),
   _=>json!({"error":"unknown bridge message type"})
  }
 }
 pub fn status(&self)->Value{
  let s=self.mem.u32(MC);
  let flags=self.mem.u32(MC+4);
  let x=self.mem.f64(MC+8);let y=self.mem.f64(MC+16);let z=self.mem.f64(MC+24);
  let yaw=self.mem.f32(MC+32);let pitch=self.mem.f32(MC+36);
  let frame=self.mem.u64(MC+56);
  if s&1!=0||s!=self.mem.u32(MC){return json!({"error":"Minecraft state being updated"})}
  json!({"seq":s,"flags":flags,"in_world":flags&ACTIVE!=0,
         "x":x,"y":y,"z":z,"yaw":yaw,"pitch":pitch,"frame":frame})
 }
}
#[cfg(test)]
mod camera_math_tests {
 use super::*;
 fn pose(camera:Option<([f64;3],u32)>)->McPose{
   McPose{frame:1,pos:[10.,20.,30.],yaw:90.,pitch:30.,
     flags:ACTIVE|INPUTS|CAM_VALID,eye:1.62,fov:70.,camera}
 }
 fn near(a:f64,b:f64){assert!((a-b).abs()<1e-6,"{a} != {b}");}
 #[test]fn actual_first_person_eye_not_scaled(){
  let (eye,_,_,_)=view_for(pose(Some(([10.,21.62,30.],0))),[100.,200.,300.]);
  assert_eq!(eye,[100.,201.62,300.]);
 }
 #[test]fn f5_rear_preserves_actual_camera_offset(){
  let (eye,forward,yaw,pitch)=view_for(
    pose(Some(([13.46,23.62,30.],1))),[100.,200.,300.]);
  near(eye[0],103.46);near(eye[1],203.62);near(eye[2],300.);
  near(yaw,90.);near(pitch,30.);
  assert!(forward[0] < -0.8);
 }
 #[test]fn f5_front_reverses_yaw_and_pitch_like_skycraft(){
  let (_,forward,yaw,pitch)=view_for(
    pose(Some(([6.54,23.62,30.],2))),[100.,200.,300.]);
  near(yaw,270.);near(pitch,-30.);
  assert!(forward[0]>0.8);
 }
 #[test]fn missing_camera_telemetry_falls_back_safely(){
  let (eye,_,_,_)=view_for(pose(None),[100.,200.,300.]);
  near(eye[0],100.);near(eye[1],201.62);near(eye[2],300.);
 }
}
