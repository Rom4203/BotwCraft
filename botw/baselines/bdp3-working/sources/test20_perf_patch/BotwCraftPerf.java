package dev.skycraft.client;

import dev.skycraft.client.render.WorldExporter;
import net.minecraft.client.Minecraft;

/**
 * Performance guard injected into the exact test20/V7 SkyClient binary.
 * Only two render invocations are redirected here. No changes to input,
 * Minecraft physics, commands, camera, network or player coordinates.
 */
public final class BotwCraftPerf {
    private static final boolean ENABLED = Boolean.parseBoolean(System.getProperty("botwcraft.fpsGuard", "true"));
    private static final int WORLD_MS = Math.max(100, Integer.getInteger("botwcraft.worldExportIntervalMs", 250));
    private static final int HUD_MS = Math.max(20, Integer.getInteger("botwcraft.hudCaptureIntervalMs", 40));
    private static final long WORLD_NS = WORLD_MS * 1_000_000L;
    private static final long HUD_NS = HUD_MS * 1_000_000L;
    private static long nextWorld, nextHud, lastFrame, suspendUntil;
    private static long worldCalls, hudCalls, skippedWorld, skippedHud, stalls;
    private static long lastReport;

    private BotwCraftPerf() {}

    /** Called at test20's original WorldExporter.frame call-site. */
    public static void frame(Minecraft minecraft, float partialTick) {
        if (!ENABLED) {
            WorldExporter.frame(minecraft, partialTick);
            return;
        }
        final long now = System.nanoTime();
        final long gap = lastFrame == 0 ? 0 : now - lastFrame;
        lastFrame = now;
        // If the GPU/render thread fell below ~4 FPS, actively shed ALL
        // optional world/HUD work for 2 seconds. An overloaded renderer
        // must be able to recover rather than piling up more copies.
        if (gap > 250_000_000L) {
            stalls++;
            suspendUntil = now + 2_000_000_000L;
        }
        if (now < suspendUntil || now < nextWorld) {
            skippedWorld++;
            return;
        }
        final long start = System.nanoTime();
        try {
            WorldExporter.frame(minecraft, partialTick);
        } finally {
            long elapsed = System.nanoTime() - start;
            worldCalls++;
            nextWorld = System.nanoTime() + (elapsed > 80_000_000L ? 12_000_000_000L : WORLD_NS);
            report(now, "world", elapsed);
        }
    }

    /** Called at test20's original FrameExporter.capture call-site. */
    public static void capture(Minecraft minecraft) {
        if (!ENABLED) {
            FrameExporter.capture(minecraft);
            return;
        }
        long now = System.nanoTime();
        if (now < suspendUntil || now < nextHud) {
            skippedHud++;
            return;
        }
        long start = System.nanoTime();
        try {
            FrameExporter.capture(minecraft);
        } finally {
            long elapsed = System.nanoTime() - start;
            hudCalls++;
            nextHud = System.nanoTime() + (elapsed > 80_000_000L ? 3_000_000_000L : HUD_NS);
            report(now, "hud", elapsed);
        }
    }

    private static void report(long now, String label, long elapsed) {
        if (elapsed > 80_000_000L) {
            System.err.println("[BotwCraft FPS Guard] slow " + label + " " + elapsed / 1_000_000L + "ms: backing off rendering work");
        }
        if (lastReport == 0 || now - lastReport >= 10_000_000_000L) {
            lastReport = now;
            System.err.println("[BotwCraft FPS Guard] world=" + worldCalls + " HUD=" + hudCalls +
                " skipped_world=" + skippedWorld + " skipped_HUD=" + skippedHud +
                " render_stalls=" + stalls);
        }
    }
}
