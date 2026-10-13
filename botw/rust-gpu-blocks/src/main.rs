// True WGPU 3D rendering of SkyCraft Minecraft section meshes/atlas.
// Not a replacement for native Zelda occlusion (BOTW depth is unavailable).
#[cfg(not(windows))]
fn main() {
    eprintln!("BotwCraft GPU blocks requires Windows and the SkyCraft v11 shared memory.");
}
#[cfg(windows)]
fn main() {
    windows_gpu::run();
}
#[cfg(windows)]
mod windows_gpu {
use std::{
    ffi::c_void, mem, ptr::{self, NonNull}, slice,
    sync::{atomic::{AtomicU64,Ordering},Arc},
    time::{Duration,Instant}
};
use raw_window_handle::{HasWindowHandle,RawWindowHandle};
use wgpu::util::DeviceExt;
use bytemuck::Zeroable;
use winit::{
    application::ApplicationHandler,
    dpi::PhysicalSize,
    event::WindowEvent,
    event_loop::{ActiveEventLoop,ControlFlow,EventLoop},
    window::{Window,WindowAttributes,WindowId},
};
use windows_sys::Win32::{
    Foundation::{BOOL,HWND,LPARAM,POINT,RECT},
    Graphics::Gdi::ClientToScreen,
    UI::WindowsAndMessaging::{
        EnumWindows,GetClientRect,GetForegroundWindow,
        GetWindowTextLengthW,GetWindowTextW,IsWindowVisible,IsIconic,
        ShowWindow,SetWindowPos,GetWindowLongPtrW,SetWindowLongPtrW,
        GWL_EXSTYLE,SW_HIDE,SW_SHOWNOACTIVATE,SWP_NOACTIVATE,SWP_SHOWWINDOW,
        HWND_TOPMOST,WS_EX_TRANSPARENT,WS_EX_TOOLWINDOW,
        WS_EX_NOACTIVATE,WS_EX_LAYERED,
    }
};
use botwcraft_rust_scene_relay::{
    Scene,RENDER_RING,RING_DATA, MAP_BYTES,MAGIC,VERSION
};

#[link(name="kernel32")]
extern "system" {
    fn OpenFileMappingW(access:u32,inherit:i32,name:*const u16)->*mut c_void;
    fn MapViewOfFile(handle:*mut c_void,access:u32,high:u32,low:u32,bytes:usize)->*mut c_void;
    fn UnmapViewOfFile(base:*mut c_void)->i32;
    fn CloseHandle(handle:*mut c_void)->i32;
    fn GetTickCount64()->u64;
}

#[repr(C)]
#[derive(Clone,Copy,bytemuck::Pod,bytemuck::Zeroable)]
struct GpuVertex {
    xyz:[f32;3],
    uv:[f32;2],
    tint:u32,
    light:u32,
    flags:u32,
}
const _:()=assert!(mem::size_of::<GpuVertex>()==32);
#[repr(C,align(16))]
#[derive(Clone,Copy,bytemuck::Pod,bytemuck::Zeroable)]
struct CameraUniform {
    eye:[f32;4],
    right:[f32;4],
    up:[f32;4],
    forward:[f32;4],
    lens:[f32;4],
}
#[derive(Clone,Copy)]
struct McCamera {
    xyz:[f32;3], yaw:f32,pitch:f32,fov:f32,
    ready:bool,gui_open:bool,
}
impl Default for McCamera {
    fn default()->Self{
        Self{xyz:[0.;3],yaw:0.,pitch:0.,fov:70.,ready:false,gui_open:true}
    }
}
impl McCamera {
    fn uniform(self,w:u32,h:u32)->CameraUniform {
        let yaw=self.yaw.to_radians();
        let pitch=self.pitch.to_radians();
        let (sy,cy)=yaw.sin_cos();
        let (sp,cp)=pitch.sin_cos();
        // Minecraft: yaw zero = +Z and pitch positive looks downward.
        let forward=[-sy*cp,-sp,cy*cp,0.0];
        let right=[cy,0.0,sy,0.0];
        // Cross(forward,right); independently derived, orthonormal.
        let up=[-sp*sy,cp,sp*cy,0.0];
        let aspect=w.max(1) as f32/h.max(1) as f32;
        let fy=1.0/(self.fov.clamp(15.0,145.0).to_radians()*0.5).tan();
        CameraUniform{
            eye:[self.xyz[0],self.xyz[1],self.xyz[2],0.0],
            right,up,forward,lens:[fy,aspect,0.05,1024.0]
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn direction_and_fov() {
        let c=McCamera{ready:true,gui_open:false,..McCamera::default()};
        let u=c.uniform(1920,1080);
        assert_eq!(u.forward,[0.,0.,1.,0.]);
        assert_eq!(u.right,[1.,0.,0.,0.]);
        assert_eq!(u.up,[0.,1.,0.,0.]);
        let tilted=McCamera{pitch:30.0,ready:true,gui_open:false,..McCamera::default()}.uniform(1920,1080);
        let dot=tilted.up.iter().zip(tilted.forward).map(|(u,f)|u*f).sum::<f32>();
        assert!(dot.abs()<0.0001,"camera up must be orthogonal to direction");
        assert!(tilted.up[2]>0.0,"look-down camera up vector points toward +Z");
        assert!((u.lens[1]-16.0/9.0).abs()<0.0001);
    }
}

struct Map {ptr:NonNull<u8>,handle:*mut c_void}
impl Map {
    fn connect()->Option<Self> {
        let name:Vec<u16>="Local\\SkyCraft_v1".encode_utf16().chain(Some(0)).collect();
        unsafe {
            let handle=OpenFileMappingW(0x0006,0,name.as_ptr());
            if handle.is_null(){return None;}
            let p=MapViewOfFile(handle,0x0006,0,0,MAP_BYTES);
            if let Some(ptr)=NonNull::new(p as *mut u8){Some(Self{ptr,handle})}
            else {CloseHandle(handle);None}
        }
    }
    #[inline]
    fn at(&self,pos:usize)->*mut u8{
        debug_assert!(pos<MAP_BYTES);
        unsafe {self.ptr.as_ptr().add(pos)}
    }
    fn u32(&self,o:usize)->u32 {unsafe{ptr::read_volatile(self.at(o) as *const u32)}}
    fn u64(&self,o:usize)->u64 {
        unsafe{(*(self.at(o) as *const AtomicU64)).load(Ordering::Acquire)}
    }
    fn f32(&self,o:usize)->f32 {f32::from_bits(self.u32(o))}
    fn f64(&self,o:usize)->f64 {
        unsafe{ptr::read_volatile(self.at(o) as *const f64)}
    }
    fn set_u64(&self,o:usize,v:u64){
        unsafe{(*(self.at(o) as *const AtomicU64)).store(v,Ordering::Release)}
    }
    fn valid(&self)->bool{self.u32(0)==MAGIC && self.u32(4)==VERSION}
    fn mc_pid(&self)->u32{self.u32(0x0c)}
    fn camera(&self)->Option<McCamera>{
        if !self.valid() || self.mc_pid()==0{return None;}
        let beat=self.u64(0x18);
        let now=unsafe{GetTickCount64()};
        if beat==0 || now<beat || now-beat>3000{return None;}
        let ms=0x200usize;
        for _ in 0..4 {
            let seq=self.u32(ms);
            if seq&1!=0 {continue;}
            let flags=self.u32(ms+4);
            let feet=[self.f64(ms+8),self.f64(ms+16),self.f64(ms+24)];
            let yaw=self.f32(ms+32);
            let pitch=self.f32(ms+36);
            let eyeheight=self.f32(ms+40);
            let fov=self.f32(ms+64);
            let eye=[self.f64(ms+80),self.f64(ms+88),self.f64(ms+96)];
            if self.u32(ms)!=seq {continue;}
            if !feet.iter().all(|v|v.is_finite()&&v.abs()<100_000.0)
               || !yaw.is_finite() || !pitch.is_finite() {return None;}
            let has_eye=eye.iter().all(|v|v.is_finite()&&v.abs()<100_000.0)
                && eye.iter().zip(feet).map(|(a,b)|(a-b)*(a-b)).sum::<f64>()<25.0;
            let coords=if has_eye {
                [eye[0] as f32,eye[1] as f32,eye[2] as f32]
            } else {
                [feet[0] as f32,
                 (feet[1]+if (0.3..3.5).contains(&eyeheight){eyeheight as f64}else{1.62}) as f32,
                 feet[2] as f32]
            };
            return Some(McCamera {
                xyz:coords,yaw,pitch,
                fov:if fov.is_finite()&&(15.0..=145.0).contains(&fov){fov}else{70.0},
                ready:(flags&0x20000)!=0 && (flags&1)!=0,
                gui_open:(flags&0x10000)==0,
            })
        }
        None
    }
    fn drain(&self,scene:&mut Scene)->Result<bool,String> {
        let base=RENDER_RING;
        let head=self.u64(base);
        let mut tail=self.u64(base+0x40);
        if head<tail || head-tail>RING_DATA as u64 {
            self.set_u64(base+0x40,head);
            return Err("RenderRing overwritten, resync required".into());
        }
        let mut geometry_changed=false;
        for _ in 0..128 {
            if tail>=head {break;}
            let pos=(tail%RING_DATA as u64) as usize;
            let remaining=RING_DATA-pos;
            if remaining<8{tail+=remaining as u64;continue;}
            let at=base+0x80+pos;
            let kind=self.u32(at);
            let size=self.u32(at+4) as usize;
            if kind==0 {tail+=remaining as u64;continue;}
            let bytes=match size.checked_add(15) {Some(v)=>v&!7usize,None=>break};
            if size>RING_DATA-8 || bytes>remaining || bytes as u64>head-tail {break;}
            if matches!(kind,1|2|3|7){
                let payload=unsafe{slice::from_raw_parts(self.at(at+8),size)};
                // Decode fully BEFORE publishing consumed tail (single producer/reader).
                match scene.apply(kind,payload) {
                    Ok(())=>{if kind==2 || kind==3 {geometry_changed=true;}},
                    Err(e)=>eprintln!("[GPU] Ignored corrupted render packet {kind}: {e}"),
                }
            }
            tail+=bytes as u64;
        }
        self.set_u64(base+0x40,tail);
        Ok(geometry_changed)
    }
}
impl Drop for Map {
    fn drop(&mut self){
        unsafe{
            UnmapViewOfFile(self.ptr.as_ptr() as *mut c_void);
            CloseHandle(self.handle);
        }
    }
}

#[derive(Default)]
struct Receiver {
    map:Option<Map>, scene:Scene,
    dirty:bool,pid:u32,
    next_retry:Option<Instant>,
}
impl Receiver {
    fn poll(&mut self)->McCamera {
        if self.map.is_none() && self.next_retry.map_or(true,|t|t.elapsed()>Duration::from_secs(1)){
            self.map=Map::connect();
            self.next_retry=Some(Instant::now());
            self.dirty=true;
        }
        let Some(map)=&self.map else {return McCamera::default();};
        if !map.valid(){
            self.map=None;self.scene=Scene::default();self.dirty=true;
            return McCamera::default()
        }
        let current_pid=map.mc_pid();
        if self.pid!=current_pid {
            self.scene=Scene::default();self.pid=current_pid;self.dirty=true;
        }
        let camera=map.camera().unwrap_or_default();
        // Consume even when GUI is up, so a large chunk export cannot stall.
        if let Ok(modified)=map.drain(&mut self.scene){self.dirty|=modified;}
        camera
    }
}

struct Gpu {
    window:Arc<Window>,
    surface:wgpu::Surface<'static>,
    device:wgpu::Device,
    queue:wgpu::Queue,
    config:wgpu::SurfaceConfiguration,
    camera_buffer:wgpu::Buffer,
    vertex_buffer:wgpu::Buffer,
    vertex_count:u32,
    atlas_rev:u64,
    bindings:wgpu::BindGroup,
    layout:wgpu::BindGroupLayout,
    pipeline:wgpu::RenderPipeline,
    depth:wgpu::TextureView,
    sampler:wgpu::Sampler,
}
impl Gpu {
    async fn new(window:Arc<Window>)->Result<Self,String>{
        let instance=wgpu::Instance::new(&wgpu::InstanceDescriptor::default());
        let surface=instance.create_surface(window.clone()).map_err(|e|e.to_string())?;
        let adapter=instance.request_adapter(&wgpu::RequestAdapterOptions{
            power_preference:wgpu::PowerPreference::HighPerformance,
            compatible_surface:Some(&surface),force_fallback_adapter:false
        }).await.map_err(|e|e.to_string())?;
        let (device,queue)=adapter.request_device(&wgpu::DeviceDescriptor::default())
            .await.map_err(|e|e.to_string())?;
        let caps=surface.get_capabilities(&adapter);
        let format=caps.formats.iter().copied()
            .find(|f|f.is_srgb()).unwrap_or(caps.formats[0]);
        let alpha_mode=caps.alpha_modes.iter().copied()
            .find(|a|*a==wgpu::CompositeAlphaMode::PreMultiplied)
            .or_else(||caps.alpha_modes.iter().copied()
                .find(|a|*a==wgpu::CompositeAlphaMode::PostMultiplied))
            .ok_or("GPU swapchain has no transparent alpha mode")?;
        let size=window.inner_size();
        let config=wgpu::SurfaceConfiguration{
            usage:wgpu::TextureUsages::RENDER_ATTACHMENT,
            format,width:size.width.max(1),height:size.height.max(1),
            present_mode:wgpu::PresentMode::Fifo,
            alpha_mode,view_formats:vec![],desired_maximum_frame_latency:2,
        };
        surface.configure(&device,&config);
        let camera_buffer=device.create_buffer_init(&wgpu::util::BufferInitDescriptor{
            label:Some("Minecraft exact camera+FOV"),
            contents:bytemuck::bytes_of(&CameraUniform::zeroed()),
            usage:wgpu::BufferUsages::UNIFORM|wgpu::BufferUsages::COPY_DST
        });
        let sampler=device.create_sampler(&wgpu::SamplerDescriptor{
            label:Some("Minecraft block atlas sampler"),
            address_mode_u:wgpu::AddressMode::ClampToEdge,
            address_mode_v:wgpu::AddressMode::ClampToEdge,
            mag_filter:wgpu::FilterMode::Nearest,
            min_filter:wgpu::FilterMode::Nearest,
            mipmap_filter:wgpu::FilterMode::Nearest,
            ..Default::default()
        });
        let layout=device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor{
            label:Some("Minecraft camera and atlas"),
            entries:&[
                wgpu::BindGroupLayoutEntry{binding:0,visibility:wgpu::ShaderStages::VERTEX,ty:wgpu::BindingType::Buffer {
                    ty:wgpu::BufferBindingType::Uniform,has_dynamic_offset:false,min_binding_size:None
                },count:None},
                wgpu::BindGroupLayoutEntry{binding:1,visibility:wgpu::ShaderStages::FRAGMENT,
                    ty:wgpu::BindingType::Texture{sample_type:wgpu::TextureSampleType::Float{filterable:true},
                        view_dimension:wgpu::TextureViewDimension::D2,multisampled:false},count:None},
                wgpu::BindGroupLayoutEntry{binding:2,visibility:wgpu::ShaderStages::FRAGMENT,
                    ty:wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering),count:None},
            ]
        });
        let make_tex=|pixels:&[u8],w:u32,h:u32|{
            let texture=device.create_texture(&wgpu::TextureDescriptor{
                label:Some("SkyCraft Minecraft RGBA atlas"),
                size:wgpu::Extent3d{width:w,height:h,depth_or_array_layers:1},
                mip_level_count:1,sample_count:1,
                dimension:wgpu::TextureDimension::D2,
                format:wgpu::TextureFormat::Rgba8UnormSrgb,
                usage:wgpu::TextureUsages::TEXTURE_BINDING|wgpu::TextureUsages::COPY_DST,
                view_formats:&[]
            });
            queue.write_texture(
                wgpu::TexelCopyTextureInfo{texture:&texture,mip_level:0,origin:wgpu::Origin3d::ZERO,aspect:wgpu::TextureAspect::All},
                pixels,
                wgpu::TexelCopyBufferLayout{offset:0,bytes_per_row:Some(w*4),rows_per_image:Some(h)},
                wgpu::Extent3d{width:w,height:h,depth_or_array_layers:1});
            texture.create_view(&wgpu::TextureViewDescriptor::default())
        };
        let white=make_tex(&[255,255,255,255],1,1);
        let bindings=device.create_bind_group(&wgpu::BindGroupDescriptor{
            label:Some("Minecraft atlas binding"),
            layout:&layout,
            entries:&[
                wgpu::BindGroupEntry{binding:0,resource:camera_buffer.as_entire_binding()},
                wgpu::BindGroupEntry{binding:1,resource:wgpu::BindingResource::TextureView(&white)},
                wgpu::BindGroupEntry{binding:2,resource:wgpu::BindingResource::Sampler(&sampler)}
            ]
        });
        let pipeline_layout=device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor{
            label:Some("Minecraft block pipeline layout"),
            bind_group_layouts:&[&layout],push_constant_ranges:&[]
        });
        let shader=device.create_shader_module(wgpu::ShaderModuleDescriptor{
            label:Some("Minecraft block GPU shader"),
            source:wgpu::ShaderSource::Wgsl(include_str!("../shaders/minecraft.wgsl").into()),
        });
        let pipeline=device.create_render_pipeline(&wgpu::RenderPipelineDescriptor{
            label:Some("Real Minecraft textured blocks (alpha/depth)"),
            layout:Some(&pipeline_layout),
            vertex:wgpu::VertexState{
                module:&shader,entry_point:Some("vs_main"),
                compilation_options:Default::default(),
                buffers:&[wgpu::VertexBufferLayout{
                    array_stride:32,step_mode:wgpu::VertexStepMode::Vertex,
                    attributes:&wgpu::vertex_attr_array![0=>Float32x3,1=>Float32x2,2=>Uint32,3=>Uint32,4=>Uint32],
                }]
            },
            primitive:wgpu::PrimitiveState{
                topology:wgpu::PrimitiveTopology::TriangleList,
                front_face:wgpu::FrontFace::Ccw,cull_mode:None,
                ..Default::default()
            },
            depth_stencil:Some(wgpu::DepthStencilState{
                format:wgpu::TextureFormat::Depth24Plus,
                depth_write_enabled:true,
                depth_compare:wgpu::CompareFunction::LessEqual,
                stencil:Default::default(),bias:Default::default()
            }),
            multisample:Default::default(),
            fragment:Some(wgpu::FragmentState{
                module:&shader,entry_point:Some("fs_main"),
                compilation_options:Default::default(),
                targets:&[Some(wgpu::ColorTargetState{
                    format,blend:Some(wgpu::BlendState::PREMULTIPLIED_ALPHA_BLENDING),
                    write_mask:wgpu::ColorWrites::ALL
                })]
            }),
            multiview:None,cache:None,
        });
        let vertex_buffer=device.create_buffer(&wgpu::BufferDescriptor{
            label:Some("Empty Minecraft mesh"),
            size:32,usage:wgpu::BufferUsages::VERTEX|wgpu::BufferUsages::COPY_DST,
            mapped_at_creation:false
        });
        let depth=Self::depth_view(&device,config.width,config.height);
        Ok(Self {window,surface,device,queue,config,camera_buffer,vertex_buffer,
            vertex_count:0,atlas_rev:u64::MAX,bindings,layout,pipeline,depth,sampler})
    }
    fn depth_view(device:&wgpu::Device,w:u32,h:u32)->wgpu::TextureView{
        device.create_texture(&wgpu::TextureDescriptor{
            label:Some("Minecraft native GPU 3D z-buffer"),
            size:wgpu::Extent3d{width:w,height:h,depth_or_array_layers:1},
            mip_level_count:1,sample_count:1,dimension:wgpu::TextureDimension::D2,
            format:wgpu::TextureFormat::Depth24Plus,
            usage:wgpu::TextureUsages::RENDER_ATTACHMENT,
            view_formats:&[],
        }).create_view(&wgpu::TextureViewDescriptor::default())
    }
    fn resize(&mut self,w:u32,h:u32){
        if w<2 || h<2 || (self.config.width==w && self.config.height==h){return;}
        self.config.width=w;self.config.height=h;
        self.surface.configure(&self.device,&self.config);
        self.depth=Self::depth_view(&self.device,w,h);
    }
    fn texture(&mut self,scene:&Scene){
        if scene.atlas_revision==self.atlas_rev || scene.atlas_rgba.is_empty() {return;}
        let w=scene.atlas_width;
        let h=scene.atlas_height;
        let texture=self.device.create_texture(&wgpu::TextureDescriptor{
            label:Some("True Minecraft texture atlas"),
            size:wgpu::Extent3d{width:w,height:h,depth_or_array_layers:1},
            mip_level_count:1,sample_count:1,dimension:wgpu::TextureDimension::D2,
            format:wgpu::TextureFormat::Rgba8UnormSrgb,
            usage:wgpu::TextureUsages::TEXTURE_BINDING|wgpu::TextureUsages::COPY_DST,
            view_formats:&[]
        });
        self.queue.write_texture(
            wgpu::TexelCopyTextureInfo{texture:&texture,mip_level:0,origin:wgpu::Origin3d::ZERO,aspect:wgpu::TextureAspect::All},
            &scene.atlas_rgba,
            wgpu::TexelCopyBufferLayout{offset:0,bytes_per_row:Some(w*4),rows_per_image:Some(h)},
            wgpu::Extent3d{width:w,height:h,depth_or_array_layers:1});
        let view=texture.create_view(&wgpu::TextureViewDescriptor::default());
        self.bindings=self.device.create_bind_group(&wgpu::BindGroupDescriptor{
            label:Some("Minecraft atlas current frame"),
            layout:&self.layout,
            entries:&[
                wgpu::BindGroupEntry{binding:0,resource:self.camera_buffer.as_entire_binding()},
                wgpu::BindGroupEntry{binding:1,resource:wgpu::BindingResource::TextureView(&view)},
                wgpu::BindGroupEntry{binding:2,resource:wgpu::BindingResource::Sampler(&self.sampler)}
            ]
        });
        self.atlas_rev=scene.atlas_revision;
    }
    fn mesh(&mut self,scene:&Scene,camera:McCamera){
        // Bound the upload to sections nearest to the actual Minecraft eye.
        const DISTANCE:f32=128.0;
        const MAX_TRIANGLES:usize=100_000;
        let mut sections:Vec<_>=scene.sections.iter().filter_map(|(coord,verts)|{
            let center=[coord.0 as f32*16.+8.,coord.1 as f32*16.+8.,coord.2 as f32*16.+8.];
            let dist2=center.iter().zip(camera.xyz).map(|(a,b)|(a-b)*(a-b)).sum::<f32>();
            (dist2<(DISTANCE+16.0).powi(2)).then_some((dist2,coord,verts))
        }).collect();
        sections.sort_by(|a,b|a.0.total_cmp(&b.0).then(a.1.cmp(b.1)));
        let mut gpu=Vec::new();
        for (_,coord,verts) in sections {
            if gpu.len()+3>MAX_TRIANGLES*3 {break;}
            let origin=[coord.0 as f32*16.,coord.1 as f32*16.,coord.2 as f32*16.];
            for v in verts.iter().take(MAX_TRIANGLES*3-gpu.len()) {
                gpu.push(GpuVertex{
                    xyz:[v.xyz[0]+origin[0],v.xyz[1]+origin[1],v.xyz[2]+origin[2]],
                    uv:v.uv,tint:v.tint,light:v.light,flags:v.flags
                });
            }
        }
        self.vertex_count=gpu.len() as u32;
        if gpu.is_empty(){return}
        self.vertex_buffer=self.device.create_buffer_init(&wgpu::util::BufferInitDescriptor{
            label:Some("Original SkyCraft Minecraft world triangles"),
            contents:bytemuck::cast_slice(&gpu),
            usage:wgpu::BufferUsages::VERTEX|wgpu::BufferUsages::COPY_DST,
        });
    }
    fn render(&mut self,cam:McCamera)->Result<(),wgpu::SurfaceError>{
        self.queue.write_buffer(&self.camera_buffer,0,
            bytemuck::bytes_of(&cam.uniform(self.config.width,self.config.height)));
        let frame=self.surface.get_current_texture()?;
        let view=frame.texture.create_view(&wgpu::TextureViewDescriptor::default());
        let mut encoder=self.device.create_command_encoder(&wgpu::CommandEncoderDescriptor{
            label:Some("BOTWCRAFT actual GPU frame")
        });
        {
            let mut pass=encoder.begin_render_pass(&wgpu::RenderPassDescriptor{
                label:Some("Minecraft blocks - transparent 3D layer"),
                color_attachments:&[Some(wgpu::RenderPassColorAttachment{
                    view:&view,resolve_target:None,depth_slice:None,ops:wgpu::Operations {
                        load:wgpu::LoadOp::Clear(wgpu::Color::TRANSPARENT),store:wgpu::StoreOp::Store
                    }
                })],
                depth_stencil_attachment:Some(wgpu::RenderPassDepthStencilAttachment{
                    view:&self.depth,
                    depth_ops:Some(wgpu::Operations{load:wgpu::LoadOp::Clear(1.0),store:wgpu::StoreOp::Store}),
                    stencil_ops:None
                }),
                timestamp_writes:None,occlusion_query_set:None,
            });
            if self.vertex_count>0 {
                pass.set_pipeline(&self.pipeline);
                pass.set_bind_group(0,&self.bindings,&[]);
                pass.set_vertex_buffer(0,self.vertex_buffer.slice(..));
                pass.draw(0..self.vertex_count,0..1);
            }
        }
        self.queue.submit(Some(encoder.finish()));
        frame.present();Ok(())
    }
}

