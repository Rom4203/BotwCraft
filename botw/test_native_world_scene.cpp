// Native BWC2 tests: world geometry, integrity, and Zelda-camera clip math.
#include "native_world_scene.hpp"
#include <cassert>
#include <cstring>
#include <cmath>
#include <cstdint>

int main() {
    using namespace BotwCraftWorld;
    static_assert(kBufferBytes == 56 + 480 * 32);
    alignas(16) uint8_t bytes[kBufferBytes] = {};
    auto* header = reinterpret_cast<Header*>(bytes);
    *header = {};
    header->magic = kMagic;
    header->version = kVersion;
    header->frameId = 7;
    header->vertexCount = 3;
    header->minecraftOrigin[0] = 34;
    header->minecraftOrigin[1] = 66;
    header->minecraftOrigin[2] = 99;
    header->hyruleOrigin[0] = -1125;
    header->hyruleOrigin[1] = 237;
    header->hyruleOrigin[2] = 1906;
    auto* v = reinterpret_cast<Vertex*>(bytes + sizeof(Header));
    v[0] = { -1126,237,1906,.125f,.5f,0xff64a0c0,0xf00,0x11 };
    v[1] = { -1125,237,1906,.75f,.5f,0xff64a0c0,0xf00,0x11 };
    v[2] = { -1125,238,1906,.75f,.9f,0xff64a0c0,0xf00,0x11 };
    header->payloadHash = Hash(v,sizeof(Vertex)*3);
    assert(Valid(bytes, sizeof(Header)+3*sizeof(Vertex)));

    // No Minecraft-camera-based screen projection in these vertices.
    assert(v[0].x == -1126 && v[0].z == 1906);
    assert(v[0].u == .125f && v[0].argb == 0xff64a0c0);

    ClipVertex out{};
    ViewProjection camera{};
    assert(!Project(camera, v[0], out));
    // A real 4x4 view/projection will be supplied by the BOTW camera hook.
    // Identity is ONLY a pure-math harness fixture, not a runtime fallback.
    for (int i=0;i<16;i++) camera.m[i] = i%5==0 ? 1.0f : 0.0f;
    camera.ready = true;
    assert(Project(camera,v[0],out));
    assert(out.x == -1126 && out.y == 237 && out.w == 1);
    assert(std::fabs(out.r-100.f/255.f)<.001f);
    assert(std::fabs(out.g-160.f/255.f)<.001f);
    assert(std::fabs(out.b-192.f/255.f)<.001f);
    assert(out.a == 1.f);

    // Full 3D Zelda camera basis: the same Hyrule world point stays fixed
    // as camera moves, and is transformed on the NATIVE frame thread.
    float eye[3]={1.f,2.f,3.f};
    float at[3]={1.f,2.f,4.f};
    float up[3]={0.f,1.f,0.f};
    ViewProjection realCamera{};
    assert(BuildViewProjection(eye,at,up,1.0f,1.0f,0.1f,100.f,realCamera));
    Vertex worldPoint={1.f,2.f,8.f,.5f,.5f,0xffffffff,0,0};
    ClipVertex worldClip{};
    assert(Project(realCamera,worldPoint,worldClip));
    assert(std::fabs(worldClip.x)<.001f);
    assert(std::fabs(worldClip.y)<.001f);
    assert(std::fabs(worldClip.w-5.f)<.001f);
    assert(worldClip.z>0.1f && worldClip.z<worldClip.w);
    eye[0] += 2.f;
    at[0] += 2.f;
    assert(BuildViewProjection(eye,at,up,1.0f,1.0f,0.1f,100.f,realCamera));
    assert(Project(realCamera,worldPoint,worldClip));
    assert(worldClip.x < -1.f);
    assert(!BuildViewProjection(eye,at,up,-1.f,1.f,0.1f,100.f,realCamera));
    assert(!realCamera.ready);

    // Corrupt textures or a truncated stream MUST NOT reach graphics.
    bytes[sizeof(Header)+5] ^= 0x1;
    assert(!Valid(bytes,sizeof(Header)+3*sizeof(Vertex)));
    bytes[sizeof(Header)+5] ^= 0x1;
    assert(!Valid(bytes,sizeof(Header)+3*sizeof(Vertex)-1));

    // Reject missing near plane and NaNs.
    camera.m[15] = -1.0f;
    assert(!Project(camera,v[0],out));
    v[0].x = __builtin_nanf("");
    assert(!Valid(bytes,sizeof(Header)+3*sizeof(Vertex)));
    return 0;
}
