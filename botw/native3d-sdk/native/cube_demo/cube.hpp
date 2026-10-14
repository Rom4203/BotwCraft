#pragma once
// BW3D first visible Zelda/NVN test. 36 hardware vertices, NOT a PNG.
// FIRST TEST ONLY: cube lives in clip/camera space, not Hyrule world space.
#include <cstdint>
namespace bw3d_test {
struct Vertex {float x,y,z,w,nx,ny,nz,nw;};
static_assert(sizeof(Vertex)==32,"NVN native mesh vertex must be 8 floats");
constexpr uint32_t kVertices=36;
inline void make_cube(uint32_t tick,Vertex out[kVertices]){
 constexpr float sinus[16]={0.f,.38268343f,.70710678f,.92387953f,
  1.f,.92387953f,.70710678f,.38268343f,0.f,-.38268343f,
  -.70710678f,-.92387953f,-1.f,-.92387953f,-.70710678f,-.38268343f};
 unsigned angle=(tick/5u)&15u;
 float s=sinus[angle],c=sinus[(angle+4u)&15u];
 constexpr float corners[8][3]={{-1,-1,-1},{1,-1,-1},{1,1,-1},{-1,1,-1},
  {-1,-1,1},{1,-1,1},{1,1,1},{-1,1,1}};
 constexpr uint8_t faces[6][4]={{4,5,6,7},{1,0,3,2},{0,4,7,3},
  {5,1,2,6},{3,7,6,2},{0,1,5,4}};
 constexpr float normals[6][3]={{0,0,1},{0,0,-1},{-1,0,0},
  {1,0,0},{0,1,0},{0,-1,0}};
 constexpr uint8_t tris[6]={0,1,2,0,2,3};
 unsigned n=0;
 for(unsigned f=0;f<6;++f)for(auto t:tris){
  unsigned idx=faces[f][t];
  float x=corners[idx][0]*.7f,y=corners[idx][1]*.7f,z=corners[idx][2]*.7f;
  float rx=x*c+z*s,rz=-x*s+z*c;
  float depth=3.f+rz;
  // Perspective is performed by the actual GPU using vertex W. Physical
  // triangle rotation, individual vertices and surface normals are real.
  out[n++]={depth*.38f+rx*1.35f,depth*(-.10f)+y*1.35f,
    depth*.55f,depth,
    normals[f][0]*c+normals[f][2]*s,normals[f][1],
    -normals[f][0]*s+normals[f][2]*c,1.f};
 }
}
}