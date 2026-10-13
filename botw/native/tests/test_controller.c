#include "../flight_controller.h"
#include <assert.h>
#include <stddef.h>
#include <stdio.h>

static int transforms, cameras, hidden, restored;
static bool move(void *u, const float p[3], float yaw) {
    (void)u; (void)yaw;
    assert(p[0] == 10.f);
    ++transforms;
    return true;
}
static bool camera(void *u, const float eye[3], const float target[3]) {
    (void)u;
    assert(eye[0] == 10.f && target[2] == 21.f);
    ++cameras;
    return true;
}
static bool visible(void *u, bool value) {
    (void)u;
    if (value) ++restored;
    else ++hidden;
    return true;
}
static bool physics(void *u, bool enabled) {
    (void)u; (void)enabled;
    return true;
}
int main(void) {
    assert(sizeof(BwcFlightPacket) == 112);
    assert(offsetof(BwcFlightPacket, position) == 32);
    BwcFlightHooks hooks = {move, camera, visible, physics, 0};
    BwcFlightController controller;
    bwc_flight_init(&controller, &hooks);
    BwcFlightPacket packet = {0};
    packet.sequence = 2;
    packet.magic = BWC_BDP1_MAGIC;
    packet.version = BWC_BDP1_VERSION;
    packet.flags = BWC_FLIGHT_ACTIVE | BWC_FLIGHT_FPS; /* no FLY bit */
    packet.host_uptime_ms = 1000;
    packet.position[0] = 10;
    packet.eye[0] = 10;
    packet.eye[2] = 20;
    packet.forward[2] = 1;
    assert(bwc_flight_tick(&controller, &packet, 1050) == BWC_FLIGHT_APPLIED);
    assert(transforms == 1 && cameras == 1 && hidden == 1);
    assert(bwc_flight_tick(&controller, &packet, 2050) == BWC_FLIGHT_STALE);
    assert(restored == 1);
    packet.flags = 0;
    assert(bwc_flight_tick(&controller, &packet, 1050) == BWC_FLIGHT_DISARMED);
    puts("PASS: packet layout, any-mode movement, camera, disarm");
    return 0;
}
