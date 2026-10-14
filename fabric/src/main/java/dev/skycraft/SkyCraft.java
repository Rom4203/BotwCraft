package dev.skycraft;

import dev.skycraft.combat.SkyCombat;
import net.fabricmc.api.ModInitializer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Standalone Fabric integration for BotwCraft. Register the binary protocol,
 * network payloads and optional data types, but NEVER alter a user's
 * Minecraft world, rules, player inventories, gamemode or save automatically.
 *
 * The old Skyrim mirror-world initialization was inappropriate for the
 * manual /botwcraft connect workflow.
 */
public final class SkyCraft implements ModInitializer {
    // Keep original protocol/mod ID and mirror preset compatibility.
    public static final String MOD_ID = "skycraft";
    public static final String WORLD_NAME = "SkyCraft";
    public static final Logger LOG = LoggerFactory.getLogger(MOD_ID);

    @Override
    public void onInitialize() {
        SkyCombat.init();
        dev.skycraft.net.SkyNet.init();
        dev.skycraft.world.SkyDig.init();
        LOG.info("BotwCraft: manual-only telemetry mode; no automatic worlds, items or gamerules");
    }
}
