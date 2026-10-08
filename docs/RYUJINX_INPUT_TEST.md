# BotwCraft input test 1 — Actual Ryujinx controller input (Windows)

**This is a usable controller smoke test in BOTW, not yet Minecraft physics or SkyCraft integration.**
It sends a virtual Xbox 360 gamepad input to Ryujinx; Link moves using BOTW's
normal mechanics and Ryujinx's own controls. No BOTW memory addresses, firmware,
ROMs or game keys are provided. It does not modify your game or save.

## Install

1. Install Python 3.10+ for Windows.
2. In PowerShell at the root of this repository, run:
   `py -m pip install vgamepad`
3. The `vgamepad` package requires the ViGEmBus virtual gamepad driver. If it
   is not present, follow vgamepad's official installation instructions:
   https://pypi.org/project/vgamepad/
4. Start Ryujinx, open **Options > Settings > Input**, set Player 1 to
   **Controller**, select the newly detected **Xbox 360 virtual controller**,
   then use Pro Controller layout. Save settings.
5. Start your personal BOTW installation in Ryujinx, and from a separate
   PowerShell window run:
   `py botw/controller_smoke_test.py`
6. Switch focus back to the game. Use WASD to move, Space to press gamepad A,
   Shift to press B, Ctrl to click the left stick. Press Esc to exit the test.

**Important:** BOTW's Switch action mappings depend on your game profile.
For example, the B button is often run. Jump is normally X, not A; this
smoke test deliberately maps Space to A to verify the virtual controller.
Rebind the gamepad action mapping as needed before interpreting controls.

The script polls keys globally, so it can work while Ryujinx is focused.
Close it before using keyboard normally; virtual pad inputs are reset
on normal exit. It cannot prevent conflicts with existing keyboard mappings:
disable Ryujinx Player 1 keyboard input and pick virtual controller instead.

## Run automated tests

`py -m unittest discover -s botw -p "test_*.py" -v`

## Next step

To drive this pad with Minecraft rather than keys, feed the Minecraft physics
output into an adapter and map its desired velocity to stick deflection.
**Input alone cannot give authentic Minecraft physics**: this requires reading
Link's state and intercepting BOTW locomotion and collision in the guest,
which varies by Ryujinx fork, game version, and target architecture.
