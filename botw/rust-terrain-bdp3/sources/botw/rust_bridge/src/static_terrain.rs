//! Streams authentic BOTW Switch Havok mesh triangles from a user-owned RomFS
//! converted into BTRI cache. Never performs in-game raycasts or generates
//! synthetic floor. Works in a separate worker, keeping the camera thread free.
use std::{collections::{BTreeSet,HashMap},fs::File,io::{self,Read},path::{Path,PathBuf},sync::{Arc,Mutex,atomic::{AtomicBool,Ordering}},thread,time::{Duration,Instant}};
use crate::{engine::Engine,terrain::{self,Region,Triangle}};

pub static STATIC_ACTIVE:AtomicBool=AtomicBool::new(false);
const GRID:f64=250.0;
const ORIGIN_X:f64=-5000.0;
const ORIGIN_Z:f64=-4000.0;
const PRELOAD_RADIUS:i32=5; // 5 * 8 = 40m around Steve
const BACKLOG_LIMIT:usize=2500;
const TILE_CACHE_LIMIT:usize=6;
const COLLISION_WAIT_MS:u64=20;

#[derive(Clone,Copy)]
struct RawTri {v:[[f32;3];3],min:[f32;3],max:[f32;3]}
impl RawTri{
 fn new(v:[[f32;3];3])->Self{
  let mut min=[f32::INFINITY;3];let mut max=[f32::NEG_INFINITY;3];
  for p in &v {for i in 0..3{min[i]=min[i].min(p[i]);max[i]=max[i].max(p[i]);}}
  Self{v,min,max}
 }
}
struct Tile {
 faces:Vec<RawTri>,
 // Indexed by 8m Zelda world-space columns. Avoid touching a whole 250m
 // terrain mesh whenever Steve needs one 8x8 Minecraft collision region.
 columns:HashMap<(i32,i32),Vec<usize>>,
}
fn index_of(x:f64,z:f64)->Option<(i32,i32)>{
 let gx=((x-ORIGIN_X)/GRID).floor() as i32;
 let gz=((z-ORIGIN_Z)/GRID).floor() as i32;
 (0..40).contains(&gx).then_some(())?;
 (0..32).contains(&gz).then_some(())?;
 Some((gx,gz))
}
fn read_f32(bytes:&[u8],offset:usize)->io::Result<f32>{
 let v=f32::from_le_bytes(bytes.get(offset..offset+4).ok_or_else(||io::Error::other("bad BTRI vertex"))?.try_into().unwrap());
 if !v.is_finite()||v.abs()>100_000. {return Err(io::Error::other("invalid BTRI float"));}
 Ok(v)
}
fn load(path:&Path,gx:i32,gz:i32)->io::Result<Tile>{
 let mut file=File::open(path)?;
 let mut head=[0u8;52];file.read_exact(&mut head)?;
 if &head[0..4]!=b"BTRI"||u32::from_le_bytes(head[4..8].try_into().unwrap())!=1{return Err(io::Error::other("unsupported BTRI cache version"));}
 let index_x=i32::from_le_bytes(head[8..12].try_into().unwrap());
 let index_z=i32::from_le_bytes(head[12..16].try_into().unwrap());
 let count=u32::from_le_bytes(head[16..20].try_into().unwrap()) as usize;
 let world_x=i32::from_le_bytes(head[20..24].try_into().unwrap());
 let world_z=i32::from_le_bytes(head[24..28].try_into().unwrap());
 if index_x!=gx||index_z!=gz||world_x!=(-5000+gx*250)||world_z!=(-4000+gz*250)||count>1_000_000 {
  return Err(io::Error::other("BTRI tile header mismatch"));
 }
 if file.metadata()?.len()!=52+count as u64*36{return Err(io::Error::other("BTRI tile length mismatch"));}
 let mut bytes=vec![0u8;count*36];file.read_exact(&mut bytes)?;
 let mut faces=Vec::with_capacity(count);
 let mut columns=HashMap::<(i32,i32),Vec<usize>>::new();
 for i in 0..count {
  let mut v=[[0f32;3];3];
  for j in 0..3 {for k in 0..3 {v[j][k]=read_f32(&bytes,i*36+j*12+k*4)?;}}
  let tri=RawTri::new(v);
  // Verify triangles remain in their own 250m tile; never inject corrupted
  // coordinates into Minecraft collision world.
  if tri.min[0] < -0.2||tri.max[0]>250.2||tri.min[2] < -0.2||tri.max[2]>250.2 {return Err(io::Error::other("BTRI face outside tile"));}
  let key_x0=((tri.min[0] as f64+world_x as f64)/8.0).floor() as i32;
  let key_x1=((tri.max[0] as f64+world_x as f64)/8.0).floor() as i32;
  let key_z0=((tri.min[2] as f64+world_z as f64)/8.0).floor() as i32;
  let key_z1=((tri.max[2] as f64+world_z as f64)/8.0).floor() as i32;
  // Bound index size for malformed input. 250m tile fits in 32 grid cells.
  if key_x1-key_x0>33||key_z1-key_z0>33{return Err(io::Error::other("BTRI face spans invalid columns"));}
  for x in key_x0..=key_x1 {for z in key_z0..=key_z1 {columns.entry((x,z)).or_default().push(i);}}
  faces.push(tri);
 }
 Ok(Tile{faces,columns})
}
fn path_for(root:&Path,gx:i32,gz:i32)->PathBuf{root.join("terrain").join(format!("{gx:02}-{gz:02}.btri"))}
struct Tiles { root:PathBuf,loaded:HashMap<(i32,i32),Tile>,last_failure:HashMap<(i32,i32),Instant> }
impl Tiles {
 fn new(root:PathBuf)->Self{Self{root,loaded:HashMap::new(),last_failure:HashMap::new()}}
 fn ensure(&mut self,index:(i32,i32))->bool{
  if self.loaded.contains_key(&index){return true}
  if self.last_failure.get(&index).is_some_and(|t|t.elapsed()<Duration::from_secs(10)){return false}
  let path=path_for(&self.root,index.0,index.1);
  if !path.is_file(){self.last_failure.insert(index,Instant::now());return false}
  match load(&path,index.0,index.1){
   Ok(tile)=>{
    if self.loaded.len()>=TILE_CACHE_LIMIT {
      // The caller requests nearby tiles first; oldest arbitrary far tile
      // will be reloaded from already converted cache as needed.
      if let Some(evict)=self.loaded.keys().copied().find(|x|*x!=index){self.loaded.remove(&evict);}
    }
    println!("[STATIC_TERRAIN] Loaded cache {:?}: {} real triangles, {} spatial cells",index,tile.faces.len(),tile.columns.len());
    self.loaded.insert(index,tile);true
   }
   Err(e)=>{eprintln!("[STATIC_TERRAIN] Invalid BTRI cache {}: {e}",path.display());self.last_failure.insert(index,Instant::now());false}
  }
 }
 fn region_faces(&mut self, region:Region, origin_delta:[f64;3])->Vec<Triangle>{
  let min_x=region.0 as f64*8.-origin_delta[0];
  let max_x=min_x+8.;
  let min_z=region.2 as f64*8.-origin_delta[2];
  let max_z=min_z+8.;
  let y_low=region.1 as f64*8.-origin_delta[1]-0.8;
  let y_high=y_low+8.8;
  let mut candidates=BTreeSet::<((i32,i32),usize)>::new();
  // Tiles overlap only at exact edges; check each touching 250m tile.
  let gx0=((min_x-ORIGIN_X)/GRID).floor() as i32;
  let gx1=((max_x-ORIGIN_X)/GRID).floor() as i32;
  let gz0=((min_z-ORIGIN_Z)/GRID).floor() as i32;
  let gz1=((max_z-ORIGIN_Z)/GRID).floor() as i32;
  for gx in gx0..=gx1 {for gz in gz0..=gz1 {
    if !(0..40).contains(&gx)||!(0..32).contains(&gz){continue}
    if !self.ensure((gx,gz)){continue}
    let tile=&self.loaded[&(gx,gz)];
    let i0=(min_x/8.).floor() as i32;let i1=(max_x/8.).floor() as i32;
    let j0=(min_z/8.).floor() as i32;let j1=(max_z/8.).floor() as i32;
    for ix in i0..=i1 {for iz in j0..=j1 {
      if let Some(indices)=tile.columns.get(&(ix,iz)){
       for &idx in indices {candidates.insert(((gx,gz),idx));}
      }
    }}
  }}
  let mut triangles=Vec::new();
  for (index,idx) in candidates{
   let tri=self.loaded[&index].faces[idx];
   let tx=ORIGIN_X+index.0 as f64*GRID;
   let tz=ORIGIN_Z+index.1 as f64*GRID;
   let ax=tri.min[0] as f64+tx;let bx=tri.max[0] as f64+tx;
   let az=tri.min[2] as f64+tz;let bz=tri.max[2] as f64+tz;
   if bx<min_x||ax>max_x||bz<min_z||az>max_z||(tri.max[1] as f64)<y_low||(tri.min[1] as f64)>y_high{continue}
   let mut v=[[0f32;3];3];
   for i in 0..3 { v[i]=[
     (tri.v[i][0] as f64+tx+origin_delta[0]) as f32,
     (tri.v[i][1] as f64+origin_delta[1]) as f32,
     (tri.v[i][2] as f64+tz+origin_delta[2]) as f32,
   ];}
   triangles.push(Triangle{v});
  }
  triangles
 }
}
fn near_regions(mc:[f64;3], delta:[f64;3])->Vec<Region>{
 let cx=(mc[0]/8.).floor() as i32;let cz=(mc[2]/8.).floor() as i32;
 let cz_future=((mc[2]+delta[2])/8.).floor() as i32;
 let cx_future=((mc[0]+delta[0])/8.).floor() as i32;
 let cy=(mc[1]/8.).floor() as i32;
 let mut cols=BTreeSet::new();
 for (px,pz) in [(cx,cz),(cx_future,cz_future)] {
  for dx in -PRELOAD_RADIUS..=PRELOAD_RADIUS {
   for dz in -PRELOAD_RADIUS..=PRELOAD_RADIUS {
    if dx*dx+dz*dz<=PRELOAD_RADIUS*PRELOAD_RADIUS+2 {cols.insert((px+dx,pz+dz));}
   }
  }
 }
 let mut regions=Vec::new();
 for (x,z) in cols {for y in cy-5..=cy+3 {regions.push(Region(x,y,z));}}
 regions.sort_by_key(|r|{
  let dx=(r.0-cx) as i64;let dz=(r.2-cz) as i64;let dy=(r.1-cy) as i64;
  dx*dx*10+dz*dz*10+dy*dy*6
 });
 regions
}
fn active_data(frame:([f64;3],[f64;3],[f64;3]),root:&Path)->Option<([f64;3],[f64;3],(i32,i32))>{
 let (mc,mc_origin,botw_origin)=frame;
 let link=[botw_origin[0]+mc[0]-mc_origin[0],botw_origin[1]+mc[1]-mc_origin[1],botw_origin[2]+mc[2]-mc_origin[2]];
 let (gx,gz)=index_of(link[0],link[2])?;
 path_for(root,gx,gz).is_file().then_some((mc,[mc_origin[0]-botw_origin[0],mc_origin[1]-botw_origin[1],mc_origin[2]-botw_origin[2]],(gx,gz)))
}

