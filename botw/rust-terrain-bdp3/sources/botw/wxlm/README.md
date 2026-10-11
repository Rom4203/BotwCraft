# BotwCraft NX150 guest: WiiXLaunch + Havok raycasts

Compiled from `mod.cpp` with WiiXLaunch SDK using devkitPro AArch64.
Keeps BDP3 actor placement, camera projection and model invisibility.
Adds asynchronous terrain Havok raycasts (3x3, 2.75 game units apart)
to a 56-byte mailbox extension at offset 432, which Rust reads over GDB.
The original mailbox fields/BDP3 fast slots at offsets <=432 are unchanged.

This integrates with Fabric SkyCraft's shared-memory v11 collision ring.
Successful Switch build does not validate runtime Havok symbols or game
stability: backup saves and check the logs before testing world collisions.