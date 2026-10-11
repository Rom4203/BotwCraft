package dev.skycraft.client;

/**
 * Opt-in gate for BotwCraft terrain triangles. Never enables Skyrim takeover.
 * This is called ONLY by the local player's EntityCollideMixin, leaving SkyClient.linked() false.
 * The collision ring is consumed only when the option is explicitly enabled.
 */
public final class BotwCollisionGate {
    private static final boolean ENABLED = Boolean.getBoolean("botwcraft.terrain");
    private static volatile boolean consumerStarted;
    private static volatile boolean loggedFailure;
    private static volatile int collisionGeneration = -1;
    private static volatile boolean ready;
    private static volatile boolean sessionEnded;

    private BotwCollisionGate() {}

    public static boolean linked() {
        if (!ENABLED) return false;
        try {
            if (!BotwCraftSession.requested()) {
                if (ready) sessionEnded = true;
                return false;
            }
            if (sessionEnded) return false;
            if (!consumerStarted) {
                synchronized (BotwCollisionGate.class) {
                    if (!consumerStarted) {
                        dev.skycraft.world.SkyCollision.startConsumer();
                        consumerStarted = true;
                        System.err.println("[BotwCraft terrain] triangle stream consumer started (experimental)");
                    }
                }
            }
            // A previously streamed mesh must NEVER reactivate after a bridge
            // restart without a fresh Minecraft session (stale world geometry).
            if (!dev.skycraft.link.SkyLink.active()) return false;
            final int currentGeneration = dev.skycraft.link.SkyLink.generation();
            if (collisionGeneration == -1) collisionGeneration = currentGeneration;
            if (collisionGeneration != currentGeneration) return false;
            // O(1) in the hot path once the first real packet arrived.
            if (!ready) ready = dev.skycraft.world.SkyCollision.triangleCount() > 0;
            return ready;
        } catch (Throwable ex) {
            if (!loggedFailure) {
                loggedFailure = true;
                System.err.println("[BotwCraft terrain] disabled: " + ex);
            }
            return false;
        }
    }
}