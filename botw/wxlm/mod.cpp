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
WXL_USE_wiixl_core(InstallHook);
WXL_USE_wiixl_call(ImageBase);
WXL_USE_wiixl_call(ResolveTarget);
WXL_USE_botw_player(RegisterTick);
WXL_USE_botw_player(Init);
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
    // NX150 live Link coordinates for Rust to READ, without any in-game
    // debug text parser and without requiring writes to the guest.
    // Guest offsets: player_tick=176 valid=180 xyz=184..195.
    volatile uint32_t player_tick;
    volatile uint32_t player_valid;
    volatile float player_xyz[3];
    volatile uint32_t camera_matrix_frames;
    volatile uint32_t link_render_hidden;
};
static_assert(offsetof(Mailbox, packet) == 40);
static_assert(offsetof(Mailbox, acknowledged_seq) == 152);
static_assert(offsetof(Mailbox, player_tick) == 176, "Live Link telemetry ABI drift");
static_assert(offsetof(Mailbox, player_valid) == 180, "Live Link validity ABI drift");
static_assert(offsetof(Mailbox, player_xyz) == 184, "Live Link position ABI drift");
static_assert(offsetof(Mailbox, camera_matrix_frames) == 196, "FPS camera matrix status drift");
static_assert(offsetof(Mailbox, link_render_hidden) == 200, "Link visibility status drift");

