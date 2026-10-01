# MGS4 Trainer — V2.0

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

## Munitions infinies / Pas de rechargement

Onglet "État de jeu" : deux cases indépendantes.

- **Munitions infinies** : fige la vraie réserve actuelle de chaque
  arme au moment où tu coches (pas un nombre fixe artificiel) et la
  réécrit en continu.
- **Pas de rechargement** : garde le chargeur de chaque arme à sa vraie
  capacité max en continu (distinct de la réserve) — suit
  automatiquement l'arme équipée, pas besoin de recocher en changeant
  d'arme.

Les deux utilisent un cycle de réassertion dédié à 50ms (plus rapide
que le rafraîchissement général de l'appli) pour suivre les armes qui
tirent vite sans dépletion visible.

## Un coup, un mort / Non létal

Onglet "État de jeu" : case "Un coup, un mort" + sélecteur Létal/Non
létal. **Technique différente de tout le reste du trainer** : un vrai
patch de code (pas juste une redirection de fonction comme le contrôle
de vitesse) — localise et redirige l'instruction du jeu qui applique
les dégâts, porté du script Cheat Engine communautaire (`MGS4.CT`,
section "aob Damage", auteur RMLSNK) plutôt que découvert de zéro.
Jamais appliqué au joueur lui-même (vérifie l'équipe de la cible avant
d'agir).

- **Létal** : tue en un coup n'importe quel ennemi touché.
- **Non létal** : les dégâts normaux ne sont plus appliqués du tout.

Confirmé fonctionnel en jeu sur les ennemis standards (2026-09-26). Peut
ne pas fonctionner si le motif attendu n'est pas trouvé dans cette
version du jeu (aucun crash dans ce cas, juste sans effet).

**Boss : mécanisme différent.** Les boss ne passent pas par l'instruction
de dégâts patchée ci-dessus (confirmé par diagnostic en jeu) - le
trainer détecte automatiquement le boss actif (Laughing Octopus/Beauty,
Raging Raven, Crying Wolf confirmés à ce jour, chacun avec ses propres
offsets mémoire) et force sa vie/stamina à 0 dès qu'un vrai coup est
détecté, sans configuration manuelle. Ce forçage est délibérément
**synchronisé sur un vrai coup** (jamais en continu) : le jeu peut
ignorer une valeur forcée hors contexte et recalculer la sienne, et un
forçage en boucle sans coup réel a déjà fait planter le jeu (2026-09-27).
Metal Gear RAY (mécha, mécanisme non trouvé) et une phase précise de
Laughing Octopus (nécessite des tirs létaux pour la déloger d'une
cachette) restent des cas non fonctionnels connus.

**Gecko (robots) : hook séparé.** Les Gecko ne passent ni par
l'instruction des ennemis humains ni par celle des boss - un troisième
patch de code dédié (porté du script CE "aob Damage Gecko") gère leur
cas, branché sur le même bouton/flag "Un coup, un mort" (pas de variante
non létale, ça n'a pas de sens pour un robot).

Modifier `native/speedhack.c` nécessite un compilateur C ciblant Windows
(testé avec `x86_64-w64-mingw32-gcc` via [MSYS2](https://www.msys2.org/),
mingw64) :

```
x86_64-w64-mingw32-gcc -shared -O2 -municode -o native/speedhack_x64.dll native/speedhack.c -lkernel32 -lwinmm
```

`mingw64/bin` doit être dans le PATH (sinon `cc1.exe` échoue silencieusement,
sans aucun message).

## Téléportation

Onglet "Téléportation" : enregistre la position actuelle de Snake
(X/Y/Z) sous un nom, puis téléporte instantanément vers un point
enregistré (double-clic ou bouton dédié). Les 3 axes sont aussi
éditables manuellement (saisie directe + bouton "Téléporter ici"), et
la liste de points peut être exportée/importée en fichier JSON.

Repose sur un hook de lecture seule capturant le pointeur de Snake via
une routine générique de calcul de distance entre deux acteurs (motif
"aob Coordinates" du CE table communautaire) - **confirmé fonctionnel
par téléportation réelle en jeu** (2026-09-27). Coordonnées absolues du
niveau (pas relatives à l'orientation du joueur) : l'axe Y semble être
la hauteur (le jeu peut annuler une position invalide, ex. sous le
sol), X/Z le plan horizontal.

⚠️ Expérimental : rien ne garantit qu'un point enregistré dans un acte
reste une position valide dans un autre acte/niveau (jamais testé) -
risque de tomber hors du niveau chargé. Les points sont sauvegardés
dans `teleport_points.json` (à côté de l'exe/du script, pas versionné
dans ce dépôt - propre à chaque partie).

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

## Crédits et sources

Ce trainer s'appuie sur le travail d'autres personnes, en plus de nos
propres recherches :

- **[zexk/bbtracker](https://github.com/zexk/bbtracker)** (licence MIT) :
  chaîne de pointeurs vers la structure de jeu, décrite plus haut.
- **Table Cheat Engine communautaire `MGS4.CT`, par RMLSNK** (version
  7.7 du fichier utilisé ici). Cette table n'est **pas redistribuée**
  dans ce dépôt (aucune licence n'y est indiquée) ; le trainer réutilise
  ses motifs d'octets (AOB), ses offsets de structure et sa logique,
  réécrits en C et en Python :
  - "Un coup, un mort" / "Non létal" : script "aob Damage" et sa logique
    "Remove Lethal" ;
  - suivi des boss : scripts "Bosses 2" et "Bosses Laughing Octopus".
    L'offset de stamina qu'elle documente (`+31C+4`) s'est révélé décalé
    de 4 octets en test : le bon champ est `+0x31C`, corrigé par nos
    propres scans ;
  - Téléportation : script "aob Coordinates" (position X/Y/Z à
    `+0x10`/`+0x14`/`+0x18`) ;
  - plusieurs formules d'adresses (table des objets, statistiques, état
    d'alerte) ont été repérées en lisant ses scripts (détail dans les
    commentaires du code), puis **vérifiées en jeu par nos propres
    tests** avant d'être utilisées.

Merci à leurs auteurs. Si tu es l'auteur d'une de ces sources et que tu
souhaites une correction ou un retrait, ouvre une issue.

## ⚠️ Avertissements

- **Usage solo uniquement, à tes risques.** Ce n'est pas un outil
  officiel : il lit/écrit dans la mémoire d'un autre processus, ce qu'un
  antivirus peut signaler à tort.
- Le contrôle de vitesse va plus loin : il **injecte du code** dans
  `mgs4.exe` (technique de type "speedhack", proche de Cheat Engine) —
  plus susceptible d'être signalé par un antivirus/EDR qu'une simple
  lecture/écriture mémoire, et jamais testé au-delà d'un ralenti/
  accéléré ponctuel (pas de session longue durée).
- "Un coup, un mort"/"Non létal" va encore plus loin : ce n'est plus
  une redirection de fonction mais un **vrai patch d'instructions** du
  jeu. Protégé contre une application au joueur lui-même, mais reste la
  technique la plus invasive du trainer — expérimental, effet réel pas
  encore confirmé visuellement en jeu.
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
