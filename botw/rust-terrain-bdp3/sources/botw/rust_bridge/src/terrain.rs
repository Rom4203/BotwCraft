//! Hyrule heightfield -> Minecraft collision, natively in the Rust bridge.
//!
//! No fake server, no Node, no Python and no player teleport. A local 256x256
//! BOTW .hght tile is sampled near the BDP3-correlated player pose. Rust writes
//! SkyCraft v11 COL_TRIS (smooth client capsule) and COL_REGION (voxel-backed
//! integrated server) messages into the EXISTING Windows shared-memory ring.
//!
//! This handles MainField terrain only: not Havok hksc/hktmrb walls, dungeons,
//! platforms, moving props, etc. It never invents geometry when data is absent.
use std::{collections::{BTreeMap,BTreeSet}, fs, path::{Path,PathBuf}, sync::{Arc,Mutex},thread,time::Duration};
use serde_json::Value;
use crate::{engine::Engine,shared::SharedMap};

const REGION:i32=8;
const MAX_TILES:usize=4096;
const MAX_TRIANGLES:usize=1024;
const GRID:usize=256;
const MAGIC_FILE_SIZE:usize=GRID*GRID*2;
const REGION_RANGE:i32=2; // five 8-block regions in X and Z
const COL_CLEAR:u32=1;
const COL_REGION:u32=2;
const COL_TRIS:u32=3;
const TRI_TERRAIN:u32=8;

#[derive(Debug)]
struct Tile { min_x:f64, min_z:f64, extent:f64, min_y:f64,max_y:f64, heights:Box<[u16]> }
impl Tile {
 fn height(&self,x:f64,z:f64)->Option<f64>{
  let u=(x-self.min_x)/self.extent;
  let v=(z-self.min_z)/self.extent;
  if !(0.0..=1.0).contains(&u)|| !(0.0..=1.0).contains(&v){return None;}
  let gx=u*255.0;let gz=v*255.0;
  let x0=gx.floor() as usize;let z0=gz.floor() as usize;
  let x1=(x0+1).min(255);let z1=(z0+1).min(255);
  let tx=gx-x0 as f64;let tz=gz-z0 as f64;
  let h=|a:usize,b:usize| self.heights[b*GRID+a] as f64 / 65535.0;
  let a=h(x0,z0)*(1.0-tx)+h(x1,z0)*tx;
  let b=h(x0,z1)*(1.0-tx)+h(x1,z1)*tx;
  Some(self.min_y+(a*(1.0-tz)+b*tz)*(self.max_y-self.min_y))
 }
}

#[derive(Default)]
struct Tiles { tiles:Vec<Tile> }
impl Tiles {
 fn read(dir:&Path)->Result<Self,String>{
  let config=dir.join("terrain.json");
  let data=fs::read(&config).map_err(|e|format!("{}: {e}",config.display()))?;
  let json:Value=serde_json::from_slice(&data).map_err(|e|e.to_string())?;
  let entries=json.get("tiles").and_then(Value::as_array)
   .ok_or("terrain.json: expected tiles array")?;
  if entries.is_empty()||entries.len()>MAX_TILES{return Err("No tiles or tile limit exceeded".into())}
  let mut tiles=Vec::with_capacity(entries.len());
  for t in entries {
   let filename=t.get("file").and_then(Value::as_str).ok_or("tile missing file")?;
   // Relative file names only: never let a game-resource manifest escape its root.
   let f=Path::new(filename);
   if f.is_absolute()||f.components().any(|v|!matches!(v,std::path::Component::Normal(_))) || !filename.ends_with(".hght"){
    return Err(format!("Unsafe heightfield filename: {filename}"));
   }
   let number=|field|->Result<f64,String>{
    let v=t.get(field).and_then(Value::as_f64).ok_or(format!("Missing {field}"))?;
    if !v.is_finite()||v.abs()>1_000_000.0{return Err(format!("Invalid {field}"))};Ok(v)
   };
   let min_x=number("x")?;let min_z=number("z")?;let extent=number("size")?;
   let min_y=number("min_y")?;let max_y=number("max_y")?;
   if extent<=0.0||extent>200_000.0||max_y<min_y{return Err("Invalid terrain tile bounds".into())}
   let path=dir.join(f);
   let bytes=fs::read(&path).map_err(|e|format!("{}: {e}",path.display()))?;
   if bytes.len()!=MAGIC_FILE_SIZE{return Err(format!("{}: expected exactly 131072 uncompressed bytes",path.display()))}
   let mut heights=Vec::with_capacity(GRID*GRID);
   for pair in bytes.chunks_exact(2){heights.push(u16::from_le_bytes([pair[0],pair[1]]));}
   tiles.push(Tile{min_x,min_z,extent,min_y,max_y,heights:heights.into_boxed_slice()});
  }
  Ok(Self{tiles})
 }
 fn height(&self,x:f64,z:f64)->Option<f64>{
  // Last (typically highest-detail) overlapping tile wins.
  self.tiles.iter().rev().find_map(|tile|tile.height(x,z))
 }
}

