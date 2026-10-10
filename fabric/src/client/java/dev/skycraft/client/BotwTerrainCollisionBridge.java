package dev.skycraft.client;

import dev.skycraft.world.SkyCollision;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.phys.Vec3;

/**
 * Only client-side collision hook added to the user's known-good test20 JAR.
 * SkyClient, BotwCraftSession, movement, teleports and camera remain untouched.
 * The original EntityCollideMixin continues to run at Entity.collide; its
 * original method refs are retargeted to this class and BotwCraftSession.
 */
public final class BotwTerrainCollisionBridge {
    private static volatile boolean started;
    private BotwTerrainCollisionBridge() {}

    public static boolean enabled() {
        return BotwCraftSession.requested();
    }

    public static Vec3 collide(LocalPlayer player, Vec3 wanted) {
        // In spectator mode it is vital to NEVER restrict or set Steve's
        // position, velocity, rotation, view, movement or Minecraft inputs.
        if (!enabled() || player.isSpectator() || player.noPhysics) return wanted;
        if (!started) {
            synchronized (BotwTerrainCollisionBridge.class) {
                if (!started) {
                    SkyCollision.startConsumer();
                    started = true;
                }
            }
        }
        // The same SkyCraft triangle collider used by the game's own
        // Minecraft physics, fed with sampled real Havok ground rays.
        return SkyCollider.collide(player, wanted);
    }
}
