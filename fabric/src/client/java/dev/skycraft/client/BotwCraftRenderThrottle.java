package dev.skycraft.client;

import dev.skycraft.client.render.WorldExporter;
import net.minecraft.client.Minecraft;

/**
 * Pure rendering throttle for the ORIGINAL, user's known-good V8 JAR.
 *
 * The release process REPLACES ONLY TWO invokestatic call-sites in the
 * original V8 SkyClient.class and includes this helper. It must NOT rebuild
 * SkyClient, BotwCraftSession, input, protocol, player or Minecraft physics.
 */
public final class BotwCraftRenderThrottle {
    private static final boolean ENABLED =
        Boolean.parseBoolean(System.getProperty("botwcraft.fpsFix", "true"));
    private static final long WORLD_INTERVAL_NS = 100_000_000L; // 10Hz
    private static final long HUD_INTERVAL_NS = 33_333_333L; // 30Hz
    private static long lastWorldTimeNs;
    private static long lastHudTimeNs;
    private static long lastPerformanceLogNs;
    private static int suppressedWorld;
    private static int suppressedHud;
    private BotwCraftRenderThrottle() {}

    public static void worldFrame(Minecraft minecraft, float partialTick) {
        if (!ENABLED) {
            WorldExporter.frame(minecraft, partialTick);
            return;
        }
        long now = System.nanoTime();
        if (lastWorldTimeNs != 0L && now - lastWorldTimeNs < WORLD_INTERVAL_NS) {
            suppressedWorld++;
            return;
        }
        lastWorldTimeNs = now;
        WorldExporter.frame(minecraft, partialTick);
    }

    public static void hudFrame(Minecraft minecraft) {
        if (!ENABLED) {
            FrameExporter.capture(minecraft);
            return;
        }
        long now = System.nanoTime();
        if (lastHudTimeNs != 0L && now - lastHudTimeNs < HUD_INTERVAL_NS) {
            suppressedHud++;
            return;
        }
        lastHudTimeNs = now;
        FrameExporter.capture(minecraft);
    }
}
