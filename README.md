# MGS4 Trainer — V2.3

Trainer de recherche/édition mémoire live pour Metal Gear Solid 4
(portage PC Steam) : lit et **écrit** en direct la mémoire du process
`mgs4.exe` pendant une partie en cours, pour forcer n'importe quel champ
déjà identifié (armes, objets, stats, vie/stamina/stress/batterie Solid
Eye...) sans passer par le fichier de sauvegarde, et sert aussi d'outil
de recherche pour identifier les ID encore inconnus. Contrôle aussi la
vitesse du jeu (ralenti/accéléré) et la pause, et permet de changer
d'arme, de tenue, de visage, de gilet ou de motif OctoCamo en direct,
sans passer par les menus du jeu, de rendre Snake intouchable ou
invisible, et de faire tomber n'importe quel ennemi ou boss en un coup
(voir plus bas).

Projet frère de [MGS4-SaveStats](https://github.com/ajikfan/MGS4-SaveStats)
(lecture seule des fichiers de sauvegarde) — deux outils distincts et
indépendants, publiés dans deux dépôts séparés pour ne pas les confondre.
Ce dépôt réutilise `mgs4save.py` (table des noms d'armes/objets) de
MGS4-SaveStats.

But : usage solo, à tes risques. Ce n'est pas un outil officiel.

## Prérequis

Windows (accès mémoire process via l'API kernel32/psapi, pas portable
Linux/Mac), et MGS4 lancé avec une partie chargée — le trainer se
connecte au process en cours, inutile s'il n'est pas lancé. Sans le jeu,
les onglets restent consultables (contenu grisé) pour parcourir
l'interface et lire les infobulles.

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

## Guide des onglets

### Barre du haut (toujours visible)

- **Statut** : connecté au jeu ou non (le trainer s'accroche tout seul
  à `mgs4.exe` dès qu'une partie est chargée).
- **Mode avancé (valeurs brutes)** : affiche les colonnes "Valeur brute"
  et "Définir (brut)" dans les tableaux, et les objets internes masqués
  par défaut (certains font planter le jeu : à n'utiliser qu'en
  connaissance de cause).
- **Rafraîchir maintenant** / **(Re)connecter** : relit tout tout de
  suite / se raccroche au jeu (après un redémarrage du jeu par exemple).
- **Aide** : résumé, version compatible et historique des versions.
- **Langue** : français ou anglais (le trainer redémarre).
- **Points Drebin** : solde actuel et total des ventes, avec un champ
  et un bouton OK pour chacun.

### Stats

Les statistiques de la partie, telles qu'enregistrées dans la
sauvegarde, rangées par thème : **Combat** (ennemis tués, tirs dans la
tête...), **Infiltration** (alertes, ennemis endormis...),
**Mouvement**, **Objets**, **Flashbacks**, **Temps** (en heures,
minutes, secondes). Chaque valeur se modifie directement.

### État de jeu

L'onglet des réglages en direct, en plusieurs groupes :

- **Vitesse du jeu** : curseur de 10 % à 300 % (100 % au centre), case
  **Pause** (gel complet du jeu), liste **Difficulté** (Liquid à The
  Boss ; change la difficulté enregistrée à la prochaine sauvegarde).
- **Alerte** :
  - **État réel** : l'état d'alerte en cours (Normal, Alerte, Évasion,
    Prudence) ;
  - **Forcer** : impose un état d'alerte au choix, ou "Automatique" pour
    laisser le jeu décider ;
  - **Pas d'alerte** : l'alerte générale ne se déclenche jamais, quelle
    qu'en soit la cause (vue, bruit, corps trouvé, lasers des mini
    Gekko...). Les ennemis peuvent encore réagir individuellement.
- **Armes et combat** :
  - **Munitions infinies** : munitions infinies d'origine du jeu sur
    toutes les armes (symbole infini au HUD) ;
  - **Pas de rechargement** : le chargeur ne se vide plus ;
  - **Un coup, un mort**, avec le choix **Létal / Non létal** : en
    Létal, tout ennemi touché tombe en un coup (soldats, Gekko, mini
    Gekko, tanks, hélicoptères, véhicules, objets destructibles, et
    tous les boss, voir plus bas) ; en Non létal, les dégâts normaux ne
    sont plus appliqués ;
  - **Rail Gun / Solar Gun toujours chargés** : tir chargé à fond dès
    l'appui sur la gâchette.
- **Snake** :
  - **Intouchable** : aucun impact n'a d'effet sur Snake (ni dégâts, ni
    projection, ni assommage) ;
  - **Invisible** : les soldats et les Gekko ne le voient plus, même
    debout devant eux (à combiner avec "Pas d'alerte" pour les lasers
    des mini Gekko).
- **Jauges** : Santé, Stamina, **Grip** (suspendu à un rebord),
  **Oxygène** (sous l'eau), Stress, batterie du Solid Eye, Santé de
  Metal Gear REX. Pour chacune : un curseur en pourcentage pour la
  régler, et une case **Verrouiller** qui la maintient à ce niveau
  (Santé verrouillée à 100 % = vie infinie, Grip à 100 % = grip
  infini...).

### Armes

Toutes les armes du jeu, rangées par catégorie (pistolets, fusils
d'assaut, fusils de précision, explosifs, accessoires...). Pour chaque
arme :

- **État** : Non possédée / Verrouillée / Utilisable ;
- **Munitions** : la réserve, modifiable ;
- **Équiper** : met l'arme en main immédiatement, sans menu (voir
  "Équiper en direct" plus bas). Actif seulement pour les armes
  possédées.

Un filtre par nom permet de retrouver une arme vite.

### Objets

Les objets (rations, médicaments, Solid Eye, iPod, objets spéciaux...),
avec leur état (Verrouillé / Obtenu) et, pour les consommables, la
quantité. La batterie du Solid Eye s'affiche sur sa ligne.

### OctoCamo

- **Équipé** : le motif OctoCamo porté en ce moment.
- **FaceCamo** : les visages, avec leur état et un bouton **Équiper**.
- **Gilet** : les gilets, avec un bouton **Équiper**.
- **Octocamo** : les 21 motifs du menu camouflage, avec un bouton
  **Équiper** (y compris les motifs spéciaux). Les motifs donnés
  d'office peuvent être masqués du menu du jeu.
- **Motifs mémorisés** : les 10 emplacements de motifs capturés sur une
  surface puis enregistrés, avec leur nom quand il est connu (Béton,
  Tuile, Main...), un bouton **Équiper**, et la possibilité d'oublier
  un motif.

Équiper un motif marche aussi en pleine cinématique.

### Tenues

Les tenues et déguisements (Moyen-Orient, Amérique du Sud, Europe de
l'Est, costume de Snake, Altaïr...), avec leur état et un bouton
**Équiper**. Les déguisements d'un acte fonctionnent dans les autres
actes.

### Statuettes, Chansons, Non classés

Les statuettes et les chansons de l'iPod à débloquer ou à retirer, et
les objets encore non identifiés (onglet de recherche).

### Téléportation

- **Lieu actuel** : l'acte et la zone en cours (noms officiels du jeu).
- **Position actuelle** de Snake, et **Enregistrer ici...** pour la
  garder sous un nom.
- **X / Y / Z** : saisie manuelle, **Actualiser depuis le jeu**, et
  **Téléporter ici**.
- **Liste des points** de la zone actuelle (nom, zone, coordonnées) :
  double-clic ou **Téléporter vers le point sélectionné**, **Supprimer
  le point sélectionné**, **Rattacher à la zone actuelle** (pour un
  point sans zone).
- **Afficher les points de toutes les zones**.
- **Exporter** / **Importer** les points en fichier JSON.

Des points sont fournis par défaut au premier lancement.

## Détails techniques

Les sections suivantes expliquent comment chaque fonction marche, ses
limites, et ce qui a été vérifié en jeu.

### Contrôle de la vitesse du jeu

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
  les deux sens (2026-09-26). Depuis la V2.2, la DLL est injectée dès
  que le trainer s'accroche au jeu (elle démarre à vitesse normale, sans
  effet tant qu'aucun réglage n'est activé) : les boutons "Équiper" et
  les autres patchs sont prêts sans avoir à toucher un réglage avant.

La DLL reste dans le jeu quand on ferme le trainer, avec ses réglages.
Depuis la V2.3, à chaque accrochage, le trainer lui renvoie l'état réel
des cases de l'onglet "État de jeu" : un réglage resté actif d'une
session précédente est coupé si sa case est décochée.

### Difficulté

Onglet "État de jeu" : liste "Difficulté" (Liquid, Naked, Solid, Big
Boss, The Boss), lue et écrite en direct. Effet vérifié : c'est cette
difficulté qui est enregistrée à la prochaine sauvegarde (rang et écran
de fin compris). Aucun changement constaté en jeu : une balle retire la
même vie en Liquid et en The Boss (mesuré), et les ennemis ne semblent
pas plus vigilants.

### Munitions infinies / Pas de rechargement

Onglet "État de jeu" : deux cases indépendantes.

- **Munitions infinies (V2.3)** : active les munitions infinies
  **d'origine du jeu**. Chaque arme a un drapeau "réserve infinie", que
  le jeu utilise déjà pour le Pistolet solaire et le Patriot ; le trainer
  le pose sur toutes les armes à munitions (69, grenades et explosifs
  compris). La réserve ne baisse plus et le HUD affiche le symbole
  infini, sans toucher à l'objet équipé (le Solid Eye reste actif). Le
  Pistolet solaire, dont la "réserve" est le chargeur rechargé au
  soleil, passe en chargeur infini et reste plein. Décocher remet les
  armes à la normale. (Avant la V2.3 : réécriture des réserves en boucle,
  qui faisait ramer le trainer.)
- **Pas de rechargement** : patch de code qui supprime l'écriture du
  nouveau nombre de munitions du chargeur après un tir, quelle que soit
  l'arme.

### Un coup, un mort / Non létal

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

**Boss (V2.3) : la mise à mort du jeu lui-même.** Chaque boss a sa
propre fonction de dégâts, trouvée au débogueur en partant de sa jauge
du HUD. Quand c'est possible, le patch fait passer chaque coup par la
"mise à mort" prévue par le jeu (dégât spécial qui retire toute la vie
restante) : transitions de phase et séquences de fin restent gérées par
le jeu. Confirmé en jeu (2026-10-04) :

- **Laughing Octopus** : un tir par phase (le jeu recale la vie au seuil
  de la phase) ;
- **Raging Raven**, **Crying Wolf**, **Metal Gear RAY** : un tir ;
- **les quatre formes Beauty** : un tir ;
- **Vamp** : à terre en un tir, la seringue reste nécessaire (mécanique
  du combat, non contournée) ;
- **Liquid Ocelot** (combat final) : deux coups par phase (la vie tombe
  au plancher de la phase, puis la phase suivante). La dernière phase
  de 7 coups scénarisés n'est pas couverte ;
- **Screaming Mantis**, forme bête : sa vie ne peut pas descendre sous
  50, seule son endurance déclenche la défaite ; le patch vide les deux
  d'un coup. **Pas encore testé en jeu** (seule la baisse de vie l'a
  été). Seule la poupée Mantis l'atteint, comme dans le jeu.

L'ancien système (forçage de la vie par paliers, synchronisé sur un vrai
coup) n'est plus utilisé dès que ces patchs sont posés.

**Gecko (robots) et tanks : hook séparé.** Les Gecko ne passent ni par
l'instruction des ennemis humains ni par celle des boss - un troisième
patch de code dédié (porté du script CE "aob Damage Gecko") gère leur
cas, branché sur le même bouton/flag "Un coup, un mort" (pas de variante
non létale, ça n'a pas de sens pour un robot). Ce patch vise en réalité
la fonction de dégâts commune aux Gecko **et aux tanks** (confirmé en
jeu sur les deux, 2026-10-03).

**Tanks : n'importe quelle arme (V2.1).** Normalement, un tank ignore la
plupart des armes : son code de collision n'enregistre que les coups de
4 armes précises, et tous les autres tirs (balles comprises) sont
écartés avant même d'être comptés, si bien que "Un coup, un mort" ne
pouvait pas s'appliquer. Deux patchs de code supplémentaires, actifs
seulement quand "Un coup, un mort" est coché, lèvent ce filtre pour les
tirs **du joueur** et font passer le coup par le chemin des dégâts :
une simple balle de fusil détruit alors un tank (confirmé en jeu,
2026-10-03). Seul le fusil a été testé à ce jour ; une arme
particulière pourrait encore être filtrée plus loin dans la chaîne.

**Hélicoptères, véhicules, mini Gekko, portails (V2.3).** Mêmes
principes, chacun avec ses patchs (confirmés en jeu, 2026-10-04) :

- **hélicoptères** : d'origine, seuls les lance-roquettes, les
  explosifs, le M82A2 et le Rail Gun les touchent ; toutes les armes
  comptent et chaque coup retire toute leur vie ;
- **véhicule de Millennium Park** : son filtre d'armes est levé ;
- **mini Gekko** : détruits au premier impact ;
- **objets destructibles** (portails à abattre au canon de tank...) :
  cèdent au premier impact. Le minimum imposé par le niveau (verrou de
  scénario éventuel) est conservé.

Modifier `native/speedhack.c` nécessite un compilateur C ciblant Windows
(testé avec `x86_64-w64-mingw32-gcc` via [MSYS2](https://www.msys2.org/),
mingw64) :

```
x86_64-w64-mingw32-gcc -shared -O2 -municode -o native/speedhack_x64.dll native/speedhack.c -lkernel32 -lwinmm
```

`mingw64/bin` doit être dans le PATH (sinon `cc1.exe` échoue silencieusement,
sans aucun message).

### Rail Gun / Solar Gun toujours chargés

Onglet "État de jeu", groupe "Armes et combat". Patch de code : la
charge du Rail Gun et du Solar Gun est pleine dès l'appui sur la
gâchette, avec l'effet visuel et le cri de Snake d'un vrai tir chargé à
fond, et sans dépendre de l'énergie solaire du Solar Gun. Le jeu
convertit le temps de charge en palier (1 à 3) dans une seule fonction,
utilisée à la fois pour les effets et pour les drapeaux du projectile ;
le patch lui fait renvoyer le palier maximal dès que la charge a
commencé. Deux patchs complémentaires forcent aussi le palier maximal
dans les drapeaux du coup reçu (soldats et tanks), pour que les dégâts
d'un tir chargé à fond s'appliquent partout. Confirmé en jeu
(2026-10-03), y compris un tank détruit d'un seul tir rapide de Rail Gun.

### Snake : Intouchable, Invisible, jauges (V2.3)

Onglet "État de jeu", groupe "Snake" et tableau des jauges.

- **Intouchable** : patch de code qui fait ignorer à Snake tous les
  impacts (balles, explosions, mines, coups, attaques non létales) : ni
  dégâts, ni projection, ni assommage.
- **Invisible** : les soldats et les Gekko ne voient plus Snake, même
  debout devant eux, comme avec le Camouflage furtif mais sans la
  transparence (l'indice de camouflage affiche 99 %). Il couvre la
  vision seulement : les lasers des mini Gekko (détection par contact en
  mouvement, à laquelle le vrai Camouflage furtif n'échappe pas non plus)
  et les autres sources d'alerte restent actifs. Cocher aussi
  **"Pas d'alerte"** pour que rien ne déclenche l'alerte générale :
  les deux réglages sont complémentaires.
- **Grip** et **Oxygène** : nouvelles lignes du tableau des jauges, avec
  curseur et case "Verrouiller" comme les autres. Elles n'existent que
  suspendu à un rebord ou sous l'eau ("pas suspendu" / "hors de l'eau"
  sinon). Verrouillées à 100 % : grip ou oxygène infinis.

### Équiper en direct, sans menu (V2.2)

Un bouton "Équiper" par ligne dans les onglets OctoCamo, Tenues et
Armes : le changement s'applique en jeu immédiatement, menu fermé,
comme si tu l'avais choisi dans le menu. Le trainer appelle les propres
fonctions du jeu, dans le fil du jeu, via la DLL injectée (après avoir
vérifié que chaque fonction a bien les octets attendus : sur une autre
version du jeu, il refuse plutôt que d'appeler n'importe quoi).

- **Motif OctoCamo** : immédiat, tous les motifs connus (y compris les
  spéciaux et les motifs mémorisés de la partie). Le trainer pilote le
  contrôleur d'auto-camouflage du jeu, celui qui change la combinaison
  contre un mur. Les motifs "forcés" (Olive, Cadavre, Pleurs...) restent
  en place même au contact d'un mur, comme dans le jeu ; les motifs
  capturés apparaissent en fondu et l'auto-camouflage reprend la main.
  Si une autre tenue est portée, la combinaison OctoCamo est remise
  d'abord. Doré et Précommande ne s'équipent que si le jeu les a
  débloqués sur ton compte.
- **Visage (FaceCamo) et tenues** (déguisements Moyen-Orient, Amérique
  du Sud, Europe de l'Est, costume de Snake, Altaïr) : le jeu doit
  recharger le modèle de Snake, ce qu'il ne fait que jeu en pause. Le
  trainer met donc le jeu en pause avec sa propre fonction (sans
  afficher de menu), équipe, attend la fin du rechargement puis reprend :
  le jeu se fige une fraction de seconde. Comme dans le menu, le visage
  passe à "aucun" si la tenue ne l'autorise pas (Altaïr). Les
  déguisements d'un acte fonctionnent aussi dans les autres actes.
- **Gilet** : immédiat.
- **Arme** : immédiat si l'arme est dans ton sous-menu rapide des
  armes (5 places). Sinon, le trainer fait comme le menu pause : il la
  place dans une place libre du sous-menu, ou à défaut dans la
  **5e place** (les 4 premières ne sont jamais touchées), charge son
  modèle puis l'équipe — le jeu se fige le temps de lire le fichier de
  l'arme. Si l'arme de la 5e place est celle que tu tiens, Snake la
  range d'abord une fraction de seconde. Seules les armes possédées ont
  un bouton actif.

**En cinématique (V2.3)** : le motif OctoCamo change en pleine
cinématique (le Snake de cinématique a sa propre tâche de camouflage,
pilotée directement), et le gilet aussi. Changer de tenue ou de visage
en cinématique faisait planter le jeu : ces boutons sont refusés tant
qu'une cinématique est en cours. Une arme équipée pendant une
cinématique n'est pas mise en main, mais placée dans le sous-menu
rapide.

Limites connues : le nombre de places du sous-menu des armes ne peut
pas être augmenté (le menu plante à l'affichage au-delà de 5) ; forcer
dans la main une arme dont le modèle n'est pas chargé fait planter le
jeu, d'où le passage par la 5e place.

### Téléportation

Onglet "Téléportation" : enregistre la position actuelle de Snake
(X/Y/Z) sous un nom, puis téléporte instantanément vers un point
enregistré (double-clic ou bouton dédié). Les 3 axes sont aussi
éditables manuellement (saisie directe + bouton "Téléporter ici"), et
la liste de points peut être exportée/importée en fichier JSON.

**Depuis la V2.3 :**

- **Acte et zone** affichés en direct ("Acte 2 - Village Vallée de
  Cove"), avec les noms officiels du jeu en français et en anglais
  (relevés dans ses fichiers de textes).
- **Points rangés par zone** : chaque point retient sa zone, et la liste
  n'affiche que ceux de la zone actuelle (case "Afficher les points de
  toutes les zones" pour tout voir). Le bouton "Rattacher à la zone
  actuelle" range les anciens points.
- **Fichier par acte et zone** : `teleport_points.json` ne contient que
  des valeurs du jeu (numéro d'acte, code de zone), le même fichier sert
  donc en français et en anglais. L'ancien format se lit toujours.
- **Points fournis** : sans fichier personnel, le trainer charge des
  points par défaut embarqués (`assets/default_teleport_points.json`).
  Le fichier personnel est créé au premier enregistrement.
- **Position fiable** : elle est lue dans la table des joueurs du jeu,
  qui suit toujours le Snake actuel. L'ancien pointeur (capturé au
  passage dans une routine de distance) restait sur l'ancien Snake après
  un changement d'acte (position à 0).

Coordonnées absolues du niveau : l'axe Y est la hauteur (le jeu peut
annuler une position invalide, ex. sous le sol), X/Z le plan
horizontal. Les points sont sauvegardés dans `teleport_points.json` (à
côté de l'exe/du script, pas versionné dans ce dépôt).

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
  - Téléportation (jusqu'à la V2.2) : script "aob Coordinates" (position
    X/Y/Z à `+0x10`/`+0x14`/`+0x18`) ;
  - plusieurs formules d'adresses (table des objets, statistiques, état
    d'alerte) ont été repérées en lisant ses scripts (détail dans les
    commentaires du code), puis **vérifiées en jeu par nos propres
    tests** avant d'être utilisées.

Merci à leurs auteurs. Si tu es l'auteur d'une de ces sources et que tu
souhaites une correction ou un retrait, ouvre une issue.

## Licence

Le code de ce dépôt est publié sous licence MIT (voir le fichier
[LICENSE](LICENSE)). Elle ne couvre pas les éléments repris d'autres
sources citées plus haut, ni le jeu lui-même (Metal Gear Solid 4,
Konami).

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
  technique la plus invasive du trainer. Ses effets sont confirmés en
  jeu cas par cas (voir plus haut), mais un ennemi non testé pourrait
  réagir autrement. Intouchable et Invisible sont aussi des patchs
  d'instructions.
- Les boutons "Équiper" appellent des fonctions internes du jeu en
  dehors de leur contexte normal (menus). Chaque cas a été testé en jeu,
  mais une situation particulière (cinématique, chargement, séquence
  scriptée) pourrait encore provoquer un plantage : sauvegarde avant
  d'expérimenter.
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
