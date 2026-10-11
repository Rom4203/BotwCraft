//! BOTW native Havok raycast samples -> SkyCraft v11 Minecraft collisions.
//!
//! Zelda Havok samples are cached as persistent 1/8-block Minecraft VoxelShape
//! tiles for BOTH the client and integrated server (no movement rollback).
//! No teleport, simulated ground, controller, proxy server or Python collider.
use std::collections::{BTreeMap,BTreeSet};
use crate::shared::SharedMap;

const SIZE:usize=56;
const STEP:f32=0.68;
const MAX_HEIGHT_EDGE:f32=3.0;
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
 // Host can sprint 15-30 m while Havok resolves a slow emulated ray grid.
 // The prior 20 m stale filter silently discarded precisely those results.
 // The rolling cache still rejects geometry farther than 36 m from Steve.
 if (0..3).map(|i|(center[i]-desired[i]).powi(2)).sum::<f32>()>1225. {return None}
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
 // Build sub-voxel Minecraft collision shapes from the real Havok triangles.
 // Only visit the block columns under each triangle, never the giant AABB
 // encompassing all cached samples (which caused lag on hills and cliffs).
 let mut result:BTreeMap<Region,BTreeMap<(i32,i32,i32),[u64;8]>>=BTreeMap::new();
 for tri in tris {
  let (low,high)=tri.bounds();
  for bx in low[0].floor() as i32..high[0].ceil() as i32 {
   for bz in low[2].floor() as i32..high[2].ceil() as i32 {
    for vz in 0..8 {for vx in 0..8 {
     let x=bx as f32+(vx as f32+0.5)/8.;
     let z=bz as f32+(vz as f32+0.5)/8.;
     let Some(h)=tri.height(x,z)else{continue};
     // Each tile is 1/8 Minecraft block. A floor is a SOLID VoxelShape
     // slab extending 0.75 blocks below the sampled Havok height.
     // This is physically resolved by vanilla Minecraft, not teleported.
     let y0=(h-0.75).floor() as i32;
     let y1=h.floor() as i32;
     for by in y0..=y1 {
      for vy in 0..8 {
       let y=by as f32+(vy as f32+0.5)/8.;
       if y>=h-0.75 && y<h {
        let region=Region::from_xyz(bx as f32,by as f32,bz as f32);
        let block=result.entry(region).or_default().entry((bx,by,bz)).or_insert([0u64;8]);
        block[vy]|=1u64<<(vx+8*vz);
       }
      }
     }
    }}
   }
  }
 }
 result.into_iter().map(|(region,blocks)|(region,blocks.into_iter()
  .map(|((x,y,z),bits)|(x,y,z,bits)).collect())).collect()
}

fn voxel_message(region:Region,blocks:&[(i32,i32,i32,[u64;8])])->Vec<u8>{
 let mut data=region.header(blocks.len());
 for (x,y,z,bits) in blocks {
  for n in [*x,*y,*z,0] {data.extend_from_slice(&n.to_le_bytes());}
  for layer in bits {data.extend_from_slice(&layer.to_le_bytes());}
 }
 packet(COL_REGION,&data)
}

