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
    // BDP2 live double buffer: one 112-byte GDB write to the inactive
    // slot, then one atomic 4-byte publish. Never read a half packet.
    // selector: 0=legacy probe, 1=fast[0], 2=fast[1].
    volatile uint32_t fast_slot;
    volatile Pose fast[2];
    // Additive, read-only host telemetry. No original BDP3 field moves.
    // One raycast work request per Zelda player tick. Height queries are
    // against actual game Havok terrain, not screenshots/teleport guesses.
    volatile uint32_t terrain_seq;
    volatile uint32_t terrain_mask;
    volatile float terrain_center[3];
    volatile float terrain_heights[9];
};
static_assert(offsetof(Mailbox, packet) == 40);
static_assert(offsetof(Mailbox, acknowledged_seq) == 152);
static_assert(offsetof(Mailbox, player_tick) == 176, "Live Link telemetry ABI drift");
static_assert(offsetof(Mailbox, player_valid) == 180, "Live Link validity ABI drift");
static_assert(offsetof(Mailbox, player_xyz) == 184, "Live Link position ABI drift");
static_assert(offsetof(Mailbox, camera_matrix_frames) == 196, "FPS camera matrix status drift");
static_assert(offsetof(Mailbox, link_render_hidden) == 200, "Link visibility status drift");
static_assert(offsetof(Mailbox, fast_slot) == 204, "BDP2 selector ABI drift");
static_assert(offsetof(Mailbox, fast) == 208, "BDP2 slots ABI drift");
static_assert(offsetof(Mailbox, fast[1]) == 320, "BDP2 second slot ABI drift");

extern "C" {
// Marker must remain in the actual guest .data of this wxlm module.
// Never conflate it with the unrelated BDP1 symbol in subsdk9.
__attribute__((used, aligned(16))) Mailbox g_BotwCraftLiveMailbox = {
    "BOTWCRAFT_WXLM_BDP1_LIVE_20261010", {}, 0, kModuleReady, 0, 0, 0, 0, 0, {0,0,0}, 0, 0, 0, {}
};
}

static uint32_t s_ticks = 0;
static uint32_t s_lastSeq = 0;
static uint32_t s_lastActiveTick = 0;
static bool s_loggedPlayer = false;
static bool s_loggedPose = false;
static bool s_loggedTimeout = false;
static bool s_loggedHideFailure = false;
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

// NX150 Link rendering is driven by TWO scales, not by `gsys::Model::_88` alone:
//   Actor::mScale       at Actor +0x418  (root actor -> model input)
//   gsys::Model::_88    at Model +0x88   (cached draw/model scale)
// The previous V7 touched only Model::_88; animation updated the actor's
// root scale afterwards, so Link remained visible inside the FPS camera.
// Hide both while keeping the actor and controller allocated and active.
static uintptr_t s_hiddenModel=0;
static uintptr_t s_hiddenActor=0;
static float s_previousScale[3]={1.f,1.f,1.f};
static float s_previousActorScale[3]={1.f,1.f,1.f};
static bool s_modelWasHidden=false;
static bool s_actorWasHidden=false;
static bool s_loggedModelHide=false;
static uint32_t s_activeActorHandle=0;
static constexpr float kHiddenDrawScale=0.00001f;
struct HiddenUnit {
    uintptr_t pointer;
    uint16_t old_mask;
};
static HiddenUnit s_hiddenUnits[32]={};
static unsigned s_hiddenUnitCount=0;

