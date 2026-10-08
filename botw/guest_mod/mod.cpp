// First BOTW Switch/AArch64 guest module for WiiXLaunch.
// Native module, NOT a gamepad adapter. This is a safe load diagnostic;
// player position requires a verified BOTW v0 game-specific symbol.
#include <wiixlaunch/imports/wiixl_core.h>
#include <wiixlaunch/mod_runtime.h>

namespace Core {
WXL_USE_wiixl_core(Log);
}

extern "C" __attribute__((used)) void WiiXLaunch_ModEntry() {
    if (Core::Log) {
        Core::Log("BotwCraft: Switch native module loaded; waiting for v0 player hooks");
    }
}
