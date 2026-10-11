param([Parameter(Mandatory=$true)][string]$Jar)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $Jar)) { throw "JAR not found: $Jar" }
$names = @(& jar tf $Jar)
if ($LASTEXITCODE -ne 0) { throw "Could not open Minecraft JAR" }
if ($names -notcontains 'dev/skycraft/client/BotwCollisionGate.class') {
  throw "Missing BotwCollisionGate.class"
}
if ($names -notcontains 'dev/skycraft/client/BotwCollisionGate$Probe.class') {
  throw "Missing inner BotwCollisionGate\$Probe.class: will crash on collision startup"
}
$disasm = (& javap -v -p -cp $Jar dev.skycraft.mixin.BlockCollisionsMixin) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "Missing BlockCollisionsMixin.class" }
if ($disasm -notmatch '(?s)SourceFile:.*RuntimeInvisibleAnnotations:\s*\d+:.*org\.spongepowered\.asm\.mixin\.Mixin') {
  throw "Invalid @Mixin: it MUST be in RuntimeInvisibleAnnotations (RetentionPolicy.CLASS)"
}
if ($disasm -notmatch 'com\.llamalad7\.mixinextras\.injector\.wrapoperation\.WrapOperation') {
  throw "WrapOperation annotation missing"
}
Write-Host '[OK] @Mixin retention CLASS, WrapOperation present, BotwCollisionGate + Probe included.' -ForegroundColor Green
