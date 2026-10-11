package dev.skycraft.client;

import dev.skycraft.link.SkyLink;
import dev.skycraft.world.SkyCollision;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import java.util.ArrayList;
import dev.skycraft.world.SkyTri;

/** Native Rust collision feed gate. The legacy Skyrim gameplay is NEVER enabled.
 * The only actor with smooth native triangles is the local Minecraft player.
 * Integrated server physics instead sees Rust-generated subvoxel shapes.
 */
public final class BotwCollisionGate {
    private static boolean consumerStarted;
    private static volatile boolean ready;
    private static volatile int generation = -1;
    private static volatile boolean disabledAfterRestart;

    // Called many times per tick by BlockCollisions; bound expensive triangle
    // lookups to 40 Hz PER thread so client FPS is not reduced.
    private static final class Probe {
        Entity entity;
        long timestamp;
        boolean nearby;
    }
    private static final ThreadLocal<Probe> probe = ThreadLocal.withInitial(Probe::new);
    private BotwCollisionGate() {}

    public static boolean linked() {
        if (!BotwCraftSession.requested() || !BotwCraftSession.compositorInputs()) {
            ready = false;
            return false;
        }
        if (!SkyLink.active() || disabledAfterRestart) {
            ready = false;
            return false;
        }
        if (!consumerStarted) {
            synchronized (BotwCollisionGate.class) {
                if (!consumerStarted) {
                    SkyCollision.startConsumer();
                    SkyCollision.setSmoothCollider(e -> e instanceof LocalPlayer && BotwCollisionGate.linked());
                    consumerStarted = true;
                    System.out.println("[BotwCraft] Rust-native Hyrule collision stream connected (waiting for real terrain)");
                }
            }
        }
        int g = SkyLink.generation();
        if (generation == -1) generation = g;
        if (generation != g) {
            // Prevent yesterday's chunks persisting over a Ryujinx restart.
            disabledAfterRestart = true;
            ready = false;
            return false;
        }
        if (!ready) ready = SkyCollision.triangleCount() > 0;
        return ready;
    }

    /** The native BOTW terrain replaces the vanilla world only while real
     * triangles have arrived. Spectators/physics-free entities are untouched.
     */
    public static boolean replacesVanilla(Entity entity) {
        if (!(entity instanceof Player) || entity.noPhysics || !linked()) return false;
        Probe p = probe.get();
        long now = System.nanoTime();
        if (p.entity != entity || now - p.timestamp > 25_000_000L) {
            var triangles = new ArrayList<SkyTri>();
            SkyCollision.trianglesNear(entity.getBoundingBox().inflate(1.25, 4.0, 1.25), triangles);
            p.entity = entity;
            p.timestamp = now;
            p.nearby = !triangles.isEmpty();
        }
        return p.nearby;
    }
}