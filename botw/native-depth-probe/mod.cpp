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

 struct DepthEntry{
   volatile uintptr_t depth;
   volatile uint32_t count;
   volatile uint32_t lastFrame;
   volatile uintptr_t companionColor;
 };
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
   DepthEntry candidates[16];
 };
 extern "C" __attribute__((used,aligned(16))) Stats g_NvnDepthProbe{
   kMagic,kArm,kIdle
 };
 using BindTargetsFn=void(*)(void*,int,const void* const*,const void*,
                             const void*,const void*);
 static BindTargetsFn s_original=nullptr;
 static bool s_attempted=false;
 static uint32_t s_attempts=0;
 static uint32_t s_lastAttempt=0;
 static uint32_t s_ticks=0;
 static uint32_t s_lastDepthCount=0;
 static uint32_t s_lastPrinted=0;
 static bool s_firstScanout=false;
 static bool s_firstTick=false;
 // WiiXLaunch modules are freestanding ARM64 (no sprintf). Keep logs bounded.
 static void appendNumber(char*& dest,uint32_t v){
    char tmp[12];unsigned n=0;
    do {tmp[n++]=char('0'+v%10);v/=10;}while(v&&n<sizeof(tmp));
    while(n)*dest++=tmp[--n];
 }
 static void appendHex(char*& dest,uintptr_t val){
   *dest++='0';*dest++='x';
   for(int shift=int(sizeof(uintptr_t)*8)-4;shift>=0;shift-=4){
      *dest++="0123456789abcdef"[(val>>shift)&15u];
   }
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
    // Most frequently rebound NVN depth texture. This is evidence only;
    // NOT proof it is an attached opaque-world buffer at scanout time.
    uint32_t best=0;uintptr_t bestDepth=0, bestColor=0;
    for(unsigned i=0;i<16u;i++){
       const auto& c=s.candidates[i];
       const auto count=__atomic_load_n(&c.count,__ATOMIC_ACQUIRE);
       if(count>best){
          best=count;
          bestDepth=__atomic_load_n(&c.depth,__ATOMIC_ACQUIRE);
          bestColor=__atomic_load_n(&c.companionColor,__ATOMIC_ACQUIRE);
       }
    }
    if(bestDepth && Core::Log){
       char detail[140]{};char* p=detail;
       auto word=[&p](const char* q){while(*q)*p++=*q++;};
       word("[DEPTH_PROBE] popularDepth=");
       appendHex(p,bestDepth);
       word(" color=");appendHex(p,bestColor);
       word(" calls=");appendNumber(p,best);
       *p=0;Core::Log(detail);
    }
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
       const uint32_t tick=__atomic_load_n(&s_ticks,__ATOMIC_RELAXED);
       __atomic_store_n(&s.candidate_frame,tick,__ATOMIC_RELAXED);
       // Fixed 16-slot bounded texture histogram, with nonblocking CAS
       // so observation never performs dynamic allocations or logging in NVN.
       for(auto& entry:s.candidates){
          uintptr_t old=__atomic_load_n(&entry.depth,__ATOMIC_ACQUIRE);
          if(!old){
              uintptr_t zero=0;
              if(__atomic_compare_exchange_n(&entry.depth,&zero,newDepth,false,
                                              __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))
                  old=newDepth;
              else old=zero;
          }
          if(old==newDepth){
              __atomic_fetch_add(&entry.count,1u,__ATOMIC_RELAXED);
              __atomic_store_n(&entry.lastFrame,tick,__ATOMIC_RELAXED);
              __atomic_store_n(&entry.companionColor,
                              reinterpret_cast<uintptr_t>(color0),__ATOMIC_RELEASE);
              break;
          }
       }
     }
   }
   // Hook can run on a distinct NVN thread immediately after patching.
   // Never call the patched game function itself (infinite recursion).
   // Wait briefly until InstallHook hands us its ORIGINAL trampoline.
   BindTargetsFn original=__atomic_load_n(&s_original,__ATOMIC_ACQUIRE);
   for(unsigned i=0;i<100000u && !original;i++){
      __asm__ __volatile__("yield" ::: "memory");
      original=__atomic_load_n(&s_original,__ATOMIC_ACQUIRE);
   }
   if(original)original(cmd,colors,color,colorResolve,depth,depthResolve);
 }

 static void ObserveScanout(uintptr_t cmd,uintptr_t texture,int32_t width,int32_t height) {
   if(!cmd || !texture || width<=0 || height<=0)return;
   if(!s_firstScanout){
     s_firstScanout=true;
     if(Core::Log)Core::Log("[DEPTH_PROBE] DRAW_CALLBACK_ACTIVE (real Zelda frame observed)");
   }
   auto& s=g_NvnDepthProbe;
   __atomic_add_fetch(&s.draw_callbacks,1u,__ATOMIC_RELAXED);
   __atomic_store_n(&s.display_color,texture,__ATOMIC_RELAXED);
   __atomic_store_n(&s.display_cmd,cmd,__ATOMIC_RELAXED);
   const uint32_t tick=__atomic_load_n(&s_ticks,__ATOMIC_ACQUIRE);
   __atomic_store_n(&s.display_frame,tick,__ATOMIC_RELAXED);
   const uint32_t frame=__atomic_load_n(&s.candidate_frame,__ATOMIC_RELAXED);
   if(frame+1>=tick) {
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
   const uint32_t tick=__atomic_add_fetch(&s_ticks,1u,__ATOMIC_RELEASE);
   if(!s_firstTick){
      s_firstTick=true;
      if(Core::Log)Core::Log("[DEPTH_PROBE] TICK_CALLBACK_ACTIVE (gameplay started)");
   }
   if(tick-s_lastPrinted>=180u){
     s_lastPrinted=tick;
     if(g_NvnDepthProbe.status==kHookInstalled)report();
     else if(Core::Log){
       char msg[145]{};char* p=msg;
       const char* title="[DEPTH_PROBE] status=";
       while(*title)*p++=*title++;
       appendNumber(p,g_NvnDepthProbe.status);
       const char* attempt=" attempts=";while(*attempt)*p++=*attempt++;
       appendNumber(p,s_attempts);
       const char* draws=" drawCalls=";while(*draws)*p++=*draws++;
       appendNumber(p,g_NvnDepthProbe.draw_callbacks);
       *p=0;Core::Log(msg);
     }
   }
   if(s_attempted || g_NvnDepthProbe.arm!=kArm)return;
   // The NVN function table may not be initialized on the first world tick.
   // Retry only a handful of times; never hook an unresolved GPU function.
   if(s_lastAttempt && tick-s_lastAttempt<30u)return;
   s_lastAttempt=tick;
   if(++s_attempts>20u) {
     s_attempted=true;g_NvnDepthProbe.status=kRefused;
     if(Core::Log)Core::Log("[DEPTH_PROBE] NVN function-table lookup unavailable after 20 retries; no GPU hook installed");
     return;
   }
   if(!Call::ResolveTarget || !Core::InstallHook){
     s_attempted=true;
     g_NvnDepthProbe.status=kNotSupported;
     if(Core::Log)Core::Log("[DEPTH_PROBE] NVN hook capabilities unavailable; leaving game unchanged");
     return;
   }
   // WiiXLaunch/wiixlaunch-botw/nvn.hpp reads this GOT entry with two
   // indirections. It is NOT a game camera offset.
   uintptr_t got=Call::ResolveTarget(kNvnSetRenderTargetsGot,0u);
   if(got<0x10000u || (got&7u)){
     if(s_attempts==1u && Core::Log)Core::Log("[DEPTH_PROBE] NVN GOT not initialized yet");
     return;
   }
   uintptr_t cell=*reinterpret_cast<const volatile uintptr_t*>(got);
   if(cell<0x10000u || (cell&7u)){
     if(s_attempts==1u && Core::Log)Core::Log("[DEPTH_PROBE] NVN GOT cell invalid");
     return;
   }
   uintptr_t fn=*reinterpret_cast<const volatile uintptr_t*>(cell);
   if(fn<0x10000u || (fn&3u)){
     if(s_attempts==1u && Core::Log)Core::Log("[DEPTH_PROBE] NVN target pointer invalid");
     return;
   }
   s_attempted=true;
   uintptr_t original=Core::InstallHook(fn,reinterpret_cast<uintptr_t>(&ObserveRenderTargets));
   if(!original){
     g_NvnDepthProbe.status=kRefused;
     if(Core::Log)Core::Log("[DEPTH_PROBE] Runtime refused NVN hook; no render target changed");
     return;
   }
   __atomic_store_n(&s_original,reinterpret_cast<BindTargetsFn>(original),__ATOMIC_RELEASE);
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
