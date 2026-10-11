package dev.skycraft.mixin;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import dev.skycraft.client.BotwCollisionGate;
import dev.skycraft.world.SkyCollision;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockCollisions;
import net.minecraft.world.level.CollisionGetter;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.EntityCollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.injection.At;

/**
 * Inject native BOTW terrain as actual 1/8-block Minecraft VoxelShapes.
 * BOTH sides see the identical collision boxes in BlockCollisions.computeNext:
 * player movement, steps, gravity and onGround use unmodified vanilla physics.
 */
@Mixin(BlockCollisions.class)
public abstract class BlockCollisionsMixin {
    @Shadow @Final private BlockPos.MutableBlockPos pos;
    @Shadow @Final private CollisionContext context;

    // Minecraft skips air BEFORE asking for its collision shape; BOTW
    // virtual blocks occupy air, so let known SkyCraft shapes past this gate.
    @WrapOperation(method="computeNext", at=@At(value="INVOKE",
        target="Lnet/minecraft/world/level/block/state/BlockState;isAir()Z"), require=0)
    private boolean botwcraft$virtualAirHasShape(BlockState state, Operation<Boolean> original) {
        if (context instanceof EntityCollisionContext ec
            && BotwCollisionGate.replacesVanilla(ec.getEntity())
            && SkyCollision.shapeAt(pos) != null) {
            return false;
        }
        return original.call(state);
    }

    @WrapOperation(method="computeNext", at=@At(value="INVOKE", target=
        "Lnet/minecraft/world/phys/shapes/CollisionContext;getCollisionShape(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/world/level/CollisionGetter;Lnet/minecraft/core/BlockPos;)Lnet/minecraft/world/phys/shapes/VoxelShape;"))
    private VoxelShape botwcraft$terrainOnly(
        CollisionContext context, BlockState state, CollisionGetter level,
        BlockPos pos, Operation<VoxelShape> original) {
        if (context instanceof EntityCollisionContext entityCtx
            && BotwCollisionGate.replacesVanilla(entityCtx.getEntity())) {
            // No client triangle pass and no server-only voxels: the SAME
            // collision shape is returned for Steve on both threads.
            VoxelShape terrain = SkyCollision.shapeAt(pos);
            return terrain != null ? terrain : Shapes.empty();
        }
        VoxelShape result = original.call(context, state, level, pos);
        // Non-BOTW world retains original SkyCraft behavior.
        if (state.isAir()) {
            VoxelShape wall = dev.skycraft.world.SkyDig.wallShape(level, pos);
            if (wall != null) result = result.isEmpty() ? wall : Shapes.or(result, wall);
        }
        if (context instanceof EntityCollisionContext ec && SkyCollision.usesSmoothCollider(ec.getEntity())) {
            return result;
        }
        VoxelShape sky = SkyCollision.shapeAt(pos);
        return sky == null ? result : result.isEmpty() ? sky : Shapes.or(result, sky);
    }
}