// NX150 gsys::Model::mUnitAccess is a sead::PtrArray<ModelInfo> at +0x38:
// {int32 size, int32 capacity, ModelInfo** data}.
// Each ModelInfo::mModelUnit is at +0x0.
// gsys::ModelUnit::mVisibilityMask is u16 at +0x0c.
// Setting it to zero suppresses ALL model render views, unlike Model::_88
// scale that was overridden by animation and left Link's head visible.
static unsigned suppressRenderUnits(uintptr_t model,bool hide) {
    if(model<0x10000u || (model&7u))return 0;
    const volatile uint8_t* header=reinterpret_cast<const volatile uint8_t*>(model+0x38u);
    const int32_t num=*reinterpret_cast<const volatile int32_t*>(header);
    const int32_t cap=*reinterpret_cast<const volatile int32_t*>(header+4u);
    if(num<0 || num>32 || cap<num || cap>512)return 0;
    const uintptr_t list=*reinterpret_cast<const volatile uintptr_t*>(header+8u);
    if(num==0 || list<0x10000u || (list&7u))return 0;
    unsigned hidden=0;
    for(int i=0;i<num;i++){
        const uintptr_t info=reinterpret_cast<const volatile uintptr_t*>(list)[i];
        if(info<0x10000u || (info&7u))continue;
        const uintptr_t unit=*reinterpret_cast<const volatile uintptr_t*>(info);
        if(unit<0x10000u || (unit&7u))continue;
        volatile uint16_t* mask=reinterpret_cast<volatile uint16_t*>(unit+0x0cu);
        unsigned saved=0;
        for(;saved<s_hiddenUnitCount;saved++)
            if(s_hiddenUnits[saved].pointer==unit)break;
        if(hide){
            if(saved==s_hiddenUnitCount && s_hiddenUnitCount<32){
                s_hiddenUnits[s_hiddenUnitCount++]={unit,*mask};
            }
            *mask=0;
            ++hidden;
        }else if(saved<s_hiddenUnitCount){
            // Restore only while the unit is STILL present in this model's
            // live unit list; never dereference a model freed on respawn.
            *mask=s_hiddenUnits[saved].old_mask;
            ++hidden;
        }
    }
    if(!hide)s_hiddenUnitCount=0;
    return hidden;
}


