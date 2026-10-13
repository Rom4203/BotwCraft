// EXPLICITLY OPT-IN NX150 native NVN depth discovery.
// A separate diagnostic module: does not modify BotwCraft gameplay.
// This captures actual nvnCommandBufferSetRenderTargets attachments in memory;
// it NEVER draws a triangle or substitutes a private depth buffer.
//
// This standalone diagnostic is armed only if the user explicitly installs
// bwc_depth_probe.wxlm in Ryujinx. It is NEVER included in the stable package.
// This is not the final renderer; it needs validation before integration.
#include <cstdint>
#include <cstddef>
#include <wiixlaunch/mod_runtime.h>
#include <wiixlaunch/imports/wiixl_core.h>
#include <wiixlaunch/imports/wiixl_call.h>
#include <wiixlaunch/imports/botw_gfx.h>

namespace Core {
 WXL_USE_wiixl_core(Log);
 WXL_USE_wiixl_core(InstallHook);
 WXL_USE_wiixl_core(RegisterTick);
}
namespace Call {
 WXL_USE_wiixl_call(ResolveTarget);
}
namespace Gfx {
 WXL_USE_botw_gfx(RegisterDraw);
}

namespace {
 constexpr uint32_t kMagic = 0x3150444Eu; // NDP1
 constexpr uint32_t kArm = 0x314D5241u; // ARM1
 constexpr uintptr_t kNvnSetRenderTargetsGot = 0x2597598u;
 enum : uint32_t {kIdle=0,kHookInstalled=1,kRefused=2,kNotSupported=3};

 struct alignas(16) Stats {
   uint32_t magic;
   volatile uint32_t arm; // armed only by explicitly installing this separate module
   volatile uint32_t status;
   volatile uint32_t all_calls;
   volatile uint32_t depth_calls;
   volatile uint32_t depth_and_color_calls;
   volatile uint32_t draw_callbacks;
   volatile uint32_t depth_seen_during_draw;
   volatile uintptr_t candidate_depth;
   volatile uintptr_t candidate_color;
   volatile uintptr_t candidate_cmd;
   volatile uintptr_t display_color;
   volatile uintptr_t display_cmd;
   volatile uint32_t candidate_frame;
   volatile uint32_t display_frame;
 };
 extern "C" __attribute__((used,aligned(16))) Stats g_NvnDepthProbe{
   kMagic,kArm,kIdle,0,0,0,0,0,0,0,0,0,0,0,0
 };
 using BindTargetsFn=void(*)(void*,int,const void* const*,const void*,
                             const void*,const void*);
 static BindTargetsFn s_original=nullptr;
 static bool s_attempted=false;
 static uint32_t s_ticks=0;
 static uint32_t s_lastDepthCount=0;

 static void printAddr(const char* label,uintptr_t addr){
   char line[128]{};
   char* out=line;
   while(*label)*out++=*label++;
   *out++='0';*out++='x';
   for(int shift=int(sizeof(uintptr_t)*8)-4;shift>=0;shift-=4)
     *out++="0123456789abcdef"[(addr>>shift)&15u];
   *out=0;
   if(Core::Log)Core::Log(line);
 }

 // Same exact six arguments as the NVN function declared in WiiXLaunch.
 // Log only pointer VALUES; do not dereference GPU resources, allocate,
 // mutate render targets, issue GPU commands, or block the render thread.
 extern "C" __attribute__((used)) void ObserveRenderTargets(
     void* cmd,int colors,const void* const* color,const void* colorResolve,
     const void* depth,const void* depthResolve){
   (void)colorResolve;(void)depthResolve;
   auto& s=g_NvnDepthProbe;
   __atomic_add_fetch(&s.all_calls,1u,__ATOMIC_RELAXED);
   if(depth){
     __atomic_add_fetch(&s.depth_calls,1u,__ATOMIC_RELAXED);
     const void* color0=colors>0 && colors<=8 && color?color[0]:nullptr;
     if(color0){
       __atomic_add_fetch(&s.depth_and_color_calls,1u,__ATOMIC_RELAXED);
       __atomic_store_n(&s.candidate_depth,reinterpret_cast<uintptr_t>(depth),__ATOMIC_RELAXED);
       __atomic_store_n(&s.candidate_color,reinterpret_cast<uintptr_t>(color0),__ATOMIC_RELAXED);
       __atomic_store_n(&s.candidate_cmd,reinterpret_cast<uintptr_t>(cmd),__ATOMIC_RELAXED);
       __atomic_store_n(&s.candidate_frame,s_ticks,__ATOMIC_RELAXED);
     }
   }
   if(s_original) s_original(cmd,colors,color,colorResolve,depth,depthResolve);
 }

