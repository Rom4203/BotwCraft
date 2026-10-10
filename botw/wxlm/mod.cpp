// BotwCraft WiiXLaunch AArch64 guest runtime: inbound pose + acknowledgement.
// Game engine transform/camera hooks are intentionally NOT fabricated here.
#include <cstdint>
#include <cstddef>
#include <wiixlaunch/mod_runtime.h>
#include <wiixlaunch/imports/wiixl_core.h>
#include <wiixlaunch/imports/botw_player.h>
#include <wiixlaunch/imports/botw_actor.h>
#include <wiixlaunch/imports/botw_camera.h>
#include <wiixlaunch/imports/wiixl_call.h>
#include <wiixlaunch/mod_math.h>

namespace S {
WXL_USE_wiixl_core(Log);
WXL_USE_wiixl_call(ImageBase);
WXL_USE_wiixl_call(ResolveTarget);
WXL_USE_wiixl_core(InstallHook);
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
static bool s_confirmedActorLayout = false;
static uintptr_t s_confirmedActor = 0;


// These callbacks must execute in-game on the player tick; there is no
// controller emulation and no host-side guessing of physical actor offsets.
static bool finiteFloat(float x) {
    return x == x && x > -100000.f && x < 100000.f;
}

// BOTW NX150 decomp (zeldaret/botw, actActor.h) confirms:
// BaseProc is 0x180, Actor primary vptr is at +0x0;
// Actor::mMtx is +0x398, with positions at floats 3/7/11;
// Actor virtual #85 is setMtx. The Wii U implementation uses the
// (Actor*, Matrix34f*, bool updateActorMtx, bool refreshPhysics) ABI.
// This Switch vtable invocation is experimental until Ryujinx verifies it.
static bool rawSwitchSetMtx(uint32_t handle, const float matrix[12],
                            const Pose& packet) {
    if (!S::ActorUnsafeRawPointer || !S::ImageBase) return false;
    const uintptr_t actor = S::ActorUnsafeRawPointer(handle);
    const uintptr_t base = S::ImageBase();
    if (actor < 0x10000 || (actor & 7u) || base < 0x10000) return false;
    if (s_confirmedActorLayout && s_confirmedActor != actor) {
        s_confirmedActorLayout = false;
        s_confirmedActor = 0;
    }
    // First check against *live* Link telemetry and the exact decompiled
    // NX150 Actor matrix layout, rather than blindly following vtable data.
    if (!s_confirmedActorLayout) {
        const volatile float* current =
            reinterpret_cast<volatile const float*>(actor + 0x398);
        const float mx = current[3], my = current[7], mz = current[11];
        const float dx = mx-packet.botw_origin[0];
        const float dy = my-packet.botw_origin[1];
        const float dz = mz-packet.botw_origin[2];
        if (!finiteFloat(mx) || !finiteFloat(my) || !finiteFloat(mz) ||
            dx*dx+dy*dy+dz*dz > 256.f) return false;
        s_confirmedActorLayout = true;
        s_confirmedActor = actor;
        S::Log("[BOTW_NATIVE] NX150 Actor +0x398 matrix validated against Link telemetry");
    }
    const uintptr_t vtable = *reinterpret_cast<const volatile uintptr_t*>(actor);
    // Nintendo NX main NSO text/rodata, no guest heap or unrelated mod pointer.
    if (vtable < base + 0x1000 || vtable >= base+0x10000000u ||
        (vtable & 7u)) return false;
    const volatile uintptr_t* vt =
        reinterpret_cast<const volatile uintptr_t*>(vtable);
    constexpr unsigned kSetMtxVirtualIndex = 85;
    const uintptr_t fn = vt[kSetMtxVirtualIndex];
    const uintptr_t next = vt[kSetMtxVirtualIndex+1];
    if (fn < base+0x1000 || fn >= base+0x10000000u ||
        next < base+0x1000 || next >= base+0x10000000u ||
        (fn & 3u)) return false;
    using SetMtx = void (*)(void*, const float*, uint32_t, uint32_t);
    reinterpret_cast<SetMtx>(fn)(reinterpret_cast<void*>(actor),matrix,1u,0u);
    g_BotwCraftLiveMailbox.warp_method=3;
    return true;
}

// zeldaret/botw NX150 Actor::mModel +0x4E0, gsys::Model::_88 render scale.
// This reduces ONLY the model render scale: Link's actor/physics stay alive.
static uintptr_t s_hiddenModel = 0;
static uintptr_t s_hiddenActor = 0;
static float s_previousScale[3] = {1.f,1.f,1.f};
static bool s_modelWasHidden = false;
static bool s_loggedModelHide = false;

static bool updateVisualModel(uint32_t handle, bool hide) {
    if (!S::ActorUnsafeRawPointer) return false;
    const uintptr_t actor=S::ActorUnsafeRawPointer(handle);
    if (actor<0x10000 || (actor&7u)) return false;
    const uintptr_t model=*reinterpret_cast<const volatile uintptr_t*>(actor+0x4e0);
    if (!model || (model&7u) || model<0x10000) return false;
    volatile float* scale=reinterpret_cast<volatile float*>(model+0x88);
    if (!hide) {
        if (s_modelWasHidden && s_hiddenModel==model &&
            s_hiddenActor==actor) {
            for (unsigned i=0;i<3;i++) scale[i]=s_previousScale[i];
        }
        s_modelWasHidden=false;
        s_hiddenModel=0;
        s_hiddenActor=0;
        return true;
    }
    if (!s_modelWasHidden || s_hiddenModel!=model || s_hiddenActor!=actor) {
        const float old[]={scale[0],scale[1],scale[2]};
        for (unsigned i=0;i<3;i++)
            if (!finiteFloat(old[i]) || old[i]<0.00001f || old[i]>100.f)
                return false;
        s_hiddenModel=model;
        s_hiddenActor=actor;
        for (unsigned i=0;i<3;i++) s_previousScale[i]=old[i];
        s_modelWasHidden=true;
    }
    // Nonzero scale avoids singular render matrices while making Link invisible.
    for (unsigned i=0;i<3;i++) scale[i]=0.0001f;
    if (!s_loggedModelHide) {
        s_loggedModelHide=true;
        S::Log("[BOTW_NATIVE] Link model scale suppressed (actor retained)");
    }
    return true;
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
    // The public actor API is not implemented on Switch; fall back to the
    // NX150 in-game actor vtable, guarded by live position/matrix validation.
    return rawSwitchSetMtx(handle,mat,p);
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

// NX150 from zeldaret/botw/data/uking_functions.csv:
// 0x7100B1BE7C sead::LookAtCamera::doUpdateMatrix(Matrix34f*) const.
// The 432-byte method is invoked to produce the camera matrix. Hook here,
// rather than a 2-instruction CameraMgr getter that cannot be safely patched.
using CameraMatrixFn = void (*)(void* camera, void* matrixOut);
static CameraMatrixFn s_nextCameraMatrix = nullptr;
static bool s_cameraHookInstalled = false;
static bool s_cameraHookActive = false;
static bool s_cameraHookLogged = false;

extern "C" __attribute__((used)) void BotwCraftCameraMatrixHook(
    void* camera, void* matrixOut) {
    // The native camera hook is run by Zelda, not by the Windows host.
    // All reads are from the guest mailbox using the packet seqlock.
    if (camera && s_cameraHookInstalled && s_lastSeq &&
        s_ticks >= s_lastActiveTick && s_ticks-s_lastActiveTick <= 2u) {
        Pose p{};
        if (readPacket(p) && p.seq==s_lastSeq && 
            (p.flags & 0x13u)==0x13u) {
            // This callback can be invoked for scene, map, and other cameras.
            // Only move a real gameplay camera already near the Link actor.
            const uintptr_t ptr=reinterpret_cast<uintptr_t>(camera);
            if ((ptr&7u)==0 && ptr >= 0x10000u) {
                const volatile float* cameraPos =
                    reinterpret_cast<const volatile float*>(ptr+0x38);
                const float x=cameraPos[0], y=cameraPos[1], z=cameraPos[2];
                if (finiteFloat(x) && finiteFloat(y) && finiteFloat(z)) {
                    const float dx=x-p.position[0];
                    const float dy=y-p.position[1];
                    const float dz=z-p.position[2];
                    // 50-block threshold allows Zelda follow camera offsets,
                    // but avoids overriding distant scripted/cutscene cameras.
                    if (dx*dx + dy*dy + dz*dz < 2500.f) {
                        g_BotwCraftLiveMailbox.camera_pointer=ptr;
                        if (updateCamera(p)) {
                            s_cameraHookActive=true;
                            if (!s_cameraHookLogged) {
                                S::Log("[BOTW_NATIVE] FIRST_PERSON camera matrix overridden by Minecraft");
                                s_cameraHookLogged=true;
                            }
                        }
                    }
                }
            }
        }
    }
    // Recompute Zelda's actual native projection/view matrix *after* applying
    // Minecraft's eye/forward so the third Rust window sees first person.
    auto original=s_nextCameraMatrix;
    if (original) original(camera,matrixOut);
}

static void installFirstPersonHook() {
    if (!S::ImageBase || !S::InstallHook) {
        S::Log("[BOTW_NATIVE] Camera hook unavailable: wiixl.core missing");
        return;
    }
    constexpr uintptr_t kLookAtCameraMatrixNX150 = 0x00B1BE7Cu;
    if (!S::ResolveTarget) return;
    const uintptr_t image=S::ImageBase();
    if (image<0x10000u || (image&0xfffu)) {
        S::Log("[BOTW_NATIVE] Camera hook refused: image base unexpected");
        return;
    }
    // wiixl.call performs the Switch relocation correctly. wiixl.core
    // ImageBase() RETURNS ZERO on Switch and must not be used here.
    const uintptr_t target=S::ResolveTarget(kLookAtCameraMatrixNX150,0);
    const uintptr_t orig=S::InstallHook(target,
        reinterpret_cast<uintptr_t>(&BotwCraftCameraMatrixHook));
    if (!orig) {
        S::Log("[BOTW_NATIVE] Camera hook refused: BOTW NX150 target conflict");
        return;
    }
    s_nextCameraMatrix=reinterpret_cast<CameraMatrixFn>(orig);
    s_cameraHookInstalled=true;
    S::Log("[BOTW_NATIVE] Zelda LookAtCamera matrix hook installed for first-person");
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
    if ((p.flags & 3u) != 3u || !actorReady) {
        if (actorReady) updateVisualModel(actor,false);
        return;
    }
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
        updateVisualModel(actor,false);
        return;
    }
    // Apply every tick while a fresh Minecraft packet exists, even if
    // the sequence has not changed: BOTW physics may republish transform.
    // The explicit 0x10 opt-in distinguishes active actuator from probing.
    if (!(p.flags & 0x10u)) {
        updateVisualModel(actor,false);
        g_BotwCraftLiveMailbox.runtime_state = kEngineUnavailable;
        return;
    }
    const bool warped = warpLink(actor,p);
    const bool hidden = warped && updateVisualModel(actor,true);
    (void)hidden;
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
    installFirstPersonHook();
    S::Log("[BOTW_NATIVE] Live mailbox and native Link + first-person camera hooks ready");
}
