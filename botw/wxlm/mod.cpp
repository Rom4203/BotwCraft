// BotwCraft WiiXLaunch AArch64 guest runtime: inbound pose + acknowledgement.
// Game engine transform/camera hooks are intentionally NOT fabricated here.
#include <cstdint>
#include <cstddef>
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
static_assert(sizeof(Pose) == 112, "Incorrect BDP1 wire size");
static_assert(offsetof(Pose, position) == 32, "Incorrect BDP1 wire offset");

enum : uint32_t {
    kMagic = 0x31504442u,
    kModuleReady = 0x42574331u, // BWC1
    kNoActor = 1,
    kActorSeen = 2,
    kPoseAccepted = 3,
    kEngineUnavailable = 4
};

struct alignas(16) Mailbox {
    char marker[40];
    volatile Pose packet;
    volatile uint32_t acknowledged_seq;
    volatile uint32_t runtime_state;
};
static_assert(offsetof(Mailbox, packet) == 40);
static_assert(offsetof(Mailbox, acknowledged_seq) == 152);
static_assert(sizeof(Mailbox) >= 160);

extern "C" {
// Marker must remain in the actual guest .data of this wxlm module.
// Never conflate it with the unrelated BDP1 symbol in subsdk9.
__attribute__((used, aligned(16))) Mailbox g_BotwCraftLiveMailbox = {
    "BOTWCRAFT_WXLM_BDP1_LIVE_20261010", {}, 0, kModuleReady
};
}

static uint32_t s_ticks = 0;
static uint32_t s_lastSeq = 0;
static uint32_t s_lastActiveTick = 0;
static bool s_loggedPlayer = false;
static bool s_loggedPose = false;
static bool s_loggedTimeout = false;

static bool readPacket(Pose& out) {
    const volatile uint8_t* input =
        reinterpret_cast<const volatile uint8_t*>(&g_BotwCraftLiveMailbox.packet);
    uint8_t* output = reinterpret_cast<uint8_t*>(&out);
    for (unsigned attempt = 0; attempt < 8; ++attempt) {
        const uint32_t before = g_BotwCraftLiveMailbox.packet.seq;
        if (before & 1u) continue;
        for (unsigned i = 0; i < sizeof(Pose); ++i) output[i] = input[i];
        const uint32_t after = g_BotwCraftLiveMailbox.packet.seq;
        if (after == before && !(after & 1u) && out.seq == after) return true;
    }
    return false;
}

extern "C" __attribute__((used)) void BotwCraftPlayerTick() {
    ++s_ticks;
    auto get = S::GetPlayerActor;
    auto valid = S::ActorIsValid;
    const uint32_t actor = get ? get() : 0;
    const bool actorReady = actor && valid && valid(actor);
    g_BotwCraftLiveMailbox.runtime_state = actorReady ? kActorSeen : kNoActor;
    if (actorReady && !s_loggedPlayer) {
        s_loggedPlayer = true;
        S::Log("[BOTW_NATIVE] Link actor resolved by player tick");
    }

    Pose p{};
    if (!readPacket(p) || p.magic != kMagic || p.version != 1) return;
    // Acknowledge even an unarmed probe so the Windows bridge can prove
    // WHICH of several identically marked guest-memory host mappings is live.
    g_BotwCraftLiveMailbox.acknowledged_seq = p.seq;
    if ((p.flags & 3u) != 3u || !actorReady) return;
    if (p.seq != s_lastSeq) {
        s_lastSeq = p.seq;
        s_lastActiveTick = s_ticks;
        s_loggedTimeout = false;
        if (!s_loggedPose) {
            s_loggedPose = true;
            S::Log("[BOTW_NATIVE] Fresh Minecraft BDP1 packets acknowledged");
        }
    }
    if (s_ticks - s_lastActiveTick > 120) {
        if (!s_loggedTimeout) {
            s_loggedTimeout = true;
            S::Log("[BOTW_NATIVE] Minecraft pose stale: game control disarmed");
        }
        return;
    }
    // This is a functioning IN-GAME receive path, not a fabricated actor warp.
    // The live Switch BOTW 1.5.0 setMtx ABI, render-hide, and camera update
    // hooks must be implemented/verified before this can drive Link.
    g_BotwCraftLiveMailbox.runtime_state = kEngineUnavailable;
}

extern "C" __attribute__((used)) void WiiXLaunch_ModEntry() {
    if (!S::Log || !S::Init || !S::RegisterTick) return;
    S::Init();
    if (!S::RegisterTick(&BotwCraftPlayerTick)) {
        S::Log("[BOTW_NATIVE] ERROR: player tick registration refused");
        return;
    }
    S::Log("[BOTW_NATIVE] Live mailbox + player tick online (no actor warp yet)");
}
