package dev.skycraft.client;

import dev.skycraft.link.SkyLink;
import java.lang.foreign.MemorySegment;
import java.lang.invoke.VarHandle;
import static java.lang.foreign.ValueLayout.*;

/**
 * Independent BotwCraft render camera. NOT Minecraft's player POV.
 *
 * SkyCraft-v11 extension in the unused header space 0x900..0x94f.
 * This is one coherent, seqlock-protected camera layer. Future verified
 * BOTW camera instrumentation can replace the pose without changing Rust.
 *
 * Current source: observed Zelda/Link pose. Link facing angles are NOT
 * guaranteed to equal the optical BOTW camera, so this is explicitly
 * tagged POSE_ESTIMATE rather than NATIVE_CAMERA.
 */
public final class BotwDedicatedCamera {
    public static final long BASE = 0x900L;
    public static final int MAGIC = 0x324D4342; // BCM2
    public static final int VERSION = 2;
    public static final int FLAG_VALID = 1;
    public static final int FLAG_LINK_POSE_ESTIMATE = 2;
    public static final int FLAG_NATIVE_CAMERA = 4;
    public static final int FLAG_MENU = 8;
    private BotwDedicatedCamera() {}

    public static void publish(SkyLink.SkyState link, double eyeHeight,
                               float verticalFov, boolean menuOpen) {
        MemorySegment s = SkyLink.segment();
        if (s == null || !SkyLink.active() || link == null ||
            !link.inGame() || link.loading() ||
            !Double.isFinite(link.x) || !Double.isFinite(link.y) ||
            !Double.isFinite(link.z) ||
            !Float.isFinite(link.yaw) || !Float.isFinite(link.pitch)) {
            clear();
            return;
        }
        long base=BASE;
        int seq=s.get(JAVA_INT,base+8);
        if ((seq&1)!=0) seq++;
        s.set(JAVA_INT,base+8,seq+1);
        VarHandle.storeStoreFence();
        s.set(JAVA_INT,base,MAGIC);
        s.set(JAVA_INT,base+4,VERSION);
        s.set(JAVA_INT,base+12,
            FLAG_VALID|FLAG_LINK_POSE_ESTIMATE|(menuOpen?FLAG_MENU:0));
        s.set(JAVA_DOUBLE,base+16,link.x);
        s.set(JAVA_DOUBLE,base+24,link.y+Math.max(0.0,Math.min(3.5,eyeHeight)));
        s.set(JAVA_DOUBLE,base+32,link.z);
        s.set(JAVA_FLOAT,base+40,link.yaw);
        s.set(JAVA_FLOAT,base+44,link.pitch);
        s.set(JAVA_FLOAT,base+48,Float.isFinite(verticalFov)
            ? Math.max(25.0F,Math.min(130.0F,verticalFov)):70.0F);
        s.set(JAVA_INT,base+52,link.worldId);
        VarHandle.storeStoreFence();
        s.set(JAVA_INT,base+8,seq+2);
    }

    public static void clear() {
        MemorySegment s=SkyLink.segment();
        if(s == null) return;
        long base=BASE;
        int seq=s.get(JAVA_INT,base+8);
        if((seq&1)!=0)seq++;
        s.set(JAVA_INT,base+8,seq+1);
        VarHandle.storeStoreFence();
        s.set(JAVA_INT,base+12,0);
        VarHandle.storeStoreFence();
        s.set(JAVA_INT,base+8,seq+2);
    }
}
