#include "flight_controller.h"

#include <math.h>
#include <string.h>

/* Avoid unaligned/tearing assumptions: read through a seqlock twice.
   Single writer publishes odd -> data -> even. */
static bool copy_packet(const volatile BwcFlightPacket *src, BwcFlightPacket *dst) {
    for (unsigned attempt = 0; attempt != 8; ++attempt) {
        uint32_t before = src->sequence;
        if (before & 1u) continue;
        const volatile uint8_t *p = (const volatile uint8_t *)src;
        uint8_t *out = (uint8_t *)dst;
        for (unsigned i = 0; i < sizeof(*dst); ++i) out[i] = p[i];
        uint32_t after = src->sequence;
        if (!(after & 1u) && before == after && dst->sequence == after)
            return true;
    }
    return false;
}

static bool finite3(const float v[3]) {
    for (int i=0; i<3; ++i) if (!isfinite(v[i]) || fabsf(v[i]) > 100000.0f) return false;
    return true;
}

void bwc_flight_init(BwcFlightController *ctrl, const BwcFlightHooks *hooks) {
    if (!ctrl) return;
    memset(ctrl, 0, sizeof(*ctrl));
    if (hooks) ctrl->hooks = *hooks;
}

void bwc_flight_disarm(BwcFlightController *ctrl) {
    if (!ctrl || !ctrl->active) return;
    /* Restore game defaults on disengage, so menus/saves remain playable. */
    if (ctrl->hooks.set_player_visible)
        ctrl->hooks.set_player_visible(ctrl->hooks.user, true);
    if (ctrl->hooks.set_player_physics_enabled)
        ctrl->hooks.set_player_physics_enabled(ctrl->hooks.user, true);
    ctrl->active = false;
}

BwcFlightResult bwc_flight_tick(BwcFlightController *ctrl,
                                const volatile BwcFlightPacket *mailbox,
                                uint64_t host_now_ms) {
    if (!ctrl || !mailbox) return BWC_FLIGHT_BAD_PACKET;
    BwcFlightPacket packet;
    if (!copy_packet(mailbox, &packet) ||
        packet.magic != BWC_BDP1_MAGIC || packet.version != BWC_BDP1_VERSION) {
        bwc_flight_disarm(ctrl);
        return BWC_FLIGHT_BAD_PACKET;
    }
    if (!(packet.flags & BWC_FLIGHT_ACTIVE) || !(packet.flags & BWC_FLIGHT_FPS)) {
        bwc_flight_disarm(ctrl);
        return BWC_FLIGHT_DISARMED;
    }
    if (host_now_ms < packet.host_uptime_ms ||
        host_now_ms - packet.host_uptime_ms > 1000u) {
        bwc_flight_disarm(ctrl);
        return BWC_FLIGHT_STALE;
    }
    if (!finite3(packet.position) || !finite3(packet.eye) ||
        !finite3(packet.forward) || !isfinite(packet.yaw) ||
        !isfinite(packet.pitch)) {
        bwc_flight_disarm(ctrl);
        return BWC_FLIGHT_BAD_PACKET;
    }
    float forward_len = 0;
    for (int i=0; i<3; ++i) forward_len += packet.forward[i]*packet.forward[i];
    if (forward_len < 0.90f || forward_len > 1.10f) {
        bwc_flight_disarm(ctrl);
        return BWC_FLIGHT_BAD_PACKET;
    }
    const BwcFlightHooks *h = &ctrl->hooks;
    if (!h->set_player_transform || !h->set_camera_lookat ||
        !h->set_player_visible || !h->set_player_physics_enabled) {
        bwc_flight_disarm(ctrl);
        return BWC_FLIGHT_NO_HOOKS;
    }
    float target[3];
    for (int i=0; i<3; ++i) target[i] = packet.eye[i] + packet.forward[i];
    /* Minecraft controls all movement modes (walking, falling, swimming, flying).
       Collision integration is deliberately deferred: BOTW physics is disabled temporarily.
       Only the verified native adapter can actually change the game.
       Never reinterpret process memory offsets as engine function pointers. */
    if (!h->set_player_physics_enabled(h->user, false) ||
        !h->set_player_transform(h->user, packet.position, packet.yaw) ||
        !h->set_camera_lookat(h->user, packet.eye, target) ||
        !h->set_player_visible(h->user, false)) {
        bwc_flight_disarm(ctrl);
        return BWC_FLIGHT_ENGINE_FAILURE;
    }
    ctrl->active = true;
    ctrl->last_sequence = packet.sequence;
    return BWC_FLIGHT_APPLIED;
}
