// BW3D native 3D cube test for BOTW Switch 1.5.0 / Ryujinx.
// Separate opt-in module. Never modifies Link, physics, save, or Minecraft.
// Sends 36 rotating, homogeneous 3D vertices into Zelda's own NVN pipeline.
// Camera-space proof, not yet a world-anchored in-game actor.
#include <cstdint>
#include <wiixlaunch/mod_runtime.h>
#include <wiixlaunch/imports/wiixl_core.h>
#include <wiixlaunch/imports/botw_gfx.h>
#include "cube.hpp"
namespace Core { WXL_USE_wiixl_core(Log); }
namespace Gfx {
 WXL_USE_botw_gfx(Init);
 WXL_USE_botw_gfx(RegisterDraw);
 WXL_USE_botw_gfx(DrawMesh);
}
namespace {
 alignas(16) bw3d_test::Vertex mesh[bw3d_test::kVertices]{};
 uint32_t frames=0,accepted=0,rejected=0;
 void putNum(char*& dst,uint32_t n){
  char buf[12];unsigned k=0;
  do{buf[k++]=char('0'+n%10u);n/=10;}while(n&&k<12);
  while(k)*dst++=buf[--k];
 }
 void report(){
  if(!Core::Log)return;
  char line[150]{};char* p=line;
  const auto emit=[&p](const char* s){while(*s)*p++=*s++;};
  emit("[BW3D_CUBE] NVN callbacks=");putNum(p,frames);
  emit(" meshDrawSubmitted=");putNum(p,accepted);
  emit(" refused=");putNum(p,rejected);
  *p=0;Core::Log(line);
 }
 void draw(uintptr_t cmd,uintptr_t color,int32_t w,int32_t h){
  if(!cmd||!color||w<320||h<200||!Gfx::DrawMesh)return;
  ++frames;
  bw3d_test::make_cube(frames,mesh);
  // Exactly the 8-float MeshVertex ABI expected by WiiXLaunch/NVN.
  if(Gfx::DrawMesh(cmd,color,reinterpret_cast<const float*>(mesh),
                   bw3d_test::kVertices)) ++accepted;
  else ++rejected;
  if(frames==1u||frames%180u==0u)report();
 }
}
extern "C" __attribute__((used)) void WiiXLaunch_ModEntry(){
 if(Core::Log)Core::Log("[BW3D_CUBE] Native Zelda NVN 3D mesh test starting");
 if(!Gfx::RegisterDraw||!Gfx::DrawMesh){
  if(Core::Log)Core::Log("[BW3D_CUBE] ERROR missing NVN gfx exports");
  return;
 }
 if(Gfx::Init)Gfx::Init();
 if(!Gfx::RegisterDraw(&draw)){
  if(Core::Log)Core::Log("[BW3D_CUBE] ERROR unable to register draw callback");
 }else if(Core::Log){
  Core::Log("[BW3D_CUBE] Registered native 36-vertex cube GPU draw callback");
 }
}