# Guide des onglets et des profils

[← Retour au README](../README.md)

Ce que fait chaque onglet et chaque réglage, et comment utiliser les profils F1 à F11.

### Barre du haut (toujours visible)

- **Statut** : connecté au jeu ou non (le trainer s'accroche tout seul
  à `mgs4.exe` dès qu'une partie est chargée).
- **Mode avancé (valeurs brutes)** : affiche les colonnes "Valeur brute"
  et "Définir (brut)" dans les tableaux, et les objets internes masqués
  par défaut (certains font planter le jeu : à n'utiliser qu'en
  connaissance de cause).
- **Rafraîchir maintenant** / **(Re)connecter** : relit tout tout de
  suite / se raccroche au jeu (après un redémarrage du jeu par exemple).
- **Mise à jour** : cherche une nouvelle version du trainer sur GitHub
  (le bouton passe en vert quand il y en a une). Seuls les fichiers
  modifiés sont téléchargés, vérifiés, puis installés au redémarrage du
  trainer (**Redémarrer maintenant** ou **Plus tard**). Une case permet
  de désactiver la recherche au lancement.
- **Aide** : résumé, version compatible et historique des versions.
- **Profil** : le profil appliqué en dernier, et **Enregistrer sous Fx**
  pour ranger la configuration actuelle sous une touche (voir "Profils
  F1 à F11" plus bas).
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
  **Pause** (gel complet du jeu), case **Chrono figé** (le compte à
  rebours du jeu ne descend plus, par exemple les 5 minutes de la fuite
  de Metal Gear REX à l'acte 4), liste **Difficulté** (Liquid à The
  Boss ; change la difficulté enregistrée à la prochaine sauvegarde).
  Au clavier, même jeu au premier plan : touche **Pause** pour la pause,
  pavé numérique **+** / **−** pour ±10 % et **0** pour revenir à 100 %
  (bandeau "Vitesse : x %" par-dessus le jeu).
- **Alerte** :
  - **État réel** : l'état d'alerte en cours (Normal, Alerte, Évasion,
    Prudence) ;
  - **Forcer** : impose un état d'alerte au choix, ou "Automatique" pour
    laisser le jeu décider. Le jeu reste dans l'étape choisie tant que tu
    ne reviens pas sur Automatique, puis reprend son décompte là où il en
    est (Alerte → Évasion → Prudence → Normal). Depuis Normal, Alerte,
    Évasion et Prudence font donner l'alerte par un vrai soldat de la zone
    (musique, renforts, recherche) ; Normal met fin à l'alerte en cours.
    Sans soldat dans la zone, le jeu ne gère pas d'alerte : forcer n'a
    aucun effet ;
  - **Pas d'alerte** : l'alerte générale ne se déclenche jamais, quelle
    qu'en soit la cause (vue, bruit, corps trouvé, lasers des mini
    Gekko...). Les ennemis réagissent encore individuellement : un
    soldat qui te voit affiche son « ! », te vise et peut te tirer
    dessus, mais sans alerte générale, renforts ni musique d'alerte.
- **Armes et combat** :
  - **Munitions infinies** : munitions infinies d'origine du jeu sur
    toutes les armes (symbole infini au HUD) ;
  - **Pas de rechargement** : le chargeur ne se vide plus (et la
    mitrailleuse de Metal Gear REX ne surchauffe plus) ;
  - **Silencieux illimités** : le silencieux monté ne s'use plus ;
  - **Un coup, un mort**, avec le choix **Létal / Non létal**, quelle
    que soit l'arme : en Létal, tout ennemi touché tombe en un coup ; en
    Non létal, les soldats et les Gekko sont endormis au premier coup, et
    les boss mis K.O. (endurance vidée, vie intacte). Les autres machines
    (tanks, hélicoptères, véhicules, Metal Gear RAY, objets destructibles)
    sont détruites dans les deux modes, les mini Gekko détruits en Létal
    et paralysés en Non létal. Boss : voir [la page des boss](boss.md) ;
  - **Rail Gun / Solar Gun toujours chargés** : tir chargé à fond dès
    l'appui sur la gâchette (et laser de Metal Gear REX au niveau 5).
- **Snake** :
  - **Intouchable** : aucun impact n'a d'effet sur Snake (ni dégâts, ni
    projection, ni assommage) ;
  - **Invisible** : les soldats, les Gekko et les mini Gekko ne le voient
    plus, même debout devant eux, et un tir sans silencieux ne les fait
    plus passer en alerte (le hold-up reste possible). À combiner avec
    "Pas d'alerte" pour que rien ne déclenche l'alerte générale ;
  - **Pas de mal de dos** : Snake ne se tient plus le dos, ni après une
    chute de haut (réception normale, les dégâts de la chute restent), ni
    après être resté longtemps accroupi ;
  - **Déclencher** : choisis une action dans la liste et clique sur
    **Déclencher** pour que Snake la joue. En tête : **Tomber de haut**,
    **Mal de dos accroupi** (seulement accroupi et immobile) et **Vomir**
    (version debout ou accroupie selon la posture), puis 214 animations
    du jeu (coups, CQC, chutes, réveils, échelles, suspendu, électrocuté,
    « ça sent mauvais »…), chacune avec son numéro. Les actions partent
    dans n'importe quelle posture, sans dégâts ni son ; Snake reprend
    ensuite sa posture (accroupi, allongé, face contre le sol, sur le
    dos). Les animations prévues pour une autre posture (échelle,
    suspendu…) peuvent donner un résultat étrange.
- **Toute la zone** : agit d'un clic sur toute la zone, par les fonctions
  du jeu lui-même, quel que soit l'état en cours (un ennemi endormi peut
  être tué).
  - **Cible** : **Ennemis**, **Rebelles**, **Tous les PNJ** (les civils,
    les boss et le Rat Patrol ne sont jamais visés) ou **Rat Patrol**
    (Tuer, Assommer et Endormir seulement) ;
  - **Tuer** : soldats, Gekko, mini Gekko, véhicules, tanks et
    hélicoptères (les machines comptent comme ennemis) ;
  - **Assommer** : les soldats tombent K.O., les Gekko tombent au sol,
    les mini Gekko sont paralysés quelques secondes, les Gekko de la
    fuite de Metal Gear REX (acte 4) s'accroupissent quelques secondes ;
  - **Endormir** : soldats et Gekko (ni les mini Gekko ni les Gekko de
    la fuite de REX ne dorment) ;
  - **Rire**, **Pleurer**, **Enrager**, **Crier** : les émotions des
    Beauty, sur les soldats éveillés, pendant une trentaine de secondes ;
  - **Rebelles : Neutres / Hostiles** : cochée, impose l'attitude des
    rebelles envers Snake (une alerte déjà en cours suit son cours).

