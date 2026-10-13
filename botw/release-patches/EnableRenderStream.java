import java.nio.file.*;
import jdk.internal.org.objectweb.asm.*;

/**
 * Bytecode patch for the tested user's BotwCraft JAR.
 * Reenable WorldExporter.frame(Minecraft,float), which publishes the genuine
 * SkyCraft REN_SECTION triangles and REN_ATLAS textures. The old compositor
 * experiment intentionally replaced this call by POP2.
 *
 * Remove the old full-frame capture to let BotwGuiLayerMixin export an isolated
 * transparent HUD separately, on its original FrameExporter.capture(target).
 *
 * Run with JDK 21+ internal ASM export flags and pass source and destination
 * SkyClient.class. Only patches the precise old client shape: fail closed.
 */
public final class EnableRenderStream {
 public static void main(String[] args) throws Exception {
  if(args.length!=2)throw new IllegalArgumentException("source/SkyClient.class target/SkyClient.class");
  byte[] input=Files.readAllBytes(Path.of(args[0]));
  int originalVersion=((input[6]&255)<<8)|(input[7]&255);
  input[6]=0;input[7]=65;
  ClassReader reader=new ClassReader(input);
  ClassWriter writer=new ClassWriter(reader,ClassWriter.COMPUTE_MAXS);
  int[] counts={0,0};
  reader.accept(new ClassVisitor(Opcodes.ASM9,writer) {
   @Override public MethodVisitor visitMethod(int access,String name,String desc,String signature,String[] exceptions){
    MethodVisitor destination=super.visitMethod(access,name,desc,signature,exceptions);
    if(!name.equals("afterRender"))return destination;
    return new MethodVisitor(Opcodes.ASM9,destination) {
     @Override public void visitInsn(int op){
      if(op==Opcodes.POP2){
       super.visitMethodInsn(Opcodes.INVOKESTATIC,
         "dev/skycraft/client/render/WorldExporter","frame",
         "(Lnet/minecraft/client/Minecraft;F)V",false);
       counts[0]++;
      }else super.visitInsn(op);
     }
     @Override public void visitMethodInsn(int op,String owner,String method,String d,boolean itf){
      if(op==Opcodes.INVOKESTATIC && owner.equals("dev/skycraft/client/BotwCraftPerf")
         && method.equals("capture") && d.equals("(Lnet/minecraft/client/Minecraft;)V")){
       super.visitInsn(Opcodes.POP);counts[1]++;
      }else super.visitMethodInsn(op,owner,method,d,itf);
     }
    };
   }
  },0);
  if(counts[0]!=1||counts[1]!=1)
    throw new IllegalStateException("Unsupported BotwCraft JAR revision; refusing modifications");
  byte[] output=writer.toByteArray();
  output[6]=(byte)(originalVersion>>8);output[7]=(byte)originalVersion;
  Path target=Path.of(args[1]);
  Files.createDirectories(target.getParent());
  Files.write(target,output);
  System.out.println("SkyCraft world exporter restored; original HUD screenshot removed");
 }
}