struct WindowTarget {hwnd:HWND,x:i32,y:i32,w:u32,h:u32}
#[derive(Default)] struct Finder {mine:HWND,found:HWND}
unsafe extern "system" fn enum_window(hwnd:HWND,param:LPARAM)->BOOL {
    let state=&mut *(param as *mut Finder);
    if hwnd==state.mine || IsWindowVisible(hwnd)==0 || IsIconic(hwnd)!=0 {return 1;}
    let len=GetWindowTextLengthW(hwnd);
    if len<10 || len>300 {return 1;}
    let mut buf=vec![0u16;len as usize+1];
    GetWindowTextW(hwnd,buf.as_mut_ptr(),len+1);
    let title=String::from_utf16_lossy(&buf).to_lowercase();
    if title.contains("botwcraft") && (title.contains("hyrule") || title.contains("minecraft"))
        && !title.contains("gpu blocks") {
        state.found=hwnd;return 0;
    }
    1
}
fn target(mine:HWND)->Option<WindowTarget>{
    let mut finder=Finder{mine,found:ptr::null_mut()};
    unsafe {
        EnumWindows(Some(enum_window),(&mut finder as *mut Finder) as LPARAM);
        if finder.found.is_null() || GetForegroundWindow()!=finder.found{return None;}
        let mut rect:RECT=mem::zeroed();let mut pt:POINT=mem::zeroed();
        if GetClientRect(finder.found,&mut rect)==0{return None;}
        if ClientToScreen(finder.found,&mut pt)==0{return None;}
        let w=(rect.right-rect.left).max(0) as u32;
        let h=(rect.bottom-rect.top).max(0) as u32;
        if w<320 || h<240{return None;}
        Some(WindowTarget{hwnd:finder.found,x:pt.x,y:pt.y,w,h})
    }
}
fn hwnd(window:&Window)->Option<HWND>{
    match window.window_handle().ok()?.as_raw(){
        RawWindowHandle::Win32(h)=>Some(h.hwnd.get() as usize as HWND),_=>None
    }
}
fn transparent_clickthrough(hwnd:HWND){
    unsafe {
        let ex=GetWindowLongPtrW(hwnd,GWL_EXSTYLE) as u32;
        SetWindowLongPtrW(hwnd,GWL_EXSTYLE,
            (ex|WS_EX_TRANSPARENT|WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE|WS_EX_LAYERED) as isize);
    }
}

