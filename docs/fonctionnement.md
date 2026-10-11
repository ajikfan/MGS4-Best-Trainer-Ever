# Comment ça marche

[← Retour au README](../README.md)

Comment chaque fonction agit sur le jeu, ses limites, et ce qui a été vérifié en jeu.

## Fonctionnement

Utilise la chaîne de pointeurs documentée par le dépôt externe
[zexk/bbtracker](https://github.com/zexk/bbtracker) (licence MIT) pour
localiser la structure de jeu en cours (`varbuf`) directement en mémoire,
sans scan. Un contrôle de cohérence (`sanity_check`, basé sur deux champs
toujours à 0 sur toute sauvegarde connue) s'exécute avant d'autoriser la
moindre écriture — si le jeu ne répond pas comme attendu, le trainer
refuse d'écrire plutôt que de risquer de corrompre la mémoire du jeu.

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
  d'un coup (confirmé en V2.4). Seule la poupée Mantis l'atteint, comme
  dans le jeu.

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
- **mini Gekko** : détruits au premier impact (V2.4 : paralysés en Non
  létal) ;
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

**V2.4 : quelle que soit l'arme, dans les deux modes.** Règle générale :
en Létal tout coup tue, en Non létal tout coup met K.O. par l'endurance
sans toucher à la vie, comme pour les soldats, y compris le Mk.2 et les
armes létales. Confirmé en jeu (2026-10-10) :

- **machines** (sans endurance) détruites dans les deux modes : Gekko,
  tanks, hélicoptères, véhicules, **Metal Gear RAY**, objets
  destructibles ; le Mk.2 les touche aussi (hélicoptères, Gekko, portails
  confirmés ; tanks non testés faute de tank) ;
- **mini Gekko** : détruits au premier coup en Létal, paralysés en Non
  létal, Mk.2 compris ;
- **Crying Wolf**, **Raging Raven**, **Screaming Mantis** (avec la
  poupée, formes bête et Beauty), **Laughing Octopus** et les Beauty :
  endurance vidée en Non létal ; en Létal, Crying Wolf et Screaming
  Mantis confirmés avec toute arme, Octopus, Beauty et Raven préparés
  pour les armes d'endurance mais pas encore revus en jeu ;
- **Liquid Ocelot** (combat final, aux poings) : dans les deux modes,
  vie **et** endurance au plancher de la phase au premier coup, le
  suivant lance la phase suivante. Les 7 derniers coups scénarisés ne
  sont pas couverts.

Les patchs Létal et Non létal se partagent certains sites (Crying
Wolf) : en changeant de mode, ceux du mode inactif sont retirés avant de
poser les autres.

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
  transparence (l'indice de camouflage affiche 99 %). Depuis la V2.4,
  les mini Gekko ne le détectent plus non plus (lasers, proximité,
  contact) ; il reste un passage en Prudence si Snake reste immobile au
  milieu d'eux. Depuis la V2.4.1, un tir sans silencieux ne fait plus
  passer en alerte : le jeu range tous les bruits dans une table commune
  que les soldats consultent, et le trainer empêche les tirs d'y être
  enregistrés. Les autres bruits (coups contre un mur, pas) restent
  actifs, car le "Freeze !" du hold-up passe par la même table. Cocher
  aussi **"Pas d'alerte"** pour que rien ne déclenche l'alerte générale :
  les deux réglages sont complémentaires.
- **Grip** et **Oxygène** : nouvelles lignes du tableau des jauges, avec
  curseur et case "Verrouiller" comme les autres. Elles n'existent que
  suspendu à un rebord ou sous l'eau ("pas suspendu" / "hors de l'eau"
  sinon). Verrouillées à 100 % : grip ou oxygène infinis.

### Profils, raccourcis, bandeau et alerte forcée (V2.4) : comment ça marche

- **Raccourcis globaux** : les touches F1 à F11 qui ont un profil, la
  touche Pause et le pavé numérique + / − / 0 sont enregistrés auprès de
  Windows (`RegisterHotKey`) : ils marchent quel que soit le programme au
  premier plan. Les touches F sans profil ne sont pas prises.
- **Retour en arrière** : au premier profil activé, le trainer garde une
  copie de la configuration en cours ; la touche du profil actif la
  remet et oublie la copie.
- **Son "GO"** : le trainer demande au jeu de jouer son propre son (moteur
  audio FMOD du jeu, via la DLL injectée), d'où le volume et la sortie
  audio du jeu. Si le jeu n'est pas accroché, un bip Windows le remplace.
- **Bandeau** : petite fenêtre transparente, toujours au premier plan,
  qui ne prend ni le focus ni les clics, centrée en haut de la fenêtre du
  jeu.
- **Alerte forcée** : le trainer choisit un soldat présent dans la zone
  (unité valide, en service, non neutralisé) et appelle la fonction du jeu
  par laquelle un soldat signale Snake ; le compte à rebours de l'alerte
  est ensuite maintenu au maximum tant que l'alerte est forcée.
- **Jauges figées** : pour chaque jauge, toutes les instructions du jeu
  qui l'écrivent (dégâts, régénération, baisse naturelle…) ont été
  trouvées au débogueur, puis neutralisées tant que la ligne est
  verrouillée ; le trainer reste seul à écrire la valeur verrouillée.
- **Accessoires** : chaque arme a un champ de bits des accessoires montés,
  que le trainer modifie directement ; il appelle ensuite les fonctions du
  jeu qui reconstruisent et redessinent le menu de personnalisation.
  Silencieux illimités : la fonction de tir retire 1 au silencieux monté
  et 1 à la réserve, les deux retraits sont neutralisés.

### Metal Gear REX (V2.4) : comment ça marche

- **Mitrailleuse** : la chaleur (0 à 4000, affichée en %) est relue,
  augmentée à chaque tir puis réécrite ; l'arme se bloque quand elle
  atteint le maximum. Le patch supprime la réécriture : la chaleur reste
  à 0 et le seuil n'est jamais atteint.
- **Missiles** : 15 tubes, chacun avec un minuteur de rechargement ; le
  compteur affiché est le nombre de tubes prêts, recompté à chaque image.
  Un tir décrémente ce compteur et arme le minuteur du tube : les deux
  sont neutralisés.
- **Laser** : la charge (0 à 10000, niveaux 1 à 5) est plafonnée par une
  réserve d'énergie (le "x/100" du HUD). Pendant la charge, le calcul
  "charge + vitesse, plafonnée" est remplacé par "charge = réserve" ;
  pendant le tir, la charge baisse normalement (durée du rayon) mais la
  réserve n'est plus diminuée.
- **Pourquoi la téléportation ne marche pas avec REX** : dans REX, la
  position que modifie le trainer est celle de Snake, que suit la
  caméra ; au premier pas, le jeu recale Snake sur la position du corps
  de REX, stockée ailleurs et non trouvée.

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