// A BDP3 anchor is rigid translation, not a teleport. Coordinates here match
// game world units already emitted in the guest Link telemetry.
#[derive(Clone,Copy,Debug)]
struct Frame { mc:[f64;3], mc_origin:[f64;3], botw_origin:[f64;3] }
impl Frame {
 fn world_xz(&self,x:f64,z:f64)->(f64,f64){
  (self.botw_origin[0]+x-self.mc_origin[0],self.botw_origin[2]+z-self.mc_origin[2])
 }
 fn mc_y(&self,world_y:f64)->f64{self.mc_origin[1]+world_y-self.botw_origin[1]}
}

#[derive(Clone,Copy,Debug,PartialEq,Eq,PartialOrd,Ord)]
struct Region(i32,i32,i32);
impl Region { fn from_mc(x:f64,y:f64,z:f64)->Self{Self((x.floor() as i32).div_euclid(REGION),(y.floor() as i32).div_euclid(REGION),(z.floor() as i32).div_euclid(REGION))} }

fn append_u32(out:&mut Vec<u8>,v:u32){out.extend_from_slice(&v.to_le_bytes())}
fn append_i32(out:&mut Vec<u8>,v:i32){out.extend_from_slice(&v.to_le_bytes())}
fn append_f32(out:&mut Vec<u8>,v:f32){out.extend_from_slice(&v.to_le_bytes())}
fn message(ty:u32,payload:&[u8])->Vec<u8>{
 let mut out=Vec::with_capacity(8+payload.len()+7);append_u32(&mut out,ty);append_u32(&mut out,payload.len() as u32);
 out.extend_from_slice(payload);out.resize((out.len()+7)&!7,0);out
}
fn region_header(r:Region,count:usize)->Vec<u8>{
 let mut p=Vec::with_capacity(32);
 for c in [r.0*REGION,r.1*REGION,r.2*REGION,r.0*REGION+7,r.1*REGION+7,r.2*REGION+7]{append_i32(&mut p,c)}
 append_i32(&mut p,1);append_u32(&mut p,count as u32);p
}
fn surface_height(tiles:&Tiles, frame:Frame,mcx:f64,mcz:f64)->Option<f64>{
 let (x,z)=frame.world_xz(mcx,mcz);
 tiles.height(x,z).map(|y|frame.mc_y(y))
}
fn tri_packet(tiles:&Tiles,frame:Frame,region:Region)->Vec<u8>{
 let x0=region.0*REGION;let z0=region.2*REGION;
 let y0=region.1*REGION;
 let mut triangles=Vec::<[f32;9]>::new();
 for x in x0..x0+REGION { for z in z0..z0+REGION {
  let xs=[x as f64,x as f64+1.0];let zs=[z as f64,z as f64+1.0];
  let heights=[surface_height(tiles,frame,xs[0],zs[0]),surface_height(tiles,frame,xs[1],zs[0]),
   surface_height(tiles,frame,xs[0],zs[1]),surface_height(tiles,frame,xs[1],zs[1])];
  if heights.iter().any(Option::is_none){continue}
  let h=heights.map(|v|v.unwrap());
  // Duplicate a sloping surface in each adjacent 8-block layer it touches.
  if h.iter().all(|v|*v < y0 as f64-0.01) || h.iter().all(|v|*v>(y0+REGION) as f64+0.01){continue}
  let t0=[xs[0] as f32,h[0] as f32,zs[0] as f32,
          xs[0] as f32,h[2] as f32,zs[1] as f32,
          xs[1] as f32,h[1] as f32,zs[0] as f32];
  let t1=[xs[1] as f32,h[1] as f32,zs[0] as f32,
          xs[0] as f32,h[2] as f32,zs[1] as f32,
          xs[1] as f32,h[3] as f32,zs[1] as f32];
  triangles.push(t0);triangles.push(t1);
 }}
 assert!(triangles.len()<=MAX_TRIANGLES);
 let mut p=region_header(region,triangles.len());
 for t in triangles { for v in t {append_f32(&mut p,v)} append_u32(&mut p,TRI_TERRAIN);}
 message(COL_TRIS,&p)
}
fn voxels_packet(tiles:&Tiles,frame:Frame,region:Region)->Vec<u8>{
 let mut p=region_header(region,0);let mut count=0u32;
 for bx in region.0*8..region.0*8+8 {
  for bz in region.2*8..region.2*8+8 {
   for by in region.1*8..region.1*8+8 {
    let mut bits=[0u64;8];
    for vz in 0..8 { for vx in 0..8 {
     let xx=bx as f64+(vx as f64+0.5)/8.0;
     let zz=bz as f64+(vz as f64+0.5)/8.0;
     if let Some(h)=surface_height(tiles,frame,xx,zz) {
      for vy in 0..8 {
       if by as f64+(vy as f64+0.5)/8.0<h {
        bits[vy]|=1u64<<(vx+8*vz);
       }
      }
     }
    }}
    if bits.iter().all(|n|*n==0){continue}
    append_i32(&mut p,bx);append_i32(&mut p,by);append_i32(&mut p,bz);append_u32(&mut p,0);
    for bit in bits {p.extend_from_slice(&bit.to_le_bytes());}
    count+=1;
   }
  }
 }
 p[28..32].copy_from_slice(&count.to_le_bytes());
 message(COL_REGION,&p)
}

