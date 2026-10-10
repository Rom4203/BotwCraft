//! Isolated BotwCraft terrain mesh relay.
//!
//! Reads actual *Havok ray hits* sampled by the native Zelda guest. Generates
//! local Minecraft collision triangles using the existing SkyCraft v11
//! collision ring. No player teleport, controller emulation or camera changes.
//! Non-spectator filtering is performed by BotwTerrainCollisionBridge.java.
use std::{collections::BTreeMap,sync::atomic::{fence,Ordering}};
use crate::shared::SharedMap;
const CR:usize=0x20000;
const CR_HEAD:usize=CR;
const CR_TAIL:usize=CR+64;
const CR_DATA:usize=CR+128;
const CAP:usize=33554304;
const TRI_FLAGS:u32=8; // Real terrain, no ghost.
const MAX_EDGE_HEIGHT:f32=1.65;
const SPACING:f32=2.75;
const RECORD_MAX:usize=4096;

fn f32at(bytes:&[u8],off:usize)->Option<f32>{
  let v=f32::from_le_bytes(bytes.get(off..off+4)?.try_into().ok()?);
  if v.is_finite() && v.abs()<100000. {Some(v)}else{None}
}
fn i32_floor8(x:f32)->i32 {(x.floor() as i32).div_euclid(8)*8}
fn push(m:&mut SharedMap,ty:u32,payload:&[u8])->bool{
 let record=((8+payload.len()+7)/8)*8;
 if record>RECORD_MAX || record>=CAP{return false}
 let head=m.u64(CR_HEAD);
 let tail=m.u64(CR_TAIL);
 if head<tail || head-tail>CAP as u64 || head-tail+(record+8) as u64>=CAP as u64{return false}
 let off=head as usize%CAP;
 let mut next=head;
 if off+record>CAP {
    // Padding marks wrap. Consumer sees command 0 and fast-forwards tail.
    m.u32_set(CR_DATA+off,0);
    m.u32_set(CR_DATA+off+4,0);
    next+=(CAP-off) as u64;
 }
 let at=CR_DATA+(next as usize%CAP);
 m.u32_set(at,ty);
 m.u32_set(at+4,payload.len() as u32);
 m.write(at+8,payload);
 fence(Ordering::Release);
 m.u64_set(CR_HEAD,next+record as u64);
 true
}
#[derive(Default)]
pub struct TerrainRelay{
 last_seq:u32,
 epoch:u32,
 logged:bool,
}
impl TerrainRelay{
 pub fn ingest(&mut self,guest:&[u8],pose:&[u8],map:&mut SharedMap)->bool{
   // Guest writes odd seq during update then even seq to commit. 56 bytes:
   // [seq:4][mask:4][center_xyz:12][heights:9*4]
   if guest.len()!=56 || pose.len()<100{return false}
   let seq=u32::from_le_bytes(guest[0..4].try_into().unwrap());
   let valid=u32::from_le_bytes(guest[4..8].try_into().unwrap());
   if seq==0 || seq&1!=0 || seq==self.last_seq{return false}
   let mut center=[0f32;3];
   let mut mc_origin=[0f32;3];
   let mut zelda_origin=[0f32;3];
   let mut height=[0f32;9];
   for a in 0..3{
     let Some(c)=f32at(guest,8+a*4)else{return false};
     let Some(m)=f32at(pose,76+a*4)else{return false};
     let Some(z)=f32at(pose,88+a*4)else{return false};
     center[a]=c;mc_origin[a]=m;zelda_origin[a]=z;
   }
   for i in 0..9{let Some(h)=f32at(guest,20+i*4)else{return false};height[i]=h;}
   let mapped=[center[0]-zelda_origin[0]+mc_origin[0],
               center[1]-zelda_origin[1]+mc_origin[1],
               center[2]-zelda_origin[2]+mc_origin[2]];
   if mapped.iter().any(|x| !x.is_finite()) {return false}
   let mut vertices=[[0f32;3];9];
   for i in 0..9 {
     let ix=i%3;let iz=i/3;
     vertices[i]=[
       mapped[0]+(ix as f32-1.)*SPACING,
       height[i]-zelda_origin[1]+mc_origin[1],
       mapped[2]+(iz as f32-1.)*SPACING
     ];
   }
   let mut groups:BTreeMap<(i32,i32,i32),Vec<[[f32;3];3]>>=BTreeMap::new();
   for z in 0..2{
     for x in 0..2{
       let a=z*3+x;let b=a+1;let c=a+3;let d=c+1;
       for indices in [[a,c,b],[b,c,d]] {
         if indices.iter().any(|i|valid&(1u32<<i)==0){continue}
         let [p,q,r]=[vertices[indices[0]],vertices[indices[1]],vertices[indices[2]]];
         if [p[1],q[1],r[1]].iter().any(|h|*h< -100000.) {continue}
         let high=p[1].max(q[1]).max(r[1]);
         let low=p[1].min(q[1]).min(r[1]);
         // Prevent phantom bridges at steep cliffs and over deep holes.
         if high-low>MAX_EDGE_HEIGHT {continue}
         // Calculate upward orientation (x,z projected) to satisfy SkyTri.
         let up=(q[2]-p[2])*(r[0]-p[0])-(q[0]-p[0])*(r[2]-p[2]);
         if up<0.001 {continue}
         let mid=[(p[0]+q[0]+r[0])/3.,(p[1]+q[1]+r[1])/3.,(p[2]+q[2]+r[2])/3.];
         groups.entry((i32_floor8(mid[0]),i32_floor8(mid[1]),i32_floor8(mid[2])))
               .or_default().push([p,q,r]);
       }
     }
   }
   self.epoch=self.epoch.wrapping_add(1);
   if self.epoch==0{self.epoch=1}
   let epoch=self.epoch;
   // Atomically begin each patch as COL_CLEAR then add real ground triangles
   // to the standard SkyCraft collision ring, not simulated teleporting.
   if !push(map,1,&epoch.to_le_bytes()){return false}
   for ((x,y,z),tris) in groups{
     let mut payload=Vec::with_capacity(32+40*tris.len());
     for n in [x,y,z,0,0,0]{payload.extend_from_slice(&n.to_le_bytes());}
     payload.extend_from_slice(&epoch.to_le_bytes());
     payload.extend_from_slice(&(tris.len() as i32).to_le_bytes());
     for t in tris {
       for v in t {for f in v {payload.extend_from_slice(&f.to_le_bytes());}}
       payload.extend_from_slice(&TRI_FLAGS.to_le_bytes());
     }
     if !push(map,3,&payload){return false}
   }
   self.last_seq=seq;
   if !self.logged {
     println!("[RUST_LINK] Native Havok terrain samples delivered to Minecraft collision ring");
     self.logged=true;
   }
   true
 }
 pub fn clear(&mut self,map:&mut SharedMap){
   self.epoch=self.epoch.wrapping_add(1).max(1);
   push(map,1,&self.epoch.to_le_bytes());
 }
}
#[cfg(test)]
mod tests {
 use super::*;
 #[test]fn xz_ground_triangle_winding_is_up(){
   let p=[0.,0.,0.];let q=[0.,0.,1.];let r=[1.,0.,0.];
   let up=(q[2]-p[2])*(r[0]-p[0])-(q[0]-p[0])*(r[2]-p[2]);
   assert!(up>0.);
 }
 #[test]fn origin_floor_handles_negative_coordinates(){
   assert_eq!(i32_floor8(-0.1),-8);
   assert_eq!(i32_floor8(7.9),0);
   assert_eq!(i32_floor8(8.1),8);
 }
}
