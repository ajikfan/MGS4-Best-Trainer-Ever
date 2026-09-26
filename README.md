# MGS4 Trainer — V1.1

Trainer de recherche/édition mémoire live pour Metal Gear Solid 4
(portage PC Steam) : lit et **écrit** en direct la mémoire du process
`mgs4.exe` pendant une partie en cours, pour forcer n'importe quel champ
déjà identifié (armes, objets, stats, vie/stamina/stress/batterie Solid
Eye...) sans passer par le fichier de sauvegarde, et sert aussi d'outil
de recherche pour identifier les ID encore inconnus. Contrôle aussi la
vitesse du jeu (ralenti/accéléré) et la pause, voir plus bas.

Projet frère de [MGS4-SaveStats](https://github.com/ajikfan/MGS4-SaveStats)
(lecture seule des fichiers de sauvegarde) — deux outils distincts et
indépendants, publiés dans deux dépôts séparés pour ne pas les confondre.
Ce dépôt réutilise `mgs4save.py` (table des noms d'armes/objets) de
MGS4-SaveStats.

But : usage solo, à tes risques. Ce n'est pas un outil officiel.

## Prérequis

Windows (accès mémoire process via l'API kernel32/psapi, pas portable
Linux/Mac), et MGS4 lancé avec une partie chargée — le trainer se
connecte au process en cours, inutile s'il n'est pas lancé.

```
python live_trainer.py
```

Bouton "Aide" dans l'appli pour un résumé rapide (version compatible,
avertissements, mode avancé) et le changelog détaillé.

## Fonctionnement

Utilise la chaîne de pointeurs documentée par le dépôt externe
[zexk/bbtracker](https://github.com/zexk/bbtracker) (licence MIT) pour
localiser la structure de jeu en cours (`varbuf`) directement en mémoire,
sans scan. Un contrôle de cohérence (`sanity_check`, basé sur deux champs
toujours à 0 sur toute sauvegarde connue) s'exécute avant d'autoriser la
moindre écriture — si le jeu ne répond pas comme attendu, le trainer
refuse d'écrire plutôt que de risquer de corrompre la mémoire du jeu.

## Contrôle de la vitesse du jeu

Onglet "État de jeu" : curseur centré sur la vitesse normale (100%),
glissable vers la gauche pour ralentir (jusqu'à 10%) ou vers la droite
pour accélérer (jusqu'à 300%), plus une case "Pause" indépendante.

- **Pause** : gel complet du process (`NtSuspendProcess`), pas juste le
  menu pause du jeu — fiable, ne nécessite aucune injection.
- **Ralenti/accéléré** : nécessite d'injecter une petite DLL
  (`native/speedhack_x64.dll`, déjà compilée et fournie dans ce dépôt —
  aucun compilateur requis pour l'utiliser telle quelle) dans `mgs4.exe`,
  qui patche sa table d'imports pour tromper son horloge interne
  (`QueryPerformanceCounter`/`timeGetTime`) et lui faire croire que le
  temps s'écoule plus ou moins vite. Confirmé fonctionnel en jeu dans
  les deux sens (2026-09-26). L'injection ne se déclenche qu'au premier
  mouvement réel du curseur (pas à la connexion).

Modifier `native/speedhack.c` nécessite un compilateur C ciblant Windows
(testé avec `x86_64-w64-mingw32-gcc` via [MSYS2](https://www.msys2.org/),
mingw64) :

```
x86_64-w64-mingw32-gcc -shared -O2 -municode -o native/speedhack_x64.dll native/speedhack.c -lkernel32 -lwinmm
```

`mingw64/bin` doit être dans le PATH (sinon `cc1.exe` échoue silencieusement,
sans aucun message).

## Compatibilité / mises à jour du jeu

**À ne pas confondre : deux numérotations indépendantes.** La version du
trainer lui-même (voir le changelog dans le bouton "Aide") n'a aucun
rapport avec la version du jeu MGS4 mentionnée ci-dessous.

Les adresses mémoire utilisées dépendent de la version exacte de
`mgs4.exe` : une mise à jour Steam du jeu peut décaler toutes les
adresses. C'est déjà arrivé une fois (mise à jour du 24 septembre 2026) :
tout un bloc de données s'est décalé d'une quantité fixe, sans changer la
structure interne — corrigé via une seule constante (`MODULE_PATCH_SHIFT`
dans `live_trainer.py`, voir le
[notes.md](https://github.com/ajikfan/MGS4-SaveStats/blob/main/notes.md)
de MGS4-SaveStats pour la méthode de diagnostic complète).

**Trainer calibré et testé sur la version Steam actuelle de MGS4 :
1.4.1.** Si une future mise à jour du jeu casse la détection (le trainer
reste bloqué sur "Non connecté", ou le contrôle de cohérence échoue en
boucle après reconnexion), c'est probablement la même cause : il faudra
recalibrer ce décalage.

## ⚠️ Avertissements

- **Usage solo uniquement, à tes risques.** Ce n'est pas un outil
  officiel : il lit/écrit dans la mémoire d'un autre processus, ce qu'un
  antivirus peut signaler à tort.
- Le contrôle de vitesse va plus loin : il **injecte du code** dans
  `mgs4.exe` (technique de type "speedhack", proche de Cheat Engine) —
  plus susceptible d'être signalé par un antivirus/EDR qu'une simple
  lecture/écriture mémoire, et jamais testé au-delà d'un ralenti/
  accéléré ponctuel (pas de session longue durée).
- Certains champs restent en confiance basse ou pas encore testés
  individuellement (documentés au cas par cas dans le `notes.md` de
  MGS4-SaveStats) : une valeur peut se comporter différemment de ce qui
  est indiqué.
- Le "Mode avancé" masque par défaut certains objets internes/de debug
  dont le comportement en jeu est incertain ou dangereux (ex. un objet
  dont l'équipement fait planter le jeu, confirmé à plusieurs reprises) —
  à n'activer qu'en connaissance de cause.

## Empaqueter en .exe autonome

```
python -m PyInstaller --noconfirm MGS4Trainer.spec
```

Utiliser le fichier `.spec` fourni (pas une commande PyInstaller "à la
main") est important : il embarque l'icône et le dossier `assets/`
(nécessaire à l'icône affichée dans la fenêtre au runtime). Le résultat
est dans `dist/MGS4Trainer/` (dossier complet à copier, pas juste
l'exe).

L'exe n'est pas signé : Windows SmartScreen affichera un avertissement
au premier lancement ("Windows a protégé votre PC") — c'est normal pour
un outil indépendant non signé, il suffit de cliquer "Informations
complémentaires" → "Exécuter quand même".
