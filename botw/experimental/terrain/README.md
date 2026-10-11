# BotwCraft — premières collisions par triangles (prototype indépendant)

**La version habituelle n'est pas modifiée** : `minecraft_mods/skycraft-0.1.2.jar`,
`bridge/*.exe`, la caméra FPS et les entrées restent celles du ZIP fonctionnel.
Le JAR facultatif est `experimental/terrain/skycraft-botw-terrain-EXPERIMENTAL.jar`.

## État réel

Le moteur `SkyCollider` / `TriCollider` de SkyCraft sait déjà gérer les
triangles, pentes et parois. Dans le code livré :

- `collision_stream.py` lit des triangles depuis un **OBJ de collision d'Hyrule
  réellement extrait**, réconcilie les coordonnées BOTW ↔ Minecraft au moment
  de la connexion, et remplit le ring COL_TRIS SkyCraft v11.
- `BotwCollisionGate` ne démarre le consumer que si le paramètre JVM
  `-Dbotwcraft.terrain=true` est défini ET si `/botwcraft connect` a été demandé.
  La collision locale n'est appliquée que lorsque des triangles existent et
  que le bridge est vivant. Un changement de session désactive l'expérience.
- La modification du JAR ne touche **qu'une seule référence de méthode** de
  l'ancien mixin de collision. Les classes Minecraft de rendu, caméra, entrées,
  commandes et FPS guard restent identiques au JAR stable.
- Le streamer **n'écrit jamais dans le processus Ryujinx**. Il ouvre seulement
  le mapping mémoire déjà créé par le bridge.

**Ce n'est pas encore l'extraction automatique du Havok de Zelda**. Aucun OBJ
réel d'Hyrule n'est inclus : les collisions BOTW ne fonctionnent donc pas avec
ce dossier seul. Les triangles d'un maillage visuel peuvent aussi différer des
collisions du jeu. Les coordonnées et l'échelle de l'OBJ doivent être celles du
monde BOTW, identiques à la télémétrie Link du bridge.

## Test facultatif (monde Minecraft jetable)

1. Sauvegarder le dossier mods Prism et le monde, puis remplacer le JAR
   stable par `skycraft-botw-terrain-EXPERIMENTAL.jar` **sans garder les deux**.
2. Ajouter aux arguments JVM Prism : `-Dbotwcraft.terrain=true`.
3. Démarrer le bridge + Zelda puis Minecraft ; faire `/botwcraft connect` et
   `/botwcraft inputs on`, rester immobile dans Zelda/Minecraft.
4. Avec **ton propre fichier OBJ de collision réellement aligné sur BOTW** :
   `python collision_stream.py "C:\chemin\terrain_collision.obj" --radius 48`
5. Si le streamer annonce `OK` puis que les triangles sont proches de Steve,
   l'injection locale de collisions sera activée. Elle ne change ni l'avatar
   Link ni la position de Steve par téléportation.
6. Pour revenir à la version stable : quitter les jeux, remettre le JAR stable
   et retirer `-Dbotwcraft.terrain=true`.

Lancer `python -m unittest -v test_collision_stream.py` pour les tests sans
Zelda. Pour vérifier le placement d'un OBJ **sans utiliser la mémoire Windows** :
`python collision_stream.py mon.obj --dry-run --botw-origin 0 0 0 --mc-origin 0 0 0`.

## Limitations connues

- Pas de géométrie native extraite automatiquement ; pas encore de collision
  BOTW prête à jouer en lançant seulement le ZIP.
- Les collisions de ces triangles sont **côté client**, pas encore validées
  avec les corrections du serveur intégré Minecraft.
- Pas de chargement dynamique de régions pendant la marche : le rayon fournit
  une zone fixe, à recharger manuellement après déplacement.
- Le premier point d'ancrage doit correspondre au bridge déjà actif, d'où
  l'obligation de rester immobile pendant l'import.
- Un nouveau monde ou bridge nécessite redémarrage Minecraft pour éviter de
  réutiliser des triangles anciens.

L'activation est opt-in pour éviter les crashs / chutes de FPS de la version
précédente. Aucun test réel sous Ryujinx Windows n'a été effectué ici.