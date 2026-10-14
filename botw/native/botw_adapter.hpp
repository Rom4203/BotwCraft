#pragma once
// BotwCraft: game-adapter contract for an actual BOTW executable mod.
// Implement using WiiXLaunch/ExLaunch hooks; no guessed game symbols.
#include <cstdint>

namespace botwcraft {
struct Vec3 { double x, y, z; };
struct Pose {
    Vec3 feet;
    float yaw, pitch;
    bool grounded;
    bool valid;
};
struct MovementCommand {
    Pose target;
    std::uint64_t sequence;
};
struct WorldSnapshot {
    Pose player;
    std::uint32_t world_id;
    std::uint32_t loading;
};
// Runs on the guest's game thread. No host pointers cross this boundary.
class GameAdapter {
public:
    virtual ~GameAdapter() = default;
    virtual bool read_world(WorldSnapshot& out) noexcept = 0;
    virtual bool apply_movement(const MovementCommand& cmd) noexcept = 0;
    virtual bool begin_tick() noexcept = 0;
    virtual void end_tick() noexcept = 0;
};
} // namespace botwcraft
