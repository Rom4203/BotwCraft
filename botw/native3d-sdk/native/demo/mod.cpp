// BW3D - isolated Switch 1.5.0 GPU-pass probe. Never touches gameplay.
// This is NOT a screen-space overlay and deliberately emits no fake cube.
#include <cstdint>
#include <wiixlaunch/mod_runtime.h>
#include <wiixlaunch/imports/wiixl_core.h>
#include <wiixlaunch/imports/wiixl_call.h>
#include <wiixlaunch/imports/botw_gfx.h>
#include <wiixlaunch/imports/botw_player.h>
namespace C {
 WXL_USE_wiixl_core(Log); WXL_USE_wiixl_core(InstallHook);
 WXL_USE_wiixl_core(RegisterTick);
}
namespace Call { WXL_USE_wiixl_call(ResolveTarget); }
namespace G { WXL_USE_botw_gfx(RegisterDraw); }
namespace Player {
 WXL_USE_botw_player(Init); WXL_USE_botw_player(RegisterTick);
 WXL_USE_botw_player(GetPlayerActor); WXL_USE_botw_player(ActorIsValid);
 WXL_USE_botw_player(ActorUnsafeRawPointer);
}
namespace {
using FnTargets=void (*)(void*,int,const void* const*,const void*,const void*,const void*);
constexpr uintptr_t kGot=0x2597598u;
struct alignas(16) State {
 uint32_t magic=0x33445742u; // BWD3 little endian
 volatile uint32_t calls=0,withDepth=0,withColorAndDepth=0;
 volatile uint32_t drawnFrames=0,modelReady=0;
 volatile uintptr_t depth=0,color=0,cmd=0;
 volatile float modelPosition[3]={0.f,0.f,0.f};
};
extern "C" __attribute__((used,aligned(16))) State g_Bw3dProbe{};
FnTargets original=nullptr;
bool worldPositionCaptured=false;
void observeTargets(void* cmd,int count,const void* const* colors,
                    const void* cr,const void* depth,const void* dr) {
 ++g_Bw3dProbe.calls;
 if(depth) {
  ++g_Bw3dProbe.withDepth;
  g_Bw3dProbe.depth=reinterpret_cast<uintptr_t>(depth);
  g_Bw3dProbe.cmd=reinterpret_cast<uintptr_t>(cmd);
 }
 if(depth && count>0 && colors && colors[0]) {
  ++g_Bw3dProbe.withColorAndDepth;
  g_Bw3dProbe.color=reinterpret_cast<uintptr_t>(colors[0]);
 }
 if(original)original(cmd,count,colors,cr,depth,dr);
}
void tick(){
 if(worldPositionCaptured || !Player::GetPlayerActor ||
    !Player::ActorIsValid || !Player::ActorUnsafeRawPointer)return;
 const uint32_t actor=Player::GetPlayerActor();
 if(!actor || !Player::ActorIsValid(actor))return;
 const uintptr_t ptr=Player::ActorUnsafeRawPointer(actor);
 // NX150 Actor::mMtx from the working BotwCraft Switch 1.5.0 module:
 // row-major Matrix34f at +0x398; xyz are elements 3,7,11.
 if(ptr<0x10000u || (ptr&7u))return;
 const volatile float* m=reinterpret_cast<const volatile float*>(ptr+0x398u);
 const float x=m[3],y=m[7],z=m[11];
 if(!__builtin_isfinite(x)||!__builtin_isfinite(y)||!__builtin_isfinite(z)||
    x < -100000.f || x > 100000.f ||
    y < -100000.f || y > 100000.f ||
    z < -100000.f || z > 100000.f)return;
 // Actual Zelda XYZ, initialized ONCE from Link, never camera-relative.
 g_Bw3dProbe.modelPosition[0]=x+3.0f;
 g_Bw3dProbe.modelPosition[1]=y+1.0f;
 g_Bw3dProbe.modelPosition[2]=z;
 g_Bw3dProbe.modelReady=1;
 worldPositionCaptured=true;
 if(C::Log)C::Log("[BW3D] Cube position fixed in Hyrule XYZ; waiting for native projection and world depth");
}
void draw(uintptr_t,uintptr_t,int32_t,int32_t){
 const unsigned n=++g_Bw3dProbe.drawnFrames;
 if(n==120 || n==600){
  if(C::Log) C::Log("[BW3D] NVN drawing active; checking GAME depth binds, no overlay or fake projection");
 }
}
void install(){
 if(!C::InstallHook||!Call::ResolveTarget)return;
 const uintptr_t got=Call::ResolveTarget(kGot,0);
 if(got<0x10000u || (got&7u))return;
 const uintptr_t cell=*reinterpret_cast<const volatile uintptr_t*>(got);
 if(cell<0x10000u||(cell&7u))return;
 const uintptr_t fn=*reinterpret_cast<const volatile uintptr_t*>(cell);
 if(fn<0x10000u || (fn&3u))return;
 uintptr_t trampoline=C::InstallHook(fn,reinterpret_cast<uintptr_t>(&observeTargets));
 if(trampoline){
  original=reinterpret_cast<FnTargets>(trampoline);
  if(C::Log)C::Log("[BW3D] Native NVN color/depth observer installed (no game state changes)");
 }else if(C::Log)C::Log("[BW3D] NVN hook unavailable: API remains passive");
}
}
extern "C" __attribute__((used)) void WiiXLaunch_ModEntry(){
 if(!C::Log)return;
 C::Log("[BW3D] Native 3D API probe: independent of BotwCraft");
 install();
 if(Player::Init)Player::Init();
 if(Player::RegisterTick)Player::RegisterTick(&tick);
 if(G::RegisterDraw)G::RegisterDraw(&draw);
}
