#pragma once
// One authoritative Minecraft frame -> one BOTW actor/Havok/camera update.
//
// This is the *atomic game-thread interface* for the eventual Switch 1.5.0
// executor. The callback is required to modify BOTH authoritative physics
// and camera; merely writing a mirrored XYZ buffer is forbidden.
//
// The real engine adapter must implement Apply with the verified BOTW 1.5.0
// actor transform (setMtx / Havok) and current gameplay camera operation.
// No vtable slots/offsets from Wii U or BOTW 1.6.0 are assumed here.
#include "native_direct_pose.hpp"

namespace BotwCraftDirect {
struct GameOps {
    // Called on the actual game simulation frame; never NVN render callback.
    // Return true only if both physics pose AND camera were applied.
    bool (*applySimultaneously)(const Target& target, void* context);
    void (*onDisarm)(void* context);
    void* context;
};

struct Executor {
    uint64_t lastFrame = 0;
    uint32_t lastSequence = 0;
    bool engaged = false;
    uint32_t rejected = 0;
    uint32_t applied = 0;

    // The caller captures seqlock seq before/after copying full payload.
    bool Tick(const Target& packet, uint32_t seqBefore, uint32_t seqAfter,
              uint64_t nowMs, const GameOps& ops) {
        if (!Accept(packet,seqBefore,seqAfter,nowMs) ||
            !ops.applySimultaneously) {
            if (engaged && ops.onDisarm) ops.onDisarm(ops.context);
            engaged = false;
            rejected++;
            return false;
        }
        if (packet.minecraftFrame < lastFrame ||
            (packet.minecraftFrame == lastFrame &&
             packet.sequence == lastSequence))
            return engaged; // Do NOT reapply last physics transform 60x.
        if (!ops.applySimultaneously(packet,ops.context)) {
            if (engaged && ops.onDisarm) ops.onDisarm(ops.context);
            engaged = false;
            rejected++;
            return false;
        }
        engaged = true;
        lastFrame = packet.minecraftFrame;
        lastSequence = packet.sequence;
        applied++;
        return true;
    }

    void Stop(const GameOps& ops) {
        if (engaged && ops.onDisarm) ops.onDisarm(ops.context);
        engaged = false;
        lastFrame = 0;
        lastSequence = 0;
    }
};
} // namespace BotwCraftDirect
