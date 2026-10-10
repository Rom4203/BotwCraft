#pragma once
// Native BWH1: one GPU-HUD frame proof, separate from BWC1 mesh/BWC2 world.
// Never read ROMFS/SD; the Windows GDB writer fills a buffer owned by us.
// A native dynamic streaming texture API is a later step; one captured frame
// is intentionally the ONLY supported content in this safe experiment.
#include <cstddef>
#include <cstdint>
namespace BotwCraftHud {
constexpr uint32_t kMagic=0x31485742u;
constexpr uint32_t kVersion=1;
constexpr uint32_t kWidth=128, kHeight=72;
constexpr size_t kPixels=size_t(kWidth)*kHeight*4;
struct Header {
    uint32_t magic,version,frameId,width,height,bytes,hash,flags;
};
static_assert(sizeof(Header)==32);
constexpr size_t kPacketBytes=sizeof(Header)+kPixels;
inline uint32_t Hash(const uint8_t* p,size_t n) {
    uint32_t h=2166136261u;
    for(size_t i=0;i<n;i++) h=(h^p[i])*16777619u;
    return h;
}
inline bool Valid(const uint8_t* packet,size_t allocated) {
    if(!packet || allocated<kPacketBytes) return false;
    const auto* h=reinterpret_cast<const Header*>(packet);
    if(h->magic!=kMagic||h->version!=kVersion||h->frameId==0 ||
       h->width!=kWidth || h->height!=kHeight ||
       h->bytes!=kPixels || h->flags!=0) return false;
    return Hash(packet+sizeof(Header),kPixels)==h->hash;
}
}
