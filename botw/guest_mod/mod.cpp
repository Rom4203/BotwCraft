// BotwCraft native BOTW adapter: real game API only, no synthetic position.
//
// BOTW 1.5.0 native diagnostic graphics PROBE, NOT Minecraft rendering.
// A ROMFS ReadFile inside a draw callback crashed Ryujinx 1.3.3 (0xD401).
// Draw a single fixed triangle using botw.gfx.DrawMesh, without any fs I/O.
// This validates native NVN callback and geometry shader separately from IPC.
// If successful, a safe host->guest live packet transport is still required.
#include <cstdint>
#include "../native_guest_mesh.hpp"
#include "../native_world_scene.hpp"
#include <wiixlaunch/imports/wiixl_core.h>
#include <wiixlaunch/imports/botw_player.h>
#include <wiixlaunch/imports/botw_input.h>
#include <wiixlaunch/imports/botw_gfx.h>
#include <wiixlaunch/mod_runtime.h>

namespace Core {
WXL_USE_wiixl_core(Log);
}
namespace Player {
WXL_USE_botw_player(SupportsPosition);
WXL_USE_botw_player(Init);
WXL_USE_botw_player(RegisterTick);
WXL_USE_botw_player(GetPosition);
}
namespace Controller {
WXL_USE_botw_input(SupportsInjection);
}
namespace Graphics {
WXL_USE_botw_gfx(IsGX2);
WXL_USE_botw_gfx(RegisterDraw);
WXL_USE_botw_gfx(DrawMesh);
}

namespace {
    uint32_t frame = 0; // Throttle authentic Link position log from PlayerTick.
    uint32_t drawCallbackCount = 0;
    // Exposed ONLY for explicit local GDB debug writes. The host discovers
    // this guest pointer from our native log, never from hard-coded offsets.
    // GDB halts the guest while writing, so a full packet lands atomically
    // with respect to the NVN frame callback.
    alignas(16) uint8_t gGdbMeshPacket[BotwCraftMesh::kMaxBytes]{};
    // BWC2: real Hyrule-world coordinates, UV, tint and light. A separate
    // game-native camera provider must mark the live view/projection ready;
    // no Minecraft camera is EVER used for this 3D scene.
    alignas(16) uint8_t gWorldPacket[BotwCraftWorld::kBufferBytes]{};
    alignas(16) BotwCraftWorld::ViewProjection gZeldaViewProjection{};
    alignas(16) BotwCraftWorld::ClipVertex
        gProjectedWorldVertices[BotwCraftWorld::kMaxVertices]{};
    uint32_t gWorldLastFrame = 0;
    bool gWorldSeen = false;

    uint32_t lastAcceptedMeshFrame = 0;
    uint32_t lastAcceptedMeshVertices = 0;
    bool gdbMeshReady = false;

    // Static 3-vertex diagnostic triangle, deliberately NOT Minecraft data.
    // Layout botw.gfx v1.1: clip (x,y,z,w), then (nx,ny,nz,nw).
    // Center of screen, moderate size; no Nintendo resources or game pointers.
    alignas(16) const float kTriangle[3 * 8] = {
        -0.18f, -0.18f, 0.5f, 1.0f, 1.0f, 0.0f, 0.0f, 1.0f,
         0.18f, -0.18f, 0.5f, 1.0f, 0.0f, 1.0f, 0.0f, 1.0f,
         0.00f,  0.18f, 0.5f, 1.0f, 0.0f, 0.0f, 1.0f, 1.0f,
    };

    void LogTaggedHex(char* buf, const char* prefix, uintptr_t address) {
        // Freestanding ARM64 guest cannot depend on snprintf/printf.
        char* p = buf;
        while (*prefix) *p++ = *prefix++;
        for (int shift = int(sizeof(uintptr_t) * 8) - 4; shift >= 0; shift -= 4) {
            unsigned nibble = static_cast<unsigned>((address >> shift) & 0xFu);
            *p++ = "0123456789abcdef"[nibble];
        }
        *p = '\0';
    }

