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
    // The Prism instance installs this marker in .minecraft. This survives
    // Prism launcher JVM argument overrides and manual instance creation.
    // No global SkyCraft behaviour is changed in other Minecraft profiles.
    private static final String PREVIEW_MARKER = "botwcraft.preview";
    private static volatile UUID initializedPlayer;
    private static volatile UUID pendingPlayer;

    private BlockPreview() {}

    public static boolean enabled() {
        if (Boolean.getBoolean("botwcraft.experimentalBlocks")) {
            return true;
        }
        Minecraft client = Minecraft.getInstance();
        return client != null && client.gameDirectory != null &&
            new java.io.File(client.gameDirectory, PREVIEW_MARKER).isFile();
    }

    public static void tick(Minecraft minecraft) {
        if (!enabled() || minecraft.player == null || minecraft.level == null) {
            initializedPlayer = null;
            pendingPlayer = null;
            return;
        }
        MinecraftServer server = minecraft.getSingleplayerServer();
        if (server == null) {
            return;  // Never edit a remote multiplayer server's world.
        }
        UUID playerId = minecraft.player.getUUID();
        if (playerId.equals(initializedPlayer) || playerId.equals(pendingPlayer)) {
            return;
        }
        pendingPlayer = playerId;
        server.execute(() -> {
            try {
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
                initializedPlayer = playerId;
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
            initializedPlayer = playerId;
            var player = server.getPlayerList().getPlayer(playerId);
            if (player != null && placed > 0) {
                // A new void mirror world otherwise spawns the player far
                // below the test island, into the void. Place him above it.
                player.teleportTo(0.5, 80.0, 0.5);
                player.resetFallDistance();
            }
            SkyCraft.LOG.info("BotwCraft block preview: {} starter blocks created", placed);
            } finally {
                pendingPlayer = null; // retry next tick if server/player was not ready
            }
        });
    }
}
