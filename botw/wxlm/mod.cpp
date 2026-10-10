// BotwCraft WiiXLaunch AArch64 guest runtime: inbound pose + acknowledgement.
// Game engine transform/camera hooks are intentionally NOT fabricated here.
#include <cstdint>
#include <cstddef>
#include <wiixlaunch/mod_runtime.h>
#include <wiixlaunch/imports/wiixl_core.h>
#include <wiixlaunch/imports/botw_player.h>
#include <wiixlaunch/imports/botw_actor.h>
#include <wiixlaunch/imports/botw_camera.h>
#include <wiixlaunch/mod_math.h>

namespace S {
WXL_USE_wiixl_core(Log);
WXL_USE_botw_player(Init);
WXL_USE_botw_player(RegisterTick);
WXL_USE_botw_player(GetPlayerActor);
WXL_USE_botw_player(ActorIsValid);
WXL_USE_botw_player(ActorUnsafeRawPointer);
WXL_USE_botw_actor(WarpTo);
WXL_USE_botw_actor(SetMtx);
WXL_USE_botw_actor(GetMatrix);
WXL_USE_botw_camera(SetPosition);
WXL_USE_botw_camera(SetLookAt);
WXL_USE_botw_camera(SetUp);
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
    kEngineUnavailable = 4,
    kWarpOK = 5,
    kCameraOK = 6,
    kWarpAndCameraOK = 7
};

struct alignas(16) Mailbox {
    char marker[40];
    volatile Pose packet;
    volatile uint32_t acknowledged_seq;
    volatile uint32_t runtime_state;
    volatile uintptr_t camera_pointer;
    volatile uint32_t applied_sequence;
    volatile uint32_t warp_method;
};
static_assert(offsetof(Mailbox, packet) == 40);
static_assert(offsetof(Mailbox, acknowledged_seq) == 152);
static_assert(sizeof(Mailbox) >= 160);

extern "C" {
// Marker must remain in the actual guest .data of this wxlm module.
// Never conflate it with the unrelated BDP1 symbol in subsdk9.
__attribute__((used, aligned(16))) Mailbox g_BotwCraftLiveMailbox = {
    "BOTWCRAFT_WXLM_BDP1_LIVE_20261010", {}, 0, kModuleReady, 0, 0, 0
};
}

static uint32_t s_ticks = 0;
static uint32_t s_lastSeq = 0;
static uint32_t s_lastActiveTick = 0;
static bool s_loggedPlayer = false;
static bool s_loggedPose = false;
static bool s_loggedTimeout = false;
static bool s_loggedWarp = false;
static bool s_loggedCamera = false;

// These callbacks must execute in-game on the player tick; there is no
// controller emulation and no host-side guessing of physical actor offsets.
static bool finiteFloat(float x) {
    return x == x && x > -100000.f && x < 100000.f;
}

static bool warpLink(uint32_t handle, const Pose& p) {
    for (unsigned i = 0; i < 3; ++i)
        if (!finiteFloat(p.position[i])) return false;
    // The actual engine setMtx updates actor+renderer+physics in one call.
    // Via the public surface, the host can refuse if unsupported on Switch.
    auto setMtx = S::SetMtx;
    auto getMtx = S::GetMatrix;
    float mat[12] = {1.f,0.f,0.f,0.f,
                     0.f,1.f,0.f,0.f,
                     0.f,0.f,1.f,0.f};
    if (getMtx) getMtx(handle, mat);
    if (!finiteFloat(p.yaw)) return false;
    const float angle = p.yaw * 0.01745329251994329577f;
    const float sn = WiiXLaunch::ModMath::Sin(angle);
    const float cs = WiiXLaunch::ModMath::Cos(angle);
    // Y-up orientation: yaw 0 faces +Z, matching Minecraft.
    mat[0] = cs; mat[2] = sn;
    mat[8] = -sn; mat[10] = cs;
    mat[3] = p.position[0];
    mat[7] = p.position[1];
    mat[11] = p.position[2];
    if (setMtx && setMtx(handle, mat, 1u)) {
        g_BotwCraftLiveMailbox.warp_method = 1;
        return true;
    }
    auto warp = S::WarpTo;
    if (warp && warp(handle,p.position[0],p.position[1],p.position[2])) {
        g_BotwCraftLiveMailbox.warp_method = 2;
        return true;
    }
    return false;
}

static bool updateCamera(const Pose& p) {
    uintptr_t addr = g_BotwCraftLiveMailbox.camera_pointer;
    // Camera pointer must be written by a verified guest camera hook.
    // Never guess one from the BWC2 camera *slot* or the host process address.
    if (!addr || (addr & 7u) || addr < 0x10000u) return false;
    for (unsigned i=0; i<3; ++i)
        if (!finiteFloat(p.eye[i]) || !finiteFloat(p.forward[i])) return false;
    auto position=S::SetPosition;
    auto target=S::SetLookAt;
    auto up=S::SetUp;
    if (!position || !target || !up) return false;
    return position(addr,p.eye[0],p.eye[1],p.eye[2]) != 0 &&
        target(addr,p.eye[0]+p.forward[0],p.eye[1]+p.forward[1],
                    p.eye[2]+p.forward[2]) != 0 &&
        up(addr,0.f,1.f,0.f) != 0;
}


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
    // Apply every tick while a fresh Minecraft packet exists, even if
    // the sequence has not changed: BOTW physics may republish transform.
    // The explicit 0x10 opt-in distinguishes active actuator from probing.
    if (!(p.flags & 0x10u)) {
        g_BotwCraftLiveMailbox.runtime_state = kEngineUnavailable;
        return;
    }
    const bool warped = warpLink(actor,p);
    const bool camera = updateCamera(p);
    g_BotwCraftLiveMailbox.runtime_state =
        warped && camera ? kWarpAndCameraOK : warped ? kWarpOK :
        camera ? kCameraOK : kEngineUnavailable;
    if (warped || camera) g_BotwCraftLiveMailbox.applied_sequence=p.seq;
    if (warped && !s_loggedWarp) {
        S::Log("[BOTW_NATIVE] Link actor transform applied");
        s_loggedWarp=true;
    }
    if (camera && !s_loggedCamera) {
        S::Log("[BOTW_NATIVE] In-game LookAtCamera first person applied");
        s_loggedCamera=true;
    }
}

extern "C" __attribute__((used)) void WiiXLaunch_ModEntry() {
    if (!S::Log || !S::Init || !S::RegisterTick) return;
    S::Init();
    if (!S::RegisterTick(&BotwCraftPlayerTick)) {
        S::Log("[BOTW_NATIVE] ERROR: player tick registration refused");
        return;
    }
    S::Log("[BOTW_NATIVE] Live mailbox and guarded native actor/camera actuation available");
}