static bool updateVisualModel(uint32_t handle,bool hide){
    if(!S::ActorUnsafeRawPointer)return false;
    const uintptr_t actor=S::ActorUnsafeRawPointer(handle);
    if(actor<0x10000u || (actor&7u))return false;
    const uintptr_t model=*reinterpret_cast<const volatile uintptr_t*>(actor+0x4e0);
    volatile float* actorScale=reinterpret_cast<volatile float*>(actor+0x418);
    volatile float* modelScale=(model>=0x10000u && !(model&7u))
        ? reinterpret_cast<volatile float*>(model+0x88) : nullptr;
    if(!hide){
        if(s_actorWasHidden && s_hiddenActor==actor){
            for(unsigned i=0;i<3;i++)actorScale[i]=s_previousActorScale[i];
        }
        if(s_modelWasHidden && s_hiddenActor==actor &&
           modelScale && s_hiddenModel==model){
            for(unsigned i=0;i<3;i++)modelScale[i]=s_previousScale[i];
        }
        g_BotwCraftLiveMailbox.link_render_hidden=0;
        s_modelWasHidden=false;
        s_actorWasHidden=false;
        s_hiddenModel=0;
        s_hiddenActor=0;
        if(modelScale)suppressRenderUnits(model,false);
        return true;
    }
    // If Link respawns, NEVER dereference an old freed pointer. Only
    // snapshot and hide the current validated actor.
    if(s_hiddenActor!=actor){
        s_actorWasHidden=false;
        s_modelWasHidden=false;
        s_hiddenActor=actor;
        s_hiddenModel=0;
        s_hiddenUnitCount=0; // Old actor may have been freed.
    }
    if(!s_actorWasHidden){
        float old[3]={actorScale[0],actorScale[1],actorScale[2]};
        for(unsigned i=0;i<3;i++){
            if(!finiteFloat(old[i]) || old[i]<0.00001f || old[i]>100.f)
                return false;
            s_previousActorScale[i]=old[i];
        }
        s_actorWasHidden=true;
    }
    if(modelScale && (!s_modelWasHidden || s_hiddenModel!=model)){
        float old[3]={modelScale[0],modelScale[1],modelScale[2]};
        bool valid=true;
        for(unsigned i=0;i<3;i++){
            if(!finiteFloat(old[i]) || old[i]<0.00001f || old[i]>100.f)
                valid=false;
        }
        if(valid){
            for(unsigned i=0;i<3;i++)s_previousScale[i]=old[i];
            s_hiddenModel=model;
            s_modelWasHidden=true;
        }
    }
    // Reapply every player tick, because normal animation/actor visual
    // updates may overwrite either cached value.
    for(unsigned i=0;i<3;i++)actorScale[i]=kHiddenDrawScale;
    if(modelScale && s_modelWasHidden && s_hiddenModel==model)
        for(unsigned i=0;i<3;i++)modelScale[i]=kHiddenDrawScale;
    const unsigned units=suppressRenderUnits(model,true);
    g_BotwCraftLiveMailbox.link_render_hidden=
        units>0 ? 3u : (s_modelWasHidden ? 2u : 1u);
    if(!s_loggedModelHide){
        S::Log("[BOTW_NATIVE] LINK_RENDER_ROOT_AND_MODEL_SCALE_SUPPRESSED");
        s_loggedModelHide=true;
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
    // Late reapplication: actor animation may have rebuilt its render-scale
    // before the camera matrix pass. Do not change Link's location here.
    if (s_activeActorHandle && s_lastFpsTick &&
        s_ticks>=s_lastFpsTick && s_ticks-s_lastFpsTick<=3u)
        updateVisualModel(s_activeActorHandle,true);
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

// Published slot pointer is atomically changed *after* the entire inactive
// pose is written by Rust. Do not read the legacy GDB seqlock during fast mode.
static bool readPoseBytes(Pose& out, const volatile Pose& src) {
    const volatile uint8_t* from =
        reinterpret_cast<const volatile uint8_t*>(&src);
    uint8_t* dest=reinterpret_cast<uint8_t*>(&out);
    for (unsigned i=0;i<sizeof(Pose);++i) dest[i]=from[i];
    return !(out.seq&1u) && out.magic==kMagic && out.version==1;
}
// BDP3 mode: exactly ONE 112-byte GDB write per motion update.
// Each independent slot contains a checksum of the other 108 bytes.
// The game chooses the newest *complete* packet without a selector write.
// This eliminates a synchronous GDB roundtrip on the camera critical path.
static uint32_t poseCrc(const Pose& pose) {
    const uint8_t* data=reinterpret_cast<const uint8_t*>(&pose);
    uint32_t hash=2166136261u;
    for (unsigned i=0;i<sizeof(Pose);i++){
        if(i>=104u && i<108u)continue; // reserved_tail[0] checksum
        hash=(hash^data[i])*16777619u;
    }
    return hash;
}
static bool readCrcSlot(Pose& out,unsigned slot) {
    if (!readPoseBytes(out,g_BotwCraftLiveMailbox.fast[slot]))return false;
    return out.seq!=0 && out.tail[0]==poseCrc(out);
}
static bool readPacket(Pose& out) {
    for(unsigned attempt=0;attempt<6;attempt++){
        const uint32_t selected=g_BotwCraftLiveMailbox.fast_slot;
        if(selected==1u || selected==2u){
            if (!readPoseBytes(out,g_BotwCraftLiveMailbox.fast[selected-1u]))
                continue;
            if (g_BotwCraftLiveMailbox.fast_slot==selected) return true;
        }else if(selected==3u){
            Pose first{}, second{};
            const bool a=readCrcSlot(first,0u);
            const bool b=readCrcSlot(second,1u);
            if (!a && !b) return false;
            if (a && b) {
                out=(static_cast<int32_t>(first.seq-second.seq)>0)
                    ? first : second;
            }else out=a?first:second;
            // If sender changes mode during read, retry instead.
            if(g_BotwCraftLiveMailbox.fast_slot==3u)return true;
        }else if(selected==0u){
            const uint32_t before=g_BotwCraftLiveMailbox.packet.seq;
            if(before&1u)continue;
            if(!readPoseBytes(out,g_BotwCraftLiveMailbox.packet))continue;
            const uint32_t after=g_BotwCraftLiveMailbox.packet.seq;
            if(before==after && !(after&1u) && out.seq==after &&
                g_BotwCraftLiveMailbox.fast_slot==0u) return true;
        }else return false;
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

// Suppress only BOTW Link actor's SOUNDLINK effects, preserving the world
// ambience, music and all unrelated actors. The NX150 sound function
// xlink2::ResourceAccessorSLink::getVolume is at main+0x00BD0DCC.
// xlink2::UserInstance::mUser is +0x30, User::mUserName is +0x10,
// confirmed against xlink2 headers used by zeldaret/botw.
//
// Hook is only installed after the normal working V8 player tick resolves
// Link; it never alters Link's transform, camera, mesh, or Minecraft sync.
static volatile uint32_t s_muteLinkSLink = 0;
static bool s_playerAudioHookAttempted = false;
static bool s_playerAudioHookInstalled = false;
static bool s_loggedMutedLink = false;
static volatile uint32_t s_linkSfxSuppressed = 0;
using SLinkGetVolume = float (*)(void*,const void*,const void*);
static SLinkGetVolume s_originalSLinkVolume = nullptr;

static bool strContainsNoCase(const char* name,const char* needle){
    if(!name || !needle)return false;
    for(unsigned i=0; i<96 && name[i]; ++i){
        unsigned j=0;
        while(j<16 && needle[j] && i+j<96 && name[i+j]){
            char a=name[i+j],b=needle[j];
            if(a>='A' && a<='Z')a+=32;
            if(b>='A' && b<='Z')b+=32;
            if(a!=b)break;
            ++j;
        }
        if(needle[j]==0)return true;
    }
    return false;
}
static bool isLinkSoundSource(const void* instance){
    const uintptr_t p=reinterpret_cast<uintptr_t>(instance);
    if(p<0x10000 || (p&7u))return false;
    // Access only the real UserInstance pointer supplied by native
    // ResourceAccessorSLink::getVolume. Null/misaligned user => no mute.
    const uintptr_t user=*reinterpret_cast<const volatile uintptr_t*>(p+0x30);
    if(user<0x10000 || (user&7u))return false;
    const uintptr_t namePtr=*reinterpret_cast<const volatile uintptr_t*>(user+0x10);
    if(namePtr<0x10000)return false;
    const char* name=reinterpret_cast<const char*>(namePtr);
    return strContainsNoCase(name,"player") ||
           strContainsNoCase(name,"link");
}
extern "C" __attribute__((used)) float BotwCraftSelectivePlayerSoundVolume(
        void* accessor,const void* callTable,const void* userInstance){
    if(s_muteLinkSLink && isLinkSoundSource(userInstance)){
        ++s_linkSfxSuppressed;
        return 0.0f; // Mute ALL SoundLink events belonging to Link only.
    }
    return s_originalSLinkVolume
        ? s_originalSLinkVolume(accessor,callTable,userInstance):1.0f;
}
static void installLinkSoundMute(){
    if(s_playerAudioHookAttempted)return;
    s_playerAudioHookAttempted=true;
    if(!S::InstallHook || !S::ResolveTarget)return;
    const uintptr_t at=S::ResolveTarget(0x00bd0dccu,0);
    if(!at || (at&3u))return;
    const uintptr_t old=S::InstallHook(
        at,reinterpret_cast<uintptr_t>(&BotwCraftSelectivePlayerSoundVolume));
    if(!old){
        S::Log("[BOTW_NATIVE] LINK_AUDIO_HOOK_REFUSED");
        return;
    }
    s_originalSLinkVolume=reinterpret_cast<SLinkGetVolume>(old);
    s_playerAudioHookInstalled=true;
    S::Log("[BOTW_NATIVE] LINK_AUDIO_SOUNDLINK_VOLUME_FILTER_ACTIVE");
}

// Native NX150 symbols matched against zeldaret/botw uking_functions.csv.
// ksys::phys::RayCastForRequest::allocRequest       main+0x00FC5590
// RayCast::enableLayer                              main+0x00FC36A4
// RayCast::setStartAndEnd                           main+0x00FC38A0
// RayCastForRequest::submitRequest                  main+0x00FC55AC
// RayCastForRequest::isRequestFinished              main+0x00FC55E8
// RayCastForRequest::release                        main+0x00FC55D4
// The result fields are from physRayCast.h (NX150, 64-bit):
// mHasHit at +0x30, mHitNormal.y +0x38, mHitFraction +0x40.
// An asynchronous Havok raycast is necessary to avoid querying a locked
// physics world from the player callback. NEVER modify Minecraft positions.
struct Vec3Raw {float x,y,z;};
using TerrainAlloc = void*(*)(void*,int);
using TerrainLayers = void(*)(void*,int);
using TerrainSetRay = void(*)(void*,const Vec3Raw*,const Vec3Raw*);
using TerrainSubmit = bool(*)(void*,int);
using TerrainDone = bool(*)(const void*);
using TerrainRelease = void(*)(void*);
static TerrainAlloc tAlloc=nullptr;
static TerrainLayers tLayers=nullptr;
static TerrainSetRay tSetRay=nullptr;
static TerrainSubmit tSubmit=nullptr;
static TerrainDone tDone=nullptr;
static TerrainRelease tRelease=nullptr;
static bool tTried=false;
static bool tReady=false;
static bool tLogged=false;
static void* tPending=nullptr;
static uint32_t tIndex=0;
static uint32_t tMask=0;
static Vec3Raw tCenter{};
static Vec3Raw tFrom{};
static Vec3Raw tTo{};
static float tHeights[9]={};
static constexpr float kTerrainGridStep=2.75f;
static void initializeTerrainQuery(){
    if(tTried)return;
    tTried=true;
    if(!S::ResolveTarget)return;
    tAlloc=reinterpret_cast<TerrainAlloc>(S::ResolveTarget(0x00fc5590u,0));
    tLayers=reinterpret_cast<TerrainLayers>(S::ResolveTarget(0x00fc36a4u,0));
    tSetRay=reinterpret_cast<TerrainSetRay>(S::ResolveTarget(0x00fc38a0u,0));
    tSubmit=reinterpret_cast<TerrainSubmit>(S::ResolveTarget(0x00fc55acu,0));
    tDone=reinterpret_cast<TerrainDone>(S::ResolveTarget(0x00fc55e8u,0));
    tRelease=reinterpret_cast<TerrainRelease>(S::ResolveTarget(0x00fc55d4u,0));
    tReady=tAlloc && tLayers && tSetRay && tSubmit && tDone && tRelease;
    S::Log(tReady?"[BOTW_NATIVE] TERRAIN_HAVOK_REQUEST_SYMBOLS_READY":
                 "[BOTW_NATIVE] TERRAIN_HAVOK_SYMBOLS_MISSING");
}
static void sampleHavokTerrain(const Pose& pose) {
    initializeTerrainQuery();
    if(!tReady)return;
    // Do not release requests until the physics worker has finished.
    if(tPending){
        if(!tDone(tPending))return;
        // This is the actual result from BOTW's Havok ray query.
        const uintptr_t at=reinterpret_cast<uintptr_t>(tPending);
        const volatile uint8_t* hit=reinterpret_cast<const volatile uint8_t*>(at+0x30);
        const volatile float* normalY=reinterpret_cast<const volatile float*>(at+0x38);
        const volatile float* fraction=reinterpret_cast<const volatile float*>(at+0x40);
        const float frac=*fraction;
        const float ny=*normalY;
        if(*hit && finiteFloat(frac) && frac>=0.0f && frac<=1.0f &&
          finiteFloat(ny) && ny>0.42f){
            tHeights[tIndex]=tFrom.y+(tTo.y-tFrom.y)*frac;
            tMask|=(1u<<tIndex);
        }
        tRelease(tPending);
        tPending=nullptr;
        ++tIndex;
        if(tIndex==9){
            const uint32_t next=g_BotwCraftLiveMailbox.terrain_seq+2u;
            g_BotwCraftLiveMailbox.terrain_seq=next-1u;
            g_BotwCraftLiveMailbox.terrain_mask=tMask;
            g_BotwCraftLiveMailbox.terrain_center[0]=tCenter.x;
            g_BotwCraftLiveMailbox.terrain_center[1]=tCenter.y;
            g_BotwCraftLiveMailbox.terrain_center[2]=tCenter.z;
            for(unsigned i=0;i<9;i++)
                g_BotwCraftLiveMailbox.terrain_heights[i]=tHeights[i];
            g_BotwCraftLiveMailbox.terrain_seq=next;
            if(tMask && !tLogged){
                tLogged=true;
                S::Log("[BOTW_NATIVE] TERRAIN_HAVOK_FIRST_GROUND_HIT");
            }
            tIndex=0;
        }
    }
    if(tIndex==0){
        tCenter={pose.position[0],pose.position[1],pose.position[2]};
        tMask=0;
    }
    // If Minecraft has travelled while old rays ran, start a new sample
    // around its current BOTW mapped position instead of an outdated patch.
    if((pose.position[0]-tCenter.x)*(pose.position[0]-tCenter.x)+
       (pose.position[2]-tCenter.z)*(pose.position[2]-tCenter.z)>25.f){
        tIndex=0;tMask=0;
        tCenter={pose.position[0],pose.position[1],pose.position[2]};
    }
    const unsigned gx=tIndex%3u, gz=tIndex/3u;
    const float x=tCenter.x+(static_cast<float>(gx)-1.f)*kTerrainGridStep;
    const float z=tCenter.z+(static_cast<float>(gz)-1.f)*kTerrainGridStep;
    tFrom={x,tCenter.y+3.0f,z};
    tTo={x,tCenter.y-10.0f,z};
    // HitAll=15. Probe ground and fixed objects, but NOT players, ragdolls
    // or sensors. The game owns the physics results.
    void* request=tAlloc(nullptr,15);
    if(!request)return;
    tLayers(request,8); // EntityGround
    tLayers(request,9); // EntityGroundSmooth
    tLayers(request,10);// EntityGroundRough
    tLayers(request,2); // EntityGroundObject
    tSetRay(request,&tFrom,&tTo);
    if(!tSubmit(request,0)){
        tRelease(request);
        return;
    }
    tPending=request;
}
extern "C" __attribute__((used)) void BotwCraftPlayerTick() {
    ++s_ticks;
    if (s_ticks==1u) S::Log("[BOTW_NATIVE] PLAYER_FRAME_TICK_RUNNING");
    auto get = S::GetPlayerActor;
    auto valid = S::ActorIsValid;
    const uint32_t actor = get ? get() : 0;
    const bool actorReady = actor && valid && valid(actor);
    g_BotwCraftLiveMailbox.runtime_state = actorReady ? kActorSeen : kNoActor;
    if(!actorReady)s_muteLinkSLink=0;
    if(s_linkSfxSuppressed && !s_loggedMutedLink){
        s_loggedMutedLink=true;
        S::Log("[BOTW_NATIVE] LINK_AUDIO_PLAYER_SOUND_SUPPRESSED");
    }
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
        s_muteLinkSLink=0;
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
        s_muteLinkSLink=0;
        updateVisualModel(actor,false);
        return;
    }
    // Apply every tick while a fresh Minecraft packet exists, even if
    // the sequence has not changed: BOTW physics may republish transform.
    // The explicit 0x10 opt-in distinguishes active actuator from probing.
    if (!(p.flags & 0x10u)) {
        s_muteLinkSLink=0;
        updateVisualModel(actor,false);
        g_BotwCraftLiveMailbox.runtime_state = kEngineUnavailable;
        return;
    }
    // Audio filter is independent of render FPS and does not touch the
    // BDP1/BDP2 transport. SoundLink audio gets filtered at source.
    s_muteLinkSLink=1;
    installLinkSoundMute();
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
    s_activeActorHandle=actor;
    const bool warped = warpLink(actor,p);
    const bool camera = updateCameraFromGame(p);
    // Opt-in terrain collision sampling: this does NOT warp Steve, alter
    // Link's actor controller, change the camera or manipulate input.
    sampleHavokTerrain(p);
    // Link's renderer is not needed for first-person BotwCraft. Do NOT
    // couple visibility to camera-matrix hook timing: that hook may run after
    // the player tick or report a one-frame delay, leaving Link on screen.
    // This does not delete the actor; visuals are restored on disconnect.
    const bool mesh_hidden=updateVisualModel(actor,true);
    if (!mesh_hidden && !s_loggedHideFailure) {
        s_loggedHideFailure=true;
        S::Log("[BOTW_NATIVE] LINK_RENDER_HIDE_FAILED: model binding unavailable");
    }
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
