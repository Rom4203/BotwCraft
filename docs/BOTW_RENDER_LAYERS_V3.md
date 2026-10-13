# BotwCraft v3: distinct render layers (Minecraft 26.3)

## Video regression (2026-10-13)

Previous JAR captured GameRenderer.mainRenderTarget after the whole frame and
tried to erase Minecraft's sky/terrain with a HUD footprint. Results:
- rectangular blue sky / empty squares over Hyrule;
- chat overlay and dark text rendered incorrectly;
- blocks positioned with MC POV rather than a separately authored camera;
- Rust WGPU block overlay can cover the existing compositor's HUD.

All screen-space masking / RGB color-keying is forbidden in the v3 design.

## Real render passes

A. Zelda Ryujinx frame: belongs to the Windows compositor.
B. Minecraft world blocks: real REN_SECTION mesh / REN_ATLAS GPU rendering,
   NO window screenshot and no Minecraft world framebuffer capture.
C. First person hand and items: an independent 3D pass; NOT exported yet.
D. Chat / hotbar / HUD / menus: GuiRenderer draws into a brand new transparent
   TextureTarget. Actual GPU RGBA capture from THAT render target is shared.
   The same retained GuiRenderer state is then drawn a second time to MC's
   main target so the vanilla Minecraft window still looks normal.

No (A,B,C,D) pass is obtained by slicing rectangular coordinates out of a
different pass. The GUI target is cleared to (0,0,0,0); a black text pixel
is a real black UI pixel, not a signal to remove it.

## Distinct Java-authored camera

Shared v11 unused header offset 0x900: BCM2 protocol v2:
offset 0: magic u32 0x324D4342
offset 4: version u32 = 2
offset 8: seq u32, odd while writing
offset 12: flags bit0=valid bit1=Link facing estimate bit2=verified
          native-camera bit3=GUI open
offset 16/24/32: eye X/Y/Z float64
offset 40/44/48: yaw/pitch/effective FOV float32
offset 52: world id u32

BotwDedicatedCamera publishes from measured Zelda Link pose, not from
Minecraft.mainCamera(). Critically **Link facing yaw/pitch is not guaranteed to
equal Zelda's optical camera yaw/pitch.** Only a future verified BOTW
camera hook can mark the 0x4 flag and guarantee alignment. The WGPU reader
never falls back to MC player POV.

## Unresolved: required before "same as SkyCraft"

- The Windows compositor's real Rust source was not in either of the ZIPs
  provided. Existing compositor EXE remains unchanged.
- Until the Rust compositor is rebuilt to render passes A -> B -> C -> D in
  ONE GPU frame, the separate WGPU block window can still appear over the HUD.
- Zelda-native view/projection and depth are unavailable: cliff/house occlusion
  remains incorrect.
- Hand + equipped item layer is not yet exported separately.
- The GuiRenderer second render pass is compiled on Java 25 but must be
  in-game tested with inventories/chat/widgets and resource reloads.
- No modification to the Ryujinx game binaries is done here.

## Important test sequence

Run isolated Java / Rust builds first, then validate Minecraft:
1. Spawn Minecraft 26.3 with only new Fabric JAR and Fabric API.
2. Verify the unconnected Minecraft world and menus render normally.
3. Connect to the existing Rust bridge, compare original MC window before
   and after enabling the GUI capture. It should remain identical.
4. Inspect GUI-only RGBA in the overlay shared-memory slots, ensuring no
   visible MC sky, blocks or scenery; chat scrollback and inventory should
   retain text, shadows and alpha.
5. Only then run the WGPU block overlay and inspect camera yaw/pitch.
6. If 3D blocks cover HUD or Zelda scenery, leave PR draft and DO NOT ship
   as a final playable SkyCraft-equivalent release.

References: Minecraft 26.3 GameRenderer.render() calls
GuiRenderer.render() and GuiRenderer.endFrame() after world rendering.