### Jauges

Toutes les jauges, toujours visibles, rangées par groupe (la page défile
si la fenêtre est petite) :

- **Snake** : Santé, Stamina, **Grip** (suspendu à un rebord),
  **Oxygène** (sous l'eau), Stress, batterie du Solid Eye ;
- **Véhicules** : **Drebin 893** (le véhicule de l'acte 2), **Van**
  (celui à protéger à l'acte 3), Santé de Metal Gear REX ;
- **Rat Patrol Team 01** : un encadré par membre (**Meryl**, **Johnny**,
  **Jonathan**, **Ed** ; actes 1 et 5 pour Meryl et Johnny, acte 1 pour
  Jonathan et Ed), avec son état en direct (actif, touché, endormi,
  assommé, mort), une liste **Réveiller / Endormir / Assommer / Tuer** et
  le bouton **Appliquer**, puis sa vie et son endurance.

Pour chacune : un curseur en pourcentage pour la régler, et une case
**Verrouiller** qui la maintient à ce niveau (Santé verrouillée à 100 % =
vie infinie, Grip à 100 % = grip infini...). Une jauge verrouillée ne
bouge plus du tout : le jeu n'écrit plus dedans. Les jauges absentes
affichent "pas suspendu", "hors de l'eau" ou "absent" ; les verrouiller à
ce moment-là les verrouille à 100 %, prêtes pour le moment où elles
servent.

Rat Patrol : une jauge verrouillée n'est plus écrite par le jeu, pour ce
membre seulement (vie et endurance séparément ; les soldats autour
prennent leurs dégâts normalement). Leur vie à 0 les tue (la mort de
Meryl à l'acte 5 fait échouer la mission), leur endurance à 0 les met
K.O. aussitôt. Réveiller les relève tout de suite ; Endormir les fait
tomber lentement (des « Z ») ; Assommer les fait tomber brusquement (des
étoiles) ; un équipier peut venir les réveiller.

### Armes

Toutes les armes du jeu, rangées par catégorie (pistolets, fusils
d'assaut, fusils de précision, explosifs, accessoires...). Pour chaque
arme :

- **État** : Non possédée / Verrouillée / Utilisable ;
- **Munitions** : la réserve, modifiable ;
- **Équiper** : met l'arme en main immédiatement, sans menu (voir
  "Équiper en direct" plus bas). Actif seulement pour les armes
  possédées ;
- **Personnaliser** (armes à emplacements d'accessoires) : un choix par
  emplacement (silencieux, lumière, laser, visée, sous le canon),
  appliqué tout de suite, même sur l'arme en main. Les accessoires non
  possédés sont grisés.

Dans la section **Accessoires**, la colonne **Munitions / Quantité**
donne le nombre de silencieux et les munitions des lance-grenades
(Masterkey, XM320, GP-30), modifiables.

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

## Profils F1 à F11


Un profil, c'est une photo de l'onglet "État de jeu" rangée sous une
touche du clavier, de F1 à F11.

**Créer un profil**

1. Règle l'onglet "État de jeu" comme tu le veux (cases cochées, Létal
   ou Non létal, jauges verrouillées et leur niveau, vitesse, difficulté,
   alerte forcée…) et monte les accessoires voulus sur tes armes.
2. Clique sur **Enregistrer sous Fx** dans la barre du haut.
3. Choisis la touche (F1 à F11), donne un nom ("godmod", "vanilla"…),
   puis **Enregistrer**. Une touche déjà prise peut être remplacée (le
   trainer demande confirmation) ou libérée avec **Supprimer**.

Ce qui est enregistré : la vitesse, la difficulté, l'alerte forcée,
toutes les cases (Pas d'alerte, Munitions infinies, Pas de rechargement,
Silencieux illimités, Un coup un mort, Rail Gun / Solar Gun toujours
chargés, Intouchable, Invisible, Pas de mal de dos), le choix Létal / Non létal, le verrou
et le niveau de chaque jauge, et les accessoires montés sur chaque arme.
Ce qui ne l'est pas : la pause, les objets et les armes elles-mêmes (un
profil ne te donne pas d'arme ; à l'application, seuls les accessoires
que ta partie possède sont montés).

**Utiliser un profil**

- **Au lancement** du trainer, une fenêtre propose de choisir le profil
  de la session (ou aucun).
- **En jeu**, appuie sur la touche du profil : il s'applique tout de
  suite, même si c'est le jeu qui est au premier plan. Seules les
  touches qui ont un profil sont prises au jeu ; les autres touches F
  restent au jeu, et F12 reste libre pour la capture d'écran Steam.
- **La même touche une deuxième fois** désactive le profil et remet la
  configuration que tu avais avant d'en activer un. Appuyer sur une
  autre touche passe directement à l'autre profil (et sa touche le
  désactive à son tour, retour à la configuration de départ).
- **Confirmation** : à chaque touche, le jeu joue lui-même son son "GO"
  (celui du tir chargé du Solar Gun, au volume du jeu), et un bandeau
  s'affiche 2 secondes en haut de la fenêtre du jeu : "F2 · godmod —
  activé" (bord vert) ou "— désactivé" (bord rouge). Le bandeau ne prend
  ni le clavier ni la souris. Il s'affiche en fenêtre et en plein écran
  fenêtré ; un plein écran exclusif peut le masquer (non testé).
- La barre du haut indique le profil appliqué en dernier.

**Deux profils sont fournis** tant que tu n'as pas enregistré les tiens :
**F1 « Normal »** (tout désactivé, aucune jauge verrouillée : le jeu
d'origine) et **F2 « God mode »** (toutes les cases cochées, Non létal,
toutes les jauges verrouillées pleines, stress à 0). Ils ne touchent ni à
la difficulté ni aux accessoires. Tu peux les remplacer ou les supprimer
comme les autres.

Les profils sont dans `profiles.json`, à côté de l'exe (ou du script),
créé au premier enregistrement.

## Raccourcis clavier


- **Pause** (la touche du clavier) : coche ou décoche la case Pause (gel
  complet du jeu).
- **Pavé numérique +** / **−** : vitesse du jeu +10 % / −10 % (de 10 % à
  300 % ; touche maintenue = répétée). **Pavé numérique 0** : retour à
  100 %. Le même bandeau affiche "Vitesse : x %" par-dessus le jeu.
