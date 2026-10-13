package dev.skycraft.client.mixin;

import com.mojang.blaze3d.pipeline.RenderTarget;
import com.mojang.blaze3d.pipeline.TextureTarget;
import com.mojang.blaze3d.systems.RenderSystem;
import com.mojang.renderpearl.api.GpuFormat;
import dev.skycraft.SkyCraft;
import dev.skycraft.client.BotwCraftSession;
import dev.skycraft.client.FrameExporter;
import net.minecraft.client.gui.render.GuiRenderer;
import net.minecraft.client.renderer.GameRenderer;
import org.joml.Vector4f;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Mutable;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * Minecraft 26.3: GameRenderer.render() draws level/hand first,
 * then invokes GuiRenderer.render() and finally GuiRenderer.endFrame().
 *
 * Export ONLY pixels produced by GuiRenderer to the v11 overlay buffer.
 * NEVER crop/mask/key an already composed world image.
 *
 * The HUD is rendered into an isolated transparent GPU target, captured,
 * and then GuiRenderer renders the SAME retained GUI state onto the normal
 * Minecraft target. The standard game window remains unchanged.
 *
 * This intentionally doesn't export the hand or 3D level. They are distinct
 * render stages and must remain independent in the compositor.
 */
@Mixin(GameRenderer.class)
public abstract class BotwGuiLayerMixin {
    @Shadow @Final @Mutable private RenderTarget mainRenderTarget;
    @Shadow @Final private GuiRenderer guiRenderer;

    private RenderTarget botwcraft$previousTarget;
    private TextureTarget botwcraft$guiTarget;
    private boolean botwcraft$captureActive;
    private boolean botwcraft$captureFailed;

    @Inject(method = "render", at = @At(value = "INVOKE",
        target = "Lnet/minecraft/client/gui/render/GuiRenderer;render()V",
        shift = At.Shift.BEFORE))
    private void botwcraft$beforeGui(CallbackInfo ci) {
        if (!BotwCraftSession.hudEnabled() || botwcraft$captureFailed) return;
        RenderTarget original = this.mainRenderTarget;
        if (original == null || original.width <= 0 || original.height <= 0) return;
        try {
            if (botwcraft$guiTarget == null ||
                botwcraft$guiTarget.width != original.width ||
                botwcraft$guiTarget.height != original.height) {
                if (botwcraft$guiTarget != null) botwcraft$guiTarget.destroyBuffers();
                botwcraft$guiTarget = new TextureTarget("botwcraft/gui-only",
                    original.width, original.height,
                    GpuFormat.RGBA8_UNORM, GpuFormat.D32_FLOAT);
            }
            RenderSystem.getDevice().createCommandEncoder().clearColorAndDepthTextures(
                botwcraft$guiTarget.getColorTexture(),
                new Vector4f(0.0F, 0.0F, 0.0F, 0.0F),
                botwcraft$guiTarget.getDepthTexture(), 0.0);
            botwcraft$previousTarget = original;
            this.mainRenderTarget = botwcraft$guiTarget;
            botwcraft$captureActive = true;
        } catch (RuntimeException ex) {
            // Fail closed: leave Minecraft's original render target alone.
            this.mainRenderTarget = original;
            botwcraft$previousTarget = null;
            botwcraft$captureActive = false;
            botwcraft$captureFailed = true;
            SkyCraft.LOG.error("BotwCraft: transparent GUI target failed; leaving Minecraft intact", ex);
        }
    }

    @Inject(method = "render", at = @At(value = "INVOKE",
        target = "Lnet/minecraft/client/gui/render/GuiRenderer;render()V",
        shift = At.Shift.AFTER))
    private void botwcraft$afterGui(CallbackInfo ci) {
        if (!botwcraft$captureActive) return;
        try {
            // First draw was to a separate transparent target: this is
            // genuinely GUI-only, with correct chat, black text and alpha.
            FrameExporter.capture(botwcraft$guiTarget);
        } finally {
            // Always restore normal Minecraft rendering, even on capture error.
            this.mainRenderTarget = botwcraft$previousTarget;
            botwcraft$previousTarget = null;
            botwcraft$captureActive = false;
        }
        try {
            // GuiRenderer.endFrame() has NOT yet been called: its draw state
            // is still available. Render the retained state onto Minecraft's
            // normal target so gameplay/chat/inventory remain functional.
            this.guiRenderer.render();
        } catch (RuntimeException ex) {
            botwcraft$captureFailed = true;
            SkyCraft.LOG.error("BotwCraft: second GUI draw unsupported; disabling separated GUI", ex);
        }
    }
}