struct App{
    window:Option<Arc<Window>>,
    gpu:Option<Gpu>,
    reader:Receiver,
    size:(u32,u32),
    last_cam:McCamera,
    hidden:bool,
    last_log:Instant,
    last_eye:[f32;3],
}
impl Default for App {
    fn default()->Self {
        Self {
            window:None,gpu:None,reader:Receiver::default(),size:(0,0),
            last_cam:McCamera::default(),hidden:true,
            last_log:Instant::now(),last_eye:[0.;3]
        }
    }
}
impl ApplicationHandler for App{
    fn resumed(&mut self,event_loop:&ActiveEventLoop){
        if self.window.is_some(){return;}
        let attr=WindowAttributes::default()
            .with_title("BotwCraft GPU blocks")
            .with_transparent(true)
            .with_decorations(false)
            .with_visible(false)
            .with_inner_size(PhysicalSize::new(640,360));
        let window=match event_loop.create_window(attr) {
            Ok(w)=>Arc::new(w),
            Err(e)=>{eprintln!("[GPU] Window: {e}");event_loop.exit();return}
        };
        if let Some(h)=hwnd(&window){transparent_clickthrough(h);}
        match pollster::block_on(Gpu::new(window.clone())) {
            Ok(gpu)=>{
                println!("[GPU] WGPU Minecraft real 3D ready - awaiting /botwcraft connect");
                self.gpu=Some(gpu);self.window=Some(window);
            }
            Err(e)=>{
                eprintln!("[GPU] Renderer: {e}");
                event_loop.exit();
            }
        }
    }
    fn window_event(&mut self,event_loop:&ActiveEventLoop,_id:WindowId,event:WindowEvent) {
        match event {
            WindowEvent::CloseRequested=>event_loop.exit(),
            WindowEvent::Resized(s)=>{
                if let Some(gpu)=&mut self.gpu{gpu.resize(s.width,s.height);}
            }
            _=>{}
        }
    }
    fn about_to_wait(&mut self,event_loop:&ActiveEventLoop){
        // WM_PAINT does not fire for hidden windows: poll shared memory on
        // the explicit 16-ms clock so the GPU overlay can become visible.
        self.redraw();
        event_loop.set_control_flow(ControlFlow::WaitUntil(
            Instant::now()+Duration::from_millis(16)));
    }
}
impl App{
    fn redraw(&mut self){
        let cam=self.reader.poll();
        self.last_cam=cam;
        let Some(win)=self.window.as_ref() else {return};
        let Some(own)=hwnd(win) else {return};
        let target=target(own);
        let should_show=cam.ready && !cam.gui_open
            && !self.reader.scene.atlas_rgba.is_empty()
            && target.is_some();
        if !should_show {
            if !self.hidden {
                unsafe{ShowWindow(own,SW_HIDE);}
                self.hidden=true;
            }
            return;
        }
        let target=target.unwrap();
        // Keep the owner window on top, but never activate the transparent layer.
        let moved=(target.w,target.h)!=self.size;
        if moved {
            self.size=(target.w,target.h);
            if let Some(gpu)=&mut self.gpu{gpu.resize(target.w,target.h);}
        }
        unsafe {
            SetWindowPos(own,HWND_TOPMOST,target.x,target.y,
                target.w as i32,target.h as i32,SWP_NOACTIVATE|SWP_SHOWWINDOW);
            if self.hidden {ShowWindow(own,SW_SHOWNOACTIVATE);}
        }
        self.hidden=false;
        let Some(gpu)=&mut self.gpu else {return};
        gpu.texture(&self.reader.scene);
        // Remesh when sections change OR eye moves into another neighborhood.
        let shifted=cam.xyz.iter().zip(self.last_eye)
            .map(|(a,b)|(a-b)*(a-b)).sum::<f32>()>64.0;
        if self.reader.dirty || shifted {
            gpu.mesh(&self.reader.scene,cam);
            self.reader.dirty=false;
            self.last_eye=cam.xyz;
        }
        match gpu.render(cam) {
            Ok(())=>{},
            Err(wgpu::SurfaceError::Lost|wgpu::SurfaceError::Outdated)=>{
                gpu.surface.configure(&gpu.device,&gpu.config);
            }
            Err(wgpu::SurfaceError::OutOfMemory)=>eprintln!("[GPU] device out of memory"),
            Err(e)=>eprintln!("[GPU] surface: {e}"),
        }
        if self.last_log.elapsed()>Duration::from_secs(15) {
            println!("[GPU] triangles={} vertices={} atlas={}x{} FOV={:.2} source=MC",
                self.reader.scene.triangles(),gpu.vertex_count,
                self.reader.scene.atlas_width,self.reader.scene.atlas_height,cam.fov);
            self.last_log=Instant::now();
        }
    }
}
pub fn run(){
    let event_loop=EventLoop::new().expect("Windows event loop");
    event_loop.set_control_flow(ControlFlow::WaitUntil(Instant::now()+Duration::from_millis(16)));
    let mut app=App::default();
    if let Err(e)=event_loop.run_app(&mut app){eprintln!("[GPU] EventLoop {e}")}
}
}