    void OnGameDraw(uintptr_t cb, uintptr_t texture, int32_t w, int32_t h) {
        (void)w; (void)h;
        if (cb == 0 || texture == 0 || !Graphics::DrawMesh) return;
        const float* vertices = kTriangle;
        uint32_t count = 3;

        // Read ONLY the buffer owned by this module. Never open guest files,
        // scan Zelda memory or dereference pointers received from Windows.
        const auto* header =
            reinterpret_cast<const BotwCraftMesh::Header*>(gGdbMeshPacket);
        if (header->magic == BotwCraftMesh::kMagic
            && header->version == BotwCraftMesh::kVersion
            && header->vertexCount > 0
            && header->vertexCount <= BotwCraftMesh::kMaxVertices
            && header->vertexCount % 3 == 0) {
            const auto bytes = sizeof(BotwCraftMesh::Header)
                + static_cast<size_t>(header->vertexCount) * sizeof(BotwCraftMesh::Vertex);
            if (BotwCraftMesh::Valid(gGdbMeshPacket, bytes)) {
                vertices = reinterpret_cast<const float*>(
                    gGdbMeshPacket + sizeof(BotwCraftMesh::Header));
                count = header->vertexCount;
                if (!gdbMeshReady || header->frameId != lastAcceptedMeshFrame) {
                    lastAcceptedMeshFrame = header->frameId;
                    lastAcceptedMeshVertices = count;
                    if (Core::Log) Core::Log("BotwCraft:GDB_MESH_FRAME_ACCEPTED");
                }
                gdbMeshReady = true;
            }
        }
        // SkyCraft parity channel: project native BWC2 world geometry only
        // against a REAL game camera view/projection. Do not confuse the old
        // triangle-probe camera with Hyrule coordinates.
        const auto* worldHeader =
            reinterpret_cast<const BotwCraftWorld::Header*>(gWorldPacket);
        if (worldHeader->magic == BotwCraftWorld::kMagic &&
            worldHeader->vertexCount > 0 &&
            worldHeader->vertexCount <= BotwCraftWorld::kMaxVertices) {
            // World space is authoritative. Do not draw the old 2D probe
            // if a BWC2 scene exists but Zelda's camera is not ready.
            if (!gZeldaViewProjection.ready) return;
            const size_t length = sizeof(BotwCraftWorld::Header) +
                size_t(worldHeader->vertexCount) * sizeof(BotwCraftWorld::Vertex);
            if (BotwCraftWorld::Valid(gWorldPacket, length)) {
                const auto* worldVertices =
                    reinterpret_cast<const BotwCraftWorld::Vertex*>(
                        gWorldPacket + sizeof(BotwCraftWorld::Header));
                uint32_t projected = 0;
                // Reject entire triangles crossing the eye/near plane until
                // the clipper owns them; never make huge turquoise strips.
                for (uint32_t i = 0; i < worldHeader->vertexCount; i += 3) {
                    BotwCraftWorld::ClipVertex triangle[3]{};
                    if (!BotwCraftWorld::Project(gZeldaViewProjection,
                                                 worldVertices[i], triangle[0]) ||
                        !BotwCraftWorld::Project(gZeldaViewProjection,
                                                 worldVertices[i+1], triangle[1]) ||
                        !BotwCraftWorld::Project(gZeldaViewProjection,
                                                 worldVertices[i+2], triangle[2]))
                        continue;
                    for (unsigned j=0; j<3; ++j)
                        gProjectedWorldVertices[projected++] = triangle[j];
                }
                if (projected) {
                    vertices =
                        reinterpret_cast<const float*>(gProjectedWorldVertices);
                    count = projected;
                    if (!gWorldSeen || worldHeader->frameId != gWorldLastFrame) {
                        gWorldLastFrame = worldHeader->frameId;
                        gWorldSeen = true;
                        if (Core::Log)
                            Core::Log("BotwCraft:WORLD_SCENE_3D_ACCEPTED");
                    }
                }
            }
        }
        const uint32_t ok = Graphics::DrawMesh(cb, texture, vertices, count);
        ++drawCallbackCount;
        if (drawCallbackCount == 1 && Core::Log) {
            Core::Log(ok
                ? "BotwCraft:VISUAL_PROBE_DRAW_CALLED result=1 vertices=3"
                : "BotwCraft:VISUAL_PROBE_DRAW_CALLED result=0 vertices=3");
        }
        if (gdbMeshReady && drawCallbackCount % 240 == 0 && Core::Log) {
            Core::Log(ok ? "BotwCraft:GDB_MESH_DRAW_OK" :
                           "BotwCraft:GDB_MESH_DRAW_FAILED");
        }
    }

    void AppendLiteral(char*& ptr, const char* text) {
        while (*text) *ptr++ = *text++;
    }

    void AppendNumber(char*& ptr, int32_t value) {
        if (value < 0) {
            *ptr++ = '-';
            value = -value; // range checked before conversion
        }
        char digits[12];
        unsigned count = 0;
        do {
            digits[count++] = char('0' + value % 10);
            value /= 10;
        } while (value && count < sizeof(digits));
        while (count) *ptr++ = digits[--count];
    }

