//! Minecraft/SkyCraft v11 section+atlas decoder for a future in-game BOTW renderer.
//! No overlay, emulator hooks, GDB proxy, or second render-ring consumer.
use std::collections::HashMap;

pub const PROTOCOL_MAGIC:u32=0x4359_4b53;
pub const PROTOCOL_VERSION:u32=11;
pub const RENDER_RING_OFFSET:usize=0x20000+32*1024*1024+3*3840*2160*4;
pub const RENDER_RING_SIZE:usize=64*1024*1024;
pub const RENDER_DATA_OFFSET:usize=0x80;
pub const RENDER_DATA_CAPACITY:usize=RENDER_RING_SIZE-RENDER_DATA_OFFSET;
pub const MAPPING_SIZE:usize=RENDER_RING_OFFSET+RENDER_RING_SIZE;
pub type SectionKey=(i32,i32,i32);

#[repr(C)]
#[derive(Clone,Copy,Debug,PartialEq)]
#[cfg_attr(feature="gpu",derive(bytemuck::Pod,bytemuck::Zeroable))]
pub struct Vertex {
    pub xyz:[f32;3],
    pub uv:[f32;2],
    pub color:u32,
    pub light:u32,
    pub flags:u32,
}
const _:[();32]=[();std::mem::size_of::<Vertex>()];
#[derive(Debug,Clone)]
pub struct MeshSection {pub vertices:Vec<Vertex>,pub revision:u64,pub translucent:bool}
#[derive(Debug,Clone)]
pub struct Atlas {pub width:u32,pub height:u32,pub rgba:Vec<u8>,pub revision:u64}
#[derive(Default,Debug,Clone)]
pub struct Stats {pub packets:u64,pub malformed:u64,pub sections_changed:u64,pub sections_removed:u64,pub vertices_received:u64,pub bytes_received:u64}
#[derive(Default)]
pub struct World {
    pub sections:HashMap<SectionKey,MeshSection>,
    pub atlas:Option<Atlas>,
    pub stats:Stats,
    next_revision:u64,
}
#[derive(Debug,PartialEq,Eq)]
pub enum PacketError{InvalidLength,InvalidCount,NonFinitePosition,InvalidAtlas}
fn u32_at(b:&[u8],i:usize)->Result<u32,PacketError>{
    let t=b.get(i..i+4).ok_or(PacketError::InvalidLength)?;
    Ok(u32::from_le_bytes([t[0],t[1],t[2],t[3]]))
}
fn i32_at(b:&[u8],i:usize)->Result<i32,PacketError>{Ok(u32_at(b,i)? as i32)}
fn f32_at(b:&[u8],i:usize)->Result<f32,PacketError>{Ok(f32::from_bits(u32_at(b,i)?))}
impl World {
    fn revision(&mut self)->u64{self.next_revision=self.next_revision.wrapping_add(1);self.next_revision}
    /// "kind" is protocol/skycraft_protocol.h's RenType. Valid messages only
    /// commit after full bounds and NaN validation.
    pub fn ingest(&mut self,kind:u32,data:&[u8])->Result<(),PacketError>{
        let result=self.apply(kind,data);
        if result.is_err(){self.stats.malformed+=1;}
        else{self.stats.packets+=1;self.stats.bytes_received+=data.len() as u64;}
        result
    }
    fn apply(&mut self,kind:u32,data:&[u8])->Result<(),PacketError>{
        match kind {
            3=>{self.sections.clear();self.revision();}
            1=>{
                let w=u32_at(data,0)?;let h=u32_at(data,4)?;
                if w==0||h==0||w>8192||h>8192{return Err(PacketError::InvalidAtlas);}
                let n=(w as usize).checked_mul(h as usize).and_then(|i|i.checked_mul(4)).ok_or(PacketError::InvalidAtlas)?;
                if data.len()!=n+8{return Err(PacketError::InvalidAtlas);}
                let revision=self.revision();
                self.atlas=Some(Atlas{width:w,height:h,rgba:data[8..].to_vec(),revision});
            }
            2=>{
                let key=(i32_at(data,0)?,i32_at(data,4)?,i32_at(data,8)?);
                let n=u32_at(data,12)? as usize;
                if n>262_144||n%3!=0||data.len()!=16+n*32{return Err(PacketError::InvalidCount);}
                if n==0{
                    if self.sections.remove(&key).is_some(){self.stats.sections_removed+=1;self.revision();}
                    return Ok(());
                }
                let origin=[key.0 as f64*16.0,key.1 as f64*16.0,key.2 as f64*16.0];
                let mut vertices=Vec::with_capacity(n);let mut translucent=false;
                for b in data[16..].chunks_exact(32){
                    let x=f32_at(b,0)?;let y=f32_at(b,4)?;let z=f32_at(b,8)?;
                    let u=f32_at(b,12)?;let v=f32_at(b,16)?;
                    if ![x,y,z,u,v].iter().all(|q|q.is_finite()){return Err(PacketError::NonFinitePosition);}
                    let xyz=[(origin[0]+x as f64) as f32,(origin[1]+y as f64) as f32,(origin[2]+z as f64) as f32];
                    if !xyz.iter().all(|q|q.is_finite()){return Err(PacketError::NonFinitePosition);}
                    let flags=u32_at(b,28)?;
                    translucent|=flags&2!=0;
                    vertices.push(Vertex{xyz,uv:[u,v],color:u32_at(b,20)?,light:u32_at(b,24)?,flags});
                }
                let revision=self.revision();
                self.sections.insert(key,MeshSection{vertices,revision,translucent});
                self.stats.sections_changed+=1;self.stats.vertices_received+=n as u64;
            }
            7=>{
                let x=u32_at(data,0)? as usize;let y=u32_at(data,4)? as usize;
                let w=u32_at(data,8)? as usize;let h=u32_at(data,12)? as usize;
                let a=self.atlas.as_ref().ok_or(PacketError::InvalidAtlas)?;
                let x2=x.checked_add(w).ok_or(PacketError::InvalidAtlas)?;
                let y2=y.checked_add(h).ok_or(PacketError::InvalidAtlas)?;
                let n=w.checked_mul(h).and_then(|i|i.checked_mul(4)).ok_or(PacketError::InvalidAtlas)?;
                if w==0||h==0||x2>a.width as usize||y2>a.height as usize||
                    data.len()!=n+16{return Err(PacketError::InvalidAtlas);}
                let revision=self.revision();
                let a=self.atlas.as_mut().unwrap();
                for row in 0..h{
                    let dst=((y+row)*a.width as usize+x)*4;
                    let src=16+row*w*4;
                    a.rgba[dst..dst+w*4].copy_from_slice(&data[src..src+w*4]);
                }
                a.revision=revision;
            }
            _=>{}
        }
        Ok(())
    }
    pub fn triangles(&self)->usize{self.sections.values().map(|s|s.vertices.len()/3).sum()}
    /// Coarse culling before GPU upload; stable order avoids unnecessary churn.
    pub fn visible_keys(&self,eye:[f32;3],range:f32)->Vec<SectionKey>{
        if !eye.iter().all(|n|n.is_finite())||range<=0.0{return vec![];}
        let limit=(range+13.8564).powi(2);
        let mut out=Vec::new();
        for &(sx,sy,sz) in self.sections.keys(){
            let delta=[(sx as f32+0.5)*16.0-eye[0],(sy as f32+0.5)*16.0-eye[1],(sz as f32+0.5)*16.0-eye[2]];
            if delta.iter().map(|x|x*x).sum::<f32>()<limit{out.push((sx,sy,sz));}
        }
        out.sort_unstable();out
    }
}

