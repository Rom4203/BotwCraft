package dev.skycraft.client;

import dev.skycraft.SkyCraft;
import dev.skycraft.client.render.WorldExporter;
import dev.skycraft.link.Proto;
import dev.skycraft.link.SkyLink;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.phys.Vec3;

/**
 * BotwCraft telemetry-only Minecraft client.
 *
 * We intentionally do NOT enable SkyCraft's Skyrim takeover mixins. Link's
 * coordinates are observations, NOT safe Minecraft destinations: Hyrule's
 * collision world has not been imported into MC. Player control, the MC
 * renderer, worlds and saves always remain under Minecraft's authority.
 */
public final class SkyClient {
    private static final SkyLink.SkyState observedLink = new SkyLink.SkyState();
    private static final SkyLink.McState mcState = new SkyLink.McState();
    private static boolean telemetryReady;
    private static int exportErrors;
    private static long frameCounter;

    private SkyClient() {}

    /** Used by Skyrim-only mixins. Never take over native Minecraft. */
    public static boolean linked() {
        return false;
    }

    /** Leave SDL keyboard/mouse capture to Minecraft, not Skyrim. */
    public static boolean tookOver() {
        return false;
    }

    public static SkyLink.SkyState sky() {
        return observedLink;
    }

    /** Read Link telemetry only when the user explicitly requested it. */
    public static void beginFrame() {
        if (!BotwCraftSession.requested()) {
            telemetryReady = false;
            return;
        }
        SkyLink.poll();
        telemetryReady = SkyLink.active()
            && SkyLink.readSkyState(observedLink)
            && observedLink.inGame();
    }

    /** No auto world, teleport, camera, menu or collision changes. */
    public static void clientTick(Minecraft minecraft) {
    }

    /** Export Minecraft geometry independently of whether Zelda has loaded. */
    public static void afterRender() {
        if (!BotwCraftSession.requested() || !SkyLink.transportOpen()) {
            return;
        }
        Minecraft minecraft = Minecraft.getInstance();
        LocalPlayer player = minecraft.player;
        if (player == null || minecraft.level == null) {
            return;
        }
        float partial = minecraft.getDeltaTracker().getGameTimeDeltaPartialTick(false);
        Vec3 feet = player.getPosition(partial);

        mcState.flags = Proto.MC_IN_WORLD;
        mcState.x = feet.x;
        mcState.y = feet.y;
        mcState.z = feet.z;
        mcState.yaw = player.getYRot();
        mcState.pitch = player.getXRot();
        mcState.frameCounter = ++frameCounter;
        mcState.teleportAck = 0;
        mcState.fov = 70.0F;
        SkyLink.writeMcState(mcState);

        // The native host bridge consumes SkyCraft v11 RenderRing packets.
        // It cannot draw them in Zelda until WiiXLaunch's SD reader works.
        try {
            WorldExporter.frame(minecraft, partial);
        } catch (RuntimeException ex) {
            if (exportErrors++ < 5) {
                SkyCraft.LOG.error("BotwCraft: render-ring export failed", ex);
            }
        }
    }

    /** Never tie Minecraft FPS to Zelda's game/render thread. */
    public static void paceFrame() {
    }
}
