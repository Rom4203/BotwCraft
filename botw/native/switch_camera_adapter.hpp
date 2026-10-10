#pragma once

#include "flight_controller.h"
#include <wiixlaunch/botw/game/camera.hpp>
#include <cmath>

// Switch 1.5.0 camera adapter. No guessed addresses: caller supplies the
// ACTUAL live camera pointer from its verified game hook each frame.
// Camera::SetPosition and SetLookAt use typed Switch SDK offsets.
namespace BotwCraft {

struct NativeCameraContext {
    void* activeCamera = nullptr;
    bool captured = false;
    float oldPosition[3] = {};
    float oldLookAt[3] = {};
    float oldUp[3] = {};
};

inline bool SetFirstPersonCamera(void* user, const float eye[3],
                                  const float target[3]) {
    auto* state = static_cast<NativeCameraContext*>(user);
    if (!state || !state->activeCamera || !eye || !target) return false;
    for (int i = 0; i < 3; ++i)
        if (!std::isfinite(eye[i]) || !std::isfinite(target[i])) return false;

    using WiiXLaunch::BotW::Camera;
    if (!state->captured) {
        Camera::GetPosition(state->activeCamera,
            state->oldPosition[0], state->oldPosition[1], state->oldPosition[2]);
        Camera::GetLookAt(state->activeCamera,
            state->oldLookAt[0], state->oldLookAt[1], state->oldLookAt[2]);
        Camera::GetUp(state->activeCamera,
            state->oldUp[0], state->oldUp[1], state->oldUp[2]);
        state->captured = true;
    }
    Camera::SetPosition(state->activeCamera, eye[0], eye[1], eye[2]);
    Camera::SetLookAt(state->activeCamera, target[0], target[1], target[2]);
    // Use world up, except at vertical pitch (the camera's own near-vertical
    // orientation must be handled by its look-at construction).
    Camera::SetUp(state->activeCamera, 0.f, 1.f, 0.f);
    return true;
}

inline void RestoreCamera(NativeCameraContext& state) {
    if (state.activeCamera && state.captured) {
        using WiiXLaunch::BotW::Camera;
        Camera::SetPosition(state.activeCamera,
            state.oldPosition[0], state.oldPosition[1], state.oldPosition[2]);
        Camera::SetLookAt(state.activeCamera,
            state.oldLookAt[0], state.oldLookAt[1], state.oldLookAt[2]);
        Camera::SetUp(state.activeCamera,
            state.oldUp[0], state.oldUp[1], state.oldUp[2]);
    }
    state.captured = false;
}

} // namespace BotwCraft
