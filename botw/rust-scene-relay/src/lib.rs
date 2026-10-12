//! Transport-only SkyCraft v11 -> BWC2 implementation.
//! Nothing here guesses the BOTW camera, HUD cutout or in-game memory address.
use std::collections::HashMap;

pub const MAGIC: u32 = 0x4359_4b53;
pub const VERSION: u32 = 11;
pub const RENDER_RING: usize = 0x20000 + (32 << 20) + 3 * (3840 * 2160 * 4);
pub const RING_BYTES: usize = 64 << 20;
pub const RING_DATA: usize = RING_BYTES - 0x80;
pub const MAP_BYTES: usize = RENDER_RING + RING_BYTES;
pub const VERT_BYTES: usize = 32;
pub const BWC2_MAX_VERTS: usize = 480;
pub const BWC2_MAGIC: u32 = 0x3243_5742;

fn u32_at(b: &[u8], o: usize) -> Option<u32> {
    Some(u32::from_le_bytes(b.get(o..o.checked_add(4)?)?.try_into().ok()?))
}
fn i32_at(b: &[u8], o: usize) -> Option<i32> {
    Some(i32::from_le_bytes(b.get(o..o.checked_add(4)?)?.try_into().ok()?))
}
fn f32_at(b: &[u8], o: usize) -> Option<f32> {
    Some(f32::from_bits(u32_at(b,o)?))
}
fn push_f32(b: &mut Vec<u8>, value:f32) { b.extend_from_slice(&value.to_le_bytes()); }
fn push_u32(b: &mut Vec<u8>, value:u32) { b.extend_from_slice(&value.to_le_bytes()); }
pub fn fnv1a(b: &[u8]) -> u32 {
    b.iter().fold(2166136261u32, |h, byte| (h ^ *byte as u32).wrapping_mul(16777619))
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Vertex {
    pub xyz: [f32;3],
    pub uv: [f32;2],
    pub tint: u32,
    pub light: u32,
    pub flags: u32,
}
impl Vertex {
    fn decode(b: &[u8]) -> Result<Self,String> {
        if b.len() != VERT_BYTES { return Err("vertex length".into()); }
        let out=Self {
            xyz:[f32_at(b,0).ok_or("x")?, f32_at(b,4).ok_or("y")?, f32_at(b,8).ok_or("z")?],
            uv:[f32_at(b,12).ok_or("u")?,f32_at(b,16).ok_or("v")?],
            tint:u32_at(b,20).ok_or("color")?,
            light:u32_at(b,24).ok_or("light")?,
            flags:u32_at(b,28).ok_or("flags")?,
        };
        if !out.xyz.iter().chain(&out.uv).all(|v| v.is_finite() && v.abs() < 100_000.0) {
            return Err("invalid vertex position/UV".into());
        }
        Ok(out)
    }
}
#[derive(Default)]
pub struct Scene {
    pub atlas_width: u32,
    pub atlas_height: u32,
    pub atlas_rgba: Vec<u8>,
    pub atlas_revision: u64,
    pub sections: HashMap<(i32,i32,i32), Vec<Vertex>>,
}
impl Scene {
    pub fn triangles(&self)->usize {
        self.sections.values().map(|v|v.len()/3).sum()
    }
    pub fn apply(&mut self, kind:u32, b:&[u8])->Result<(),String> {
        match kind {
            3 => { // REN_CLEAR_ALL
                if !b.is_empty() {return Err("unexpected clear body".into())}
                self.sections.clear();
            },
            1 => { // REN_ATLAS: dimensions + exact RGBA pixels
                let w=u32_at(b,0).ok_or("atlas width")?;
                let h=u32_at(b,4).ok_or("atlas height")?;
                if !(1..=8192).contains(&w) || !(1..=8192).contains(&h)
                    || b.len()!=8+(w as usize*h as usize*4) {
                    return Err("invalid atlas payload".into())
                }
                self.atlas_width=w; self.atlas_height=h;
                self.atlas_rgba=b[8..].to_vec();
                self.atlas_revision=self.atlas_revision.wrapping_add(1);
            },
            7 => { // REN_ATLAS_REGION: animated Minecraft texture pixels
                if b.len()<16 {return Err("short atlas region".into())}
                let x=u32_at(b,0).ok_or("region x")?;
                let y=u32_at(b,4).ok_or("region y")?;
                let w=u32_at(b,8).ok_or("region w")?;
                let h=u32_at(b,12).ok_or("region h")?;
                if w==0 || h==0 || x.checked_add(w).map_or(true,|n|n>self.atlas_width)
                    || y.checked_add(h).map_or(true,|n|n>self.atlas_height)
                    || b.len()!=16+(w as usize*h as usize*4)
                    || self.atlas_rgba.len()!=self.atlas_width as usize*self.atlas_height as usize*4 {
                    return Err("invalid atlas region bounds".into())
                }
                for row in 0..h as usize {
                    let dst=((y as usize+row)*self.atlas_width as usize+x as usize)*4;
                    let src=16+row*w as usize*4;
                    self.atlas_rgba[dst..dst+w as usize*4]
                        .copy_from_slice(&b[src..src+w as usize*4]);
                }
                self.atlas_revision=self.atlas_revision.wrapping_add(1);
            },
            2 => { // REN_SECTION: coordinates + real Minecraft triangles
                if b.len()<16 {return Err("short section".into())}
                let xyz=(i32_at(b,0).ok_or("sx")?,i32_at(b,4).ok_or("sy")?,
                         i32_at(b,8).ok_or("sz")?);
                let count=u32_at(b,12).ok_or("vertices")? as usize;
                if count>200_000 || count%3!=0
                    || [xyz.0,xyz.1,xyz.2].iter().any(|v|(*v as i64).abs()>100_000)
                    || b.len()!=16+count*VERT_BYTES {
                    return Err("invalid section length".into())
                }
                if count==0 {self.sections.remove(&xyz);}
                else {
                    let mut vertices=Vec::with_capacity(count);
                    for slice in b[16..].chunks_exact(VERT_BYTES) {
                        vertices.push(Vertex::decode(slice)?);
                    }
                    self.sections.insert(xyz,vertices);
                }
            },
            _ => {}, // avatars, particle, textures and light records are independent
        }
        Ok(())
    }
}

/// Decode only published SkyCraft ring records. Caller must be the ONLY
/// consumer and update the tail after processing, not before.
pub fn decode_ring(ring:&[u8], head:u64, mut tail:u64, max_packets:usize)
    -> Result<(Vec<(u32,Vec<u8>)>,u64),String> {
    if ring.len()!=RING_DATA || head<tail || head-tail>RING_DATA as u64 {
        return Err("ring cursor invalid or consumer lapped".into())
    }
    let mut out=Vec::new();
    for _ in 0..max_packets {
        if tail>=head {break}
        let pos=(tail%RING_DATA as u64) as usize;
        let remaining=RING_DATA-pos;
        if remaining<8 {tail+=remaining as u64;continue}
        let kind=u32_at(ring,pos).ok_or("packet type")?;
        let size=u32_at(ring,pos+4).ok_or("packet size")? as usize;
        if kind==0 {tail+=remaining as u64;continue}
        let bytes=size.checked_add(15).ok_or("length overflow")? & !7usize;
        if size>RING_DATA-8 || bytes>remaining || tail+bytes as u64>head {
            break; // not yet fully published or invalid; don't access beyond head
        }
        if matches!(kind,1|2|3|7) {
            out.push((kind,ring[pos+8..pos+8+size].to_vec()));
        }
        tail+=bytes as u64;
    }
    Ok((out,tail))
}

/// User supplied, MEASURED row-major 4x4 affine MC-world -> Hyrule-world mapping.
/// Not a projection matrix; the actual Zelda view/projection is the guest's job.
#[derive(Clone,Debug)]
pub struct Transform(pub [[f32;4];4]);
impl Transform {
    pub fn parse(text:&str)->Result<Self,String> {
        let floats:Vec<f32>=text.lines()
          .map(|line|line.split('#').next().unwrap_or(""))
          .flat_map(str::split_whitespace)
          .map(str::parse::<f32>)
          .collect::<Result<_,_>>().map_err(|_|"matrix contains invalid float")?;
        if floats.len()!=16 || floats.iter().any(|v|!v.is_finite()) {
            return Err("transform must contain 16 finite floats".into())
        }
        let mut m=[[0f32;4];4];
        for row in 0..4 {m[row].copy_from_slice(&floats[row*4..row*4+4]);}
        if m[3]!=[0.0,0.0,0.0,1.0] {
            return Err("last affine matrix row must be 0 0 0 1".into());
        }
        Ok(Self(m))
    }
    pub fn apply(&self,p:[f32;3])->[f32;3] {
        let dot=|r:usize|self.0[r][0]*p[0]+self.0[r][1]*p[1]+self.0[r][2]*p[2]+self.0[r][3];
        [dot(0),dot(1),dot(2)]
    }
}
/// BWC2 56-byte header, 32-byte vertices; matches botw/native_world_scene.hpp.
/// A debug packet contains <=480 vertices. Multiple pages prevent data loss.
pub fn encode_bwc2(frame:u32,vertices:&[(Vertex,[f32;3])],mc_origin:[f32;3],
                   hyrule_origin:[f32;3])->Result<Vec<u8>,String> {
    if vertices.len()>BWC2_MAX_VERTS || vertices.len()%3!=0 {
        return Err("BWC2 must contain 0..480 vertices in triples".into())
    }
    let mut body=Vec::with_capacity(vertices.len()*32);
    for (v,world_pos) in vertices {
        if !world_pos.iter().chain(&v.uv).all(|x|x.is_finite() && x.abs()<100_000.0) {
            return Err("out-of-range world vertex".into());
        }
        for x in world_pos.iter().chain(&v.uv) {push_f32(&mut body,*x);}
        for x in [v.tint,v.light,v.flags] {push_u32(&mut body,x);}
    }
    let mut result=Vec::with_capacity(56+body.len());
    for x in [BWC2_MAGIC,2,frame,vertices.len() as u32,fnv1a(&body),0,0,0] {
        push_u32(&mut result,x);
    }
    for x in mc_origin.into_iter().chain(hyrule_origin) {
        if !x.is_finite() {return Err("invalid origin".into());}
        push_f32(&mut result,x);
    }
    debug_assert_eq!(result.len(),56);
    result.extend_from_slice(&body);
    Ok(result)
}
pub fn world_pages(scene:&Scene,transform:&Transform,eye:[f32;3])
  -> Vec<Vec<(Vertex,[f32;3])>> {
    let mut sections:Vec<_>=scene.sections.iter().collect();
    sections.sort_by(|(a,_),(b,_)| {
        let distance=|p:&&(i32,i32,i32)| {
            let d=[p.0 as f32*16.0+8.0-eye[0],
                   p.1 as f32*16.0+8.0-eye[1],
                   p.2 as f32*16.0+8.0-eye[2]];
            d.iter().map(|v|v*v).sum::<f32>()
        };
        distance(a).total_cmp(&distance(b)).then(a.cmp(b))
    });
    let mut pages=Vec::new();let mut page=Vec::with_capacity(BWC2_MAX_VERTS);
    for (coords,triangles) in sections {
        for tri in triangles.chunks_exact(3) {
            if page.len()+3>BWC2_MAX_VERTS {
                pages.push(page);page=Vec::with_capacity(BWC2_MAX_VERTS);
            }
            for v in tri {
                let abs=[coords.0 as f32*16.0+v.xyz[0],
                         coords.1 as f32*16.0+v.xyz[1],
                         coords.2 as f32*16.0+v.xyz[2]];
                page.push((*v,transform.apply(abs)));
            }
        }
    }
    if !page.is_empty() {pages.push(page);}
    pages
}

#[cfg(test)]
mod tests {
    use super::*;
    fn vertex()->Vertex {Vertex{xyz:[1.,2.,3.],uv:[0.25,0.75],tint:0xFF_A0B0C0,light:15,flags:3}}
    #[test] fn real_uv_and_section_coordinates() {
        let t=Transform::parse("1 0 0 0\n0 1 0 0\n0 0 1 0\n0 0 0 1 # measured\n").unwrap();
        let mut s=Scene::default();s.sections.insert((2,-1,4),vec![vertex();3]);
        let pages=world_pages(&s,&t,[32.,0.,64.]);
        assert_eq!(pages[0][0].1,[33.,-14.,67.]);
        assert_eq!(pages[0][0].0.uv,[0.25,0.75]);
        let b=encode_bwc2(5,&pages[0],[1.,2.,3.],[4.,5.,6.]).unwrap();
        assert_eq!(b.len(),56+3*32);
        assert_eq!(u32_at(&b,0),Some(BWC2_MAGIC));
        assert_eq!(u32_at(&b,16),Some(fnv1a(&b[56..])));
    }
    #[test] fn rejects_bad_geometry() {
        let mut s=Scene::default();
        assert!(s.apply(1,&[0;8]).is_err());
        let mut invalid=Vec::new();
        for n in [0i32,0,0]{invalid.extend_from_slice(&n.to_le_bytes());}
        invalid.extend_from_slice(&3u32.to_le_bytes());
        invalid.extend_from_slice(&f32::NAN.to_le_bytes());
        invalid.resize(16+3*32,0);
        assert!(s.apply(2,&invalid).is_err());
    }
    #[test] fn packet_and_animated_atlas() {
        let mut s=Scene::default();
        let mut a=Vec::new();a.extend_from_slice(&2u32.to_le_bytes());
        a.extend_from_slice(&2u32.to_le_bytes());a.extend_from_slice(&[0;16]);
        s.apply(1,&a).unwrap();
        let mut sub=Vec::new();
        for n in [1u32,1,1,1]{sub.extend_from_slice(&n.to_le_bytes());}
        sub.extend_from_slice(&[12,34,56,78]);
        s.apply(7,&sub).unwrap();
        assert_eq!(&s.atlas_rgba[12..16],&[12,34,56,78]);
    }
    #[test] fn pages_do_not_silently_drop_triangles() {
        let mut s=Scene::default();
        s.sections.insert((0,0,0),vec![vertex();BWC2_MAX_VERTS+6]);
        let identity=Transform::parse("1 0 0 0\n0 1 0 0\n0 0 1 0\n0 0 0 1").unwrap();
        let pages=world_pages(&s,&identity,[0.,0.,0.]);
        assert_eq!(pages.len(),2);
        assert_eq!(pages[0].len(),BWC2_MAX_VERTS);
        assert_eq!(pages[1].len(),6);
    }
}