// Fixed, world-aligned 1.36m tiles rather than moving the same 3x3 ray grid
// every time Steve moves. Each completed tile is transmitted only on change.
// Recompute only dirty 8-block Minecraft regions, NOT the entire 36m cache.
const CACHE_TILE:f32=1.36;
const CACHE_RADIUS:f32=24.0;
const CACHE_MAX:usize=384;
fn cache_key(center:[f32;3])->(i32,i32){
 ((center[0]/CACHE_TILE).round() as i32,(center[2]/CACHE_TILE).round() as i32)
}
struct Patch {
 seq:u32,
 triangles:Vec<Triangle>,
 tri_regions:BTreeMap<Region,Vec<Triangle>>,
 voxel_regions:BTreeMap<Region,Vec<(i32,i32,i32,[u64;8])>>,
}
impl Patch {
 fn new(seq:u32,triangles:Vec<Triangle>)->Self{
  let tri_regions=tri_regions(&triangles);
  let voxel_regions=voxel_regions(&triangles);
  Self{seq,triangles,tri_regions,voxel_regions}
 }
 fn regions(&self)->BTreeSet<Region>{
  self.tri_regions.keys().chain(self.voxel_regions.keys()).copied().collect()
 }
}
#[derive(Default)]
pub struct TerrainRelay {
 seq:u32,
 patches:BTreeMap<(i32,i32),Patch>,
 tri_packets:BTreeMap<Region,Vec<u8>>,
 voxel_packets:BTreeMap<Region,Vec<u8>>,
 started:bool,
 reports:u32,
 stats_updates:u32,
}
impl TerrainRelay {
 pub fn ingest(&mut self,guest:&[u8],pose:&[u8],map:&mut SharedMap)->bool{
  if guest.len()!=SIZE || pose.len()<100{return false}
  let seq=u32::from_le_bytes(guest[0..4].try_into().unwrap());
  if seq==0 || seq&1==1 || seq==self.seq{return false}
  let Some(tris)=triangles(guest,pose)else{return false};
  let mc=[at(pose,76).unwrap(),at(pose,80).unwrap(),at(pose,84).unwrap()];
  let zelda=[at(pose,88).unwrap(),at(pose,92).unwrap(),at(pose,96).unwrap()];
  let center=[at(guest,8).unwrap()-zelda[0]+mc[0],
              at(guest,12).unwrap()-zelda[1]+mc[1],
              at(guest,16).unwrap()-zelda[2]+mc[2]];
  let current=[at(pose,32).unwrap()-zelda[0]+mc[0],
               at(pose,36).unwrap()-zelda[1]+mc[1],
               at(pose,40).unwrap()-zelda[2]+mc[2]];
  let mut dirty=BTreeSet::new();
  if !tris.is_empty(){
   let key=cache_key(center);
   // Duplicate partial tile publications merge into the latest data.
   // Preserve a full known mesh rather than replacing it with fewer hits.
   let replace=self.patches.get(&key).is_none_or(|old|tris.len()>=old.triangles.len());
   if replace{
    let patch=Patch::new(seq,tris.clone());
    if let Some(old)=self.patches.insert(key,patch){dirty.extend(old.regions());}
    dirty.extend(self.patches.get(&key).unwrap().regions());
   }
  }
  let expired:Vec<_>=self.patches.iter().filter_map(|(key,_)|{
   let x=(key.0 as f32)*CACHE_TILE;
   let z=(key.1 as f32)*CACHE_TILE;
   ((x-current[0]).abs()>CACHE_RADIUS || (z-current[2]).abs()>CACHE_RADIUS).then_some(*key)
  }).collect();
  for key in expired {if let Some(old)=self.patches.remove(&key){dirty.extend(old.regions());}}
  while self.patches.len()>CACHE_MAX {
   let key=*self.patches.iter().min_by_key(|(_,p)|p.seq).unwrap().0;
   if let Some(old)=self.patches.remove(&key){dirty.extend(old.regions());}
  }
  let mut messages=Vec::new();
  if !self.started {
   messages.push(clear());
   for patch in self.patches.values(){dirty.extend(patch.regions());}
  }
  let mut solid_blocks=0usize;
  for region in &dirty{
   // Most updates touch one 8-block region, not hundreds of cached patches.
   let mut tris_region=Vec::new();
   let mut blocks:BTreeMap<(i32,i32,i32),[u64;8]>=BTreeMap::new();
   for patch in self.patches.values(){
    if let Some(part)=patch.tri_regions.get(region){tris_region.extend_from_slice(part);}
    if let Some(part)=patch.voxel_regions.get(region){
     for (x,y,z,bits) in part {
      let dest=blocks.entry((*x,*y,*z)).or_insert([0u64;8]);
      for i in 0..8{dest[i]|=bits[i]}
     }
    }
   }
   solid_blocks+=blocks.len();
   let tri=tri_message(*region,&tris_region);
   if self.tri_packets.get(region)!=Some(&tri){messages.push(tri.clone());}
   if tris_region.is_empty(){self.tri_packets.remove(region);}else{self.tri_packets.insert(*region,tri);}
   let vox:Vec<_>=blocks.into_iter().map(|((x,y,z),bits)|(x,y,z,bits)).collect();
   let msg=voxel_message(*region,&vox);
   if self.voxel_packets.get(region)!=Some(&msg){messages.push(msg.clone());}
   if vox.is_empty(){self.voxel_packets.remove(region);}else{self.voxel_packets.insert(*region,msg);}
  }
  // Avoid repeating unchanged blocks every 20-50ms and clogging the
  // Minecraft collision ring with redundant updates.
  for packet in &messages {
   if !map.collision_write(packet){
    eprintln!("[TERRAIN] collision ring saturated ({} messages); retry when consumer drains",messages.len());
    // Force a full refresh on next successful packet rather than pretending
    // an unaccepted mesh is already installed.
    self.started=false;self.tri_packets.clear();self.voxel_packets.clear();
    return false;
   }
  }
  self.seq=seq;self.started=true;
  self.reports=self.reports.wrapping_add(1);
  self.stats_updates+=messages.len() as u32;
  if self.reports==1 || self.reports%80==0 {
   let cached:usize=self.patches.values().map(|p|p.triangles.len()).sum();
   println!("[TERRAIN] FINE 0.68m grid seq={} new_tris={} cached_tiles={} cached_tris={} dirty_regions={} dirty_solid_blocks={} sent_packets={} (cached regions not rescanned)",
    seq,tris.len(),self.patches.len(),cached,dirty.len(),solid_blocks,self.stats_updates);
   self.stats_updates=0;
  }
  true
 }
 pub fn clear(&mut self,map:&mut SharedMap){
  if self.started {let _=map.collision_write(&clear());}
  self.seq=0;self.patches.clear();self.tri_packets.clear();self.voxel_packets.clear();self.started=false;
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
 #[test]fn server_solid_blocks_and_client_triangles(){let (g,p)=sample();let tris=triangles(&g,&p).unwrap();let solids=voxel_regions(&tris);assert!(solids.values().map(Vec::len).sum::<usize>()>=2);assert_eq!(u32::from_le_bytes(tri_message(Region(0,0,0),&tris)[..4].try_into().unwrap()),COL_TRIS);assert_eq!(u32::from_le_bytes(voxel_message(Region(0,0,0),&[])[..4].try_into().unwrap()),COL_REGION)}
 #[test]fn sample_mask_rejects_unknown_bits_and_cliff_bridge(){let(mut g,p)=sample();g[4..8].copy_from_slice(&0x8000u32.to_le_bytes());assert!(triangles(&g,&p).is_none());g[4..8].copy_from_slice(&511u32.to_le_bytes());g[20..24].copy_from_slice(&20f32.to_le_bytes());assert!(triangles(&g,&p).unwrap().len()<8)}
 #[test]fn guest_center_is_checked_against_bdp3_pose(){let(mut g,p)=sample();g[8..12].copy_from_slice(&400f32.to_le_bytes());assert!(triangles(&g,&p).is_none());}
 #[test]fn packet_header_is_skymod_v11_compatible(){let(guest,p)=sample();let t=triangles(&guest,&p).unwrap();let r=Region(0,0,0);let b=tri_message(r,&t);assert_eq!(u32::from_le_bytes(b[0..4].try_into().unwrap()),3);assert_eq!(u32::from_le_bytes(b[8+28..8+32].try_into().unwrap()),8);assert_eq!(u32::from_le_bytes(b[4..8].try_into().unwrap()),(32+8*40) as u32);}
}

#[cfg(test)]
mod coverage_tests {
 use super::*;
 #[test]
 fn adjacent_samples_do_not_replace_full_terrain_patch() {
  let a=cache_key([3.0,0.0,8.0]);
  let b=cache_key([4.5,0.0,8.0]);
  assert_ne!(a,b,"adjacent 1.36m tiles must not evict each other");
 }
 #[test]
 fn steep_cliff_does_not_generate_fabricated_floor_between_banks(){
  let left=Triangle{v:[[0.,0.,0.],[0.,0.,2.],[1.,0.,0.]]};
  let right=Triangle{v:[[3.,10.,0.],[3.,10.,2.],[4.,10.,0.]]};
  let solid=voxel_regions(&[left,right]);
  assert!(!solid.values().flat_map(|b|b.iter()).any(|(x,_,_,_)| *x==2));
 }
}

#[cfg(test)]
mod lookahead_tests {
 use super::*;
 #[test]
 fn tolerate_a_late_real_havok_result_at_running_speed() {
  let (mut sample, pose)={
   let mut g=[0u8;56];let p=[0u8;112];
   g[0..4].copy_from_slice(&2u32.to_le_bytes());
   g[4..8].copy_from_slice(&511u32.to_le_bytes());
   for i in 0..9{g[20+i*4..24+i*4].copy_from_slice(&1f32.to_le_bytes())}
   (g,p)
  };
  sample[8..12].copy_from_slice(&29f32.to_le_bytes());
  assert_eq!(triangles(&sample,&pose).unwrap().len(),8);
  sample[8..12].copy_from_slice(&45f32.to_le_bytes());
  assert!(triangles(&sample,&pose).is_none());
 }
}