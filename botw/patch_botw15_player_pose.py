"""Install a fingerprint-locked BOTW Switch 1.5.0 Link position callback.

Sources for addresses: zeldaret/botw decomp (Switch 1.5.0):
  data/data_symbols.csv:
    0x71025CDB60 _ZN5uking3act10PlayerInfo9sInstanceE
  data/uking_functions.csv:
    0x7100854BA0 PlayerInfo::getPlayerUnchecked
    0x7100854BA8 PlayerInfo::getPlayerPos

Unlike the mismatched 1.0.0 PlayerTick patch, this never installs an arbitrary
player hook. NVN callback already comes from WiiXLaunch's 1.5.0 graphics path.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = ROOT / "WiiXLaunch"
MAIN = HOST / "src" / "main.cpp"
HEADER = HOST / "include" / "wiixlaunch" / "botwcraft_switch15_pose.hpp"
DIRECT_SOURCE = ROOT / "botw" / "switch15_direct_hook.hpp"
DIRECT_HEADER = HOST / "include" / "wiixlaunch" / "botwcraft_switch15_direct.hpp"

INCLUDE_ANCHOR = "#include <wiixlaunch/game_version.hpp>"
INCLUDE_INSERT = "#include <wiixlaunch/botwcraft_switch15_pose.hpp>"
DRAW_ANCHOR = """if (WiiXLaunch::GameVersion::Recognised()) {
        NVN::Init();
    }"""
DRAW_REPLACE = """if (WiiXLaunch::GameVersion::Recognised()) {
        NVN::Init();
        BotwCraft15::Register();
    }"""

HEADER_CONTENT = r"""#pragma once
// BotwCraft: native PlayerInfo pose sampling, only BOTW Switch 1.5.0.
//
// Addresses from zeldaret/botw data_symbols.csv / uking_functions.csv,
// NOT guessed from Wii U, and NOT the incompatible PlayerTick hook.
// Actual run-time CRC is gated below, before touching even the singleton.
#include <wiixlaunch/platform.hpp>
#if WIIXL_SWITCH
#include <wiixlaunch/game_version.hpp>
#include <wiixlaunch/debug_log.hpp>
#include <wiixlaunch/botwcraft_switch15_direct.hpp>
#include <wiixlaunch/botw/graphics/nvn.hpp>
#include <lib.hpp>
#include <cstdint>

namespace BotwCraft15 {
constexpr uint32_t kExpectedFingerprint = 0xA982D2BC;
constexpr uintptr_t kSingletonOffset    = 0x25CDB60;
constexpr uintptr_t kGetPlayerOffset    = 0x854BA0;
constexpr uintptr_t kGetPositionOffset  = 0x854BA8;

using GetPlayerUncheckedFn = void* (*)(void*);
using GetPositionFn = const float* (*)(void*);

inline bool ValidCoordinate(float x) {
    // Guards integer conversion and rejects NaN/Infinity/implausible data.
    return x == x && x > -100000.0f && x < 100000.0f;
}

inline void Poll(WiiXLaunch::BotW::NVN::CommandBuffer*, void*, int, int) {
    if (WiiXLaunch::GameVersion::Fingerprint() != kExpectedFingerprint) return;
    static uint32_t frames = 0;
    ++frames;

    const uintptr_t main = exl::util::GetMainModuleInfo().m_Total.m_Start;
    // This symbol is a POINTER to PlayerInfo, not the object itself.
    auto** singleton = reinterpret_cast<void**>(main + kSingletonOffset);
    if (!singleton || !*singleton) return;
    void* const info = *singleton;

    // Validate a real player exists before calling getPlayerPos, which
    // acquires the actor and may access game state unavailable in menus.
    const auto getPlayer = reinterpret_cast<GetPlayerUncheckedFn>(
        main + kGetPlayerOffset);
    void* const player = getPlayer(info);
    if (!player) return;
    const auto getPos = reinterpret_cast<GetPositionFn>(
        main + kGetPositionOffset);
    const float* xyz = getPos(info);
    if (!xyz || !ValidCoordinate(xyz[0]) ||
        !ValidCoordinate(xyz[1]) || !ValidCoordinate(xyz[2])) return;

    BotwCraft15Direct::Poll(player, xyz);
    if ((frames % 6) != 0) return;

    const int32_t x = static_cast<int32_t>(xyz[0] * 1000.0f);
    const int32_t y = static_cast<int32_t>(xyz[1] * 1000.0f);
    const int32_t z = static_cast<int32_t>(xyz[2] * 1000.0f);
    WIIXL_LOG("BotwCraft:NATIVE_POSITION_MILLI x=%d y=%d z=%d", x, y, z);
}

inline void Register() {
    if (WiiXLaunch::GameVersion::Fingerprint() != kExpectedFingerprint) {
        WIIXL_LOG("BotwCraft: Link pose sampling disabled - requires Switch 1.5.0 fingerprint 0xA982D2BC");
        return;
    }
    BotwCraft15Direct::Register();
    WiiXLaunch::BotW::NVN::RegisterDrawCallback(&Poll);
    WIIXL_LOG("BotwCraft: Switch 1.5.0 Link pose reader registered from PlayerInfo");
}
} // namespace BotwCraft15
#endif // WIIXL_SWITCH
"""

def patch():
    if not DIRECT_SOURCE.is_file():
        raise RuntimeError("Missing botw/switch15_direct_hook.hpp")
    if DIRECT_HEADER.exists() and DIRECT_HEADER.read_text(encoding="utf-8") != DIRECT_SOURCE.read_text(encoding="utf-8"):
        raise RuntimeError("Existing BOTW direct hook differs; refusing overwrite")
    DIRECT_HEADER.parent.mkdir(parents=True, exist_ok=True)
    DIRECT_HEADER.write_text(DIRECT_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    if not MAIN.exists():
        raise RuntimeError("WiiXLaunch src/main.cpp missing; run setup_wiixlaunch.py first")
    text = MAIN.read_text(encoding="utf-8")
    if INCLUDE_INSERT in text and "BotwCraft15::Register();" in text:
        if not HEADER.is_file() or HEADER.read_text(encoding="utf-8") != HEADER_CONTENT:
            raise RuntimeError("Existing BotwCraft pose header differs from verified source")
        print("[OK] Switch 1.5.0 PlayerInfo sampler already installed")
        return False
    if text.count(INCLUDE_ANCHOR) != 1 or text.count(DRAW_ANCHOR) != 1:
        raise RuntimeError("Unexpected WiiXLaunch host version or missing Switch hook guard")
    if HEADER.exists() and HEADER.read_text(encoding="utf-8") != HEADER_CONTENT:
        raise RuntimeError("Refusing to replace a modified native player sampler")
    HEADER.write_text(HEADER_CONTENT, encoding="utf-8")
    text = text.replace(INCLUDE_ANCHOR, INCLUDE_ANCHOR + "\n" + INCLUDE_INSERT, 1)
    text = text.replace(DRAW_ANCHOR, DRAW_REPLACE, 1)
    MAIN.write_text(text, encoding="utf-8")
    print("[OK] Installed build-fingerprint-locked Switch 1.5.0 Link pose sampling")
    return True

if __name__ == "__main__":
    try:
        patch()
    except (OSError, RuntimeError) as exc:
        raise SystemExit(f"[BotwCraft] Pose patch ERROR: {exc}")
