// The actual Minecraft section mesh, not a rendered screen-space screenshot.
// One world-to-view perspective for ALL blocks; hardware clips and z-tests.
struct Camera {
 eye:vec4<f32>,right:vec4<f32>,up:vec4<f32>,
 forward:vec4<f32>,lens:vec4<f32>,
};
@group(0) @binding(0) var<uniform> camera:Camera;
@group(0) @binding(1) var atlas:texture_2d<f32>;
@group(0) @binding(2) var sampler_minecraft:sampler;
struct Input {
 @location(0) xyz:vec3<f32>,@location(1) uv:vec2<f32>,
 @location(2) tint:u32,@location(3) light:u32,@location(4) flags:u32,
};
struct Out {
 @builtin(position) pos:vec4<f32>,
 @location(0) uv:vec2<f32>,
 @location(1) tint:vec4<f32>,
};
@vertex
fn vs_main(v:Input)->Out{
 let relative=v.xyz-camera.eye.xyz;
 let x=dot(relative,camera.right.xyz);
 let y=dot(relative,camera.up.xyz);
 let z=dot(relative,camera.forward.xyz);
 let near=camera.lens.z;
 let far=camera.lens.w;
 let depth_a=far/(far-near);
 var out:Out;
 out.pos=vec4<f32>(x*camera.lens.x/camera.lens.y,y*camera.lens.x,
                     z*depth_a-near*depth_a,z);
 out.uv=v.uv;
 out.tint=vec4<f32>(f32(v.tint&255u),f32((v.tint>>8u)&255u),
      f32((v.tint>>16u)&255u),f32((v.tint>>24u)&255u))/255.0;
 return out;
}
@fragment
fn fs_main(v:Out)->@location(0) vec4<f32>{
 let pixel=textureSample(atlas,sampler_minecraft,v.uv)*v.tint;
 if(pixel.a<0.125){discard;}
 return vec4<f32>(pixel.rgb*pixel.a,pixel.a);
}
