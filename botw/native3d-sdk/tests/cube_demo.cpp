#include "../native/cube_demo/cube.hpp"
#include <cassert>
#include <cmath>
int main(){
 using namespace bw3d_test;
 Vertex a[kVertices]{},b[kVertices]{};
 make_cube(0,a);make_cube(20,b);
 bool rotating=false;
 for(unsigned i=0;i<kVertices;++i){
  assert(a[i].w>1.f&&a[i].w<6.f);
  assert(a[i].z>=0.f&&a[i].z<a[i].w);
  assert(std::abs(a[i].x/a[i].w)<1.f);
  assert(std::abs(a[i].y/a[i].w)<1.f);
  assert(std::isfinite(a[i].nx)&&std::isfinite(a[i].nz));
  rotating|=std::abs(a[i].x-b[i].x)>.01f;
 }
 assert(rotating);
}