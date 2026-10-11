package org.spongepowered.asm.mixin;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

/**
 * Build-time only stub. Sponge Mixin's real @Mixin has CLASS retention.
 * Do not change to RUNTIME: MixinInfo only reads RuntimeInvisibleAnnotations.
 * Never package this stub into skycraft-0.1.2.jar.
 */
@Retention(RetentionPolicy.CLASS)
public @interface Mixin {
    Class<?>[] value();
}
