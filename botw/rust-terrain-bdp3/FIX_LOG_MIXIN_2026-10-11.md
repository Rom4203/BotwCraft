# Correction du crash Fabric au demarrage (11 octobre 2026)

Symptome dans le log Prism Launcher / Minecraft 26.3 Fabric 0.19.5:

```text
InvalidMixinException: The mixin 'dev.skycraft.mixin.BlockCollisionsMixin' is missing an @Mixin annotation
```

La classe compilée contenait `@Mixin` mais dans **RuntimeVisibleAnnotations**.
Le vrai Mixin/Sponge declare `@Mixin` avec `RetentionPolicy.CLASS`, qui produit
**RuntimeInvisibleAnnotations**. Un faux stub `RetentionPolicy.RUNTIME` a fait
compiler l'annotation au mauvais endroit. Le code source `@Mixin(...)` n'etait
pas absent : c'etait le bytecode du JAR qui etait incorrect.

Deuxieme erreur evitee : le JAR corrige doit inclure
`dev/skycraft/client/BotwCollisionGate$Probe.class` en plus de
`BotwCollisionGate.class`. La premiere archive avait oublie cette classe
interne necessaire au cache de proximity des triangles.

Correction sur le JAR BDP3 original :
1. Recompiler `BlockCollisionsMixin.java` avec le vrai Mixin dans le
   classpath, ou un stub local avec `@Retention(RetentionPolicy.CLASS)`.
2. Conserver `WrapOperation` dans `RuntimeVisibleAnnotations` et
   `@Mixin` dans `RuntimeInvisibleAnnotations`.
3. Copier **toutes** les classes generees du gate, y compris ses `$*.class`.
4. Ne pas changer `skycraft.mixins.json`, les classes d'input/FPS, les
   executables Rust, ni la camera BDP3.
5. Verifier le resultat avec `tools/VERIFY_MIXIN_JAR.ps1 -Jar skycraft-0.1.2.jar`.

JAR genere dans le chat: `skycraft-0.1.2.jar`
SHA-256: `b5f43917fe62cb31f35ca08621ce042df02f1782cbeace9fb5654c7321812292`.
Seules deux modifications entre l'archive defectueuse et le JAR fixe :
le bytecode de `BlockCollisionsMixin.class`, et l'ajout de
`BotwCollisionGate$Probe.class`.

Ce correctif supprime l'erreur structurelle visible dans le log.
Le lancement effectif de Minecraft/Ryujinx n'a pas ete verifie sur le PC.
La collision Hyrule complete exige toujours une source valide de maillages
ou de hauteurs et une validation en jeu.
