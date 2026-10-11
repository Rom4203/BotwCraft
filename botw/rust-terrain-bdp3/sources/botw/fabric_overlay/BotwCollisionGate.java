package dev.skycraft.client;

import dev.skycraft.link.SkyLink;
import dev.skycraft.world.SkyCollision;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;

/**
 * One collision engine for both Minecraft client and integrated server:
 * native Shape-based collision from SkyCraft's COL_REGION ring. No rewind,
 * smooth triangle pass, fake block state or netcode teleport correction.
 */
public final class BotwCollisionGate {
    private static volatile boolean started;
    private static volatile int generation = -1;
    private BotwCollisionGate() {}

    /** Called only by the legacy EntityCollideMixin. Never run SkyCollider:
     * client and server must see the SAME vanilla VoxelShape geometry. */
    public static boolean linked() { return false; }

    public static boolean replacesVanilla(Entity entity) {
        if (!(entity instanceof Player player) || player.isSpectator() || entity.noPhysics) {
            return false;
        }
        if (!BotwCraftSession.requested() || !BotwCraftSession.compositorInputs() || !SkyLink.active()) {
            return false;
        }
        if (!started) {
            synchronized (BotwCollisionGate.class) {
                if (!started) {
                    SkyCollision.startConsumer();
                    started = true;
                    System.out.println("[BotwCraft] SkyCraft VoxelShape 1/8 ground enabled: same colliders for client and integrated server");
                }
            }
        }
        // A Ryujinx restart clears the mesh via Rust COL_CLEAR. Unlike the old
        // irreversible 'disabledAfterRestart', this gate can recover normally.
        int current = SkyLink.generation();
        if (generation != current) generation = current;
        return SkyCollision.blockCount() > 0;
    }
}