    bool FinitePosition(float v) {
        // Range must keep *1000 representable as signed 32-bit.
        return v == v && v > -100000.0f && v < 100000.0f;
    }
    bool active = false;

    void Log(const char* message) {
        if (Core::Log) Core::Log(message);
    }

    // This callback is only registered after Player::SupportsPosition() says
    // the actual current game build is supported. Never read raw offsets.
    void PlayerTick() {
        if (!active || !Player::GetPosition) return;
        if ((++frame % 6) != 0) return;
        float xyz[3] = {};
        if (!Player::GetPosition(xyz)) return;
        if (!FinitePosition(xyz[0]) ||
            !FinitePosition(xyz[1]) ||
            !FinitePosition(xyz[2])) return;
        // No libc printf dependency in a freestanding .wxlm guest.
        char buf[150] = {};
        char* ptr = buf;
        AppendLiteral(ptr, "BotwCraft:NATIVE_POSITION_MILLI x=");
        AppendNumber(ptr, static_cast<int32_t>(xyz[0] * 1000.0f));
        AppendLiteral(ptr, " y=");
        AppendNumber(ptr, static_cast<int32_t>(xyz[1] * 1000.0f));
        AppendLiteral(ptr, " z=");
        AppendNumber(ptr, static_cast<int32_t>(xyz[2] * 1000.0f));
        *ptr = 0;
        Log(buf);
    }
}

extern "C" __attribute__((used)) void WiiXLaunch_ModEntry() {
    Log("BotwCraft: native game adapter, strict capabilities; no preview world");
    // No ROMFS, no SD, no sockets and NO live Minecraft mesh packets in this
    // stage. Only a fixed 3-vertex triangle to isolate the NVN draw capability.
    Log("BotwCraft:STATIC_PROBE_AND_GDB; native BWC1 packet buffer ready");
    char addressMessage[80] = {};
    LogTaggedHex(addressMessage, "BotwCraft:GDB_MESH_BUFFER_ADDR=0x",
                 reinterpret_cast<uintptr_t>(gGdbMeshPacket));
    Log(addressMessage);
    Log("BotwCraft:GDB_MESH_CAPACITY=16416 (32 + 512*32); GDB required");
    LogTaggedHex(addressMessage, "BotwCraft:BWC2_WORLD_BUFFER_ADDR=0x",
                 reinterpret_cast<uintptr_t>(gWorldPacket));
    Log(addressMessage);
    LogTaggedHex(addressMessage, "BotwCraft:BWC2_CAMERA_SLOT_ADDR=0x",
                 reinterpret_cast<uintptr_t>(&gZeldaViewProjection));
    Log(addressMessage);
    Log("BotwCraft:BWC2_WORLD_BUFFER_CAPACITY=15416");
    Log("BotwCraft:BWC2_WAITING_FOR_ZELDA_CAMERA");

    if (Graphics::RegisterDraw && Graphics::DrawMesh) {
        if (Graphics::RegisterDraw(&OnGameDraw)) {
            Log("BotwCraft:VISUAL_PROBE_REGISTERED; awaiting Zelda NVN frames");
        } else {
            Log("BotwCraft:VISUAL_PROBE_REJECTED by native graphics backend");
        }
    } else {
        Log("BotwCraft:VISUAL_PROBE_UNSUPPORTED; NVN drawing imports missing");
    }

    if (!Player::SupportsPosition || Player::SupportsPosition() == 0) {
        Log("BotwCraft: BOTW_NATIVE_UNSUPPORTED: player position API absent");
        Log("BotwCraft: render channel independent; no Link pose hook installed");
        return;
    }
    if (!Player::Init || !Player::RegisterTick || !Player::GetPosition) {
        Log("BotwCraft: BOTW_NATIVE_UNSUPPORTED: required player import missing");
        return;
    }
    Player::Init();
    if (!Player::RegisterTick(&PlayerTick)) {
        Log("BotwCraft: BOTW_NATIVE_UNSUPPORTED: player tick refused");
        return;
    }
    active = true;
    const bool input = Controller::SupportsInjection && Controller::SupportsInjection() != 0;
    const bool gx2 = Graphics::IsGX2 && Graphics::IsGX2() != 0;
    Log(input ? "BotwCraft: game input capability present"
              : "BotwCraft: game input injection unsupported");
    Log(gx2 ? "BotwCraft: GX2 graphics" : "BotwCraft: NVN/unknown graphics");
    Log("BotwCraft: real native pose telemetry active");
}
