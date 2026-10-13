//! SkyCraft's actual REN_SECTION / REN_ATLAS triangle pipeline rendered in the
//! SAME WGPU compositor as the Zelda image and the Minecraft HUD.
//! No Minecraft world screenshot, window overlay or synthetic cubes.
//! Zelda's native depth is not available here; depth handles MC against MC.
use std::{ffi::c_void,mem,ptr, sync::{Arc,Mutex,atomic::{AtomicU64,Ordering}}, time::{Duration,Instant}};
use eframe::{egui,egui_wgpu};
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
     unsafe{(*(p as *const AtomicU64 as *mut AtomicU64)).as_ref().unwrap().store(v,Ordering::Release);}
   }
 }
 fn camera(&self)->Option<Camera>{
   let now=unsafe{GetTickCount64()};
   let beat=self.u64(0x18);
   if beat==0 || now<beat || now-beat>2000{return None;}
   for _ in 0..5 {
     let seq=self.u32(MC);
     if seq&1!=0{continue;}
     let flags=self.u32(MC+4);
     if flags&1==0{return None;}
     let player=[self.f64(MC+8),self.f64(MC+16),self.f64(MC+24)];
     let yaw=self.f32(MC+32);let pitch=self.f32(MC+36);
     let fov=self.f32(MC+64);
     let mode=self.u32(MC+0xC0);
     let optical=[self.f64(MC+0x50),self.f64(MC+0x58),self.f64(MC+0x60)];
     let verified=flags&CAM_VALID!=0 && mode<=2 && optical.iter().chain(&player)
       .all(|n|n.is_finite()&&n.abs()<100000.)
       && (0..3).map(|i|(optical[i]-player[i]).powi(2)).sum::<f64>()<1024.;
     if self.u32(MC)!=seq {continue;}
     if !player.iter().all(|n|n.is_finite()&&n.abs()<100000.)||!yaw.is_finite()||!pitch.is_finite(){return None;}
     let mut angle=yaw;
     let mut slope=pitch;
     if verified && mode==2 {angle+=180.;slope=-slope;}
     let eye=if verified {optical} else {[player[0],player[1]+1.62,player[2]]};
     return Some(Camera{eye:eye.map(|v|v as f32),angle,slope,
       fov:if (25.0..=130.0).contains(&fov){fov}else{70.}});
   }
   None
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
struct Camera{eye:[f32;3],angle:f32,slope:f32,fov:f32}
#[repr(C)]
#[derive(Clone,Copy,bytemuck::Pod,bytemuck::Zeroable)]
struct GpuVertex{xyz:[f32;3],uv:[f32;2],tint:u32,light:u32,flags:u32}
const _:()=assert!(mem::size_of::<GpuVertex>()==32);
#[repr(C)]
#[derive(Clone,Copy,bytemuck::Pod,bytemuck::Zeroable)]
struct CameraUniform{eye:[f32;4],right:[f32;4],up:[f32;4],forward:[f32;4],lens:[f32;4]}
fn uniform(cam:Camera)->CameraUniform{
 let (sy,cy)=cam.angle.to_radians().sin_cos();
 let (sp,cp)=cam.slope.to_radians().sin_cos();
 // Minecraft: yaw 0 looks +Z, positive pitch down.
 let forward=[-sy*cp,-sp,cy*cp,0.];
 let right=[cy,0.,sy,0.];
 let up=[sy*sp,cp,-cy*sp,0.];
 let cot=1./(cam.fov.to_radians()*0.5).tan();
 CameraUniform{
   eye:[cam.eye[0],cam.eye[1],cam.eye[2],0.],
   right,up,forward,
   lens:[cot,WIDTH as f32/HEIGHT as f32,0.05,1024.],
 }
}
#[derive(Clone)]
struct Snapshot {
 cam:Option<Camera>,
 mesh:Arc<Vec<GpuVertex>>,mesh_rev:u64,
 atlas:Arc<Vec<u8>>,atlas_w:u32,atlas_h:u32,atlas_rev:u64,
}
impl Default for Snapshot{
 fn default()->Self{Self{cam:None,mesh:Arc::new(vec![]),mesh_rev:0,
   atlas:Arc::new(vec![]),atlas_w:0,atlas_h:0,atlas_rev:0}}
}
pub struct Layer {
 map:Option<Map>,scene:Scene,last_try:Instant,
 frame:Arc<Mutex<Snapshot>>, pub id:egui::TextureId,
}
impl Layer {
 pub fn new(cc:&eframe::CreationContext<'_>)->Self{
   let rs=cc.wgpu_render_state.as_ref().expect("WGPU renderer required");
   let gpu=Gpu::new(&rs.device);
   let id=rs.renderer.write().register_native_texture(&rs.device,&gpu.color_view,wgpu::FilterMode::Linear);
   rs.renderer.write().callback_resources.insert(gpu);
   Self{map:None,scene:Scene::default(),
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
     self.map=None;self.scene=Scene::default();snap.cam=None;return;
   }
   snap.cam=map.camera();
   // No active MC camera -> don't render ghost blocks over the Zelda menu.
   let (mesh_changed,atlas_changed)=map.drain(&mut self.scene);
   if mesh_changed{
     let eye=snap.cam.map_or([0.;3],|c|c.eye);
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
 pipeline:wgpu::RenderPipeline,layout:wgpu::BindGroupLayout,
 bind_group:wgpu::BindGroup,uniform:wgpu::Buffer,
 sampler:wgpu::Sampler,vertices:wgpu::Buffer,vertex_count:u32,mesh_rev:u64,atlas_rev:u64,
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
   let vertices=device.create_buffer(&wgpu::BufferDescriptor{
     label:Some("Empty Minecraft mesh"),size:32,usage:wgpu::BufferUsages::VERTEX,mapped_at_creation:false});
   Self{color_view,depth_view,pipeline,layout,bind_group,uniform,sampler,
     vertices,vertex_count:0,mesh_rev:u64::MAX,atlas_rev:u64::MAX}
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
   if snap.cam.is_some() && self.vertex_count>0 && snap.atlas_w>0 {
     pass.set_pipeline(&self.pipeline);pass.set_bind_group(0,&self.bind_group,&[]);
     pass.set_vertex_buffer(0,self.vertices.slice(..));pass.draw(0..self.vertex_count,0..1);
   }
 }
}
#[cfg(test)]
mod tests {
 use super::*;
 #[test]fn minecraft_camera_orthonormal(){
   for yaw in [0.,30.,90.,180.,270.]{
     for pitch in [-60.,0.,50.]{
       let m=uniform(Camera{eye:[0.;3],angle:yaw,slope:pitch,fov:70.});
       let d=|a:[f32;4],b:[f32;4]|a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
       assert!(d(m.right,m.up).abs()<0.0001);
       assert!(d(m.forward,m.up).abs()<0.0001);
       assert!(d(m.forward,m.right).abs()<0.0001);
     }
   }
 }
}
