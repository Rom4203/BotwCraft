package dev.skycraft.client;

import dev.skycraft.SkyCraft;
import java.util.UUID;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.Blocks;

/**
 * BotwCraft experimental MC block-building preview.
 *
 * Builds a tiny grass platform in the existing SkyCraft mirror (void) world
 * once, on the integrated server thread. No Zelda world files are modified.
 * The standard Minecraft client handles creative inventory, placing, breaking
 * and saving the real blocks. This is NOT BOTW terrain collision.
 */
public final class BlockPreview {
    private static final boolean ENABLED = Boolean.getBoolean("botwcraft.experimentalBlocks");
    private static UUID initializedPlayer;

    private BlockPreview() {}

    public static boolean enabled() {
        return ENABLED;
    }

    public static void tick(Minecraft minecraft) {
        if (!ENABLED || minecraft.player == null || minecraft.level == null) {
            initializedPlayer = null;
            return;
        }
        MinecraftServer server = minecraft.getSingleplayerServer();
        if (server == null) {
            return;  // Never edit a remote multiplayer server's world.
        }
        UUID playerId = minecraft.player.getUUID();
        if (playerId.equals(initializedPlayer)) {
            return;
        }
        initializedPlayer = playerId;
        server.execute(() -> {
            if (server.getPlayerList().getPlayer(playerId) == null) {
                return;
            }
            ServerLevel world = server.overworld();
            if (world == null) {
                return;
            }
            // The preview always spawns at MC (0, 80, 0), with Y-up. Platform
            // supports the player at Y=80 (top of block at Y=79).
            BlockPos center = new BlockPos(0, 79, 0);
            if (!world.getBlockState(center).isAir()) {
                return;  // Existing saved platform: never reset players' builds.
            }
            int placed = 0;
            for (int x = -10; x <= 10; ++x) {
                for (int z = -10; z <= 10; ++z) {
                    BlockPos pos = new BlockPos(x, 79, z);
                    if (world.getBlockState(pos).isAir()
                            && world.setBlockAndUpdate(pos, Blocks.GRASS_BLOCK.defaultBlockState())) {
                        ++placed;
                    }
                }
            }
            SkyCraft.LOG.info("BotwCraft block preview: {} starter blocks created", placed);
        });
    }
}
