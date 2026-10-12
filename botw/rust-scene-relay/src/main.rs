//! Safe, headless Windows diagnostic relay. The actual renderer is a separate
//! integration concern; never uses guessed Zelda FOV or injected guest memory.
use botwcraft_rust_scene_relay::{encode_bwc2,world_pages,Scene,Transform};
use std::{env,fs,io::{self,Write},path::{Path,PathBuf},thread,time::Duration};

#[cfg(windows)]
mod windows {
    use botwcraft_rust_scene_relay::{MAGIC,VERSION,MAP_BYTES,RENDER_RING,RING_BYTES,RING_DATA};
    use std::{ffi::c_void,ptr::{self,NonNull},slice,sync::atomic::{AtomicU64,Ordering}};
    #[link(name="kernel32")]
    extern "system" {
        fn OpenFileMappingW(access:u32,inherit:i32,name:*const u16)->*mut c_void;
        fn MapViewOfFile(mapping:*mut c_void,access:u32,hi:u32,lo:u32,size:usize)->*mut c_void;
        fn UnmapViewOfFile(ptr:*mut c_void)->i32;
        fn CloseHandle(handle:*mut c_void)->i32;
        pub fn GetTickCount64()->u64;
    }
    const ACCESS:u32=0xF001F;
    pub struct SharedMap {ptr:NonNull<u8>,handle:*mut c_void}
    impl SharedMap {
        pub fn open()->io::Result<Self>{
            let name:Vec<u16>="Local\\SkyCraft_v1".encode_utf16().chain(std::iter::once(0)).collect();
            unsafe {
                let handle=OpenFileMappingW(ACCESS,0,name.as_ptr());
                if handle.is_null(){return Err(std::io::Error::last_os_error());}
                let ptr=MapViewOfFile(handle,ACCESS,0,0,MAP_BYTES);
                match NonNull::new(ptr as *mut u8){
                    Some(ptr)=>Ok(Self{ptr,handle}),
                    None=>{
                        let e=std::io::Error::last_os_error();CloseHandle(handle);Err(e)
                    }
                }
            }
        }
        fn at(&self,off:usize)->*mut u8 {
            assert!(off<MAP_BYTES);
            unsafe{self.ptr.as_ptr().add(off)}
        }
        fn load32(&self,off:usize)->u32 {
            unsafe{ptr::read_volatile(self.at(off) as *const u32)}
        }
        fn load64(&self,off:usize)->u64 {
            unsafe{(*(self.at(off) as *const AtomicU64)).load(Ordering::Acquire)}
        }
        fn store64(&self,off:usize,n:u64){
            unsafe{(*(self.at(off) as *const AtomicU64)).store(n,Ordering::Release)}
        }
        pub fn valid(&self)->bool {self.load32(0)==MAGIC && self.load32(4)==VERSION}
        pub fn active(&self)->bool {
            let beat=self.load64(0x18);
            let now=unsafe{GetTickCount64()};
            beat!=0 && now>=beat && now-beat<3_500
        }
        pub fn mc_pos(&self)->Option<[f32;3]>{
            let seq=self.load32(0x200);
            if seq&1!=0 || self.load32(0x204)&1==0{return None;}
            let read=|off:usize| {
                let v=unsafe{ptr::read_volatile(self.at(off) as *const f64)};
                (v.is_finite() && v.abs()<100_000.0).then_some(v as f32)
            };
            let pos=[read(0x208)?,read(0x210)?,read(0x218)?];
            (self.load32(0x200)==seq).then_some(pos)
        }
        /// Read only the packet bytes actually published, not a 64MiB snapshot
        /// every frame. This process must be the ONLY RenderRing consumer.
        pub fn drain(&self,limit:usize)->Result<Vec<(u32,Vec<u8>)>,String>{
            let head=self.load64(RENDER_RING);
            let mut tail=self.load64(RENDER_RING+0x40);
            if head<tail || head-tail>RING_DATA as u64 {
                self.store64(RENDER_RING+0x40,head);
                return Err("RenderRing consumer was lapped; resynced".into());
            }
            let mut events=Vec::new();
            let mut n=0;
            while tail<head && n<limit {
                n+=1;
                let pos=(tail%RING_DATA as u64) as usize;
                let span=RING_DATA-pos;
                if span<8 {tail+=span as u64;continue;}
                let offset=RENDER_RING+0x80+pos;
                let kind=self.load32(offset);
                let payload=self.load32(offset+4) as usize;
                if kind==0 {tail+=span as u64;continue;}
                let bytes=match payload.checked_add(15) {
                    Some(v)=>v&!7usize,
                    None=>break,
                };
                if payload>RING_DATA-8 || bytes>span || tail+bytes as u64>head {
                    // Producer may still be writing, never access unpublished bytes.
                    break;
                }
                if matches!(kind,1|2|3|7) {
                    let mut buf=vec![0u8;payload];
                    if payload>0 {
                        unsafe{ptr::copy_nonoverlapping(self.at(offset+8),buf.as_mut_ptr(),payload);}
                    }
                    events.push((kind,buf));
                }
                tail+=bytes as u64;
            }
            self.store64(RENDER_RING+0x40,tail);
            Ok(events)
        }
    }
    impl Drop for SharedMap{
        fn drop(&mut self){
            unsafe{
                UnmapViewOfFile(self.ptr.as_ptr() as *mut c_void);
                CloseHandle(self.handle);
            }
        }
    }
    use std::io;
}
fn atomic_write(file:&Path,b:&[u8])->io::Result<()> {
    let name=file.file_name().ok_or_else(||io::Error::other("invalid path"))?
        .to_string_lossy().into_owned();
    let part=file.with_file_name(format!("{name}.{}.tmp",std::process::id()));
    let mut f=fs::File::create(&part)?;
    f.write_all(b)?;f.sync_all()?;drop(f);
    fs::rename(&part,file)
}
fn help(){
    println!("BotwCraft Rust scene relay — authentic SkyCraft render stream (BWC2)");
    println!("  --hz 20                 Diagnostic refresh (1..60)");
    println!("  --out PATH --transform PATH   Write offline BWC2 debug packets");
    println!("  --help                  Show this help");
    println!("  NOTE: No Ryujinx injection, no guessed projection, no GUI compositing.");
}
fn parse_args()->Result<(u64,Option<PathBuf>,Option<Transform>),String>{
    let mut args=env::args().skip(1);let mut hz=20;let mut output=None;let mut transform=None;
    while let Some(arg)=args.next() {
        match arg.as_str(){
            "--help"|"-h"=>{help();std::process::exit(0);}
            "--hz"=>{
                hz=args.next().ok_or("missing --hz value")?
                    .parse::<u64>().map_err(|_|"invalid --hz")?;
                if !(1..=60).contains(&hz){return Err("--hz must be 1..60".into());}
            }
            "--out"=>output=Some(PathBuf::from(args.next().ok_or("missing --out value")?)),
            "--transform"=>{
                let p=PathBuf::from(args.next().ok_or("missing --transform value")?);
                let body=fs::read_to_string(&p).map_err(|e|format!("{}: {e}",p.display()))?;
                transform=Some(Transform::parse(&body)?);
            }
            _=>return Err(format!("unknown option {arg}")),
        }
    }
    if output.is_some()!=transform.is_some(){
        return Err("debug output requires BOTH --out and --transform".into());
    }
    Ok((hz,output,transform))
}
#[cfg(windows)]
fn run(hz:u64,output:Option<PathBuf>,matrix:Option<Transform>)->Result<(),Box<dyn std::error::Error>>{
    use windows::SharedMap;
    let mut scene=Scene::default();
    let mut published_atlas_revision=u64::MAX;
    let mut frame=1u32;
    let mut last_report=std::time::Instant::now();
    if let Some(ref dir)=output {fs::create_dir_all(dir)?;}
    println!("Rust scene relay ready. Native injection OFF; no texture keying.");
    loop {
        let map=match SharedMap::open(){
            Ok(v)=>v,
            Err(_)=>{thread::sleep(Duration::from_secs(1));continue;}
        };
        if !map.valid(){
            eprintln!("SkyCraft shared mapping does not use v11");
            thread::sleep(Duration::from_secs(1));continue;
        }
        scene=Scene::default();published_atlas_revision=u64::MAX;
        while map.valid(){
            if map.active(){
                match map.drain(256){
                    Ok(events)=>for (kind,payload) in events {
                        if let Err(e)=scene.apply(kind,&payload){
                            eprintln!("Ignored invalid RenderRing packet {kind}: {e}");
                        }
                    },
                    Err(e)=>{eprintln!("{e}");scene=Scene::default();}
                };
                if let (Some(ref dir),Some(ref t),Some(eye))=
                    (output.as_ref(),matrix.as_ref(),map.mc_pos()) {
                    if scene.atlas_width>0 && scene.atlas_revision!=published_atlas_revision {
                        let mut atlas=Vec::with_capacity(8+scene.atlas_rgba.len());
                        atlas.extend_from_slice(&scene.atlas_width.to_le_bytes());
                        atlas.extend_from_slice(&scene.atlas_height.to_le_bytes());
                        atlas.extend_from_slice(&scene.atlas_rgba);
                        atomic_write(&dir.join("atlas.rgba"),&atlas)?;
                        published_atlas_revision=scene.atlas_revision;
                    }
                    let pages=world_pages(&scene,t,eye);
                    for (i,page) in pages.iter().enumerate() {
                        let name=format!("world_{i:04}.bwc2");
                        let body=encode_bwc2(frame,page,eye,t.apply(eye))?;
                        atomic_write(&dir.join(name),&body)?;
                    }
                    // Debug format may have multiple packet pages. Native guest
                    // cannot consume these pages without a separate integration.
                    frame=frame.wrapping_add(1).max(1);
                }
                if last_report.elapsed()>=Duration::from_secs(10){
                    println!("Minecraft: {} sections, {} triangles, atlas {}x{}, BWC2 debug only",
                        scene.sections.len(),scene.triangles(),
                        scene.atlas_width,scene.atlas_height);
                    last_report=std::time::Instant::now();
                }
            }
            thread::sleep(Duration::from_millis(1000/hz));
        }
    }
}
fn main()->Result<(),Box<dyn std::error::Error>>{
    let (hz,output,matrix)=parse_args()?;
    #[cfg(windows)]
    {run(hz,output,matrix)}
    #[cfg(not(windows))]
    {
        let _=(hz,output,matrix);
        Err("Windows required for SkyCraft named memory mapping".into())
    }
}
