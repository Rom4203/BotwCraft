package dev.skycraft.client;

import dev.skycraft.link.SkyLink;
import java.util.Locale;

/** User-owned opt-in shared-memory diagnostics; never takes control of Minecraft. */
public final class BotwCraftSession {
    private static volatile boolean requested;
    // Keep Minecraft input focus; native HUD transport is explicitly opt-in.
    private static volatile boolean hudEnabled;
    private static volatile boolean compositorInputs;

    private BotwCraftSession() {}

    public static boolean requested() {
        return requested;
    }

    public static boolean hudEnabled() {
        return hudEnabled && requested;
    }

    public static String setHudEnabled(boolean enabled) {
        if (enabled && !requested) {
            return "BotwCraft: utilise d'abord /botwcraft connect.";
        }
        hudEnabled = enabled;
        return enabled
            ? "BotwCraft: capture du vrai HUD Minecraft activee (SkyCraft v11). "
                + "Minecraft garde clavier et souris. Le rendu du HUD dans Zelda "
                + "requiert encore son recepteur natif."
            : "BotwCraft: capture du HUD desactivee; rendu Minecraft normal.";
    }

    public static String hudStatus() {
        return "BotwCraft: capture HUD " + (hudEnabled() ? "active" : "inactive")
            + ". Entrées clavier/souris dans Minecraft; Zelda reste l'affichage cible.";
    }

    public static boolean compositorInputs() {
        return requested && compositorInputs;
    }

    public static String setCompositorInputs(boolean enabled) {
        if (enabled && !requested) {
            return "BotwCraft: /botwcraft connect necessaire avant les controles.";
        }
        compositorInputs = enabled;
        if (!enabled) {
            InputBridge.releaseAll();
        }
        return enabled
            ? "BotwCraft: INPUTS COMPOSITOR actifs. Le clavier/souris de la "
                + "fenetre Rust controle Minecraft via SkyCraft v11."
            : "BotwCraft: entrees Rust desactivees, touches relachees.";
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
        hudEnabled = false;
        compositorInputs = false;
        InputBridge.releaseAll();
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
