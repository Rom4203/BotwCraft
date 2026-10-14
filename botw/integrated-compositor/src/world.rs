//! SkyCraft's actual REN_SECTION / REN_ATLAS triangle pipeline rendered in the
//! SAME WGPU compositor as the Zelda image and the Minecraft HUD.
//! No Minecraft world screenshot, window overlay or synthetic cubes.
//! Zelda's native depth is not available here; depth handles MC against MC.
use std::{ffi::c_void,mem,ptr, sync::{Arc,Mutex,atomic::{AtomicU64,Ordering}}, time::{Duration,Instant}};
use eframe::{egui,egui_wgpu};
use crate::terrain_depth::TerrainDepth;
use wgpu::util::DeviceExt;
use botwcraft_rust_scene_relay::{Scene,MAP_BYTES,MAGIC,VERSION,RENDER_RING,RING_DATA};

const WIDTH:u32=1280;
const HEIGHT:u32=720;
const MC:usize=0x200;
const CAM_VALID:u32=0x40000;
const MAX_VERTS:usize=300_000;
const RANGE:f32=128.0;

#[link(name="kernel32")]
unsafe extern "system" {
 fn OpenFileMappingW(access:u32,inherit:i32,name:*const u16)->isize;
 fn MapViewOfFile(handle:isize,access:u32,hi:u32,lo:u32,bytes:usize)->*mut c_void;
 fn UnmapViewOfFile(base:*const c_void)->i32;
 fn CloseHandle(handle:isize)->i32;
 fn GetTickCount64()->u64;
}
struct Map {handle:isize,base:*const u8}
impl Drop for Map {fn drop(&mut self){unsafe {UnmapViewOfFile(self.base.cast());CloseHandle(self.handle);}}}
impl Map {
 fn open()->Option<Self> {
   let name:Vec<u16>="Local\\SkyCraft_v1".encode_utf16().chain(Some(0)).collect();
   unsafe {
     let handle=OpenFileMappingW(6,0,name.as_ptr());
     if handle==0 {return None;}
     let base=MapViewOfFile(handle,6,0,0,MAP_BYTES) as *const u8;
     if base.is_null(){CloseHandle(handle);return None;}
     let out=Self{handle,base};
     if out.u32(0)!=MAGIC || out.u32(4)!=VERSION{return None;}
     Some(out)
   }
 }
 fn ptr(&self,off:usize,len:usize)->Option<*const u8>{
   (off<=MAP_BYTES && len<=MAP_BYTES-off).then(||unsafe{self.base.add(off)})
 }
 fn u32(&self,off:usize)->u32{self.ptr(off,4).map_or(0,|p|unsafe{ptr::read_unaligned(p.cast())})}
 fn f32(&self,off:usize)->f32{f32::from_bits(self.u32(off))}
 fn f64(&self,off:usize)->f64{self.ptr(off,8).map_or(0.,|p|unsafe{ptr::read_unaligned(p.cast())})}
 fn u64(&self,off:usize)->u64{self.ptr(off,8).map_or(0,|p|unsafe{(*(p as *const AtomicU64)).load(Ordering::Acquire)})}
 fn set_tail(&self,v:u64){
   if let Some(p)=self.ptr(RENDER_RING+0x40,8){
     unsafe{(*(p as *const AtomicU64)).store(v,Ordering::Release);}
   }
 }
 fn camera(&self)->Option<Camera>{
   const B:usize=0x980;
   let now=unsafe{GetTickCount64()};
   let seq=self.u32(B+4);
   if seq==0 || seq&1!=0 || self.u32(B)!=0x31575642 {return None;}
   let stamp=self.u64(B+8);
   if stamp==0 || now<stamp || now-stamp>200{return None;}
   if self.u32(B+20)&1==0 {return None;}
   let eye=[self.f32(B+24),self.f32(B+28),self.f32(B+32)];
   let forward=[self.f32(B+36),self.f32(B+40),self.f32(B+44)];
   let mut view=[0f32;12];
   for (i,v) in view.iter_mut().enumerate(){*v=self.f32(B+48+i*4);}
   let mc_origin=[self.f32(B+96),self.f32(B+100),self.f32(B+104)];
   let zelda_origin=[self.f32(B+108),self.f32(B+112),self.f32(B+116)];
   // Never use MC yaw, pitch, FOV or virtual third-person camera here.
   if self.u32(B+4)!=seq{return None;}
   if !eye.iter().chain(&forward).chain(&view).chain(&mc_origin)
     .chain(&zelda_origin).all(|f|f.is_finite()&&f.abs()<100_000.){return None;}
   let shift=std::array::from_fn(|i|zelda_origin[i]-mc_origin[i]);
   // Mat34's third row usually points backwards (OpenGL right-handed).
   // Determine the game-native sign, not Minecraft's look angles.
   let alignment=view[8]*forward[0]+view[9]*forward[1]+view[10]*forward[2];
   if alignment.abs()<0.5||alignment.abs()>1.5 {return None;}
   let depth_sign=alignment.signum();
   // Verify the native view really transforms the native camera's eye to zero.
   let camera_space: [f32;3]=std::array::from_fn(|r|{
     view[r*4]*eye[0]+view[r*4+1]*eye[1]+view[r*4+2]*eye[2]+view[r*4+3]
   });
   if camera_space.iter().any(|c|c.abs()>2.) {return None;}
   Some(Camera{eye,view,shift,depth_sign})
 }
 /// Consume bounded complete packets. Exactly one consumer advances the tail.
 /// Renderer never reads stale or unpublished data.
 fn drain(&self,scene:&mut Scene)->(bool,bool){
   let head=self.u64(RENDER_RING);
   let mut tail=self.u64(RENDER_RING+0x40);
   if head<tail || head-tail>RING_DATA as u64{
     self.set_tail(head);scene.sections.clear();return (true,false);
   }
   let mut geometry=false;
   let mut atlas=false;
   for _ in 0..192 {
     if tail>=head {break;}
     let ring_pos=(tail%RING_DATA as u64) as usize;
     let remain=RING_DATA-ring_pos;
     if remain<8 {tail+=remain as u64;continue;}
     let off=RENDER_RING+0x80+ring_pos;
     let kind=self.u32(off);
     let size=self.u32(off+4) as usize;
     if kind==0{tail+=remain as u64;continue;}
     let Some(bytes)=size.checked_add(15).map(|x|x&!7) else {break};
     if size>32<<20 || bytes>remain || bytes as u64>head-tail {break;}
     if matches!(kind,1|2|3|7){
       if let Some(p)=self.ptr(off+8,size){
         let input=unsafe{std::slice::from_raw_parts(p,size)};
         if scene.apply(kind,input).is_ok() {
           geometry|=kind==2||kind==3;
           atlas|=kind==1||kind==7;
         }
       }
     }
     tail+=bytes as u64;
   }
   self.set_tail(tail);
   (geometry,atlas)
 }
}
#[derive(Clone,Copy)]
pub(super) struct Camera{pub(super) eye:[f32;3],view:[f32;12],shift:[f32;3],depth_sign:f32}
#[repr(C)]
#[derive(Clone,Copy,bytemuck::Pod,bytemuck::Zeroable)]
struct GpuVertex{xyz:[f32;3],uv:[f32;2],tint:u32,light:u32,flags:u32}
const _:()=assert!(mem::size_of::<GpuVertex>()==32);
#[repr(C)]
#[derive(Clone,Copy,bytemuck::Pod,bytemuck::Zeroable)]
struct CameraUniform{
 offset:[f32;4], right:[f32;4], up:[f32;4], forward:[f32;4],lens:[f32;4],
}
fn uniform(cam:Camera)->CameraUniform{
 // Zelda controls the VIEW. Its optical projection is still opaque to the
 // WiiXLaunch API, so use a fixed 70 degree baseline, NEVER Minecraft's FOV.
 // This calibration remains approximate until Ryujinx exposes P/depth.
 const ZELDA_VERTICAL_FOV:f32=70.0;
 let cot=1./(ZELDA_VERTICAL_FOV.to_radians()*0.5).tan();
 CameraUniform{
   offset:[cam.shift[0],cam.shift[1],cam.shift[2],0.],
   right:cam.view[0..4].try_into().unwrap(),
   up:cam.view[4..8].try_into().unwrap(),
   forward:cam.view[8..12].try_into().unwrap(),
   lens:[cot,WIDTH as f32/HEIGHT as f32,cam.depth_sign,0.05],
 }
}
#[derive(Clone)]
struct Snapshot {
 cam:Option<Camera>,
 mesh:Arc<Vec<GpuVertex>>,mesh_rev:u64,
 atlas:Arc<Vec<u8>>,atlas_w:u32,atlas_h:u32,atlas_rev:u64,
 occlusion:Arc<Vec<[f32;3]>>,occlusion_rev:u64,occlusion_tiles:usize,
}
impl Default for Snapshot{
 fn default()->Self{Self{cam:None,mesh:Arc::new(vec![]),mesh_rev:0,
   atlas:Arc::new(vec![]),atlas_w:0,atlas_h:0,atlas_rev:0,
   occlusion:Arc::new(vec![]),occlusion_rev:0,occlusion_tiles:0}}
}
pub struct Layer {
 map:Option<Map>,scene:Scene,last_try:Instant,
 last_mesh_eye:Option<[f32;3]>,
 // MC -> Hyrule is a fixed WORLD registration, never recalculated while
 // the player turns their head or walks. Coordinates of placed blocks are
 // owned by Minecraft sections, not the player's camera/hand.
 locked_world_offset:Option<[f32;3]>,
 last_valid_view:Option<Instant>,
 last_origin_report:Instant,
 depth:TerrainDepth,
 frame:Arc<Mutex<Snapshot>>, pub id:egui::TextureId,
}
impl Layer {
 pub fn new(cc:&eframe::CreationContext<'_>)->Self{
   let rs=cc.wgpu_render_state.as_ref().expect("WGPU renderer required");
   let gpu=Gpu::new(&rs.device);
   let id=rs.renderer.write().register_native_texture(&rs.device,&gpu.color_view,wgpu::FilterMode::Linear);
   rs.renderer.write().callback_resources.insert(gpu);
   Self{map:None,scene:Scene::default(),last_mesh_eye:None,
     locked_world_offset:None,last_valid_view:None,
     last_origin_report:Instant::now()-Duration::from_secs(5),
     depth:TerrainDepth::new(),
     last_try:Instant::now()-Duration::from_secs(3),
     frame:Arc::new(Mutex::new(Snapshot::default())),id}
 }
 pub fn tick(&mut self){
   if self.map.is_none()&&self.last_try.elapsed()>=Duration::from_secs(1){
     self.last_try=Instant::now();self.map=Map::open();
   }
   let mut snap=self.frame.lock().unwrap();
   let Some(map)=&self.map else {snap.cam=None;return;};
   if map.u32(0)!=MAGIC||map.u32(4)!=VERSION{
     self.map=None;self.scene=Scene::default();self.last_mesh_eye=None;
     self.locked_world_offset=None;self.last_valid_view=None;
     snap.cam=None;return;
   }
   // The bridge sends its native camera matrix independently of the
   // Minecraft section mesh ring. The registration of the two WORLDS must
   // remain immutable for all placed blocks within a connected session.
   // In earlier builds each incoming (possibly delayed) host pose carried
   // a fresh shift, so whole chunks could appear to slide with the player.
   let current=map.camera();
   if let Some(mut cam)=current {
     let locked=*self.locked_world_offset.get_or_insert(cam.shift);
     let d2=(0..3).map(|i|(locked[i]-cam.shift[i]).powi(2)).sum::<f32>();
     if d2>0.25 && self.last_origin_report.elapsed()>Duration::from_secs(5){
        eprintln!("[BOTWCRAFT_WORLD_LOCK] Ignoring moving world origin: drift={:.2}m; placed blocks stay at their original Hyrule coordinates",d2.sqrt());
        self.last_origin_report=Instant::now();
     }
     cam.shift=locked;
     self.last_valid_view=Some(Instant::now());
     snap.cam=Some(cam);
   }else{
     snap.cam=None;
     if self.last_valid_view.is_some_and(|t|t.elapsed()>Duration::from_secs(5)){
       // A disconnected/restarted Ryujinx world may legitimately have a
       // new origin. Re-register once after the session actually stops.
       self.locked_world_offset=None;
       self.last_valid_view=None;
       self.last_mesh_eye=None;
     }
   }
   self.depth.tick(snap.cam);
   if let Ok(frame)=self.depth.shared.try_lock(){
     if frame.revision!=snap.occlusion_rev {
       snap.occlusion=frame.vertices.clone();snap.occlusion_rev=frame.revision;
       snap.occlusion_tiles=frame.tiles;
     }
   }
   // No active MC camera -> don't render ghost blocks over the Zelda menu.
   let (mesh_changed,atlas_changed)=map.drain(&mut self.scene);
   // Rebuild when the native camera first appears OR crosses the 32-block
   // culling-cell margin. The mesh stream may arrive before Zelda's hook.
   let mc_eye=snap.cam.map(|cam:Camera|
     std::array::from_fn(|i|cam.eye[i]-cam.shift[i]));
   let culling_changed=match (self.last_mesh_eye,mc_eye){
     (None,Some(_))=>true,
     (Some(last),Some(now))=>(0..3).map(|i|(last[i]-now[i]).powi(2)).sum::<f32>()>32.0f32.powi(2),
     (Some(_),None)=>true,
     _=>false,
   };
   if mesh_changed||culling_changed {
     let eye=mc_eye.unwrap_or([0.;3]);
     self.last_mesh_eye=mc_eye;
     let mut sections:Vec<_>=self.scene.sections.iter().filter_map(|(pos,vertices)|{
       let origin=[pos.0 as f32*16.,pos.1 as f32*16.,pos.2 as f32*16.];
       let d=(0..3).map(|i|(origin[i]+8.-eye[i]).powi(2)).sum::<f32>();
       (d<(RANGE+16.).powi(2)).then_some((d,pos,vertices))
     }).collect();
     sections.sort_by(|a,b|a.0.total_cmp(&b.0).then(a.1.cmp(b.1)));
     let mut gpu=Vec::new();
     'mesh:for (_,pos,verts) in sections{
       let origin=[pos.0 as f32*16.,pos.1 as f32*16.,pos.2 as f32*16.];
       for triple in verts.chunks_exact(3){
         if gpu.len()+3>MAX_VERTS{break 'mesh;}
         for v in triple {
           gpu.push(GpuVertex{
             xyz:[origin[0]+v.xyz[0],origin[1]+v.xyz[1],origin[2]+v.xyz[2]],
             uv:v.uv,tint:v.tint,light:v.light,flags:v.flags,
           });
         }
       }
     }
     snap.mesh=Arc::new(gpu);
     snap.mesh_rev=snap.mesh_rev.wrapping_add(1);
   }
   if atlas_changed {
     snap.atlas=Arc::new(self.scene.atlas_rgba.clone());
     snap.atlas_w=self.scene.atlas_width;snap.atlas_h=self.scene.atlas_height;
     snap.atlas_rev=snap.atlas_rev.wrapping_add(1);
   }
 }
 pub fn schedule(&self,painter:&egui::Painter,rect:egui::Rect){
   painter.add(egui_wgpu::Callback::new_paint_callback(rect, WorldCallback{frame:self.frame.clone()}));
   painter.image(self.id,rect,egui::Rect::from_min_max(egui::Pos2::ZERO,egui::pos2(1.,1.)),
     egui::Color32::WHITE);
 }
}
struct WorldCallback{frame:Arc<Mutex<Snapshot>>}
impl egui_wgpu::CallbackTrait for WorldCallback {
 fn prepare(&self,device:&wgpu::Device,queue:&wgpu::Queue,
   _: &egui_wgpu::ScreenDescriptor,encoder:&mut wgpu::CommandEncoder,
   resources:&mut egui_wgpu::CallbackResources)->Vec<wgpu::CommandBuffer>{
   let data=self.frame.lock().unwrap().clone();
   let gpu=resources.get_mut::<Gpu>().expect("Minecraft 3D renderer registered");
   gpu.prepare(device,queue,encoder,&data);
   vec![]
 }
 fn paint(&self,_:egui::PaintCallbackInfo,_:&mut wgpu::RenderPass<'static>,_:&egui_wgpu::CallbackResources){}
}
struct Gpu{
 color_view:wgpu::TextureView,depth_view:wgpu::TextureView,
 pipeline:wgpu::RenderPipeline,
 occluder_pipeline:wgpu::RenderPipeline,layout:wgpu::BindGroupLayout,
 bind_group:wgpu::BindGroup,uniform:wgpu::Buffer,
 sampler:wgpu::Sampler,vertices:wgpu::Buffer,vertex_count:u32,mesh_rev:u64,atlas_rev:u64,
 depth_vertices:wgpu::Buffer,depth_count:u32,depth_rev:u64,
}
impl Gpu {
 fn new(device:&wgpu::Device)->Self{
   let make=|label,fmt,usage|{
     device.create_texture(&wgpu::TextureDescriptor{label:Some(label),
       size:wgpu::Extent3d{width:WIDTH,height:HEIGHT,depth_or_array_layers:1},
       mip_level_count:1,sample_count:1,dimension:wgpu::TextureDimension::D2,
       format:fmt,usage,view_formats:&[]})
   };
   let color=make("True SkyCraft blocks RGBA 3D",
       wgpu::TextureFormat::Rgba8UnormSrgb,
       wgpu::TextureUsages::RENDER_ATTACHMENT|wgpu::TextureUsages::TEXTURE_BINDING);
   let depth=make("Minecraft triangle depth",wgpu::TextureFormat::Depth24Plus,
       wgpu::TextureUsages::RENDER_ATTACHMENT);
   let color_view=color.create_view(&Default::default());
   let depth_view=depth.create_view(&Default::default());
   let uniform=device.create_buffer(&wgpu::BufferDescriptor{
     label:Some("SkyCraft camera matrix"),size:mem::size_of::<CameraUniform>() as u64,
     usage:wgpu::BufferUsages::UNIFORM|wgpu::BufferUsages::COPY_DST,mapped_at_creation:false});
   let sampler=device.create_sampler(&wgpu::SamplerDescriptor{
     label:Some("Minecraft pixel texture atlas"), mag_filter:wgpu::FilterMode::Nearest,
     min_filter:wgpu::FilterMode::Nearest,mipmap_filter:wgpu::FilterMode::Nearest,..Default::default()});
   let layout=device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor{
     label:Some("Minecraft world texture/materials"),entries:&[
     wgpu::BindGroupLayoutEntry{binding:0,visibility:wgpu::ShaderStages::VERTEX,
       ty:wgpu::BindingType::Buffer{ty:wgpu::BufferBindingType::Uniform,has_dynamic_offset:false,min_binding_size:None},count:None},
     wgpu::BindGroupLayoutEntry{binding:1,visibility:wgpu::ShaderStages::FRAGMENT,
       ty:wgpu::BindingType::Texture{sample_type:wgpu::TextureSampleType::Float{filterable:true},
         view_dimension:wgpu::TextureViewDimension::D2,multisampled:false},count:None},
     wgpu::BindGroupLayoutEntry{binding:2,visibility:wgpu::ShaderStages::FRAGMENT,
       ty:wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering),count:None},
   ]});
   let white=device.create_texture(&wgpu::TextureDescriptor{label:Some("Atlas fallback"),
     size:wgpu::Extent3d{width:1,height:1,depth_or_array_layers:1},mip_level_count:1,sample_count:1,
     dimension:wgpu::TextureDimension::D2,format:wgpu::TextureFormat::Rgba8UnormSrgb,
     usage:wgpu::TextureUsages::TEXTURE_BINDING|wgpu::TextureUsages::COPY_DST,view_formats:&[]});
   let view=white.create_view(&Default::default());
   let bind_group=Self::bind(device,&layout,&uniform,&sampler,&view);
   let shader=device.create_shader_module(wgpu::ShaderModuleDescriptor{
     label:Some("WorldExporter original SkyCraft triangles"),
     source:wgpu::ShaderSource::Wgsl(include_str!("../shaders/world.wgsl").into())});
   let p_layout=device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor{
     label:Some("Minecraft native geometry render"),bind_group_layouts:&[&layout],push_constant_ranges:&[]});
   let pipeline=device.create_render_pipeline(&wgpu::RenderPipelineDescriptor{
     label:Some("Minecraft 3D atlas geometry"),
     layout:Some(&p_layout),
     vertex:wgpu::VertexState{module:&shader,entry_point:Some("vs_main"),
       compilation_options:Default::default(),buffers:&[wgpu::VertexBufferLayout{
         array_stride:32,step_mode:wgpu::VertexStepMode::Vertex,
         attributes:&wgpu::vertex_attr_array![0=>Float32x3,1=>Float32x2,2=>Uint32,3=>Uint32,4=>Uint32]}]},
     primitive:wgpu::PrimitiveState{topology:wgpu::PrimitiveTopology::TriangleList,
       front_face:wgpu::FrontFace::Ccw,cull_mode:None,..Default::default()},
     depth_stencil:Some(wgpu::DepthStencilState{format:wgpu::TextureFormat::Depth24Plus,
       depth_write_enabled:true,depth_compare:wgpu::CompareFunction::LessEqual,
       stencil:Default::default(),bias:Default::default()}),
     multisample:Default::default(),fragment:Some(wgpu::FragmentState{
       module:&shader,entry_point:Some("fs_main"),compilation_options:Default::default(),
       targets:&[Some(wgpu::ColorTargetState{format:wgpu::TextureFormat::Rgba8UnormSrgb,
         blend:Some(wgpu::BlendState::PREMULTIPLIED_ALPHA_BLENDING),write_mask:wgpu::ColorWrites::ALL})]}),
     multiview:None,cache:None});
   // TRUE native Zelda collision geometry: write only depth, NOT pixels.
   // This occludes Minecraft behind real terrain, rocks and buildings.
   // It is a geometry-depth PROXY, not Ryujinx's original NVN depth target.
   let occluder_pipeline=device.create_render_pipeline(&wgpu::RenderPipelineDescriptor{
     label:Some("Zelda BTRI real terrain and static decor depth-only"),
     layout:Some(&p_layout),
     vertex:wgpu::VertexState{module:&shader,entry_point:Some("vs_zelda_depth"),
       compilation_options:Default::default(),buffers:&[wgpu::VertexBufferLayout{
         array_stride:12,step_mode:wgpu::VertexStepMode::Vertex,
         attributes:&wgpu::vertex_attr_array![0=>Float32x3]}]},
     primitive:wgpu::PrimitiveState{topology:wgpu::PrimitiveTopology::TriangleList,
       cull_mode:None,..Default::default()},
     depth_stencil:Some(wgpu::DepthStencilState{format:wgpu::TextureFormat::Depth24Plus,
       depth_write_enabled:true,depth_compare:wgpu::CompareFunction::LessEqual,
       stencil:Default::default(),bias:Default::default()}),
     multisample:Default::default(),fragment:Some(wgpu::FragmentState{
       module:&shader,entry_point:Some("fs_occluder"),compilation_options:Default::default(),
       targets:&[Some(wgpu::ColorTargetState{format:wgpu::TextureFormat::Rgba8UnormSrgb,
         blend:None,write_mask:wgpu::ColorWrites::empty()})]}),
     multiview:None,cache:None});
   let depth_vertices=device.create_buffer(&wgpu::BufferDescriptor{
     label:Some("Empty native Zelda occluder"),
     size:12,usage:wgpu::BufferUsages::VERTEX,mapped_at_creation:false});
   let vertices=device.create_buffer(&wgpu::BufferDescriptor{
     label:Some("Empty Minecraft mesh"),size:32,usage:wgpu::BufferUsages::VERTEX,mapped_at_creation:false});
   Self{color_view,depth_view,pipeline,occluder_pipeline,layout,bind_group,uniform,sampler,
     vertices,vertex_count:0,mesh_rev:u64::MAX,atlas_rev:u64::MAX,
     depth_vertices,depth_count:0,depth_rev:u64::MAX}
 }
 fn bind(device:&wgpu::Device,layout:&wgpu::BindGroupLayout,uniform:&wgpu::Buffer,sampler:&wgpu::Sampler,view:&wgpu::TextureView)->wgpu::BindGroup{
   device.create_bind_group(&wgpu::BindGroupDescriptor{label:Some("Minecraft atlas/camera"),
     layout,entries:&[
       wgpu::BindGroupEntry{binding:0,resource:uniform.as_entire_binding()},
       wgpu::BindGroupEntry{binding:1,resource:wgpu::BindingResource::TextureView(view)},
       wgpu::BindGroupEntry{binding:2,resource:wgpu::BindingResource::Sampler(sampler)}]})
 }
 fn prepare(&mut self,device:&wgpu::Device,queue:&wgpu::Queue,
       encoder:&mut wgpu::CommandEncoder,snap:&Snapshot){
   if snap.occlusion_rev!=self.depth_rev {
     self.depth_rev=snap.occlusion_rev;
     self.depth_count=snap.occlusion.len() as u32;
     if !snap.occlusion.is_empty(){
       self.depth_vertices=device.create_buffer_init(&wgpu::util::BufferInitDescriptor{
         label:Some("Genuine BOTW terrain collision triangles depth-only"),
         contents:bytemuck::cast_slice(snap.occlusion.as_slice()),
         usage:wgpu::BufferUsages::VERTEX});
     }
   }
   if snap.mesh_rev!=self.mesh_rev {
     self.mesh_rev=snap.mesh_rev;self.vertex_count=snap.mesh.len() as u32;
     if !snap.mesh.is_empty(){
       self.vertices=device.create_buffer_init(&wgpu::util::BufferInitDescriptor{
         label:Some("Real Minecraft section triangles"),
         contents:bytemuck::cast_slice(&snap.mesh),usage:wgpu::BufferUsages::VERTEX});
     }
   }
   if snap.atlas_rev!=self.atlas_rev && snap.atlas_w>0 && snap.atlas_h>0
       && snap.atlas.len()==snap.atlas_w as usize*snap.atlas_h as usize*4 {
     let texture=device.create_texture(&wgpu::TextureDescriptor{
       label:Some("Real Minecraft RGBA atlas"),
       size:wgpu::Extent3d{width:snap.atlas_w,height:snap.atlas_h,depth_or_array_layers:1},
       mip_level_count:1,sample_count:1,dimension:wgpu::TextureDimension::D2,
       format:wgpu::TextureFormat::Rgba8UnormSrgb,
       usage:wgpu::TextureUsages::TEXTURE_BINDING|wgpu::TextureUsages::COPY_DST,view_formats:&[]});
     queue.write_texture(wgpu::TexelCopyTextureInfo{texture:&texture,mip_level:0,
       origin:wgpu::Origin3d::ZERO,aspect:wgpu::TextureAspect::All},
       &snap.atlas,wgpu::TexelCopyBufferLayout{offset:0,bytes_per_row:Some(snap.atlas_w*4),
       rows_per_image:Some(snap.atlas_h)},
       wgpu::Extent3d{width:snap.atlas_w,height:snap.atlas_h,depth_or_array_layers:1});
     self.bind_group=Self::bind(device,&self.layout,&self.uniform,&self.sampler,
       &texture.create_view(&Default::default()));
     self.atlas_rev=snap.atlas_rev;
   }
   if let Some(cam)=snap.cam{
     queue.write_buffer(&self.uniform,0,bytemuck::bytes_of(&uniform(cam)));
   }
   let mut pass=encoder.begin_render_pass(&wgpu::RenderPassDescriptor{
     label:Some("Actual Minecraft 3D section meshes (one compositor frame)"),
     color_attachments:&[Some(wgpu::RenderPassColorAttachment{view:&self.color_view,
       resolve_target:None,depth_slice:None,ops:wgpu::Operations{
         load:wgpu::LoadOp::Clear(wgpu::Color::TRANSPARENT),store:wgpu::StoreOp::Store}})],
     depth_stencil_attachment:Some(wgpu::RenderPassDepthStencilAttachment{view:&self.depth_view,
       depth_ops:Some(wgpu::Operations{load:wgpu::LoadOp::Clear(1.),store:wgpu::StoreOp::Store}),
       stencil_ops:None}),
     timestamp_writes:None,occlusion_query_set:None});
   if snap.cam.is_some() && self.depth_count>0 && snap.occlusion_tiles>0 {
     pass.set_pipeline(&self.occluder_pipeline);
     pass.set_bind_group(0,&self.bind_group,&[]);
     pass.set_vertex_buffer(0,self.depth_vertices.slice(..));
     pass.draw(0..self.depth_count,0..1);
   }
   if snap.cam.is_some() && self.vertex_count>0 && snap.atlas_w>0 {
     pass.set_pipeline(&self.pipeline);pass.set_bind_group(0,&self.bind_group,&[]);
     pass.set_vertex_buffer(0,self.vertices.slice(..));pass.draw(0..self.vertex_count,0..1);
   }
 }
}
#[cfg(test)]
mod tests {
 use super::*;
 #[test]fn native_zeldaview_is_unaffected_by_minecraft_fov(){
   let cam=Camera{eye:[11.,21.,31.],view:[1.,0.,0.,-11.,0.,1.,0.,-21.,0.,0.,1.,-31.],
     shift:[100.,200.,300.],depth_sign:1.};
   let u=uniform(cam);
   assert_eq!(u.right,[1.,0.,0.,-11.]);
   assert_eq!(u.up,[0.,1.,0.,-21.]);
   assert_eq!(u.offset,[100.,200.,300.,0.]);
   assert!((u.lens[0]-1.4281).abs()<0.001);
 }
}
