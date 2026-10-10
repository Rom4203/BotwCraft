#ifndef BOTWCRAFT_FLIGHT_CONTROLLER_H
#define BOTWCRAFT_FLIGHT_CONTROLLER_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Host-produced BDP1 record; little-endian and exactly 112 bytes. */
#define BWC_BDP1_MAGIC 0x31504442u
#define BWC_BDP1_VERSION 1u
#define BWC_FLIGHT_ACTIVE 1u
#define BWC_FLIGHT_FPS 2u
#define BWC_FLIGHT_FLY 4u

typedef struct {
    uint32_t sequence;
    uint32_t magic;
    uint32_t version;
    uint32_t flags;
    uint64_t minecraft_frame;
    uint64_t host_uptime_ms;
    float position[3];
    float eye[3];
    float forward[3];
    float yaw;
    float pitch;
    float minecraft_origin[3];
    float botw_origin[3];
    float reserved;
    uint32_t reserved_tail[2];
} BwcFlightPacket;

typedef struct {
    /* These must be bound to VERIFIED BOTW 1.5.0 engine entry points.
       NULL callbacks cannot produce an active flight session. */
    bool (*set_player_transform)(void *user, const float xyz[3], float yaw);
    bool (*set_camera_lookat)(void *user, const float eye[3], const float target[3]);
    bool (*set_player_visible)(void *user, bool visible);
    bool (*set_player_physics_enabled)(void *user, bool enabled);
    void *user;
} BwcFlightHooks;

typedef enum {
    BWC_FLIGHT_DISARMED = 0,
    BWC_FLIGHT_APPLIED = 1,
    BWC_FLIGHT_NO_HOOKS = 2,
    BWC_FLIGHT_BAD_PACKET = 3,
    BWC_FLIGHT_STALE = 4,
    BWC_FLIGHT_ENGINE_FAILURE = 5
} BwcFlightResult;

typedef struct {
    BwcFlightHooks hooks;
    uint32_t last_sequence;
    bool active;
} BwcFlightController;

void bwc_flight_init(BwcFlightController *ctrl, const BwcFlightHooks *hooks);
BwcFlightResult bwc_flight_tick(BwcFlightController *ctrl,
                                const volatile BwcFlightPacket *mailbox,
                                uint64_t host_now_ms);
void bwc_flight_disarm(BwcFlightController *ctrl);

#ifdef __cplusplus
}
#endif
#endif
