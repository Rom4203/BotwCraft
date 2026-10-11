//! BOTW native Havok raycast samples -> SkyCraft v11 Minecraft collisions.
//!
//! The guest (WiiXLaunch) owns physics queries. This relay NEVER fabricates
//! ground, teleports Steve, calls Zelda through a virtual controller, or
//! injects a fake Minecraft server. The *same* original Fabric JAR receives
//! smooth client triangles and 1/8-block server-side voxel collision solids.
//! The 3x3 grid covers a local patch around Link; remote objects and walls
//! beyond ground raycasts are NOT represented yet.
use std::collections::{BTreeMap, BTreeSet};
use crate::shared::SharedMap;

const SIZE:usize=56;
const STEP:f32=2.75;
const MAX_HEIGHT_EDGE:f32=2.4;
const REGION:i32=8;
const TRI_TERRAIN:u32=8;
const COL_CLEAR:u32=1;
const COL_REGION:u32=2;
const COL_TRIS:u32=3;

#[derive(Clone,Copy,Debug,PartialEq,Eq,PartialOrd,Ord)]
struct Region(i32,i32,i32);
impl Region {
 fn from_xyz(x:f32,y:f32,z:f32)->Self{
   Self((x.floor() as i32).div_euclid(REGION),
        (y.floor() as i32).div_euclid(REGION),
        (z.floor() as i32).div_euclid(REGION))
 }
 fn header(&self,count:usize)->Vec<u8>{
  let mut b=Vec::with_capacity(32);
  for x in [self.0*REGION,self.1*REGION,self.2*REGION,
            self.0*REGION+7,self.1*REGION+7,self.2*REGION+7] {b.extend_from_slice(&x.to_le_bytes())}
  b.extend_from_slice(&1i32.to_le_bytes()); // epoch 1 per Rust bridge
  b.extend_from_slice(&(count as u32).to_le_bytes());b
 }
}
fn at(b:&[u8],i:usize)->Option<f32>{
 let x=f32::from_le_bytes(b.get(i..i+4)?.try_into().ok()?);
 (x.is_finite()&&x.abs()<100000.).then_some(x)
}
fn packet(kind:u32,payload:&[u8])->Vec<u8>{
 let mut b=Vec::with_capacity((payload.len()+15)&!7);
 b.extend_from_slice(&kind.to_le_bytes());b.extend_from_slice(&(payload.len() as u32).to_le_bytes());
 b.extend_from_slice(payload);b.resize((b.len()+7)&!7,0);b
}
fn clear()->Vec<u8>{packet(COL_CLEAR,&1u32.to_le_bytes())}

#[derive(Clone,Copy,Debug)]
struct Triangle{v:[[f32;3];3]}
impl Triangle{
 fn bounds(&self)->([f32;3],[f32;3]){
  let mut a=[f32::INFINITY;3];let mut b=[f32::NEG_INFINITY;3];
  for p in &self.v {for i in 0..3{a[i]=a[i].min(p[i]);b[i]=b[i].max(p[i]);}}
  (a,b)
 }
 fn height(&self,x:f32,z:f32)->Option<f32>{
  let [a,b,c]=self.v;
  let cross=|p:[f32;3],q:[f32;3]|(p[0]-x)*(q[2]-z)-(p[2]-z)*(q[0]-x);
  let s=[cross(a,b),cross(b,c),cross(c,a)];
  if s.iter().any(|v|*v>1e-5) && s.iter().any(|v|*v< -1e-5) {return None}
  let d=(b[0]-a[0])*(c[2]-a[2])-(c[0]-a[0])*(b[2]-a[2]);
  if d.abs()<1e-7 {return None}
  let u=((x-a[0])*(c[2]-a[2])-(z-a[2])*(c[0]-a[0]))/d;
  let v=((z-a[2])*(b[0]-a[0])-(x-a[0])*(b[2]-a[2]))/d;
  Some(a[1]+u*(b[1]-a[1])+v*(c[1]-a[1]))
 }
}
fn surface(tris:&[Triangle],x:f32,z:f32)->Option<f32>{
 tris.iter().filter_map(|t|t.height(x,z)).max_by(|a,b|a.total_cmp(b))
}
fn triangles(guest:&[u8],pose:&[u8])->Option<Vec<Triangle>>{
 if guest.len()!=SIZE || pose.len()<100{return None}
 let mask=u32::from_le_bytes(guest[4..8].try_into().ok()?);
 if mask&!0x1ff!=0{return None}
 let center=[at(guest,8)?,at(guest,12)?,at(guest,16)?];
 let mc=[at(pose,76)?,at(pose,80)?,at(pose,84)?];
 let zelda=[at(pose,88)?,at(pose,92)?,at(pose,96)?];
 let desired=[at(pose,32)?,at(pose,36)?,at(pose,40)?];
 // A previous session's mailbox or a wrong NX150 build must NEVER
 // corrupt Steve's physics with unrelated memory interpreted as heights.
 if (0..3).map(|i|(center[i]-desired[i]).powi(2)).sum::<f32>()>400. {return None}
 let mut points=[[0f32;3];9];
 for i in 0..9{
  let h=at(guest,20+i*4)?;
  points[i]=[
   center[0]-zelda[0]+mc[0]+(i%3) as f32*STEP-STEP,
   h-zelda[1]+mc[1],
   center[2]-zelda[2]+mc[2]+(i/3) as f32*STEP-STEP,
  ];
 }
 let mut result=Vec::new();
 for z in 0..2 {for x in 0..2 {
  let a=z*3+x;let b=a+1;let c=a+3;let d=c+1;
  for vertices in [[a,c,b],[b,c,d]]{
   if vertices.iter().any(|i|mask&(1<<i)==0){continue}
   let v=[points[vertices[0]],points[vertices[1]],points[vertices[2]]];
   let high=v.iter().map(|p|p[1]).fold(f32::NEG_INFINITY,f32::max);
   let low=v.iter().map(|p|p[1]).fold(f32::INFINITY,f32::min);
   // A missing surface or cliff is not an invisible bridge.
   if high-low>MAX_HEIGHT_EDGE {continue}
   result.push(Triangle{v});
  }
 }}
 Some(result)
}

