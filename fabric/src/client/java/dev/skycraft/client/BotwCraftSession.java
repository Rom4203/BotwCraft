package dev.skycraft.client;

import dev.skycraft.link.SkyLink;

/**
 * Explicit opt-in for the existing SkyCraft v11 shared-memory transport.
 * Neither Prism nor Minecraft is launched, and no world is opened until the
 * user issues /botwcraft connect AND the bridge has authentic game telemetry.
 */
public final class BotwCraftSession {
    private static volatile boolean requested;

    private BotwCraftSession() {}

    public static boolean requested() {
        return requested;
    }

    public static String connect() {
        if (BlockPreview.enabled()) {
            return "BotwCraft: ancien mode preview actif. Desactive experimentalBlocks/retire "
                + "botwcraft.preview puis redemarre Minecraft. Aucun lien Zelda etabli.";
        }
        requested = true;
        return "BotwCraft: connexion demandee. Attente de la position reelle de Link "
            + "sur le protocole SkyCraft v11 (pas de monde force).";
    }

    public static String disconnect() {
        requested = false;
        SkyLink.stopHeartbeat();
        return "BotwCraft: deconnecte. Minecraft reste ouvert, aucun monde modifie.";
    }

    public static String status() {
        if (!requested) {
            return "BotwCraft: deconnecte. Tape /botwcraft connect pour autoriser le lien.";
        }
        if (!SkyLink.active()) {
            return "BotwCraft: en attente d'une vraie position Link. "
                + "Verifier le bridge et la compatibilite BOTW (1.6.0 non supportee).";
        }
        return "BotwCraft: protocole SkyCraft v11 actif; telemetrie de jeu recue.";
    }
}
