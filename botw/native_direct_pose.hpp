#pragma once
// BotwCraft BDP1 cross-process direct Steve->Hyrule actor/camera target.
// Reuses SkyCraft v11's reserved 0x18000..0x1ffff shared-memory region,
// which is not occupied by the input ring or collision ring.
//
// A Ryujinx-native producer/consumer (NOT WiiXLaunch socket or GDB) will
// transfer a validated BDP1 target into BOTW guest. The game module MUST
// only apply it via a verified 1.5.0 Actor::setMtx + real CameraMgr setter.
// A raw actor position field is NOT an authoritative movement setter.
//
// Layout intentionally mirrors Python botw/direct_pose_sync.py; reader uses
// even/odd seqlock and timestamp to reject torn/old frames.
#include <cstddef>
#include <cstdint>

namespace BotwCraftDirect {
constexpr std::size_t kSkyCraftOffset = 0x18000;
constexpr uint32_t kMagic = 0x31504442; // BDP1
constexpr uint32_t kVersion = 1;
constexpr uint32_t kActive=1, kFirstPerson=2, kFly=4;
constexpr uint64_t kStaleMs=1000;

struct alignas(8) Target {
    uint32_t sequence;
    uint32_t magic;
    uint32_t version;
    uint32_t flags;
    uint64_t minecraftFrame;
    uint64_t timeMs;
    float position[3];    // exact destination of Link's physics actor
    float eye[3];         // Steve's view point anchored to Hyrule
    float forward[3];     // unit look direction from Minecraft yaw/pitch
    float yaw;
    float pitch;
    float minecraftAnchor[3];
    float hyruleAnchor[3];
    float reservedFloat;
    uint32_t reserved0;
    uint32_t reserved1;
};
static_assert(sizeof(Target)==112);
static_assert(offsetof(Target, position)==32);
static_assert(offsetof(Target, eye)==44);
static_assert(offsetof(Target, forward)==56);
static_assert(offsetof(Target, yaw)==68);
static_assert(offsetof(Target, minecraftAnchor)==76);
static_assert(offsetof(Target, hyruleAnchor)==88);

inline bool Finite(float v) {
    return v==v && v>-100000.f && v<100000.f;
}

inline bool Accept(const Target& p, uint32_t seq1, uint32_t seq2,
                   uint64_t nowMs) {
    if (seq1 != seq2 || (seq1 & 1) || p.sequence != seq1) return false;
    if (p.magic!=kMagic || p.version!=kVersion) return false;
    if ((p.flags & (kActive|kFirstPerson))!=(kActive|kFirstPerson)) return false;
    if (!p.minecraftFrame || nowMs < p.timeMs || nowMs-p.timeMs>kStaleMs)
        return false;
    for(float x:p.position) if(!Finite(x)) return false;
    for(float x:p.eye) if(!Finite(x)) return false;
    for(float x:p.forward) if(!Finite(x)) return false;
    for(float x:p.minecraftAnchor) if(!Finite(x)) return false;
    for(float x:p.hyruleAnchor) if(!Finite(x)) return false;
    if(!Finite(p.yaw) || !Finite(p.pitch)) return false;
    float len=p.forward[0]*p.forward[0]+p.forward[1]*p.forward[1]+
              p.forward[2]*p.forward[2];
    if (!(len>0.98f && len<1.02f)) return false;
    return true;
}
} // namespace BotwCraftDirect
