// BotwCraft native BOTW adapter: real game API only, no synthetic position.
//
// Safe BOTW 1.5.0 adapter. The ROMFS frame polling experiment crashed
// Ryujinx 1.3.3 in nn::fs::ReadFile (0xD401). Never call GameReadFile,
// register a mesh draw callback or attempt Switch filesystem I/O here.
// Link's real native pose telemetry remains independent of mesh rendering.
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
}

namespace {
    // Native graphics handoff disabled until a proven live IPC channel exists.
    // The WiiXLaunch host's own NVN hooks remain under its control.

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
    // Crash-proof telemetry mode: no native guest filesystem access.
    Log("BotwCraft:MESH_DISABLED - ROMFS ReadFile caused Ryujinx abort 0xD401; "
        "native render bridge unvalidated");

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
