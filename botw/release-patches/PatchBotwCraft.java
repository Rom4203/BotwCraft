import java.nio.file.*;
import jdk.internal.org.objectweb.asm.*;

/**
 * Patches exactly the two client classes of BotwCraft's working 2026-10-13 JAR.
 * Does not modify the Rust movement bridge, guest modules, or collisions.
 *
 * Compile with:
 * javac --add-exports java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED PatchBotwCraft.java
 * Run with:
 * java --add-exports java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED PatchBotwCraft \
 *   SkyClient.class BotwCraftPerf.class output-dir
 */
public final class PatchBotwCraft {
    private static byte[] patch(byte[] bytes, boolean sky) {
        byte[] input=bytes.clone();
        int major=((input[6]&255)<<8)|(input[7]&255);
        input[6]=0;
        input[7]=65; // Permit JDK21's embedded ASM to parse Java25 class bytecode.
        ClassReader reader=new ClassReader(input);
        ClassWriter writer=new ClassWriter(reader,ClassWriter.COMPUTE_MAXS);
        reader.accept(new ClassVisitor(Opcodes.ASM9,writer) {
            @Override public MethodVisitor visitMethod(int access,String name,String desc,String signature,String[] exceptions) {
                MethodVisitor base=super.visitMethod(access,name,desc,signature,exceptions);
                if(sky && !name.equals("afterRender"))return base;
                if(!sky && !name.equals("<clinit>") && !name.equals("capture"))return base;
                return new MethodVisitor(Opcodes.ASM9,base) {
                    @Override public void visitMethodInsn(int op,String owner,String method,String d,boolean itf) {
                        if(sky && name.equals("afterRender") && op==Opcodes.INVOKESTATIC
                            && owner.equals("dev/skycraft/client/BotwCraftPerf") && method.equals("frame")) {
                            super.visitInsn(Opcodes.POP2); // No redundant world mesh export.
                            return;
                        }
                        super.visitMethodInsn(op,owner,method,d,itf);
                    }
                    @Override public void visitLdcInsn(Object v) {
                        if(sky && name.equals("afterRender") && v instanceof Float && ((Float)v)==70.0f) {
                            super.visitVarInsn(Opcodes.ALOAD,0);
                            super.visitFieldInsn(Opcodes.GETFIELD,"net/minecraft/client/Minecraft","gameRenderer","Lnet/minecraft/client/renderer/GameRenderer;");
                            super.visitMethodInsn(Opcodes.INVOKEVIRTUAL,"net/minecraft/client/renderer/GameRenderer","mainCamera","()Lnet/minecraft/client/Camera;",false);
                            super.visitMethodInsn(Opcodes.INVOKEVIRTUAL,"net/minecraft/client/Camera","getFov","()F",false);
                            return;
                        }
                        if(!sky && name.equals("capture") && v instanceof Long && ((Long)v)==3000000000L) {
                            super.visitLdcInsn(100000000L); // 100ms backoff instead of 3s.
                            return;
                        }
                        super.visitLdcInsn(v);
                    }
                    @Override public void visitIntInsn(int op,int n) {
                        if(!sky && name.equals("<clinit>") && op==Opcodes.BIPUSH) {
                            if(n==20)n=12; // Minimum configurable capture period.
                            else if(n==40)n=16; // Default capture period, ~60 FPS.
                        }
                        super.visitIntInsn(op,n);
                    }
                };
            }
        },0);
        byte[] result=writer.toByteArray();
        result[6]=(byte)(major>>8);
        result[7]=(byte)major;
        return result;
    }
    public static void main(String[] args) throws Exception {
        if(args.length!=3)throw new IllegalArgumentException("SkyClient.class BotwCraftPerf.class output-dir");
        Path out=Path.of(args[2]);Files.createDirectories(out);
        Files.write(out.resolve("SkyClient.class"),patch(Files.readAllBytes(Path.of(args[0])),true));
        Files.write(out.resolve("BotwCraftPerf.class"),patch(Files.readAllBytes(Path.of(args[1])),false));
    }
}
