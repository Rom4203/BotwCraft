// World material stage for the future native Rust wgpu compositor.
// IMPORTANT: view_proj is the LIVE BOTW camera matrix, not a guessed Minecraft FOV.
// Geometry is in calibrated Hyrule world-space (BWC2). Zelda scene depth
// must be provided by the compositor's renderer, not reconstructed from RGB.
struct SceneUniforms {
    view_proj: mat4x4<f32>,
}
@group(0) @binding(0) var<uniform> scene: SceneUniforms;
@group(0) @binding(1) var block_atlas: texture_2d<f32>;
@group(0) @binding(2) var block_sampler: sampler;

struct VertexIn {
    @location(0) position: vec3<f32>,
    @location(1) uv: vec2<f32>,
    @location(2) rgba8: u32,
    @location(3) light: u32,
    @location(4) flags: u32,
}
struct VertexOut {
    @builtin(position) clip: vec4<f32>,
    @location(0) uv: vec2<f32>,
    @location(1) tint: vec4<f32>,
    @location(2) @interpolate(flat) flags: u32,
}
@vertex
fn vs_main(v: VertexIn) -> VertexOut {
    var out: VertexOut;
    out.clip = scene.view_proj * vec4<f32>(v.position, 1.0);
    out.uv = v.uv;
    // SkyCraft RenVertex.color is packed RGBA8, low byte = red.
    let c = v.rgba8;
    out.tint = vec4<f32>(
        f32(c & 255u),
        f32((c >> 8u) & 255u),
        f32((c >> 16u) & 255u),
        f32((c >> 24u) & 255u)
    ) * (1.0 / 255.0);
    out.flags = v.flags;
    return out;
}
@fragment
fn fs_main(v: VertexOut) -> @location(0) vec4<f32> {
    let texel = textureSample(block_atlas, block_sampler, v.uv);
    // SkyCraft RenVertex flags: bit0 = cutout, bit1 = translucent.
    if ((v.flags & 1u) != 0u && texel.a < 0.5) {
        discard;
    }
    return texel * v.tint;
}
