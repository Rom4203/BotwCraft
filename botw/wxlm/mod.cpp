// BotwCraft WiiXLaunch AArch64 guest runtime: inbound pose + acknowledgement.
// Game engine transform/camera hooks are intentionally NOT fabricated here.
#include <cstdint>
#include <cstddef>
#include <wiixlaunch/mod_runtime.h>
#include <wiixlaunch/imports/wiixl_core.h>
#include <wiixlaunch/imports/botw_player.h>
#include <wiixlaunch/imports/botw_actor.h>
#include <wiixlaunch/imports/botw_camera.h>
#include <wiixlaunch/imports/botw_input.h>
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
namespace Inputs {
WXL_USE_botw_input(Init);
WXL_USE_botw_input(HoldInputCapture);
WXL_USE_botw_input(IsInputCaptured);
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
static bool s_inputInit=false;
static bool s_loggedInputCapture=false;
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

// BOTW Switch 1.5.0 FIRST PERSON CAMERA (crash fix).
//
// Prior build crashed at WXLM+0x6A0: ldr s4,[x22,#0x38] after calling
// main+0x0131E194 using an unverified no-argument function signature.
// The returned X0 was 0x8b080c089a9f3108 (invalid camera pointer).
// NEVER call that getter or dereference its unvalidated result again.
//
// Instead the game's real sead::LookAtCamera::doUpdateMatrix callback
// supplies a genuine LookAtCamera *this* in its first argument.
static uintptr_t s_liveCamera=0;
static bool s_cameraHookInstalled=false;
static bool s_cameraHookTried=false;
static bool s_loggedCameraCandidate=false;
static float s_lastEye[3]={};
static float s_lastForward[3]={0.f,0.f,1.f};
static float s_lastLinkPosition[3]={};
static uint32_t s_lastFpsTick=0;
static uint32_t s_lastMatrixTick=0;
using CameraMatrixUpdate=void (*)(void*,void*);
static CameraMatrixUpdate s_cameraMatrixOriginal=nullptr;

// Camera offsets are Switch-specific: +0x38 pos, +0x44 target, +0x50 up.
static bool setCameraLookAt(uintptr_t ptr,const float eye[3],const float forward[3]){
    if (ptr<0x10000 || (ptr&7u)) return false;
    const float len2=forward[0]*forward[0]+forward[1]*forward[1]+forward[2]*forward[2];
    if (!(len2>0.5f && len2<1.5f)) return false;
    for(unsigned i=0;i<3;i++)
      if(!finiteFloat(eye[i])||!finiteFloat(forward[i])) return false;
    volatile float* pos=reinterpret_cast<volatile float*>(ptr+0x38);
    volatile float* at=reinterpret_cast<volatile float*>(ptr+0x44);
    volatile float* up=reinterpret_cast<volatile float*>(ptr+0x50);
    for(unsigned i=0;i<3;i++){
      pos[i]=eye[i];at[i]=eye[i]+forward[i];
    }
    up[0]=0.f;up[1]=1.f;up[2]=0.f;
    return true;
}

// This callback gets an actual in-game camera receiver from Zelda's native
// camera method. Unlike the old getter, the camera pointer is NEVER guessed.
extern "C" __attribute__((used)) void BotwCraftFirstPersonMatrix(
     void* camera,void* outputMatrix) {
    const uintptr_t ptr=reinterpret_cast<uintptr_t>(camera);
    if (ptr>=0x10000u && (ptr&7u)==0 &&
        s_lastFpsTick && s_ticks>=s_lastFpsTick &&
        s_ticks-s_lastFpsTick<=3u) {
        const volatile float* oldPos=
            reinterpret_cast<const volatile float*>(ptr+0x38);
        const float x=oldPos[0],y=oldPos[1],z=oldPos[2];
        if (finiteFloat(x)&&finiteFloat(y)&&finiteFloat(z)) {
            const float dx=x-s_lastLinkPosition[0];
            const float dy=y-s_lastLinkPosition[1];
            const float dz=z-s_lastLinkPosition[2];
            // Do not redirect cutscene, minimap or distant scene cameras.
            if (dx*dx+dy*dy+dz*dz < 10000.f &&
                setCameraLookAt(ptr,s_lastEye,s_lastForward)) {
                s_liveCamera=ptr;
                s_lastMatrixTick=s_ticks;
                g_BotwCraftLiveMailbox.camera_pointer=ptr;
                ++g_BotwCraftLiveMailbox.camera_matrix_frames;
                if (!s_loggedCameraCandidate) {
                    s_loggedCameraCandidate=true;
                    S::Log("[BOTW_NATIVE] CAMERA_FIRST_PERSON_MATRIX_EXECUTED");
                }
            }
        }
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
    // NX150 sead::LookAtCamera::doUpdateMatrix(Matrix34f*) const,
    // relative 0x00B1BE7C (relocated by WiiXLaunch).
    // Only install once Link and Minecraft are both active.
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
    if (!(p.flags & 0x10u))return false;
    for(unsigned i=0;i<3;i++){
        if(!finiteFloat(p.eye[i]) || !finiteFloat(p.forward[i]) ||
           !finiteFloat(p.position[i]))return false;
        s_lastEye[i]=p.eye[i];
        s_lastForward[i]=p.forward[i];
        s_lastLinkPosition[i]=p.position[i];
    }
    s_lastFpsTick=s_ticks;
    installGameplayCameraHook();
    // Hook installation alone is not proof of in-game FPS mode.
    return s_cameraHookInstalled && s_lastMatrixTick>0 &&
           s_ticks>=s_lastMatrixTick &&
           s_ticks-s_lastMatrixTick<=3u;
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
    // Zelda must not simultaneously act on its ProController/analog stick:
    // Minecraft is authoritative. Capture is automatically released in two
    // frames if BotwCraft stops updating, so menus stay usable on disconnect.
    if (!s_inputInit && Inputs::Init) {
        s_inputInit=Inputs::Init()!=0;
    }
    if(s_inputInit && Inputs::HoldInputCapture){
        Inputs::HoldInputCapture(2u);
        if(!s_loggedInputCapture && Inputs::IsInputCaptured && Inputs::IsInputCaptured()){
            s_loggedInputCapture=true;
            S::Log("[BOTW_NATIVE] ZELDA_CONTROLLER_INPUT_CAPTURED");
        }
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
