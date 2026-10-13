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
   // Hardware-only measurements; never dereference these raw game pointers.
   volatile uint32_t same_cmd_depth_and_display;
   volatile uint32_t color_is_display;
   volatile uint32_t candidate_changes;
   volatile uint32_t same_depth_reuse;
   volatile uintptr_t previous_depth;
   volatile uintptr_t last_scanout_depth;
 };
 extern "C" __attribute__((used,aligned(16))) Stats g_NvnDepthProbe{
   kMagic,kArm,kIdle
 };
 using BindTargetsFn=void(*)(void*,int,const void* const*,const void*,
                             const void*,const void*);
 static BindTargetsFn s_original=nullptr;
 static bool s_attempted=false;
 static uint32_t s_ticks=0;
 static uint32_t s_lastDepthCount=0;
 static uint32_t s_lastPrinted=0;
 // WiiXLaunch modules are freestanding ARM64 (no sprintf). Keep logs bounded.
 static void appendNumber(char*& dest,uint32_t v){
    char tmp[12];unsigned n=0;
    do {tmp[n++]=char('0'+v%10);v/=10;}while(v&&n<sizeof(tmp));
    while(n)*dest++=tmp[--n];
 }
 static void report(){
    char line[250]{};char* out=line;
    auto lit=[&out](const char* p){while(*p)*out++=*p++;};
    const auto& s=g_NvnDepthProbe;
    lit("[DEPTH_PROBE] calls=");appendNumber(out,s.all_calls);
    lit(" color+depth=");appendNumber(out,s.depth_and_color_calls);
    lit(" scanout=");appendNumber(out,s.draw_callbacks);
    lit(" sameCmd=");appendNumber(out,s.same_cmd_depth_and_display);
    lit(" sameColor=");appendNumber(out,s.color_is_display);
    lit(" reusedDepth=");appendNumber(out,s.same_depth_reuse);
    lit(" depthChanges=");appendNumber(out,s.candidate_changes);
    *out=0;if(Core::Log)Core::Log(line);
 }

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
       const uintptr_t newDepth=reinterpret_cast<uintptr_t>(depth);
       const uintptr_t oldDepth=__atomic_exchange_n(&s.previous_depth,newDepth,__ATOMIC_RELAXED);
       if(oldDepth==newDepth)__atomic_add_fetch(&s.same_depth_reuse,1u,__ATOMIC_RELAXED);
       else if(oldDepth!=0)__atomic_add_fetch(&s.candidate_changes,1u,__ATOMIC_RELAXED);
       __atomic_store_n(&s.candidate_depth,newDepth,__ATOMIC_RELAXED);
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
   const uint32_t frame=__atomic_load_n(&s.candidate_frame,__ATOMIC_RELAXED);
   if(frame+1>=s_ticks) {
     __atomic_add_fetch(&s.depth_seen_during_draw,1u,__ATOMIC_RELAXED);
     __atomic_store_n(&s.last_scanout_depth,
         __atomic_load_n(&s.candidate_depth,__ATOMIC_RELAXED),__ATOMIC_RELAXED);
     if(cmd==__atomic_load_n(&s.candidate_cmd,__ATOMIC_RELAXED))
       __atomic_add_fetch(&s.same_cmd_depth_and_display,1u,__ATOMIC_RELAXED);
     if(texture==__atomic_load_n(&s.candidate_color,__ATOMIC_RELAXED))
       __atomic_add_fetch(&s.color_is_display,1u,__ATOMIC_RELAXED);
   }
 }

 static void Tick(){
   ++s_ticks;
   if(s_ticks-s_lastPrinted>=300u && g_NvnDepthProbe.status==kHookInstalled){
     s_lastPrinted=s_ticks;
     report();
     // Depth attachment is a pointer observed during frame submission.
     // NEVER treat it as a safe drawable scene depth until Ryujinx confirms
     // attachment identity, lifetime, viewport and command-buffer ownership.
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