pub fn run(state:Arc<Mutex<Engine>>){
 let root=std::env::var_os("BOTWCRAFT_TERRAIN_CACHE").map(PathBuf::from)
  .unwrap_or_else(||PathBuf::from("terrain_cache"));
 println!("[STATIC_TERRAIN] Offline genuine BOTW mesh loader; directory={} (no in-game raycasts)",root.display());
 let mut tiles=Tiles::new(root.clone());
 let mut regions_sent=BTreeSet::<Region>::new();
 let mut active=false;
 let mut last_origin:Option<[f64;3]>=None;
 let mut prev_mc:Option<([f64;3],Instant)>=None;
 let mut last_report=Instant::now();
 loop {
  let frame=state.lock().ok().and_then(|x|x.collision_frame());
  let frame=frame.and_then(|f|active_data(f,&root));
  let tile_index=frame.as_ref().map(|x|x.2);
  let validated=tile_index.is_some_and(|idx|tiles.ensure(idx));
  let Some((mc,delta,_))=frame.filter(|_|validated) else {
   if active {
    STATIC_ACTIVE.store(false,Ordering::Release);
    // Explicitly discard stale static meshes when stepping into a tile
    // not yet converted, allowing the existing Havok fallback to work.
    if let Ok(mut engine)=state.lock(){let _=engine.mem.collision_write(&terrain::clear());}
    regions_sent.clear();last_origin=None;prev_mc=None;active=false;
    println!("[STATIC_TERRAIN] Local cache unavailable or session disconnected; Havok fallback enabled");
   }
   thread::sleep(Duration::from_millis(100));continue
  };
  if !active || last_origin.is_some_and(|o|o!=delta) {
    STATIC_ACTIVE.store(true,Ordering::Release);
    let clear=terrain::clear();
    if let Ok(mut engine)=state.lock(){let _=engine.mem.collision_write(&clear);}
    active=true;regions_sent.clear();last_origin=Some(delta);prev_mc=None;
    println!("[STATIC_TERRAIN] ACTIVATED: real BTRI terrain collisions, camera and inputs unchanged");
  }
  let mut lead=[0f64;3];
  if let Some((previous,when))=prev_mc {
   let elapsed=when.elapsed().as_secs_f64();
   if elapsed>0.01 && elapsed<2.0 {
    for axis in [0,2]{let speed=((mc[axis]-previous[axis])/elapsed).clamp(-12.,12.);lead[axis]=speed*0.55;}
   }
  }
  prev_mc=Some((mc,Instant::now()));
  let mut new_packets=0usize;
  let mut new_tris=0usize;
  let mut checked_regions=0usize;
  let regions=near_regions(mc,lead);
  for region in regions{
   if regions_sent.contains(&region){continue}
   let tris=tiles.region_faces(region,delta);
   // Empty regions can be left entirely absent (vanilla air).
   if !tris.is_empty() {
    let vox=terrain::voxel_regions(&tris);
    let blocks=vox.get(&region).cloned().unwrap_or_default();
    let messages=[terrain::tri_message(region,&tris),terrain::voxel_message(region,&blocks)];
    if let Ok(mut engine)=state.lock(){
     if !messages.iter().all(|m|engine.mem.collision_write(m)) {break}
    }else{break}
    new_tris+=tris.len();new_packets+=2;
   }
   regions_sent.insert(region);
   checked_regions+=1;
   // Time slice conversion work to avoid 1FPS spikes on slower CPUs.
   if new_packets>=12 || checked_regions>=45 {break}
  }
  if regions_sent.len()>BACKLOG_LIMIT {
    // Expire the oldest remote cells with *real* per-region clear packets
    // rather than accumulating an unbounded 2000km trip in Minecraft RAM.
    let px=(mc[0]/8.).floor() as i32;let pz=(mc[2]/8.).floor() as i32;
    let far:Vec<_>=regions_sent.iter().filter(|r|(r.0-px).abs()>17||(r.2-pz).abs()>17).take(128).copied().collect();
    for key in far{
     let empty=[terrain::tri_message(key,&[]),terrain::voxel_message(key,&[])];
     if let Ok(mut engine)=state.lock(){for msg in empty {let _=engine.mem.collision_write(&msg);}}
     regions_sent.remove(&key);
    }
  }
  if last_report.elapsed()>=Duration::from_secs(6) {
   println!("[STATIC_TERRAIN] active: cached_regions={} new_packets={} new_triangle_refs={} resident_physics_tiles={} (no Havok raycasts)",regions_sent.len(),new_packets,new_tris,tiles.loaded.len());
   last_report=Instant::now();
  }
  thread::sleep(Duration::from_millis(COLLISION_WAIT_MS));
 }
}

#[cfg(test)]
mod tests{
 use super::*;
 #[test]fn tile_coordinates_match_real_botw_mainfield(){
  assert_eq!(index_of(-5000.,-4000.),Some((0,0)));
  assert_eq!(index_of(-4750.,3750.),Some((1,31)));
  assert_eq!(index_of(0.,0.),Some((20,16)));
  assert_eq!(index_of(5000.,0.),None);
 }
 #[test]fn priority_starts_near_player(){
  let cells=near_regions([0.,100.,0.],[4.,0.,4.]);
  assert!(!cells.is_empty());
  assert_eq!((cells[0].0,cells[0].2),(0,0));
 }
}