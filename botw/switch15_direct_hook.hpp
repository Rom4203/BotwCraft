#pragma once
// BOTWCRAFT: strictly opt-in BOTW Switch 1.5.0 direct Link PHYSICS adapter.
//
// This header is compiled into the same WiiXLaunch Switch host as the verified
// PlayerInfo pose reader. It is deliberately not compiled for Wii U/Cemu.
//
// Win32 host writes a BDP1 target into this private mod-owned guest allocation,
// using a process-memory address discovered by its immutable 40-byte marker.
// The native code never reads paths, game files or arbitrary host pointers.
//
// IMPORTANT: Actor::setMtx vtable index 85 and its argument layout are known
// from the 1.5.0 Actor type declaration; the exact SWITCH runtime implementation
// has not yet been validated in a running build. Enable writes ONLY after
// explicit opt-in. This adapter NEVER claims that virtual dispatch is safe
// merely because a target contains plausible floats.
#include <cstdint>
#include <cstddef>
#include <wiixlaunch/game_version.hpp>
#include <wiixlaunch/debug_log.hpp>
#include <lib.hpp>

namespace BotwCraft15Direct {
constexpr uint32_t kFingerprint = 0xA982D2BC;
constexpr uint32_t kMagic = 0x31504442;
constexpr uint32_t kActive = 1;
constexpr uint32_t kFirstPerson = 2;
constexpr uint32_t kAllowActorWrite = 0x10;
// Marker EXACTLY 40 bytes, installed once in the guest's real writable memory.
// The scanner only accepts this marker in the genuine Ryujinx process.
constexpr char kMarker[40] = "BOTWCRAFT15_DIRECT_GUEST_XYZ_20261010";
static_assert(sizeof(kMarker) == 40);
struct alignas(8) Target {
    uint32_t sequence, magic, version, flags;
    uint64_t minecraftFrame, hostTimeMs;
    float position[3], eye[3], forward[3], yaw, pitch;
    float mcAnchor[3], hyruleAnchor[3], reserved;
    uint32_t r0, r1;
};
static_assert(sizeof(Target) == 112);
struct alignas(16) Mailbox {
    char marker[40];
    Target target;
};
inline Mailbox gMailbox = [] {
    Mailbox m{};
    for (size_t i = 0; i < sizeof(kMarker); ++i) m.marker[i] = kMarker[i];
    return m;
}();
inline uint32_t gApplied = 0;
inline uint32_t gRefused = 0;
inline uint32_t gLastSeq = 0;
inline uint64_t gLastMcFrame = 0;
inline uint32_t gRenderFramesSinceUpdate = 10000;
inline bool gWriteEnabled = false;

inline bool Finite(float v) {
    return v == v && v > -100000.f && v < 100000.f;
}
inline bool Valid(const Target& t, uint32_t a, uint32_t b) {
    if (a != b || (a & 1) || t.sequence != a) return false;
    if (t.magic != kMagic || t.version != 1 ||
        (t.flags & (kActive|kFirstPerson|kAllowActorWrite)) !=
        (kActive|kFirstPerson|kAllowActorWrite)) return false;
    if (!t.minecraftFrame) return false;
    for (float n : t.position) if (!Finite(n)) return false;
    for (float n : t.eye) if (!Finite(n)) return false;
    for (float n : t.forward) if (!Finite(n)) return false;
    float norm = t.forward[0]*t.forward[0]+t.forward[1]*t.forward[1]+
                 t.forward[2]*t.forward[2];
    return norm > 0.98f && norm < 1.02f;
}
inline bool Read(Target& out) {
    // External process writes even/odd seqlock; guest copies atomically by
    // sequence. No GDB calls or per-frame emulator thread interruption.
    const volatile uint8_t* bytes =
        reinterpret_cast<const volatile uint8_t*>(&gMailbox.target);
    auto* start = reinterpret_cast<volatile uint32_t*>(&gMailbox.target.sequence);
    const uint32_t first = *start;
    if (first & 1) return false;
    uint8_t* dest = reinterpret_cast<uint8_t*>(&out);
    for (size_t i=0; i<sizeof(Target); i++) dest[i]=bytes[i];
    __atomic_thread_fence(__ATOMIC_ACQUIRE);
    const uint32_t last = *start;
    return Valid(out,first,last);
}
inline void Register() {
    if (WiiXLaunch::GameVersion::Fingerprint() != kFingerprint) return;
    // On each run, host OS address changes and is discovered by marker scan.
    WIIXL_LOG("BotwCraft:DIRECT_GUEST_MAILBOX_ADDR=0x%lx bytes=152",
             static_cast<unsigned long>(reinterpret_cast<uintptr_t>(&gMailbox)));
    WIIXL_LOG("BotwCraft:DIRECT_LINK_BACKEND_ARMED=0 (requires explicit BDP1 opt-in)");
}

// Returns false for an unverified vtable, and does not mutate any coordinates.
// Index is from zeldaret/botw ksys::act::Actor virtual declaration.
inline bool TryApplyActor(void* actor, const float xyz[3], float yawDeg,
                          uintptr_t textStart, uintptr_t textEnd) {
    if (!actor || textStart == 0 || textEnd <= textStart) return false;
    uintptr_t ptr = reinterpret_cast<uintptr_t>(actor);
    if (ptr < 0x10000000 || ptr > 0x0000010000000000ull ||
        (ptr & 7u)) return false;
    auto** vtable = *reinterpret_cast<uintptr_t***>(actor);
    uintptr_t vtp = reinterpret_cast<uintptr_t>(vtable);
    if (vtp < 0x10000000 || vtp > 0x0000010000000000ull ||
        (vtp & 7u)) return false;
    // No call whatsoever unless the candidate entry is in game's TEXT.
    constexpr size_t kSetMtxVirtualIndex = 85;
    uintptr_t targetFunction = reinterpret_cast<uintptr_t>(
        vtable[kSetMtxVirtualIndex]);
    if (targetFunction < textStart || targetFunction >= textEnd ||
        (targetFunction & 3u)) return false;

    // Keep Link's existing rotation until the BOTW 1.5.0 PlayerBase yaw
    // convention is confirmed. SetMtx updates the actor, character controller,
    // and render model; refresh=false prevents cloth reset each frame.
    // The identity matrix is placeholder for rotation ONLY; see camera hook.
    const float matrix[12]{
        1.f,0.f,0.f,xyz[0],
        0.f,1.f,0.f,xyz[1],
        0.f,0.f,1.f,xyz[2]
    };
    (void)yawDeg;
    using SetMtx = void (*)(void*, const float*, int, int);
    reinterpret_cast<SetMtx>(targetFunction)(actor,matrix,1,0);
    return true;
}

inline void Poll(void* player, const float current[3]) {
    if (WiiXLaunch::GameVersion::Fingerprint() != kFingerprint ||
        !player || !current) return;
    Target packet{};
    if (!Read(packet)) {
        ++gRenderFramesSinceUpdate;
        return;
    }
    if (packet.sequence != gLastSeq) {
        gLastSeq=packet.sequence;
        gRenderFramesSinceUpdate=0;
    } else {
        ++gRenderFramesSinceUpdate;
    }
    if (gRenderFramesSinceUpdate > 12) {
        if (gWriteEnabled) WIIXL_LOG("BotwCraft:DIRECT_LINK_DISARMED_STALE");
        gWriteEnabled=false;
        return;
    }
    if (packet.minecraftFrame == gLastMcFrame) return;
    const float dx=packet.position[0]-current[0];
    const float dy=packet.position[1]-current[1];
    const float dz=packet.position[2]-current[2];
    if (dx*dx+dy*dy+dz*dz > 256.f) {
        ++gRefused;
        if ((gRefused % 60)==1)
            WIIXL_LOG("BotwCraft:DIRECT_LINK_REJECTED_DELTA");
        return;
    }
    const auto info = exl::util::GetMainModuleInfo();
    const uintptr_t textLo = info.m_Text.m_Start;
    const uintptr_t textHi = info.m_Text.m_End;
    if (!TryApplyActor(player,packet.position,packet.yaw,textLo,textHi)) {
        ++gRefused;
        if ((gRefused % 60)==1)
            WIIXL_LOG("BotwCraft:DIRECT_LINK_SETMTX_UNVERIFIED");
        return;
    }
    gWriteEnabled=true;
    gLastMcFrame=packet.minecraftFrame;
    ++gApplied;
    if ((gApplied % 120)==1)
        WIIXL_LOG("BotwCraft:DIRECT_LINK_SETMTX_CALLED applied=%u",gApplied);
}
} // namespace BotwCraft15Direct
