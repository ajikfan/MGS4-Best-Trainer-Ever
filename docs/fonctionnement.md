# Comment ça marche

[← Retour au README](../README.md) · *[English version](en/how-it-works.md)*

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

- **Pause** : en partie (V2.6.0), la pause interne du jeu, celle qu'il
  utilise lui-même pour recharger le modèle de Snake, appelée par la DLL :
  le monde est figé mais le jeu continue de dessiner chaque image (le
  mode photo reste utilisable). Dans les menus, ou si elle échoue, gel
  complet du process (`NtSuspendProcess`), comme avant.
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
létal. Ce sont des patchs de code (instructions du jeu modifiées,
octets d'origine vérifiés avant d'écrire).

**Soldats (refait le 13 octobre 2026).** La fonction de dégâts des
soldats (trouvée par point d'arrêt matériel sur la vie d'un soldat)
connaît déjà une "mise à mort" : un dégât spécial qui vide toute la
jauge visée. Le trainer donne cette valeur à chaque coup, quel que soit
son type, puis choisit la jauge :

- **Létal** : la vie — le soldat meurt au premier coup, fléchettes
  tranquillisantes comprises ;
- **Non létal** : le sommeil — le soldat s'endort aussitôt, balles
  comprises, sans jamais perdre de vie.

Le joueur a sa propre fonction de dégâts, il n'est jamais concerné.
Jusqu'à la V2.4.1, les soldats passaient par un hook porté du script
"aob Damage" de la table `MGS4.CT` (RMLSNK), qui forçait la vie à 0 au
moment de son écriture.

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
coup) a été retiré le 12 octobre 2026, avec les hooks de suivi des boss
qu'il utilisait (repris des scripts "Bosses 2" et "Bosses Laughing
Octopus" de la table `MGS4.CT`) : il ne servait plus que de repli si les
patchs refusaient de s'appliquer.

**Gekko et tanks (refait le 13 octobre 2026).** Ils partagent une même
fonction de dégâts, qui connaît elle aussi la "mise à mort" du jeu : le
trainer y fait passer chaque coup en Létal (tanks : dans les deux
modes). En Non létal, un Gekko s'endort au premier coup, toute arme, où
qu'on le touche : le trainer traite chaque coup comme une fléchette du
Mk.2 dans la jambe et vide d'un coup ses deux jauges de tranquillisant. Jusqu'à la V2.4.1, les Gekko et les tanks passaient par un
hook porté du script "aob Damage Gecko" de la table `MGS4.CT`.

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

**Hélicoptères, véhicules, Gekko nains, portails (V2.3).** Mêmes
principes, chacun avec ses patchs (confirmés en jeu, 2026-10-04) :

- **hélicoptères** : d'origine, seuls les lance-roquettes, les
  explosifs, le M82A2 et le Rail Gun les touchent ; toutes les armes
  comptent et chaque coup retire toute leur vie ;
- **véhicule de Millennium Park** : son filtre d'armes est levé ;
- **Gekko nains** : détruits au premier impact (V2.4 : paralysés en Non
  létal) ;
- **objets destructibles** (portails à abattre au canon de tank...) :
  cèdent au premier impact. Le minimum imposé par le niveau (verrou de
  scénario éventuel) est conservé.

