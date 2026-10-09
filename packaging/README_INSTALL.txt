BOTWCRAFT — PREMIER TEST NATIF (SWITCH BOTW 1.5.0)
=====================================================

CETTE ARCHIVE EST UNE COMPILATION ARM64 REELLE, MAIS LA JOUABILITE
COMPLETE MINECRAFT DANS HYRULE N'A PAS ENCORE ETE DEMONTREE.

VERSION CIBLE : BOTW Switch 1.5.0 exclusivement.
Emulateur : Ryujinx sur Windows.
Minecraft : Java 26.3, Fabric, Java 25, via Prism Launcher.

CE QUI EST INCLUS
-----------------
- subsdk9 : vrai module WiiXLaunch compilé pour Switch ARM64.
- botwcraft.wxlm : vrai module WiiXLaunch BOTW, avec rendu de mesh natif.
- skycraft-*.jar : Minecraft Fabric basé sur SkyCraft original.
- Le pont Windows, le relais des coordonnées Link et des maillages.
- Un installateur Windows avec sauvegarde des anciens fichiers BotwCraft.

CORRECTION CRITIQUE :
Le .wxlm doit être copié dans la SD virtuelle Ryujinx :
  sdcard/WiiXLaunch/mods/01007EF00011E000/botwcraft.wxlm
Il NE DOIT PAS se trouver uniquement dans romfs du mod Ryujinx !
Le module subsdk9 va, lui, dans :
  mods/contents/01007ef00011e000/BotwCraft/exefs/subsdk9

COMMENT FAIRE LE PREMIER TEST
-----------------------------
1. Fermer Ryujinx, Minecraft et Prism. Sauvegarder les parties Zelda.
   Retirer les anciens modules BotwCraft des emplacements actifs
   (pas seulement les renommer).
2. Extraire le ZIP et exécuter INSTALL_NATIVE_TEST.bat.
   S'il ne trouve pas Prism ou les données Ryujinx, choisir leur dossier
   dans la fenêtre affichée. L'installateur prépare BotwCraftNative dans
   Prism et installe Fabric API (téléchargé et vérifié).
3. Exécuter START_BRIDGE.bat. Il démarre le pont Windows et Minecraft
   BotwCraftNative via Prism Launcher.
4. Lancer BOTW Switch 1.5.0 dans Ryujinx. Charger une partie.
5. Si Minecraft ne crée pas son monde, ou si Zelda plante, arrêter le
   test : c'est une information sur l'intégration native, pas une raison
   de forcer la version 1.0.0.

OBJECTIF DU PREMIER TEST
------------------------
- Zelda arrive-t-il au jeu sans planter ?
- Le journal Ryujinx indique-t-il le chargement de botwcraft.wxlm ?
- L'enregistrement NVN est-il confirmé ?
- Des messages BotwCraft:NATIVE_POSITION_MILLI apparaissent-ils lorsque
  Link se déplace ? Si oui, la liaison Link -> Minecraft est active.
- Minecraft peut-il ouvrir automatiquement son monde via SkyCraft ?

ATTENTION : Le bon affichage des blocs, la camera, les textures,
les collisions et la physique complete ne sont pas encore verifies en jeu.
La compilation reussie ne suffit PAS pour declarer BotwCraft jouable.

INSTALLATION SANS RISQUE SUR LES AUTRES MODS
-------------------------------------------
L'installateur ne modifie pas les sauvegardes et sauvegarde les anciens
fichiers du mod nomme BotwCraft. Il ne retire pas les mods tiers.
Pour annuler : arreter les jeux et deplacer le dossier BotwCraft hors du
repertoire mods/contents, puis supprimer ou deplacer le botwcraft.wxlm de
la SD virtuelle Ryujinx. Ne pas les laisser dans un autre dossier actif
de mods/contents.

DEPENDANCES
-----------
- Ryujinx installe et votre propre jeu BOTW mis a jour en 1.5.0.
- Prism Launcher avec compte Minecraft valide.
- Python 3.10+ (le script essaie egalement py -3).
- Connexion internet pour Fabric API au premier demarrage.
- Aucun fichier Nintendo, cle, firmware, XCI ou ROM n'est fourni ici.

SOURCE : https://github.com/Rom4203/BotwCraft
LICENCES : voir LICENSE et THIRD-PARTY-NOTICES.md
