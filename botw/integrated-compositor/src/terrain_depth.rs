//! Async depth-only occluder from authentic BOTW Havok triangle caches.
//! These meshes are a geometric approximation of Zelda's pixel depth:
//! no fabricated boxes, no pixels from a Minecraft screenshot. They were
//! extracted from the user's OWN BOTW RomFS by the existing installers.
//! CPU file IO never blocks the render thread.
use std::{fs,io,path::{Path,PathBuf},sync::{mpsc::{self,SyncSender},Arc,Mutex},thread};
use crate::world::Camera;

const TILE_SIZE:f32=250.;
const ORIGIN_X:f32=-5000.;
const ORIGIN_Z:f32=-4000.;
const RADIUS:f32=135.;
const MAX_OCCLUDER_VERTICES:usize=750_000;
const TRI_LEN:usize=36;
const BTRI_HEADER:usize=52;
#[derive(Clone,Default)]
pub struct DepthFrame{pub vertices:Arc<Vec<[f32;3]>>,pub revision:u64,pub tiles:usize}
pub struct TerrainDepth{
 tx:SyncSender<[f32;3]>,
 pub shared:Arc<Mutex<DepthFrame>>,
 requested:Option<[f32;3]>,
}
impl TerrainDepth{
 pub fn new()->Self{
   let root=std::env::var_os("BOTWCRAFT_TERRAIN_CACHE").map(PathBuf::from)
     .unwrap_or_else(||PathBuf::from("../terrain_cache"));
   let (tx,rx)=mpsc::sync_channel::<[f32;3]>(1);
   let shared=Arc::new(Mutex::new(DepthFrame::default()));
   let out=shared.clone();
   thread::Builder::new().name("BotwCraft genuine Zelda BTRI depth".into())
      .spawn(move||{
         let mut revision=0;
         while let Ok(mut eye)=rx.recv(){
           while let Ok(newest)=rx.try_recv(){eye=newest;}
           let (geometry,tiles)=build(&root,eye);
           revision+=1;
           if let Ok(mut target)=out.lock(){
              *target=DepthFrame{vertices:Arc::new(geometry),
                revision,tiles};
           }
         }
      }).expect("depth terrain thread failed");
   Self{tx,shared,requested:None}
 }
 pub fn tick(&mut self,cam:Option<Camera>){
   let Some(c)=cam else {return};
   let eye=c.eye;
   let update=self.requested.map_or(true,|old|
      (0..3).map(|i|(old[i]-eye[i]).powi(2)).sum::<f32>()>24.0f32.powi(2));
   if update && self.tx.try_send(eye).is_ok(){self.requested=Some(eye);}
 }
}
fn f32_at(bytes:&[u8],offset:usize)->io::Result<f32>{
  let b: [u8;4]=bytes.get(offset..offset+4).ok_or_else(||io::Error::other("truncated BTRI"))?
     .try_into().unwrap();
  let value=f32::from_le_bytes(b);
  if value.is_finite()&&value.abs()<100000. {Ok(value)}
  else {Err(io::Error::other("non finite BTRI"))}
}
fn load_tile(path:&Path,gx:i32,gz:i32,eye:[f32;3],vertices:&mut Vec<[f32;3]>)->io::Result<()>{
  let data=fs::read(path)?;
  if data.len()<BTRI_HEADER || &data[0..4]!=b"BTRI"{
    return Err(io::Error::other("invalid BTRI"));
  }
  let header=|off|u32::from_le_bytes(data[off..off+4].try_into().unwrap());
  let count=header(16) as usize;
  let x0=ORIGIN_X+gx as f32*TILE_SIZE;
  let z0=ORIGIN_Z+gz as f32*TILE_SIZE;
  if header(4)!=1 || header(8) as i32!=gx || header(12) as i32!=gz ||
     header(20) as i32!=x0 as i32 || header(24) as i32!=z0 as i32 ||
     count>1_000_000 || data.len()!=BTRI_HEADER+count*TRI_LEN{
    return Err(io::Error::other("BTRI header/size mismatch"));
  }
  for triangle in data[BTRI_HEADER..].chunks_exact(TRI_LEN){
    if vertices.len()+3>MAX_OCCLUDER_VERTICES {break;}
    let mut p=[[0.;3];3];
    for v in 0..3{for axis in 0..3{
       p[v][axis]=f32_at(triangle,(v*3+axis)*4)?;
    }}
    if p.iter().any(|v|v[0]< -0.2||v[0]>250.2||v[2]< -0.2||v[2]>250.2){continue}
    let min_x=p.iter().map(|v|v[0]+x0).fold(f32::INFINITY,f32::min);
    let max_x=p.iter().map(|v|v[0]+x0).fold(f32::NEG_INFINITY,f32::max);
    let min_z=p.iter().map(|v|v[2]+z0).fold(f32::INFINITY,f32::min);
    let max_z=p.iter().map(|v|v[2]+z0).fold(f32::NEG_INFINITY,f32::max);
    let nearest_x=eye[0].clamp(min_x,max_x);
    let nearest_z=eye[2].clamp(min_z,max_z);
    let distance_x=nearest_x-eye[0];
    let distance_z=nearest_z-eye[2];
    if distance_x*distance_x+distance_z*distance_z>RADIUS*RADIUS{continue;}
    // Preserve ALL faces near the camera: terrain, pillars, rocks and
    // building walls must write occluder depth, but never color.
    for point in p{
      vertices.push([point[0]+x0,point[1],point[2]+z0]);
    }
  }
  Ok(())
}
fn build(root:&Path,eye:[f32;3])->(Vec<[f32;3]>,usize){
 let gx=((eye[0]-ORIGIN_X)/TILE_SIZE).floor() as i32;
 let gz=((eye[2]-ORIGIN_Z)/TILE_SIZE).floor() as i32;
 let mut tiles=0;
 let mut vertices=Vec::new();
 for x in (gx-1)..=(gx+1){for z in (gz-1)..=(gz+1){
   if !(0..40).contains(&x)||!(0..32).contains(&z){continue}
   let x0=ORIGIN_X+x as f32*TILE_SIZE;let z0=ORIGIN_Z+z as f32*TILE_SIZE;
   let closest_x=eye[0].clamp(x0,x0+TILE_SIZE);
   let closest_z=eye[2].clamp(z0,z0+TILE_SIZE);
   if (eye[0]-closest_x).powi(2)+(eye[2]-closest_z).powi(2)>RADIUS*RADIUS{continue}
   let mut valid=false;
   for kind in ["terrain","decor"]{
     let path=root.join(kind).join(format!("{x:02}-{z:02}.btri"));
     if path.is_file(){
       if load_tile(&path,x,z,eye,&mut vertices).is_ok(){valid=true;}
     }
   }
   if valid{tiles+=1;}
   if vertices.len()>=MAX_OCCLUDER_VERTICES{break}
 }}
 (vertices,tiles)
}
#[cfg(test)]
mod tests{
 use super::*;
 #[test]fn genuine_botw_coordinate_transform(){
   assert_eq!(((0.-ORIGIN_X)/TILE_SIZE).floor() as i32,20);
   assert_eq!(((0.-ORIGIN_Z)/TILE_SIZE).floor() as i32,16);
 }
 #[test]fn empty_cache_is_safe_and_does_not_fake_terrain(){
   let root=PathBuf::from("__botwcraft_unavailable_BTRI__");
   let (mesh,n)=build(&root,[0.,0.,0.]);assert!(mesh.is_empty());assert_eq!(n,0);
 }
 #[test]fn read_actual_btri_triangle(){
   let root=std::env::temp_dir().join(format!("btri-depth-{}",std::process::id()));
   fs::create_dir_all(&root).unwrap();
   let path=root.join("20-16.btri");
   let mut data=vec![0u8;BTRI_HEADER];
   data[0..4].copy_from_slice(b"BTRI");
   for (off,v) in [(4,1u32),(8,20),(12,16),(16,1),(20,0),(24,0)]{
     data[off..off+4].copy_from_slice(&v.to_le_bytes());
   }
   for f in [0f32,0.,1.,1.,0.,1.,0.,1.,1.]{
     data.extend_from_slice(&f.to_le_bytes());
   }
   fs::write(&path,&data).unwrap();
   let mut out=Vec::new();load_tile(&path,20,16,[0.,1.,0.],&mut out).unwrap();
   assert_eq!(out,vec![[0.,0.,1.],[1.,0.,1.],[0.,1.,1.]]);
   let _=fs::remove_dir_all(root);
 }
}
