package dev.skycraft.client.mixin;

import dev.skycraft.client.SkyClient;
import net.minecraft.client.renderer.GameRenderer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * World blocks must be section meshes anchored in Hyrule, NEVER the first-person
 * held-item camera overlay. Keep Minecraft hotbar/inventory and player input,
 * but omit hand and held block ONLY while BotwCraft is fusing the two games.
 * Minecraft 26.3 GameRenderer.renderItemInHand has three arguments.
 */
@Mixin(GameRenderer.class)
public abstract class BotwNoHandsMixin {
    @Inject(method = "renderItemInHand(Lnet/minecraft/client/renderer/state/level/CameraRenderState;Lnet/minecraft/client/renderer/state/level/PlayerRenderState;Lcom/mojang/renderpearl/api/textures/GpuTextureView;)V",
            at = @At("HEAD"), cancellable = true)
    private void botwcraft$skipFirstPersonHeldItem(CallbackInfo ci) {
        if (SkyClient.hudCaptureActive()) ci.cancel();
    }
}
