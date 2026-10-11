package dev.skycraft.client;

import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.blaze3d.vertex.VertexConsumer;
import dev.skycraft.world.SkyCollision;
import dev.skycraft.world.SkyTri;
import java.util.ArrayList;
import java.util.List;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.rendering.v1.level.LevelRenderContext;
import net.fabricmc.fabric.api.client.rendering.v1.level.LevelRenderEvents;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.rendertype.RenderTypes;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

/**
 * Optional debug-only collision wireframe. Rendered ONLY inside the Minecraft 3D level,
 * never in the Ryujinx framebuffer or compositor. F1 hides the HUD and shows these
 * triangles; showing the HUD disables the overlay.
 *
 * This is a read-only consumer of SkyCollision's real COL_TRIS stream. It does not
 * mutate movement, send packets, sample Havok or synthesize fake walkable surfaces.
 */
public final class CollisionWireframe implements ClientModInitializer {
    private static final int MAX_TRIANGLES = 1600;
    private static final int WALKABLE = 0xff28f7bd;
    private static final int STEEP = 0xffffb347;
    private static final double RANGE = 32.0;

    @Override
    public void onInitializeClient() {
        LevelRenderEvents.BEFORE_TRANSLUCENT_TERRAIN.register(CollisionWireframe::render);
    }

    private static void render(LevelRenderContext context) {
        Minecraft minecraft = Minecraft.getInstance();
        // F1: hideGui=true. Never draw over the normal on-screen HUD.
        if (!minecraft.options.hideGui || minecraft.level == null || minecraft.player == null) {
            return;
        }

        Vec3 camera = context.levelState().cameraRenderState.pos;
        AABB visible = new AABB(
            camera.x - RANGE, camera.y - 18, camera.z - RANGE,
            camera.x + RANGE, camera.y + 18, camera.z + RANGE
        );
        List<SkyTri> nearby = new ArrayList<>();
        SkyCollision.trianglesNear(visible, nearby);
        if (nearby.isEmpty()) {
            return;
        }
        int count = Math.min(MAX_TRIANGLES, nearby.size());
        // Snapshot primitives now: rendering submissions are executed later, and the
        // collision consumer thread can update the source map in the meantime.
        float[] coords = new float[count * 9];
        int[] colors = new int[count];
        for (int i = 0; i < count; ++i) {
            SkyTri t = nearby.get(i);
            int o = i * 9;
            coords[o] = (float) (t.ax - camera.x);
            coords[o + 1] = (float) (t.ay - camera.y);
            coords[o + 2] = (float) (t.az - camera.z);
            coords[o + 3] = (float) (t.bx - camera.x);
            coords[o + 4] = (float) (t.by - camera.y);
            coords[o + 5] = (float) (t.bz - camera.z);
            coords[o + 6] = (float) (t.cx - camera.x);
            coords[o + 7] = (float) (t.cy - camera.y);
            coords[o + 8] = (float) (t.cz - camera.z);
            colors[i] = t.walkable ? WALKABLE : STEEP;
        }

        PoseStack stack = context.poseStack();
        stack.pushPose();
        context.submitNodeCollector().submitCustomGeometry(stack, RenderTypes.lines(), (pose, buffer) -> {
            for (int i = 0; i < count; ++i) {
                int p = i * 9;
                int color = colors[i];
                line(pose, buffer, coords, p, p + 3, color);
                line(pose, buffer, coords, p + 3, p + 6, color);
                line(pose, buffer, coords, p + 6, p, color);
            }
        });
        stack.popPose();
    }

    private static void line(PoseStack.Pose pose, VertexConsumer buffer, float[] v, int a, int b, int color) {
        buffer.addVertex(pose, v[a], v[a + 1], v[a + 2]).setColor(color).setNormal(pose, 0, 1, 0);
        buffer.addVertex(pose, v[b], v[b + 1], v[b + 2]).setColor(color).setNormal(pose, 0, 1, 0);
    }
}