fn clear_packet()->Vec<u8>{message(COL_CLEAR,&1u32.to_le_bytes())}

pub fn start(state:Arc<Mutex<Engine>>){
 let Some(root)=std::env::var_os("BOTWCRAFT_TERRAIN_DIR") else {
  println!("[TERRAIN] No BOTWCRAFT_TERRAIN_DIR: Rust collision streamer inactive");return;
 };
 let root=PathBuf::from(root);
 thread::Builder::new().name("botwcraft-terrain-native".into()).spawn(move||{
  let tiles=match Tiles::read(&root){Ok(t)=>t,Err(err)=>{
   eprintln!("[TERRAIN] No valid BOTW terrain, refusing to fake ground: {err}");return
  }};
  println!("[TERRAIN] Native Rust terrain: {} original BOTW .hght tiles",tiles.tiles.len());
  let mut regions=BTreeSet::<Region>::new();
  let mut previous_anchor=None::<([f64;3],[f64;3])>;
  let mut was_live=false;
  loop{
   let current=state.lock().ok().and_then(|e|e.collision_frame());
   match current {
    None=>{
     if was_live {if let Ok(mut e)=state.lock(){let _=e.mem.collision_write(&clear_packet());}}
     regions.clear();previous_anchor=None;was_live=false;
    }
    Some((mc,ma,ba))=>{
     let frame=Frame{mc,mc_origin:ma,botw_origin:ba};
     let anchor=(ma,ba);
     if previous_anchor!=Some(anchor){
      regions.clear();
      if let Ok(mut e)=state.lock(){let _=e.mem.collision_write(&clear_packet());}
      previous_anchor=Some(anchor);
     }
     was_live=true;
     let center=Region::from_mc(mc[0],mc[1],mc[2]);
     let mut next=BTreeSet::new();
     for dx in -REGION_RANGE..=REGION_RANGE{for dz in -REGION_RANGE..=REGION_RANGE {
      for dy in -2..=1 { next.insert(Region(center.0+dx,center.1+dy,center.2+dz)); }
     }}
     // Prepare on the independent Rust thread: NEVER block the 120 Hz pose tick.
     let mut packets=Vec::new();
     for region in regions.difference(&next){
      packets.push(message(COL_TRIS,&region_header(*region,0)));
      packets.push(message(COL_REGION,&region_header(*region,0)));
     }
     for region in next.difference(&regions){
      packets.push(tri_packet(&tiles,frame,*region));
      packets.push(voxels_packet(&tiles,frame,*region));
     }
     // Write each packet under the existing bridge mutex (bounded ring).
     if let Ok(mut e)=state.lock(){
      for p in &packets { if !e.mem.collision_write(p){eprintln!("[TERRAIN] Collision ring full: skipping update");break} }
     }
     regions=next;
    }
   }
   thread::sleep(Duration::from_millis(350));
  }
 }).expect("could not start Rust terrain worker");
}

#[cfg(test)]
mod tests {
 use super::*;
 fn flat()->(Tiles,Frame){
  let tile=Tile{min_x:-128.0,min_z:-128.0,extent:256.0,min_y:0.0,max_y:64.0,
      heights:vec![32768u16;65536].into_boxed_slice()};
  (Tiles{tiles:vec![tile]}, Frame{mc:[0.0,32.0,0.0],mc_origin:[0.0,32.0,0.0],botw_origin:[0.0,32.0,0.0]})
 }
 #[test] fn height_interpolation(){let(t,f)=flat();let h=surface_height(&t,f,1.0,-1.0).unwrap();assert!((h-32.0005).abs()<0.01)}
 #[test] fn finite_terrain_collision_packet(){let(t,f)=flat();let r=Region(0,4,0);let p=tri_packet(&t,f,r);assert_eq!(u32::from_le_bytes(p[0..4].try_into().unwrap()),COL_TRIS);assert_eq!(u32::from_le_bytes(p[36..40].try_into().unwrap()),128);}
 #[test] fn minecraft_server_voxels(){let(t,f)=flat();let p=voxels_packet(&t,f,Region(0,3,0));assert_eq!(u32::from_le_bytes(p[..4].try_into().unwrap()),COL_REGION);assert!(u32::from_le_bytes(p[36..40].try_into().unwrap())>0);}
 #[test] fn region_floor_division(){assert_eq!(Region::from_mc(-0.01,-9.0,17.0),Region(-1,-2,2));}
}