La DLL est fournie déjà compilée (`native/speedhack_x64.dll`) : aucun
compilateur n'est nécessaire pour utiliser le trainer. Pour la modifier,
voir [Recompiler la DLL](maintenance.md#recompiler-la-dll).

**V2.4 : quelle que soit l'arme, dans les deux modes.** Règle générale :
en Létal tout coup tue, en Non létal tout coup met K.O. par l'endurance
sans toucher à la vie, comme pour les soldats, y compris le Mk.2 et les
armes létales. Confirmé en jeu (2026-10-10) :

- **machines** (sans endurance) détruites dans les deux modes : Gekko,
  tanks, hélicoptères, véhicules, **Metal Gear RAY**, objets
  destructibles ; le Mk.2 les touche aussi (hélicoptères, Gekko, portails
  confirmés ; tanks non testés faute de tank), ainsi que les balles
  tranquillisantes du Mosin-Nagant (Gekko confirmé) ;
- **Gekko nains** : détruits au premier coup en Létal, paralysés en Non
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
  les Gekko nains ne le détectent plus non plus (lasers, proximité,
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

### Pas d'alerte : comment ça marche

L'état d'alerte du jeu est recalculé à chaque image par une fonction
qui parcourt les unités de soldats : chacune propose un état et donne
ses minuteries (compte à rebours d'Alerte, minuterie d'Évasion et de
Prudence). La fonction garde le plus grave et recopie les minuteries
les plus hautes. Le trainer neutralise ces trois prises (patch de code,
octets d'origine vérifiés) : la fonction tourne toujours, mais renvoie
Normal avec des minuteries à 0. Les soldats gardent leurs réactions
individuelles (« ! », visée, tirs) sans que l'alerte générale parte.

C'est la même fonction que le script "aob No Alerts" de la table
`MGS4.CT`, qui la court-circuitait dès son entrée (méthode utilisée
jusqu'à la V2.4.1) ; nous l'avons retrouvée de notre côté en remontant
depuis l'instruction qui écrit l'état d'alerte (12 octobre 2026).

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
- **Alerte forcée** (refaite le 12 octobre 2026) : chaque soldat qui
  participe à l'alerte a deux minuteries, le compte à rebours de l'Alerte
  (99.99, qui descend quand plus personne ne voit Snake) puis celle de
  l'Évasion et de la Prudence (passage en Prudence à mi-course, en Normal
  à 0). Le jeu en recopie le maximum à chaque image pour décider de
  l'état. Le trainer place les minuteries des soldats dans l'étape choisie
  et les y maintient ; en Automatique, il n'écrit plus rien et le jeu
  reprend son décompte là où il en est. Si la zone n'est pas en alerte,
  il fait d'abord signaler Snake par un soldat (fonction du jeu appelée
  par la DLL). L'ancienne méthode, qui court-circuitait la fonction de
  calcul de l'alerte (script "Alert -- Ignore" de `MGS4.CT`), n'est plus
  utilisée : au retour en Automatique, le jeu retombait d'un coup en
  Normal.
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
- **Téléportation** : dans REX, la position du joueur n'est qu'un point
  invisible que le jeu ramène à chaque image vers REX. Le trainer trouve
  le vrai REX dans la liste des acteurs du jeu (juste après Snake) et
  décale sa position de base (six copies, toutes ensemble) ; Snake suit.
  Le cockpit est posé un peu au-dessus du point, REX retombe seul au sol.

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

### Mode photo (V2.6.0)

- **Caméra** : la fonction du jeu qui règle la caméra recopie sa
  position et son orientation à chaque image ; le trainer neutralise
  cette copie, et c'est la DLL qui déplace la caméra, une fois par image
  dans le fil du jeu (une boucle dans le trainer était interrompue par le
  reste de l'interface, d'où des saccades).
- **Commandes** : le jeu remplit une manette virtuelle (au format PS3) à
  partir de la manette et du clavier/souris. Pendant le mode, ses
  écritures sont redirigées vers une copie que lit la DLL : Snake ne
  reçoit plus rien, et la caméra se pilote avec les commandes habituelles.
  Pendant certaines cinématiques, le jeu ne met plus le clavier ni la
  souris dans cette manette : la DLL les lit alors elle-même (la souris
  par une accroche de bas niveau, la position du curseur n'étant pas
  fiable).
- **Temps figé** : la pause interne du jeu (voir la Pause plus haut),
  relancée ou refigée par Y / E / Pause.
- **Zoom** : la fonction de caméra reçoit le zoom en argument ; un
  détour le remplace par une valeur du trainer, que la croix et la
  molette modifient. Les zooms des cinématiques sont ainsi neutralisés.
- **HUD** : chaque élément du HUD teste un mot de drapeaux global ; la
  DLL l'impose à chaque image, puis le trainer le remet comme avant.
- **Téléportation** : la position de la caméra est écrite comme position
  de Snake (refusé en cinématique).

### Menu pause des cinématiques : ligne QUITTER (V2.6.0)

Le menu est une tâche du jeu dont le nombre d'entrées (2) est écrit en
dur dans son code. Le trainer le passe à 3, lui donne une table de
surbrillance à trois entrées (la troisième ne lance aucune animation) et
détourne la validation : la troisième entrée ramène au menu principal.
L'interface du menu vient d'un fichier du jeu, compressé dans une
archive : plutôt que de le modifier, le trainer dessine le mot dans une
fenêtre transparente par-dessus le jeu. Quand le curseur est dessus, il
descend la barre de sélection du jeu d'une ligne et grise les deux autres
textes, directement dans la scène d'interface en mémoire. Les patchs sont
retirés à la fermeture du trainer.

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
