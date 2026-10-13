//! WGPU geometry pass designed to be embedded in the host's existing GPU
//! render pass. No independent compositor window, PNG overlay, or GDB proxy.
//! The caller must supply its own color + **real BOTW** depth attachments.
//! The current prebuilt Ryujinx compositor cannot do that without its source.
use std::collections::{HashMap,HashSet};
use wgpu::util::DeviceExt;
use crate::{World,SectionKey,Vertex};
struct Chunk {
    vb:wgpu::Buffer,
    allocated:usize,
    count:u32,
    revision:u64,
    translucent:bool,
}
pub struct GpuWorld {
    opaque:wgpu::RenderPipeline,
    transparent:wgpu::RenderPipeline,
    layout:wgpu::BindGroupLayout,
    bind:Option<wgpu::BindGroup>,
    atlas:Option<wgpu::Texture>,
    atlas_size:(u32,u32),
    atlas_revision:u64,
    camera:wgpu::Buffer,
    sampler:wgpu::Sampler,
    chunks:HashMap<SectionKey,Chunk>,
    visible:Vec<SectionKey>,
    pub uploaded_vertices:u64,
}
impl GpuWorld {
    pub fn new(device:&wgpu::Device,color_format:wgpu::TextureFormat,depth_format:wgpu::TextureFormat)->Self{
        let shader=device.create_shader_module(wgpu::ShaderModuleDescriptor{
            label:Some("BotwCraft block triangles and Minecraft UVs"),
            source:wgpu::ShaderSource::Wgsl(include_str!("mesh.wgsl").into())
        });
        let layout=device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor{
            label:Some("Minecraft atlas & camera"),
            entries:&[
                wgpu::BindGroupLayoutEntry{binding:0,visibility:wgpu::ShaderStages::VERTEX,ty:wgpu::BindingType::Buffer{ty:wgpu::BufferBindingType::Uniform,has_dynamic_offset:false,min_binding_size:None},count:None},
                wgpu::BindGroupLayoutEntry{binding:1,visibility:wgpu::ShaderStages::FRAGMENT,ty:wgpu::BindingType::Texture{multisampled:false,view_dimension:wgpu::TextureViewDimension::D2,sample_type:wgpu::TextureSampleType::Float{filterable:true}},count:None},
                wgpu::BindGroupLayoutEntry{binding:2,visibility:wgpu::ShaderStages::FRAGMENT,ty:wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering),count:None},
            ],
        });
        let pipeline_layout=device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor{label:Some("Block pass"),bind_group_layouts:&[&layout],push_constant_ranges:&[]});
        let attrs=wgpu::vertex_attr_array![0=>Float32x3,1=>Float32x2,2=>Uint32,3=>Uint32,4=>Uint32];
        let create=|blend:Option<wgpu::BlendState>,depth_write_enabled|{
            device.create_render_pipeline(&wgpu::RenderPipelineDescriptor{
                label:Some("Minecraft mesh pipeline"),
                layout:Some(&pipeline_layout),
                vertex:wgpu::VertexState{
                    module:&shader,entry_point:Some("vs_main"),
                    buffers:&[wgpu::VertexBufferLayout{array_stride:32,step_mode:wgpu::VertexStepMode::Vertex,attributes:&attrs}],
                    compilation_options:Default::default()
                },
                primitive:wgpu::PrimitiveState{topology:wgpu::PrimitiveTopology::TriangleList,cull_mode:None,..Default::default()},
                depth_stencil:Some(wgpu::DepthStencilState{format:depth_format,depth_write_enabled,depth_compare:wgpu::CompareFunction::LessEqual,stencil:Default::default(),bias:Default::default()}),
                multisample:Default::default(),
                fragment:Some(wgpu::FragmentState{
                    module:&shader,entry_point:Some("fs_main"),
                    targets:&[Some(wgpu::ColorTargetState{format:color_format,blend,write_mask:wgpu::ColorWrites::ALL})],
                    compilation_options:Default::default()
                }),
                multiview:None,cache:None
            })
        };
        let opaque=create(None,true);
        let transparent=create(Some(wgpu::BlendState::ALPHA_BLENDING),false);
        let camera=device.create_buffer(&wgpu::BufferDescriptor{
            label:Some("BotwCraft camera matrix"),
            size:64,usage:wgpu::BufferUsages::UNIFORM|wgpu::BufferUsages::COPY_DST,
            mapped_at_creation:false
        });
        let sampler=device.create_sampler(&wgpu::SamplerDescriptor{
            mag_filter:wgpu::FilterMode::Nearest,min_filter:wgpu::FilterMode::Nearest,
            mipmap_filter:wgpu::FilterMode::Nearest,
            address_mode_u:wgpu::AddressMode::ClampToEdge,
            address_mode_v:wgpu::AddressMode::ClampToEdge,
            ..Default::default()
        });
        Self{opaque,transparent,layout,bind:None,atlas:None,atlas_size:(0,0),atlas_revision:0,camera,sampler,chunks:HashMap::new(),visible:Vec::new(),uploaded_vertices:0}
    }
    /// Mesh geometry is uploaded when sections change, *not every frame*.
    pub fn sync(&mut self,device:&wgpu::Device,queue:&wgpu::Queue,world:&World,eye:[f32;3],max_distance:f32,vp:[[f32;4];4]){
        self.visible=world.visible_keys(eye,max_distance);
        queue.write_buffer(&self.camera,0,bytemuck::cast_slice(&vp));
        if let Some(a)=world.atlas.as_ref(){
            if a.revision!=self.atlas_revision{
                if self.atlas_size!=(a.width,a.height){
                    self.atlas_size=(a.width,a.height);
                    self.atlas=Some(device.create_texture(&wgpu::TextureDescriptor{
                        label:Some("Minecraft texture atlas"),
                        size:wgpu::Extent3d{width:a.width,height:a.height,depth_or_array_layers:1},
                        mip_level_count:1,sample_count:1,dimension:wgpu::TextureDimension::D2,
                        format:wgpu::TextureFormat::Rgba8Unorm,
                        usage:wgpu::TextureUsages::TEXTURE_BINDING|wgpu::TextureUsages::COPY_DST,
                        view_formats:&[],
                    }));
                }
                if let Some(texture)=self.atlas.as_ref(){
                    queue.write_texture(
                        wgpu::TexelCopyTextureInfo{texture,mip_level:0,origin:wgpu::Origin3d::ZERO,aspect:wgpu::TextureAspect::All},
                        &a.rgba,
                        wgpu::TexelCopyBufferLayout{offset:0,bytes_per_row:Some(a.width*4),rows_per_image:Some(a.height)},
                        wgpu::Extent3d{width:a.width,height:a.height,depth_or_array_layers:1}
                    );
                    let texture_view=texture.create_view(&Default::default());
                    self.bind=Some(device.create_bind_group(&wgpu::BindGroupDescriptor{
                        label:Some("Minecraft texture binding"),layout:&self.layout,
                        entries:&[
                            wgpu::BindGroupEntry{binding:0,resource:self.camera.as_entire_binding()},
                            wgpu::BindGroupEntry{binding:1,resource:wgpu::BindingResource::TextureView(&texture_view)},
                            wgpu::BindGroupEntry{binding:2,resource:wgpu::BindingResource::Sampler(&self.sampler)},
                        ]
                    }));
                }
                self.atlas_revision=a.revision;
            }
        }
        let visible:HashSet<_>=self.visible.iter().copied().collect();
        self.chunks.retain(|key,_|visible.contains(key)&&world.sections.contains_key(key));
        for &key in &self.visible{
            let Some(section)=world.sections.get(&key) else{continue;};
            if section.vertices.is_empty(){continue;}
            let len=section.vertices.len()*std::mem::size_of::<Vertex>();
            if let Some(chunk)=self.chunks.get_mut(&key){
                if chunk.revision==section.revision{continue;}
                if chunk.allocated<len{
                    chunk.vb=device.create_buffer_init(&wgpu::util::BufferInitDescriptor{
                        label:Some("Updated Minecraft chunk"),
                        contents:bytemuck::cast_slice(&section.vertices),
                        usage:wgpu::BufferUsages::VERTEX|wgpu::BufferUsages::COPY_DST
                    });
                    chunk.allocated=len;
                }else{
                    queue.write_buffer(&chunk.vb,0,bytemuck::cast_slice(&section.vertices));
                }
                chunk.revision=section.revision;
                chunk.count=section.vertices.len() as u32;
                chunk.translucent=section.translucent;
            }else{
                let vb=device.create_buffer_init(&wgpu::util::BufferInitDescriptor{
                    label:Some("Minecraft chunk GPU cache"),
                    contents:bytemuck::cast_slice(&section.vertices),
                    usage:wgpu::BufferUsages::VERTEX|wgpu::BufferUsages::COPY_DST
                });
                self.chunks.insert(key,Chunk{vb,allocated:len,count:section.vertices.len() as u32,revision:section.revision,translucent:section.translucent});
            }
            self.uploaded_vertices+=section.vertices.len() as u64;
        }
    }
    /// Called by the host INSIDE its GPU draw pass; no extra window and
    /// no capture/readback/copy of an entire full-HD framebuffer.
    pub fn draw<'a>(&'a self,pass:&mut wgpu::RenderPass<'a>){
        let Some(bind)=self.bind.as_ref() else{return;};
        pass.set_bind_group(0,bind,&[]);
        for translucent in [false,true]{
            pass.set_pipeline(if translucent{&self.transparent}else{&self.opaque});
            for key in &self.visible{
                let Some(chunk)=self.chunks.get(key) else{continue;};
                if chunk.translucent!=translucent{continue;}
                pass.set_vertex_buffer(0,chunk.vb.slice(..));
                pass.draw(0..chunk.count,0..1);
            }
        }
    }
}