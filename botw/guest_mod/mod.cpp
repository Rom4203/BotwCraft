// BotwCraft native BOTW adapter: real game API only, no synthetic position.
//
// BOTW 1.5.0 native diagnostic graphics PROBE, NOT Minecraft rendering.
// A ROMFS ReadFile inside a draw callback crashed Ryujinx 1.3.3 (0xD401).
// Draw a single fixed triangle using botw.gfx.DrawMesh, without any fs I/O.
// This validates native NVN callback and geometry shader separately from IPC.
// If successful, a safe host->guest live packet transport is still required.
#include <cstdint>
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

    // Static 3-vertex diagnostic triangle, deliberately NOT Minecraft data.
    // Layout botw.gfx v1.1: clip (x,y,z,w), then (nx,ny,nz,nw).
    // Center of screen, moderate size; no Nintendo resources or game pointers.
    alignas(16) const float kTriangle[3 * 8] = {
        -0.18f, -0.18f, 0.5f, 1.0f, 1.0f, 0.0f, 0.0f, 1.0f,
         0.18f, -0.18f, 0.5f, 1.0f, 0.0f, 1.0f, 0.0f, 1.0f,
         0.00f,  0.18f, 0.5f, 1.0f, 0.0f, 0.0f, 1.0f, 1.0f,
    };

    void OnGameDraw(uintptr_t cb, uintptr_t texture, int32_t w, int32_t h) {
        (void)w; (void)h;
        if (cb == 0 || texture == 0 || !Graphics::DrawMesh) return;
        const uint32_t ok = Graphics::DrawMesh(cb, texture, kTriangle, 3);
        ++drawCallbackCount;
        if (drawCallbackCount == 1 && Core::Log) {
            Core::Log(ok
                ? "BotwCraft:VISUAL_PROBE_DRAW_CALLED result=1 vertices=3"
                : "BotwCraft:VISUAL_PROBE_DRAW_CALLED result=0 vertices=3");
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
    Log("BotwCraft:VISUAL_PROBE_ONLY; triangle is NOT Minecraft terrain");
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