extern "C" {
// Marker must remain in the actual guest .data of this wxlm module.
// Never conflate it with the unrelated BDP1 symbol in subsdk9.
__attribute__((used, aligned(16))) Mailbox g_BotwCraftLiveMailbox = {
    "BOTWCRAFT_WXLM_BDP1_LIVE_20261010", {}, 0, kModuleReady, 0, 0, 0, 0, 0, {0,0,0}, 0, 0
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
        g_BotwCraftLiveMailbox.link_render_hidden=0;
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
    g_BotwCraftLiveMailbox.link_render_hidden=1;
    if (!s_loggedModelHide) {
        s_loggedModelHide=true;
        S::Log("[BOTW_NATIVE] Link model scale suppressed (actor retained)");
    }
    return true;
}

static bool warpLink(uint32_t handle, const Pose& p) {
    if(!S::ActorUnsafeRawPointer)return false;
    for(unsigned i=0;i<3;i++)if(!finiteFloat(p.position[i]))return false;
    // The v3/v4 implementation rebuilt Link's Y-rotation from Minecraft yaw
    // EVERY frame. BOTW animation and physics own actor rotation; that caused
    // Link to spin, side-step, and glide as Zelda continuously reconciled its
    // movement controller with a foreign rotation.
    //
    // Physics/translation authority comes from Minecraft. Rotation remains
    // unchanged. First-person yaw/pitch belong ONLY to LookAtCamera.
    const uintptr_t raw=S::ActorUnsafeRawPointer(handle);
    if (raw<0x10000u || (raw&7u))return false;
    const volatile float* liveMtx=
        reinterpret_cast<const volatile float*>(raw+0x398);
    float mtx[12]={};
    for(unsigned i=0;i<12;i++){
        const float component=liveMtx[i];
        if(!finiteFloat(component))return false;
        mtx[i]=component;
    }
    mtx[3]=p.position[0];
    mtx[7]=p.position[1];
    mtx[11]=p.position[2];
    if(S::SetMtx && S::SetMtx(handle,mtx,1u)){
        g_BotwCraftLiveMailbox.warp_method=1;
        return true;
    }
    if(S::WarpTo && S::WarpTo(handle,p.position[0],p.position[1],p.position[2])){
        g_BotwCraftLiveMailbox.warp_method=2;
        return true;
    }
    // Neither public function is Switch-capable in the current upstream
    // surface; preserve the live actor's rotation in the guarded NX150
    // setMtx vtable path as well.
    return rawSwitchSetMtx(handle,mtx,p);
}

// Direct Switch LookAtCamera writer. The public botw.camera surface filters
// to [0x10000000,0xa0000000), even though Switch heap camera objects may live
// above that range. That filter made the previous camera SetPosition calls
// return false without writing. We validate the actual object from the game's
// camera getter instead of treating the range as a capability test.
static uintptr_t s_liveCamera=0;
static bool s_cameraHookInstalled=false;
static bool s_cameraHookTried=false;
static bool s_loggedCameraCandidate=false;
static float s_lastEye[3]={};
static float s_lastForward[3]={0.f,0.f,1.f};
static uint32_t s_lastFpsTick=0;
using CameraMatrixUpdate=void (*)(void*,void*);
static CameraMatrixUpdate s_cameraMatrixOriginal=nullptr;

static bool plausibleCamera(uintptr_t ptr, const Pose& p) {
    if (ptr < 0x10000 || (ptr&7u)) return false;
    // Game returns a camera pointer; read ONLY after a validated in-game
    // lookup and a valid player actor. Weed out nonsense and cutscene cameras.
    const volatile float* pos=reinterpret_cast<const volatile float*>(ptr+0x38);
    const float x=pos[0],y=pos[1],z=pos[2];
    if (!finiteFloat(x)||!finiteFloat(y)||!finiteFloat(z)) return false;
    float dx=x-p.position[0],dy=y-p.position[1],dz=z-p.position[2];
    return dx*dx+dy*dy+dz*dz < 10000.f;
}
static bool setCameraLookAt(uintptr_t ptr,const float eye[3],const float forward[3]){
    if (ptr<0x10000 || (ptr&7u)) return false;
    float len2=forward[0]*forward[0]+forward[1]*forward[1]+forward[2]*forward[2];
    if (!(len2>0.5f && len2<1.5f)) return false;
    for(unsigned i=0;i<3;i++)
      if(!finiteFloat(eye[i])||!finiteFloat(forward[i])) return false;
    // Switch sead::LookAtCamera layout verified by WiiXLaunch camera.hpp.
    // Camera pos +0x38, at +0x44, up +0x50: these are VIEW coordinates,
    // independent from Link actor rotation and its chase-camera behaviour.
    volatile float* pos=reinterpret_cast<volatile float*>(ptr+0x38);
    volatile float* at=reinterpret_cast<volatile float*>(ptr+0x44);
    volatile float* up=reinterpret_cast<volatile float*>(ptr+0x50);
    for(unsigned i=0;i<3;i++){
      pos[i]=eye[i];at[i]=eye[i]+forward[i];
    }
    up[0]=0.f;up[1]=1.f;up[2]=0.f;
    return true;
}

// Replaces the *matrix computation* not just the camera's tracking state.
// Zelda is free to run its normal chase-camera code earlier in the frame,
// but the final camera matrix is rebuilt from Minecraft's eye and yaw/pitch.
// Installed only after player+camera pointers are valid and the game is in
// gameplay, never during Ryujinx start or its menus.
extern "C" __attribute__((used)) void BotwCraftFirstPersonMatrix(
     void* camera,void* outputMatrix) {
    if (camera && reinterpret_cast<uintptr_t>(camera)==s_liveCamera &&
        s_lastFpsTick && s_ticks-s_lastFpsTick<=3u){
        if(setCameraLookAt(s_liveCamera,s_lastEye,s_lastForward))
            ++g_BotwCraftLiveMailbox.camera_matrix_frames;
    }
    if (s_cameraMatrixOriginal)
        s_cameraMatrixOriginal(camera,outputMatrix);
}
static void installGameplayCameraHook() {
    if(s_cameraHookTried)return;
    s_cameraHookTried=true;
    if(!S::ResolveTarget || !S::InstallHook){
        S::Log("[BOTW_NATIVE] CAMERA_NO_HOOK_EXPORT");
        return;
    }
    // NX150 sead::LookAtCamera::doUpdateMatrix(Matrix34f*) const.
    // Function address supplied by the decomp symbol set and relocated by
    // wiixl.call; do not patch instructions by guessing a host address.
    const uintptr_t at=S::ResolveTarget(0x00b1be7cu,0);
    if(!at || (at&3u))return;
    const uintptr_t original=S::InstallHook(
       at,reinterpret_cast<uintptr_t>(&BotwCraftFirstPersonMatrix));
    if(!original){
        S::Log("[BOTW_NATIVE] CAMERA_MATRIX_HOOK_REFUSED");
        return;
    }
    s_cameraMatrixOriginal=reinterpret_cast<CameraMatrixUpdate>(original);
    s_cameraHookInstalled=true;
    S::Log("[BOTW_NATIVE] CAMERA_MATRIX_HOOK_ACTIVE_NX150");
}
static bool updateCameraFromGame(const Pose& p) {
    if (!S::ResolveTarget || !(p.flags & 0x10u))return false;
    // ksys/cam getter, NX150 main NSO relative; obtain actual camera object.
    using GetGameplayCamera=uintptr_t (*)();
    const uintptr_t target=S::ResolveTarget(0x0131e194u,0);
    if (!target || (target&3u))return false;
    const uintptr_t addr=reinterpret_cast<GetGameplayCamera>(target)();
    if(!plausibleCamera(addr,p)) return false;
    if(!s_loggedCameraCandidate){
       s_loggedCameraCandidate=true;
       S::Log("[BOTW_NATIVE] VALIDATED_GAME_CAMERA_FOUND");
    }
    // Store a snapshot of the current Minecraft look vector. The hook will
    // consume the same pose without interpreting Link's rotation.
    for(unsigned i=0;i<3;i++){
       s_lastEye[i]=p.eye[i];s_lastForward[i]=p.forward[i];
    }
    s_liveCamera=addr;
    s_lastFpsTick=s_ticks;
    g_BotwCraftLiveMailbox.camera_pointer=addr;
    if (!setCameraLookAt(addr,s_lastEye,s_lastForward))return false;
    installGameplayCameraHook();
    return s_cameraHookInstalled;
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

static void printGuestMailboxAddress() {
    char line[]="[BOTW_NATIVE] GUEST_MAILBOX=0x0000000000000000";
    uintptr_t value=reinterpret_cast<uintptr_t>(&g_BotwCraftLiveMailbox);
    const char* hex="0123456789abcdef";
    constexpr unsigned start=sizeof(line)-1-16;
    for (unsigned i=0;i<16;i++) {
        const unsigned shift=(15-i)*4;
        line[start+i]=hex[(value>>shift)&15u];
    }
    S::Log(line);
}

extern "C" __attribute__((used)) void BotwCraftPlayerTick() {
    ++s_ticks;
    if (s_ticks==1u) S::Log("[BOTW_NATIVE] PLAYER_FRAME_TICK_RUNNING");
    auto get = S::GetPlayerActor;
    auto valid = S::ActorIsValid;
    const uint32_t actor = get ? get() : 0;
    const bool actorReady = actor && valid && valid(actor);
    g_BotwCraftLiveMailbox.runtime_state = actorReady ? kActorSeen : kNoActor;
    g_BotwCraftLiveMailbox.player_valid = 0;
    if (actorReady && S::ActorUnsafeRawPointer) {
        const uintptr_t raw = S::ActorUnsafeRawPointer(actor);
        // BOTW NX150 Actor::mMtx (matrix 3x4) lives at +0x398.
        // Matrix column 3 holds XYZ. A live valid ActorHandle is required.
        if (raw >= 0x10000u && (raw & 7u) == 0) {
            const volatile float* mtx =
                reinterpret_cast<const volatile float*>(raw + 0x398u);
            const float x=mtx[3], y=mtx[7], z=mtx[11];
            if (finiteFloat(x) && finiteFloat(y) && finiteFloat(z)) {
                g_BotwCraftLiveMailbox.player_xyz[0]=x;
                g_BotwCraftLiveMailbox.player_xyz[1]=y;
                g_BotwCraftLiveMailbox.player_xyz[2]=z;
                g_BotwCraftLiveMailbox.player_valid=1;
            }
        }
    }
    g_BotwCraftLiveMailbox.player_tick = s_ticks;
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
    const bool camera = updateCameraFromGame(p);
    // Hiding Link should not depend on whether movement was accepted.
    // Hide the render mesh only after the actual camera is in FPS mode;
    // retain Link's physics/actor and restore visibility on disarm.
    if (camera) updateVisualModel(actor,true);
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

// Player callbacks execute after the engine has a real Link actor; unlike
// NVN EndRecording they never inject a graphics command buffer into frames.
// This avoids the 1081+ extra GPU injections and concurrent debugger traffic
// that preceded the 2026-10-10 JIT AccessViolationException in Ryujinx.
extern "C" __attribute__((used)) void WiiXLaunch_ModEntry() {
    if (!S::Log || !S::Init || !S::RegisterTick) return;
    S::Init();
    printGuestMailboxAddress();
    if (!S::RegisterTick(&BotwCraftPlayerTick)) {
        S::Log("[BOTW_NATIVE] ERROR: botw.player per-frame callback refused");
        return;
    }
    S::Log("[BOTW_NATIVE] player-frame callback registered; NO NVN draw hook or overlay");
}