 static void ObserveScanout(uintptr_t cmd,uintptr_t texture,int32_t width,int32_t height) {
   if(!cmd || !texture || width<=0 || height<=0)return;
   auto& s=g_NvnDepthProbe;
   __atomic_add_fetch(&s.draw_callbacks,1u,__ATOMIC_RELAXED);
   __atomic_store_n(&s.display_color,texture,__ATOMIC_RELAXED);
   __atomic_store_n(&s.display_cmd,cmd,__ATOMIC_RELAXED);
   __atomic_store_n(&s.display_frame,s_ticks,__ATOMIC_RELAXED);
   if(__atomic_load_n(&s.candidate_frame,__ATOMIC_RELAXED)+1>=s_ticks)
     __atomic_add_fetch(&s.depth_seen_during_draw,1u,__ATOMIC_RELAXED);
 }

 static void Tick(){
   ++s_ticks;
   if(s_ticks%600==0 && g_NvnDepthProbe.status==kHookInstalled){
      uint32_t count=g_NvnDepthProbe.depth_and_color_calls;
      if(count!=s_lastDepthCount){
         s_lastDepthCount=count;
         if(Core::Log)Core::Log("[DEPTH_PROBE] Native NVN real depth+color targets observed; read NDP1 mailbox for candidate pointers");
      }
   }
   if(s_attempted || g_NvnDepthProbe.arm!=kArm)return;
   s_attempted=true;
   if(!Call::ResolveTarget || !Core::InstallHook){
     g_NvnDepthProbe.status=kNotSupported;
     if(Core::Log)Core::Log("[DEPTH_PROBE] NVN hook capabilities unavailable; leaving game unchanged");
     return;
   }
   // WiiXLaunch/wiixlaunch-botw/nvn.hpp reads this GOT entry with two
   // indirections. It is NOT a game camera offset.
   uintptr_t got=Call::ResolveTarget(kNvnSetRenderTargetsGot,0u);
   if(got<0x10000u || (got&7u)){
     g_NvnDepthProbe.status=kRefused;return;
   }
   uintptr_t cell=*reinterpret_cast<const volatile uintptr_t*>(got);
   if(cell<0x10000u || (cell&7u)){
     g_NvnDepthProbe.status=kRefused;return;
   }
   uintptr_t fn=*reinterpret_cast<const volatile uintptr_t*>(cell);
   if(fn<0x10000u || (fn&3u)){
     g_NvnDepthProbe.status=kRefused;return;
   }
   uintptr_t original=Core::InstallHook(fn,reinterpret_cast<uintptr_t>(&ObserveRenderTargets));
   if(!original){
     g_NvnDepthProbe.status=kRefused;
     if(Core::Log)Core::Log("[DEPTH_PROBE] Runtime refused NVN hook; no render target changed");
     return;
   }
   s_original=reinterpret_cast<BindTargetsFn>(original);
   g_NvnDepthProbe.status=kHookInstalled;
   if(Core::Log)Core::Log("[DEPTH_PROBE] NVN SetRenderTargets observer installed: PASSIVE, original called");
 }
}
extern "C" __attribute__((used)) void WiiXLaunch_ModEntry(){
  if(!Core::Log)return;
  Core::Log("[DEPTH_PROBE] Experimental NDP1 native depth diagnosis; enabled ONLY in explicitly-installed test module");
  printAddr("[DEPTH_PROBE] NDP1_MAILBOX_ADDR=",reinterpret_cast<uintptr_t>(&g_NvnDepthProbe));
  if(Core::RegisterTick) Core::RegisterTick(&Tick);
  if(Gfx::RegisterDraw) Gfx::RegisterDraw(&ObserveScanout);
  Core::Log("[DEPTH_PROBE] Does not draw or inject geometry; uses existing Zelda graphics only");
}
