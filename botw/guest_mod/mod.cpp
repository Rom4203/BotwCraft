// BotwCraft native BOTW adapter: real game API only, no synthetic position.
//
// This is the missing HOST half of SkyCraft, not an alternate Minecraft
// implementation. WiiXLaunch currently reports that Switch Player::GetPosition
// is unsupported, so on BOTW 1.0.0 the safe result is to refuse player hooks
// rather than install an address from another executable and crash Ryujinx.
#include <cstdint>
#include <cstdio>
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
    uint32_t frame = 0;
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
        // One decimal per 1/1000 game unit; not a fabricated or stale pose.
        const int32_t x = static_cast<int32_t>(xyz[0] * 1000.0f);
        const int32_t y = static_cast<int32_t>(xyz[1] * 1000.0f);
        const int32_t z = static_cast<int32_t>(xyz[2] * 1000.0f);
        char buf[160] = {};
        std::snprintf(buf, sizeof(buf),
            "BotwCraft:NATIVE_POSITION_MILLI x=%d y=%d z=%d", x, y, z);
        Log(buf);
    }
}

extern "C" __attribute__((used)) void WiiXLaunch_ModEntry() {
    Log("BotwCraft: native game adapter, strict capabilities; no preview world");
    if (!Player::SupportsPosition || Player::SupportsPosition() == 0) {
        Log("BotwCraft: BOTW_NATIVE_UNSUPPORTED: verified player position API absent");
        Log("BotwCraft: no player hook installed; Minecraft is NOT linked to Hyrule");
        return;
    }
    if (!Player::Init || !Player::RegisterTick || !Player::GetPosition) {
        Log("BotwCraft: BOTW_NATIVE_UNSUPPORTED: required API import missing");
        return;
    }
    // Init() returns 0 both when the hook already exists and if unavailable.
    // Registration must also succeed; we only enable our own callback then.
    Player::Init();
    if (!Player::RegisterTick(&PlayerTick)) {
        Log("BotwCraft: BOTW_NATIVE_UNSUPPORTED: tick registration refused");
        return;
    }
    active = true;
    const bool input = Controller::SupportsInjection && Controller::SupportsInjection() != 0;
    const bool gx2 = Graphics::IsGX2 && Graphics::IsGX2() != 0;
    char buf[140] = {};
    std::snprintf(buf, sizeof(buf),
        "BotwCraft: native position ready; input=%u graphics=%s",
        static_cast<unsigned>(input), gx2 ? "GX2" : "NVN/unknown");
    Log(buf);
    Log("BotwCraft: native position telemetry active (orientation/collision/render not wired)");
}
