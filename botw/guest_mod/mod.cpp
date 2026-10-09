// BotwCraft native BOTW adapter: real game API only, no synthetic position.
//
// This is the missing HOST half of SkyCraft, not an alternate Minecraft
// implementation. WiiXLaunch currently reports that Switch Player::GetPosition
// is unsupported, so on BOTW 1.0.0 the safe result is to refuse player hooks
// rather than install an address from another executable and crash Ryujinx.
#include <cstdint>
#include <wiixlaunch/imports/wiixl_core.h>
#include <wiixlaunch/imports/botw_player.h>
#include <wiixlaunch/imports/botw_input.h>
#include <wiixlaunch/imports/botw_gfx.h>
#include <wiixlaunch/mod_runtime.h>
#include "../native_guest_mesh.hpp"

namespace Core {
WXL_USE_wiixl_core(Log);
WXL_USE_wiixl_core(GameReadFile);
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
    // Read ROMFS first: WiiXLaunch loaded us from the game's mounted ROMFS
    // even when MountSdCardForDebug was denied by Ryujinx.
    // This is a relative path by design: FS::Candidates resolves it through
    // the game's actual live ROMFS mount (often "content:").
    //
    // IMPORTANT: ROMFS overlay may be SNAPSHOTTED by Ryujinx at game start.
    // This path guarantees neither live updates nor a functioning renderer.
    constexpr const char* kMeshRomfsPath =
        "WiiXLaunch/mods/botwcraft/frame.bin";
    constexpr const char* kMeshSdPath =
        "sd:/WiiXLaunch/mods/01007EF00011E000/botwcraft/frame.bin";
    alignas(16) uint8_t meshBytes[BotwCraftMesh::kMaxBytes]{};
    alignas(16) uint8_t stagingBytes[BotwCraftMesh::kMaxBytes]{};
    uint32_t meshFrame = 0;
    uint32_t meshCount = 0;
    uint32_t gfxFrame = 0;
    bool meshReady = false;
    bool meshReadLogged = false;
    bool romfsReadAvailable = false;
    uint32_t meshPolls = 0;
    uint32_t frame = 0;

    void OnGameDraw(uintptr_t commandBuffer, uintptr_t dstTexture,
                    int32_t width, int32_t height) {
        (void)width; (void)height;
        // 5 fps SD polling. Avoid I/O on every draw call. The GPU reuses the
        // verified previous frame in between.
        if ((++gfxFrame % 12) == 1 && Core::GameReadFile) {
            ++meshPolls;
            // ROMFS is mounted to load botwcraft.wxlm, whereas Ryujinx's
            // MountSdCardForDebug may be denied (0x320002).
            int32_t n =
                Core::GameReadFile(kMeshRomfsPath, stagingBytes, sizeof(stagingBytes));
            bool valid = n >= int32_t(sizeof(BotwCraftMesh::Header))
                && BotwCraftMesh::Valid(stagingBytes, static_cast<size_t>(n));
            const bool romfsValid = valid;
            if (romfsValid && !romfsReadAvailable) {
                romfsReadAvailable = true;
                if (Core::Log)
                    Core::Log("BotwCraft:MESH_ROMFS_READ_OK; "
                              "static file accessible, live updates unverified");
            }
            // Switch SD fallback no more often than approximately 40 sec.
            // Only use the contents if the complete BWC1 hash validates.
            // Re-read ROMFS if a failed SD probe overwrote staging.
            if (meshPolls % 240 == 0) {
                const int32_t sd =
                    Core::GameReadFile(kMeshSdPath, stagingBytes, sizeof(stagingBytes));
                if (sd >= int32_t(sizeof(BotwCraftMesh::Header))
                    && BotwCraftMesh::Valid(stagingBytes, static_cast<size_t>(sd))) {
                    n = sd;
                    valid = true;
                    if (!meshReadLogged && Core::Log)
                        Core::Log("BotwCraft:MESH_SD_READ_OK");
                    meshReadLogged = true;
                } else {
                    n = Core::GameReadFile(kMeshRomfsPath,
                                           stagingBytes, sizeof(stagingBytes));
                    valid = n >= int32_t(sizeof(BotwCraftMesh::Header))
                        && BotwCraftMesh::Valid(stagingBytes, static_cast<size_t>(n));
                }
            }
            if (valid) {
                const auto* h =
                    reinterpret_cast<const BotwCraftMesh::Header*>(stagingBytes);
                if (h->frameId != meshFrame || !meshReadLogged) {
                    memcpy(meshBytes, stagingBytes, static_cast<size_t>(n));
                    meshFrame = h->frameId;
                    meshCount = h->vertexCount;
                    meshReady = meshCount > 0;
                    if (!meshReadLogged && Core::Log)
                        Core::Log("BotwCraft:MESH_FRAME_FIRST_ACCEPT");
                    else if (Core::Log)
                        Core::Log("BotwCraft:MESH_FRAME_CHANGED");
                    meshReadLogged = true;
                }
            }
        }
        if (meshReady && Graphics::DrawMesh && commandBuffer != 0 && dstTexture != 0) {
            const float* packed = reinterpret_cast<const float*>(
                meshBytes + sizeof(BotwCraftMesh::Header));
            // 8 floats per vertex: native NVN normals shader input.
            Graphics::DrawMesh(commandBuffer, dstTexture, packed, meshCount);
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
    // Graphics and position are separate capabilities. The native NVN
    // renderer can run even when BOTW Switch position is still unsupported.
    if (Graphics::RegisterDraw && Graphics::DrawMesh && Core::GameReadFile) {
        if (Graphics::RegisterDraw(&OnGameDraw)) {
            Log("BotwCraft: native NVN renderer registered; awaiting MC mesh on SD");
        } else {
            Log("BotwCraft: native NVN draw registration refused");
        }
    } else {
        Log("BotwCraft: native renderer import missing");
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
