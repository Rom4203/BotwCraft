package dev.skycraft.mixin;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import dev.skycraft.client.BotwCollisionGate;
import dev.skycraft.world.SkyCollision;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockCollisions;
import net.minecraft.world.level.CollisionGetter;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.EntityCollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;

/** Replace vanilla MC WORLD collisions, not player movement/inputs/camera.
 * Client: exact smooth triangles via EntityCollideMixin -> SkyCollider.
 * Integrated server: Rust-created subvoxel blocks prevent validation rubberband.
 */
@Mixin(BlockCollisions.class)
public abstract class BlockCollisionsMixin {
    @WrapOperation(method="computeNext", at=@At(value="INVOKE", target=
        "Lnet/minecraft/world/phys/shapes/CollisionContext;getCollisionShape(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/world/level/CollisionGetter;Lnet/minecraft/core/BlockPos;)Lnet/minecraft/world/phys/shapes/VoxelShape;"))
    private VoxelShape botwcraft$terrainOnly(
        CollisionContext context, BlockState state, CollisionGetter level,
        BlockPos pos, Operation<VoxelShape> original) {
        if (context instanceof EntityCollisionContext entityCtx
            && BotwCollisionGate.replacesVanilla(entityCtx.getEntity())) {
            if (entityCtx.getEntity() instanceof LocalPlayer) {
                return Shapes.empty(); // smooth triangle collision is applied AFTER vanilla's pass
            }
            // Integrated server receives only terrain voxel shapes.
            VoxelShape terrain = SkyCollision.shapeAt(pos);
            return terrain != null ? terrain : Shapes.empty();
        }
        VoxelShape blockShape = original.call(context, state, level, pos);
        // Preserve original SkyCraft behaviour for non-BOTW situations.
        if (state.isAir()) {
            VoxelShape wall = dev.skycraft.world.SkyDig.wallShape(level, pos);
            if (wall != null) blockShape = blockShape.isEmpty() ? wall : Shapes.or(blockShape, wall);
        }
        if (context instanceof EntityCollisionContext ec && SkyCollision.usesSmoothCollider(ec.getEntity())) {
            return blockShape;
        }
        VoxelShape sky = SkyCollision.shapeAt(pos);
        return sky == null ? blockShape : blockShape.isEmpty() ? sky : Shapes.or(blockShape, sky);
    }
}