// BotwCraft native BOTW v1.5.0 standalone WiiXLaunch module.
// Build with the WiiXLaunch mod SDK. This module is NOT the existing botwcraft.wxlm.
// This stage provides a verified player tick and an owned BDP1 guest mailbox;
// applying actor/camera transforms still requires correct Switch engine hooks.
#include <cstdint>
#include <wiixlaunch/mod_runtime.h>
#include <wiixlaunch/imports/wiixl_core.h>
#include <wiixlaunch/imports/botw_player.h>

namespace S {
WXL_USE_wiixl_core(Log);
WXL_USE_botw_player(Init);
WXL_USE_botw_player(RegisterTick);
WXL_USE_botw_player(GetPlayerActor);
WXL_USE_botw_player(ActorIsValid);
WXL_USE_botw_player(ActorUnsafeRawPointer);
}

struct Pose {
    uint32_t seq, magic, version, flags;
    uint64_t frame, host_ms;
    float position[3], eye[3], forward[3], yaw, pitch;
    float mc_origin[3], botw_origin[3], reserved;
    uint32_t tail[2];
};
static_assert(sizeof(Pose) == 112, "BDP1 layout changed");

struct Mailbox {
    char marker[40];
    volatile Pose pose;
};

extern "C" {
// Intentionally one dedicated mailbox in the MODULE OWNED BSS.
// The Python sender must resolve this mailbox by a real guest-module address,
// not by assuming it equals the unrelated subsdk9 BDP1 marker.
__attribute__((used, aligned(16))) Mailbox g_BotwCraftGameMailbox = {
    "BOTWCRAFT_NATIVE_BDP1_GUEST_20261010", {}
};
}

static uint32_t s_ticks;
static uint32_t s_lastSeq;
static bool s_announcedActor;

static bool ReadPose(Pose& output) {
    auto* data = reinterpret_cast<volatile const uint8_t*>(&g_BotwCraftGameMailbox.pose);
    for (int attempt = 0; attempt < 4; ++attempt) {
        uint32_t a = g_BotwCraftGameMailbox.pose.seq;
        if (a & 1u) continue;
        auto* dest = reinterpret_cast<uint8_t*>(&output);
        for (unsigned n = 0; n < sizeof(output); ++n) dest[n] = data[n];
        uint32_t b = g_BotwCraftGameMailbox.pose.seq;
        if (a == b && !(b & 1u) && output.seq == a) return true;
    }
    return false;
}

extern "C" __attribute__((used)) void BotwCraftPlayerTick() {
    ++s_ticks;
    auto player = S::GetPlayerActor;
    auto valid = S::ActorIsValid;
    if (!player || !valid) return;
    uint32_t handle = player();
    if (!handle || !valid(handle)) return;
    if (!s_announcedActor) {
        s_announcedActor = true;
        if (S::ActorUnsafeRawPointer && S::ActorUnsafeRawPointer(handle))
            S::Log("[BOTW_NATIVE] Link actor tick captured via botw.player");
    }

    Pose p{};
    if (!ReadPose(p) || p.magic != 0x31504442u || p.version != 1u) return;
    if (!(p.flags & 1u) || !(p.flags & 2u) || p.seq == s_lastSeq) return;
    s_lastSeq = p.seq;
    if (s_ticks % 120 == 0) {
        S::Log("[BOTW_NATIVE] BDP1 guest packet received on player tick; transform hook not installed");
    }
    // DO NOT report movement as working here. The authoritative player Havok
    // transform setter and live LookAtCamera pointer must be resolved on Switch.
}
extern "C" __attribute__((used)) void WiiXLaunch_ModEntry() {
    if (!S::Log || !S::Init || !S::RegisterTick) return;
    S::Init();
    if (!S::RegisterTick(&BotwCraftPlayerTick)) {
        S::Log("[BOTW_NATIVE] RegisterTick refused");
        return;
    }
    S::Log("[BOTW_NATIVE] standalone module started; native player tick active");
}
