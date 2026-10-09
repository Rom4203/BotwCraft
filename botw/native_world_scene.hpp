#pragma once
// BWC2 world-space scene packet: a SkyCraft BlockQuadOutput payload, kept in
// Hyrule units until the ACTUAL Zelda camera renderer transforms it.
//
// No screen-space projection, no guest file I/O, no Nintendo assets, no
// dependence on any guessed game memory address. This is intentionally a
// separate scene type from the old BWC1 overlay diagnostic.
#include <cstddef>
#include <cstdint>

namespace BotwCraftWorld {
constexpr uint32_t kMagic = 0x32435742u;
constexpr uint32_t kVersion = 2;
constexpr uint32_t kMaxVertices = 480;

struct Header {
    uint32_t magic, version, frameId, vertexCount, payloadHash;
    uint32_t flags, reserved0, reserved1;
    float minecraftOrigin[3];
    float hyruleOrigin[3];
};
static_assert(sizeof(Header) == 56);

struct Vertex {
    float x,y,z;          // Hyrule absolute world coordinates
    float u,v;            // Minecraft block atlas UV
    uint32_t argb;        // Minecraft AO/tint/shading
    uint32_t light;       // block+sky light
    uint32_t flags;       // transparent/face normal for native shaders
};
static_assert(sizeof(Vertex) == 32);

constexpr std::size_t kBufferBytes = sizeof(Header) + sizeof(Vertex)*kMaxVertices;

inline uint32_t Hash(const void* data, std::size_t bytes) {
    auto* p = static_cast<const uint8_t*>(data);
    uint32_t result=2166136261u;
    for (std::size_t i=0; i<bytes; ++i)
        result = (result ^ p[i])*16777619u;
    return result;
}

inline bool Finite(float a) {
    return a == a && a > -100000.0f && a < 100000.0f;
}

inline bool Valid(const void* data, std::size_t length) {
    if (!data || length < sizeof(Header) || length > kBufferBytes) return false;
    auto* h = static_cast<const Header*>(data);
    if (h->magic != kMagic || h->version != kVersion) return false;
    if (h->vertexCount % 3 || h->vertexCount > kMaxVertices) return false;
    std::size_t bytes = std::size_t(h->vertexCount)*sizeof(Vertex);
    if (length != sizeof(Header)+bytes) return false;
    for (float x : h->minecraftOrigin) if (!Finite(x)) return false;
    for (float x : h->hyruleOrigin) if (!Finite(x)) return false;
    auto* payload = reinterpret_cast<const uint8_t*>(data)+sizeof(Header);
    if (Hash(payload,bytes) != h->payloadHash) return false;
    auto* verts = reinterpret_cast<const Vertex*>(payload);
    for (uint32_t i=0;i<h->vertexCount;++i) {
        const auto& v=verts[i];
        if (!Finite(v.x) || !Finite(v.y) || !Finite(v.z)) return false;
        if (v.u != v.u || v.v != v.v) return false;
    }
    return true;
}

// A projected vertex is produced on the native render thread using Zelda's
// LIVE view/projection matrix. No Minecraft camera yaw/pitch is read here.
struct ClipVertex {
    float x,y,z,w;
    float r,g,b,a;
};
static_assert(sizeof(ClipVertex)==32);

struct ViewProjection {
    // Column-major 4x4 view * projection, from the game graphics camera.
    float m[16];
    bool ready;
};

// Converts a REAL Zelda camera object's position/target/up vectors to a
// column-major NVN 0..1 depth projection. Call the SDK Camera::GetPosition,
// GetLookAt, GetUp only with a verified live game camera pointer.
//
// This is deliberately NOT called with Minecraft's yaw/pitch. A Zelda
// camera hook must supply the vectors and actual FOV/aspect from the game.
inline bool BuildViewProjection(const float eye[3], const float at[3],
                                const float sourceUp[3], float verticalFocal,
                                float aspect, float zNear, float zFar,
                                ViewProjection& out) {
    out.ready = false;
    if (!eye || !at || !sourceUp) return false;
    if (!(verticalFocal > 0.05f && verticalFocal < 100.0f &&
          aspect > 0.1f && aspect < 10.0f &&
          zNear > 0.001f && zFar > zNear)) return false;
    for (int i=0;i<3;i++)
        if (!Finite(eye[i]) || !Finite(at[i]) || !Finite(sourceUp[i]))
            return false;

    float forward[3]={at[0]-eye[0],at[1]-eye[1],at[2]-eye[2]};
    auto normalize=[](float v[3]) -> bool {
        float lenSq = v[0]*v[0]+v[1]*v[1]+v[2]*v[2];
        if (!(lenSq > 1.e-8f && lenSq < 1.e12f)) return false;
        float inv=1.0f / __builtin_sqrtf(lenSq);
        for (int i=0;i<3;i++) v[i]*=inv;
        return true;
    };
    auto cross=[](const float a[3],const float b[3],float outVec[3]) {
        outVec[0]=a[1]*b[2]-a[2]*b[1];
        outVec[1]=a[2]*b[0]-a[0]*b[2];
        outVec[2]=a[0]*b[1]-a[1]*b[0];
    };
    auto dot=[](const float a[3],const float b[3]) {
        return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
    };
    if (!normalize(forward)) return false;
    float right[3]{};
    cross(forward,sourceUp,right);
    if (!normalize(right)) return false;
    float up[3]{};
    cross(right,forward,up);
    if (!normalize(up)) return false;

    // Vertical focal = cot(game vertical FOV / 2), provided by Zelda's
    // own current projection matrix. No trig/libm guesswork on Switch.
    float fy=verticalFocal;
    float fx=fy/aspect;
    float depthA=zFar/(zFar-zNear);
    float depthB=-zNear*zFar/(zFar-zNear);
    float* m=out.m;
    m[0]=right[0]*fx; m[4]=right[1]*fx; m[8]=right[2]*fx;
    m[12]=-dot(right,eye)*fx;
    m[1]=up[0]*fy; m[5]=up[1]*fy; m[9]=up[2]*fy;
    m[13]=-dot(up,eye)*fy;
    m[2]=forward[0]*depthA; m[6]=forward[1]*depthA;
    m[10]=forward[2]*depthA;
    m[14]=-dot(forward,eye)*depthA+depthB;
    m[3]=forward[0]; m[7]=forward[1]; m[11]=forward[2];
    m[15]=-dot(forward,eye);
    out.ready=true;
    return true;
}

// This is the native camera adapter's math kernel. It cannot replace a true
// Zelda camera hook: caller MUST set ready only with a measured game matrix.
inline bool Project(const ViewProjection& camera, const Vertex& v,
                    ClipVertex& out) {
    if (!camera.ready) return false;
    auto& m=camera.m;
    float x=v.x,y=v.y,z=v.z;
    float px=m[0]*x+m[4]*y+m[8]*z+m[12];
    float py=m[1]*x+m[5]*y+m[9]*z+m[13];
    float pz=m[2]*x+m[6]*y+m[10]*z+m[14];
    float pw=m[3]*x+m[7]*y+m[11]*z+m[15];
    if (!(pw > 0.0001f && pw < 1.0e9f) || px!=px || py!=py || pz!=pz)
        return false;
    const float scale=1.0f/255.0f;
    out={px,py,pz,pw,
         float((v.argb>>16)&255)*scale,
         float((v.argb>>8)&255)*scale,
         float(v.argb&255)*scale,
         float((v.argb>>24)&255)*scale};
    return true;
}
} // namespace BotwCraftWorld
