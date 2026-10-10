#pragma once
#include "flight_controller.h"
#include "switch_camera_adapter.hpp"

#include <cstdint>

/* Integration glue for a real, externally verified BOTW 1.5.0 hook.
   It deliberately does not guess a Link pointer, a vtable, or a camera object.
   The calling WiiXLaunch module supplies these at its player/camera update hook. */
namespace BotwCraft {

struct SwitchEngine {
    NativeCameraContext camera;
    void* player = nullptr;
    bool (*warp_player)(void*, const float[3], float) = nullptr;
    bool (*show_player)(void*, bool) = nullptr;
    bool (*enable_player_physics)(void*, bool) = nullptr;
    BwcFlightController controller = {};
    bool initialized = false;
};

inline bool Warp(void* context, const float xyz[3], float yaw) {
    auto& e = *static_cast<SwitchEngine*>(context);
    return e.player && e.warp_player && e.warp_player(e.player, xyz, yaw);
}

inline bool Show(void* context, bool visible) {
    auto& e = *static_cast<SwitchEngine*>(context);
    return e.player && e.show_player && e.show_player(e.player, visible);
}

inline bool Physics(void* context, bool enabled) {
    auto& e = *static_cast<SwitchEngine*>(context);
    return e.player && e.enable_player_physics &&
           e.enable_player_physics(e.player, enabled);
}

inline bool CameraLook(void* context, const float eye[3], const float target[3]) {
    auto& e = *static_cast<SwitchEngine*>(context);
    return SetFirstPersonCamera(&e.camera, eye, target);
}

inline void Bind(SwitchEngine& e) {
    BwcFlightHooks hooks = {Warp, CameraLook, Show, Physics, &e};
    bwc_flight_init(&e.controller, &hooks);
    e.initialized = true;
}

/* Call once per game camera-update frame after resolving live objects.
   A null pointer or missing callback safely refuses activation.
   Do not call from a host process on a guest pointer. */
inline BwcFlightResult OnGameFrame(SwitchEngine& e,
                                  void* livePlayer,
                                  void* liveCamera,
                                  const volatile BwcFlightPacket* guestMailbox,
                                  uint64_t alignedHostClockMs) {
    if (!e.initialized) Bind(e);
    if (e.player != livePlayer || e.camera.activeCamera != liveCamera) {
        bwc_flight_disarm(&e.controller);
        RestoreCamera(e.camera);
    }
    e.player = livePlayer;
    e.camera.activeCamera = liveCamera;
    if (!e.player || !e.camera.activeCamera ||
        !e.warp_player || !e.show_player || !e.enable_player_physics) {
        bwc_flight_disarm(&e.controller);
        return BWC_FLIGHT_NO_HOOKS;
    }
    BwcFlightResult result = bwc_flight_tick(&e.controller, guestMailbox,
                                             alignedHostClockMs);
    if (result != BWC_FLIGHT_APPLIED) RestoreCamera(e.camera);
    return result;
}

inline void Stop(SwitchEngine& e) {
    bwc_flight_disarm(&e.controller);
    RestoreCamera(e.camera);
}

} // namespace BotwCraft
