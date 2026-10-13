// SkyCraft's REAL Minecraft mesh/UV/color rendered on the GPU.
// FOV is measured by GameRenderer.mainCamera(), not assumed to be 70 degrees.
// MC coordinates are converted from camera position/direction into clip space.
// This depth buffer resolves Minecraft-to-Minecraft occlusion.
// It is NOT Zelda's native depth buffer.
struct Camera {
    eye: vec4<f32>,
    right: vec4<f32>,
    up: vec4<f32>,
    forward: vec4<f32>,
    lens: vec4<f32>,      // cot(vfov/2), aspect, near, far
}
@group(0) @binding(0) var<uniform> camera: Camera;
@group(0) @binding(1) var atlas: texture_2d<f32>;
@group(0) @binding(2) var tex_sampler: sampler;
struct Input {
    @location(0) xyz: vec3<f32>,
    @location(1) uv: vec2<f32>,
    @location(2) tint: u32,
    @location(3) light: u32,
    @location(4) flags: u32,
}
struct Vertex {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
    @location(1) color: vec4<f32>,
    @location(2) @interpolate(flat) flags: u32,
}
@vertex
fn vs_main(v:Input)->Vertex{
    let p=v.xyz-camera.eye.xyz;
    let x=dot(p,camera.right.xyz);
    let y=dot(p,camera.up.xyz);
    let z=dot(p,camera.forward.xyz);
    let a=camera.lens.w/(camera.lens.w-camera.lens.z);
    let b=-camera.lens.z*a;
    var out:Vertex;
    out.position=vec4<f32>(
        x*camera.lens.x/camera.lens.y,
        y*camera.lens.x,
        z*a+b,
        z
    );
    out.uv=v.uv;
    out.color=vec4<f32>(
        f32(v.tint & 255u),
        f32((v.tint>>8u)&255u),
        f32((v.tint>>16u)&255u),
        f32((v.tint>>24u)&255u)
    )/255.0;
    out.flags=v.flags;
    return out;
}
@fragment
fn fs_main(v:Vertex)->@location(0) vec4<f32>{
    let rgba=textureSample(atlas,tex_sampler,v.uv)*v.color;
    if (rgba.a < 0.125) { discard; }
    // Swapchain expects premultiplied alpha for true desktop transparency.
    return vec4<f32>(rgba.rgb*rgba.a,rgba.a);
}