/// Only ONE participant can advance ring TAIL. This is for embedding in the
/// existing native renderer after its sources become available.
pub fn drain_ring(mapping:&mut [u8],world:&mut World,max_packets:usize,max_bytes:usize)->Result<usize,PacketError>{
    if mapping.len()<MAPPING_SIZE||u32_at(mapping,0)?!=PROTOCOL_MAGIC||
        u32_at(mapping,4)?!=PROTOCOL_VERSION{return Err(PacketError::InvalidLength);}
    let off=RENDER_RING_OFFSET;
    let head=u64::from_le_bytes(mapping[off..off+8].try_into().unwrap());
    let mut tail=u64::from_le_bytes(mapping[off+0x40..off+0x48].try_into().unwrap());
    if head<tail||head-tail>RENDER_DATA_CAPACITY as u64{return Err(PacketError::InvalidLength);}
    let mut packets=0;let mut bytes=0;
    while tail<head&&packets<max_packets&&bytes<max_bytes{
        let pos=(tail%RENDER_DATA_CAPACITY as u64) as usize;
        if RENDER_DATA_CAPACITY-pos<8{return Err(PacketError::InvalidLength);}
        let at=off+RENDER_DATA_OFFSET+pos;
        let kind=u32_at(mapping,at)?;let len=u32_at(mapping,at+4)? as usize;
        if kind==0{tail+=(RENDER_DATA_CAPACITY-pos) as u64;}
        else{
            let aligned=(len.checked_add(8).ok_or(PacketError::InvalidLength)?+7)&!7;
            if len>32*1024*1024||aligned>RENDER_DATA_CAPACITY-pos||aligned as u64>head-tail{
                return Err(PacketError::InvalidLength);
            }
            world.ingest(kind,&mapping[at+8..at+8+len])?;
            tail+=aligned as u64;packets+=1;bytes+=len;
        }
        mapping[off+0x40..off+0x48].copy_from_slice(&tail.to_le_bytes());
    }
    Ok(packets)
}
#[cfg(feature="gpu")]
pub mod gpu;
#[cfg(test)]
mod tests{
    use super::*;
    fn section(n:u32)->Vec<u8>{
        let mut p=vec![0;12];p.extend(n.to_le_bytes());
        for _ in 0..n{
            for v in [0.0f32;5]{p.extend(v.to_le_bytes());}
            for u in [0xffff_ffffu32,15,0]{p.extend(u.to_le_bytes());}
        }
        p
    }
    #[test]fn replace_and_remove(){
        let mut w=World::default();w.ingest(2,&section(6)).unwrap();
        assert_eq!(w.triangles(),2);
        w.ingest(2,&section(3)).unwrap();assert_eq!(w.triangles(),1);
        w.ingest(2,&section(0)).unwrap();assert_eq!(w.triangles(),0);
    }
    #[test]fn atlas_region_and_clear(){
        let mut w=World::default();let mut a=Vec::new();
        a.extend(2u32.to_le_bytes());a.extend(2u32.to_le_bytes());a.extend([0u8;16]);
        w.ingest(1,&a).unwrap();
        let mut r=Vec::new();for v in [1u32,0,1,1]{r.extend(v.to_le_bytes());}
        r.extend([1u8,2,3,4]);w.ingest(7,&r).unwrap();
        assert_eq!(&w.atlas.as_ref().unwrap().rgba[4..8],&[1,2,3,4]);
        w.ingest(3,&[]).unwrap();assert!(w.atlas.is_some());
    }
    #[test]fn rejects_invalid_without_replacing(){
        let mut w=World::default();w.ingest(2,&section(3)).unwrap();
        assert_eq!(w.ingest(2,&section(4)),Err(PacketError::InvalidCount));
        assert_eq!(w.triangles(),1);
    }
}