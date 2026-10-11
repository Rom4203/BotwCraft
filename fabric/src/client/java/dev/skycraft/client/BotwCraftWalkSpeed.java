package dev.skycraft.client;

import dev.skycraft.SkyCraft;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.minecraft.client.Minecraft;
import net.minecraft.resources.Identifier;
import net.minecraft.world.entity.ai.attributes.AttributeModifier;
import net.minecraft.world.entity.ai.attributes.Attributes;

/** Only the local host's authoritative MC player gets a temporary +6% walk boost. */
public final class BotwCraftWalkSpeed implements ClientModInitializer {
    private static final Identifier BOOST_ID = Identifier.fromNamespaceAndPath("skycraft", "botw_walk_6_percent");
    private static final AttributeModifier BOOST = new AttributeModifier(BOOST_ID, 0.06, AttributeModifier.Operation.ADD_MULTIPLIED_BASE);
    private int ticks;

    @Override
    public void onInitializeClient() {
        ClientTickEvents.END_CLIENT_TICK.register(this::tick);
    }

    private void tick(Minecraft mc) {
        if (++ticks % 10 != 0 || mc.player == null) return;
        var server = mc.getSingleplayerServer();
        if (server == null) return;
        var playerId = mc.player.getUUID();
        boolean enabled = SkyClient.linked();
        server.execute(() -> {
            var player = server.getPlayerList().getPlayer(playerId);
            if (player == null) return;
            var speed = player.getAttribute(Attributes.MOVEMENT_SPEED);
            if (speed == null) return;
            boolean present = speed.hasModifier(BOOST_ID);
            if (enabled && !present) {
                speed.addTransientModifier(BOOST);
                SkyCraft.LOG.info("BotwCraft: local Minecraft movement speed +6% (temporary)");
            } else if (!enabled && present) {
                speed.removeModifier(BOOST_ID);
                SkyCraft.LOG.info("BotwCraft: temporary movement speed modifier removed");
            }
        });
    }
}