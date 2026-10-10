BOTWCRAFT — TEST NATIF 1.5.0 (UNE SEULE INSTALLATION)
=====================================================

CE PAQUET EST UN AJOUT AUX FICHIERS DU DERNIER BOTWCRAFT FONCTIONNEL.
Il n'inclut pas le jeu BOTW, Ryujinx, ni les binaires du jeu Nintendo.

1. Fermer Ryujinx et l'ancien START_BRIDGE.
2. Extraire ce ZIP À CÔTÉ du dossier BotwCraft existant, en fusionnant
   les deux dossiers BotwCraft. Ne pas effacer les anciens fichiers.
3. Lancer BotwCraft/START_BOTWCRAFT_NATIVE_TEST.bat.
4. Le lanceur installe bwc_pose.wxlm dans le profil Ryujinx actuellement
   configuré, puis démarre le bridge Rust et la troisième fenêtre Rust.
5. Ouvrir BOTW Switch 1.5.0 dans Ryujinx et Minecraft.
6. Dans Minecraft, utiliser /botwcraft connect puis /botwcraft inputs on.
   Le focus et la souris restent dans la fenêtre indépendante Rust.
7. La fenêtre de jeu Rust doit suivre les mouvements de Steve dans Hyrule.
   S'il n'y a aucun déplacement, NE PAS multiplier les tests : transmettre
   BotwCraft/logs/botwcraft.log une fois.

DIAGNOSTIC NATIF:
  [RUST_LINK] guest ACK=...          = communication avec le module confirmée
  [RUST_LINK] state=5 method=3       = setMtx virtuel appelé pour Link
  [RUST_LINK] state=7 camera=0x...   = Link + caméra appelés côté BOTW
  [BOTW_NATIVE] FIRST_PERSON...      = caméra Zelda recalculée depuis Steve
  [BOTW_NATIVE] Link model scale...  = Link masqué visuellement

ATTENTION : LA COMPILATION ET LES TESTS UNITAIRES NE VALIDENT PAS LE JEU.
L'appel de la fonction virtuelle setMtx, l'activation du hook camera et
l'absence de crash nécessitent un test réel avec BOTW 1.5.0 sous Ryujinx.
Ne pas commencer avec une sauvegarde importante : faire une sauvegarde
séparée avant le premier test.

Ce paquet conserve l'ancien mod botwcraft.wxlm et subsdk9, n'utilise
aucune manette virtuelle et ne remplace pas le compositor Rust.
