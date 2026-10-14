package dev.skycraft.client.mixin;

import com.mojang.blaze3d.pipeline.RenderTarget;
import com.mojang.blaze3d.pipeline.TextureTarget;
import com.mojang.blaze3d.systems.RenderSystem;
import com.mojang.renderpearl.api.GpuFormat;
import com.mojang.renderpearl.api.textures.GpuTextureView;
import net.minecraft.client.renderer.state.level.CameraRenderState;
import net.minecraft.client.renderer.state.level.PlayerRenderState;
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
 * Minecraft's first-person hand is rendered as an independent transparent
 * layer into the SAME GPU buffer as the GUI, without disabling the real hand.
 * The Minecraft WORLD remains a separate render-ring mesh, and Zelda remains
 * the background. This retains Skyrim-equivalent dual game interaction.
 */
@Mixin(GameRenderer.class)
public abstract class BotwGuiLayerMixin {
    @Shadow @Final @Mutable private RenderTarget mainRenderTarget;
    @Shadow @Final private GuiRenderer guiRenderer;

    private RenderTarget botwcraft$previousTarget;
    private TextureTarget botwcraft$guiTarget;
    private boolean botwcraft$captureActive;
    private boolean botwcraft$captureFailed;
    private boolean botwcraft$handCaptureForThisFrame;
    private boolean botwcraft$replayingHand;

    // Mixin shadow resolves the PRIVATE vanilla Minecraft 26.3 method.
    // Never modify, replace or cancel the genuine on-screen Minecraft hand.
    @Shadow private void renderItemInHand(
        CameraRenderState cameraState, PlayerRenderState playerState,
        GpuTextureView depthTextureView) {}

    private boolean botwcraft$ensureOverlayTarget(RenderTarget original) {
        if (original == null || original.width <= 0 || original.height <= 0) return false;
        if (botwcraft$guiTarget == null ||
            botwcraft$guiTarget.width != original.width ||
            botwcraft$guiTarget.height != original.height) {
            if (botwcraft$guiTarget != null) botwcraft$guiTarget.destroyBuffers();
            botwcraft$guiTarget = new TextureTarget("botwcraft/hand-and-gui",
                original.width, original.height,
                GpuFormat.RGBA8_UNORM, GpuFormat.D32_FLOAT);
        }
        return true;
    }

    @Inject(method = "renderItemInHand", at = @At("RETURN"))
    private void botwcraft$copyFirstPersonHand(
        CameraRenderState cameraState, PlayerRenderState playerState,
        GpuTextureView depthTextureView, CallbackInfo ci) {
        if (botwcraft$replayingHand || botwcraft$captureFailed ||
            !BotwCraftSession.hudEnabled()) return;
        RenderTarget original = this.mainRenderTarget;
        try {
            if (!botwcraft$ensureOverlayTarget(original)) return;
            // Draw the FIRST PERSON HAND again ONLY into a transparent layer.
            // The original vanilla pass already rendered to Minecraft's own
            // framebuffer, so the Minecraft game itself is left intact.
            RenderSystem.getDevice().createCommandEncoder().clearColorAndDepthTextures(
                botwcraft$guiTarget.getColorTexture(),
                new Vector4f(0F,0F,0F,0F),
                botwcraft$guiTarget.getDepthTexture(),0.0);
            botwcraft$replayingHand=true;
            this.mainRenderTarget=botwcraft$guiTarget;
            this.renderItemInHand(cameraState,playerState,
                botwcraft$guiTarget.getDepthTextureView());
            botwcraft$handCaptureForThisFrame=true;
        }catch(RuntimeException ex){
            botwcraft$captureFailed=true;
            botwcraft$handCaptureForThisFrame=false;
            SkyCraft.LOG.error("BotwCraft isolated hand layer failed; preserving native Minecraft",ex);
        }finally{
            this.mainRenderTarget=original;
            botwcraft$replayingHand=false;
        }
    }

    @Inject(method = "render", at = @At(value = "INVOKE",
        target = "Lnet/minecraft/client/gui/render/GuiRenderer;render()V",
        shift = At.Shift.BEFORE))
    private void botwcraft$beforeGui(CallbackInfo ci) {
        if (!BotwCraftSession.hudEnabled() || botwcraft$captureFailed) return;
        RenderTarget original = this.mainRenderTarget;
        if (original == null || original.width <= 0 || original.height <= 0) return;
        try {
            if (!botwcraft$ensureOverlayTarget(original)) return;
            // KEEP the hand pixels drawn earlier in this frame, then add GUI
            // over them. With no hand, keep the target transparent.
            if (!botwcraft$handCaptureForThisFrame) {
                RenderSystem.getDevice().createCommandEncoder().clearColorAndDepthTextures(
                    botwcraft$guiTarget.getColorTexture(),
                    new Vector4f(0.0F, 0.0F, 0.0F, 0.0F),
                    botwcraft$guiTarget.getDepthTexture(), 0.0);
            }
            botwcraft$handCaptureForThisFrame=false;
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
