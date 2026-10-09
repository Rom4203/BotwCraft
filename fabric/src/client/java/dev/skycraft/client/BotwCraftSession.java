package dev.skycraft.client;

import dev.skycraft.link.SkyLink;
import java.util.Locale;

/** User-owned opt-in shared-memory diagnostics; never takes control of Minecraft. */
public final class BotwCraftSession {
    private static volatile boolean requested;

    private BotwCraftSession() {}

    public static boolean requested() {
        return requested;
    }

    public static String connect() {
        if (BlockPreview.enabled()) {
            return "BotwCraft: ancien mode preview actif (experimentalBlocks=true ou "
                + "botwcraft.preview). Retire le mode preview et redemarre Minecraft.";
        }
        requested = true;
        return "BotwCraft: connexion manuelle demandee. Mode lecture seule : "
            + "aucun TP, aucune modification du monde ou de la souris. "
            + "Tape /botwcraft status.";
    }

    public static String disconnect() {
        requested = false;
        SkyLink.stopHeartbeat();
        return "BotwCraft: liaison desactivee, Minecraft reste normal.";
    }

    public static String status() {
        if (!requested) {
            return "BotwCraft: desactive. Utilise /botwcraft connect.";
        }
        if (SkyLink.segment() == null) {
            return "BotwCraft: bridge memoire introuvable. "
                + "Verifie START_BRIDGE.bat. Minecraft reste intact.";
        }
        if (!SkyLink.active()) {
            return "BotwCraft: bridge detecte mais pas de position Link recente. "
                + "Verifie le relais Ryujinx. Aucun TP applique.";
        }
        SkyLink.SkyState snapshot = new SkyLink.SkyState();
        if (!SkyLink.readSkyState(snapshot) || !snapshot.inGame()) {
            return "BotwCraft: transport actif, position Link indisponible "
                + "(jeu en chargement ou trame incomplete).";
        }
        return String.format(Locale.ROOT,
            "BotwCraft: Zelda connecte, Link X=%.3f Y=%.3f Z=%.3f "
                + "(lecture seule, Minecraft reste a sa position).",
            snapshot.x, snapshot.y, snapshot.z);
    }
}
