#!/usr/bin/env python3
"""Refuse mixing Skyrim-only SkyCraft sources with a BotwCraft release JAR."""
import json
import sys
import zipfile
from pathlib import Path

def validate_jar(path: Path):
    with zipfile.ZipFile(path) as z:
        members=set(z.namelist())
        assert "skycraft.client.mixins.json" in members, "Missing Minecraft client mixin manifest"
        mixins=json.loads(z.read("skycraft.client.mixins.json"))
        for name in mixins["client"]:
            full="dev/skycraft/client/mixin/"+name.replace(".","/")+".class"
            assert full in members, "Mixin registered but missing from JAR: "+full
        assert "BotwNoHandsMixin" not in mixins["client"], "DO NOT remove vanilla hand"
        assert "dev/skycraft/client/mixin/BotwGuiLayerMixin.class" in members, "Missing separate GUI+hand renderer"
        assert "dev/skycraft/client/render/WorldExporter.class" in members, "Missing Minecraft true geometry exporter"
        assert "dev/skycraft/client/BotwCraftSession.class" in members, "Skyrim-only SkyCraft JAR, not BotwCraft"
        print(f"OK BotwCraft Java JAR, {len(mixins['client'])} registered real mixin classes, hand not disabled")
if __name__=="__main__":
    paths=[Path(p) for p in sys.argv[1:]]
    if not paths:
        paths=[p for p in Path("fabric/build/libs").glob("*.jar") if "-sources" not in p.name and "-dev" not in p.name]
    if not paths:
        sys.exit("No candidate compiled BotwCraft JAR")
    for path in paths:
        validate_jar(path)