// Minecraft's triangle reader indexes by 8-block REGION rather than
// by triangle bounds; duplicate across every overlapped region so walking
// across region boundaries never makes a slope disappear.
fn tri_regions(tris:&[Triangle])->BTreeMap<Region,Vec<Triangle>>{
 let mut out=BTreeMap::<Region,Vec<Triangle>>::new();
 for tri in tris {
  let (a,b)=tri.bounds();
  let start=Region::from_xyz(a[0],a[1],a[2]);let end=Region::from_xyz(b[0],b[1],b[2]);
  for x in start.0..=end.0 {for y in start.1..=end.1 {for z in start.2..=end.2 {
   out.entry(Region(x,y,z)).or_default().push(*tri);
  }}}
 }
 out
}
fn tri_message(region:Region,tris:&[Triangle])->Vec<u8>{
 let mut data=region.header(tris.len());
 for t in tris {for v in t.v {for f in v {data.extend_from_slice(&f.to_le_bytes());}}
  data.extend_from_slice(&TRI_TERRAIN.to_le_bytes());
 }
 packet(COL_TRIS,&data)
}

// SkyCraft expects COL_REGION blocks encoded as coordinates + reserved
// + eight u64 8x8 bit-plane voxels (Y layers). The server simulates Steve
// against these, independently of the client triangle pass.
fn voxel_regions(tris:&[Triangle])->BTreeMap<Region,Vec<(i32,i32,i32,[u64;8])>>{
 let mut out=BTreeMap::<Region,Vec<(i32,i32,i32,[u64;8])>>::new();
 if tris.is_empty(){return out}
 let mut low=[f32::INFINITY;3];let mut high=[f32::NEG_INFINITY;3];
 for t in tris {let (a,b)=t.bounds();for i in 0..3{low[i]=low[i].min(a[i]);high[i]=high[i].max(b[i]);}}
 let x0=low[0].floor() as i32;let x1=high[0].ceil() as i32;
 let z0=low[2].floor() as i32;let z1=high[2].ceil() as i32;
 let y0=(low[1]-2.).floor() as i32;let y1=high[1].ceil() as i32;
 for bx in x0..x1 {for bz in z0..z1 {for by in y0..=y1 {
  let mut bits=[0u64;8];
  for vz in 0..8 {for vx in 0..8 {
   let xx=bx as f32+(vx as f32+0.5)/8.;
   let zz=bz as f32+(vz as f32+0.5)/8.;
   let Some(h)=surface(tris,xx,zz)else{continue};
   for vy in 0..8 {
    let yy=by as f32+(vy as f32+0.5)/8.;
    if yy<h && yy>=h-2.0 {bits[vy]|=1u64<<(vx+8*vz);}
   }
  }}
  if bits.iter().any(|v|*v!=0){
   let region=Region::from_xyz(bx as f32,by as f32,bz as f32);
   out.entry(region).or_default().push((bx,by,bz,bits));
  }
 }}}
 out
}
fn voxel_message(region:Region,blocks:&[(i32,i32,i32,[u64;8])])->Vec<u8>{
 let mut data=region.header(blocks.len());
 for (x,y,z,bits) in blocks {
  for n in [*x,*y,*z,0] {data.extend_from_slice(&n.to_le_bytes());}
  for layer in bits {data.extend_from_slice(&layer.to_le_bytes());}
 }
 packet(COL_REGION,&data)
}

