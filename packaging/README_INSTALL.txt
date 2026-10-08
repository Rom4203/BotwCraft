BOTWCRAFT - EXPERIMENTAL DEVELOPMENT PACKAGE
=============================================

GAME: The Legend of Zelda: Breath of the Wild Switch 1.0.0
ARCHITECTURE: WiiXLaunch (Switch), Fabric Minecraft (Java 25), Windows bridge
SOURCE: https://github.com/Rom4203/BotwCraft/tree/botw-ryujinx-development

HONEST STATUS: NOT YET PLAYABLE AS MINECRAFT INSIDE BOTW.
This package can compile and contains both game mods plus the bridge, but
Minecraft->Link control, collision streaming, native blocks and rendering are
not yet connected to the game. Never mistake "build succeeded" for "game works".

CONTENTS
--------
ryujinx_mods/contents/01007ef00011e000/BotwCraft/exefs/subsdk9
ryujinx_mods/contents/01007ef00011e000/BotwCraft/romfs/WiiXLaunch/mods/botwcraft.wxlm
minecraft_mods/skycraft-*.jar
bridge/host_bridge.py
bridge/ryujinx_log_relay.py
bridge/control_bridge.py
bridge/launcher.py
START_BRIDGE.bat

BUILD FROM SOURCE
-----------------
Extract the source ZIP, run BUILD_AND_PACKAGE.bat.
Prerequisites:
- Git (auto-downloads WiiXLaunch source and submodules if absent)
- devkitPro/devkitA64 in D:\Bordel\Code\gameboy\devkit\devkitPro
- Python in D:\Program Files\Python\python.exe
- JDK 25 on PATH or JAVA_HOME
- Internet for Gradle/Fabric/Minecraft build dependencies
Compiled ZIP appears at dist\BotwCraft-experimental.zip.

PLAYTEST SAFETY
---------------
Ryujinx v1.3.3 was previously observed crashing with an unverified BOTW
player hook at relative address 0x873374. The build applies a source
guard against that hook. This is NOT a verified compatible game implementation.
Do not use your only Zelda saves or expect working Minecraft gameplay.

Only install in a separate test profile, after backing up Ryujinx data.
Copy ryujinx_mods/contents into the Ryujinx mods/contents directory.
Install Minecraft 26.3, Fabric Loader 0.19.5+, Fabric API matching 26.3
and Java 25; copy minecraft_mods/skycraft-*.jar into MC instance mods.
START_BRIDGE.bat runs the Windows-side host, log relay and keyboard/controller\nbridge together. For controller mode you also need the ViGEmBus driver and\nthe 'vgamepad' Python package, and must select the virtual Xbox 360 pad\nas Ryujinx Player 1. Without these, input can still go to a linked Minecraft\ninstance, but it cannot control BOTW. Minecraft does NOT start automatically.\nThe controller can follow measured Minecraft velocity only if a valid BOTW\nposition feed has first activated Minecraft's SkyCraft shared-memory link.\nThe old version-mismatched BOTW player hook is deliberately disabled, so\nthat feed is unavailable on BOTW Switch 1.0.0 until the hook is reverse-engineered.

UNDO
----
Close Ryujinx and MOVE the BotwCraft folder out of ALL Ryujinx mod paths.
Renaming BotwCraft_DESACTIVE does not disable it if still inside mods/contents.
Restore your earlier known-good copy and saves if needed.

THIRD PARTY
-----------
SkyCraft is by chasmlol (MIT); WiiXLaunch and other upstream components have
their own licenses. This package does not distribute Nintendo keys, firmware,
the XCI or decrypted Zelda binaries.
