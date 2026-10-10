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

    /** Capture the ACTUAL Minecraft GUI in SkyCraft's original GPU staging.
     * The 3D terrain render is skipped during this explicit test, while
     * Minecraft retains its own keyboard/mouse and normal game simulation.
     */
    public static boolean hudCaptureActive() {
        return BotwCraftSession.hudEnabled() && SkyLink.transportOpen();
    }

    /** Used by Skyrim-only mixins. Never take over native Minecraft. */
    public static boolean linked() {
        return false;
    }

    /** SkyCraft virtual input only during explicit 3rd-window control.
     * Prevent SDL mouse grab in the background Minecraft window, while
     * routing compositor keys through the actual Fabric input handlers.
     */
    public static boolean tookOver() {
        return BotwCraftSession.compositorInputs();
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
        if (BotwCraftSession.compositorInputs() && SkyLink.transportOpen()) {
            // Actual Minecraft keyboard/mouse handlers, running on its client
            // thread. No fake SendInput to an unfocused background window.
            InputBridge.drain(Minecraft.getInstance());
        }
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

        // High bits are BotwCraft-only, unused by SkyCraft original:
        // 0x10000 = world gameplay without GUI; 0x20000 = Rust input opt-in.
        // The Rust app only grabs the pointer if BOTH are true.
        mcState.flags = Proto.MC_IN_WORLD
            | (minecraft.gui.screen() == null ? 0x10000 : 0)
            | (BotwCraftSession.compositorInputs() ? 0x20000 : 0);
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

        // Original SkyCraft GPU asynchronous HUD readback and RGBA triple
        // buffer publication. No fabricated HUD, and no input interception.
        // Do not export the full Minecraft scene into the HUD texture:
        // LevelRendererMixin explicitly skips it ONLY in this HUD mode.
        if (hudCaptureActive()) {
            FrameExporter.capture(minecraft);
        }
    }

    /** Never tie Minecraft FPS to Zelda's game/render thread. */
    public static void paceFrame() {
    }
}