#[derive(Default)]
pub struct TerrainRelay {
 seq:u32,
 tri_regions:BTreeSet<Region>,
 voxel_regions:BTreeSet<Region>,
 started:bool,
 reports:u32,
}
impl TerrainRelay {
 pub fn ingest(&mut self,guest:&[u8],pose:&[u8],map:&mut SharedMap)->bool{
  if guest.len()!=SIZE || pose.len()<100 {return false}
  let seq=u32::from_le_bytes(guest[0..4].try_into().unwrap());
  if seq==0 || seq&1==1 || seq==self.seq {return false}
  let Some(tris)=triangles(guest,pose) else {return false};
  let t=tri_regions(&tris);let vox=voxel_regions(&tris);
  let new_t:BTreeSet<Region>=t.keys().copied().collect();
  let new_v:BTreeSet<Region>=vox.keys().copied().collect();
  let mut packets=Vec::new();
  if !self.started {packets.push(clear());}
  for r in self.tri_regions.difference(&new_t){packets.push(tri_message(*r,&[]))}
  for r in self.voxel_regions.difference(&new_v){packets.push(voxel_message(*r,&[]))}
  for (r,v) in &t {packets.push(tri_message(*r,v));}
  for (r,v) in &vox{packets.push(voxel_message(*r,v));}
  for packet in &packets{if !map.collision_write(packet){
   eprintln!("[TERRAIN] SkyCraft collision ring full; frame will retry ({} packets)",packets.len());
   return false
  }}
  self.started=true;
  self.seq=seq;self.tri_regions=new_t;self.voxel_regions=new_v;
  self.reports+=1;
  if self.reports==1 || self.reports%40==0 {
   println!("[TERRAIN] Havok surface seq={} triangles={} solid_blocks={} MC_regions={} (no teleport)",
    seq,tris.len(),vox.values().map(Vec::len).sum::<usize>(),vox.len());
  }
  true
 }
 pub fn clear(&mut self,map:&mut SharedMap){
  if self.started {let _=map.collision_write(&clear());}
  self.seq=0;self.tri_regions.clear();self.voxel_regions.clear();self.started=false;
 }
}

#[cfg(test)]
mod tests{
 use super::*;
 fn sample()->([u8;56],[u8;112]){
  let mut g=[0u8;56];let mut p=[0u8;112];
  g[0..4].copy_from_slice(&2u32.to_le_bytes());
  g[4..8].copy_from_slice(&511u32.to_le_bytes());
  for i in 0..9{g[20+i*4..24+i*4].copy_from_slice(&1f32.to_le_bytes())}
  (g,p)
 }
 #[test]fn flat_havok_grid_generates_eight_tris(){let (g,p)=sample();let tris=triangles(&g,&p).unwrap();assert_eq!(tris.len(),8);assert!((surface(&tris,0.,0.).unwrap()-1.).abs()<0.001)}
 #[test]fn server_solid_blocks_and_client_triangles(){let (g,p)=sample();let tris=triangles(&g,&p).unwrap();let solids=voxel_regions(&tris);assert!(solids.values().map(Vec::len).sum::<usize>()>20);assert_eq!(u32::from_le_bytes(tri_message(Region(0,0,0),&tris)[..4].try_into().unwrap()),COL_TRIS);assert_eq!(u32::from_le_bytes(voxel_message(Region(0,0,0),&[])[..4].try_into().unwrap()),COL_REGION)}
 #[test]fn sample_mask_rejects_unknown_bits_and_cliff_bridge(){let(mut g,p)=sample();g[4..8].copy_from_slice(&0x8000u32.to_le_bytes());assert!(triangles(&g,&p).is_none());g[4..8].copy_from_slice(&511u32.to_le_bytes());g[20..24].copy_from_slice(&20f32.to_le_bytes());assert!(triangles(&g,&p).unwrap().len()<8)}
 #[test]fn guest_center_is_checked_against_bdp3_pose(){let(mut g,p)=sample();g[8..12].copy_from_slice(&400f32.to_le_bytes());assert!(triangles(&g,&p).is_none());}
 #[test]fn packet_header_is_skymod_v11_compatible(){let(guest,p)=sample();let t=triangles(&guest,&p).unwrap();let r=Region(0,0,0);let b=tri_message(r,&t);assert_eq!(u32::from_le_bytes(b[0..4].try_into().unwrap()),3);assert_eq!(u32::from_le_bytes(b[8+28..8+32].try_into().unwrap()),8);assert_eq!(u32::from_le_bytes(b[4..8].try_into().unwrap()),(32+8*40) as u32);}
}