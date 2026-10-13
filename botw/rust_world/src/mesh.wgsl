struct Frame { vp: mat4x4<f32> }
@group(0) @binding(0) var<uniform> frame: Frame;
@group(0) @binding(1) var atlas: texture_2d<f32>;
@group(0) @binding(2) var atlas_sampler: sampler;
struct In {
    @location(0) xyz: vec3<f32>,
    @location(1) uv: vec2<f32>,
    @location(2) tint: u32,
    @location(3) light: u32,
    @location(4) flags: u32,
};
struct Out {
    @builtin(position) pos: vec4<f32>,
    @location(0) uv: vec2<f32>,
    @location(1) tint: vec4<f32>,
    @location(2) shade: f32,
};
@vertex fn vs_main(v: In) -> Out {
    var o: Out;
    o.pos = frame.vp * vec4<f32>(v.xyz, 1.0);
    o.uv = v.uv;
    o.tint = vec4<f32>(f32(v.tint & 255u), f32((v.tint>>8u)&255u),
                       f32((v.tint>>16u)&255u), f32((v.tint>>24u)&255u)) / 255.0;
    let sky = f32((v.light>>8u)&15u)/15.0;
    let block = f32(v.light&15u)/15.0;
    let normal = (v.flags>>4u)&7u;
    var face = 1.0;
    if (normal == 1u) { face = 0.58; }
    if (normal == 3u || normal == 4u) { face = 0.82; }
    if (normal == 5u || normal == 6u) { face = 0.72; }
    o.shade = face*(0.58+0.42*max(sky,block));
    return o;
}
@fragment fn fs_main(v: Out) -> @location(0) vec4<f32> {
    let color = textureSample(atlas, atlas_sampler, v.uv)*v.tint;
    if (color.a < 0.1) { discard; }
    return vec4<f32>(color.rgb*v.shade, color.a);
}
