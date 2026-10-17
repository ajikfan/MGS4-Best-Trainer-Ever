# Nouveautés par version

[← Retour au README](../README.md)

Le détail des dernières versions. L'historique complet est aussi dans le bouton **Aide** du trainer et sur la page des [releases](https://github.com/ajikfan/MGS4-Best-Trainer-Ever/releases).

## Nouveautés de la V2.5.2

### Pas de mal de dos

Nouvelle case dans le groupe Snake : Snake ne se tient plus le dos, ni à
la réception d'une chute de haut (réception normale, les dégâts de la
chute restent), ni après être resté longtemps accroupi. Enregistrée dans
les profils F1 à F11.

### Déclencher une action

Nouvelle liste dans le groupe Snake, avec un bouton **Déclencher** :

- **Tomber de haut**, **Mal de dos accroupi** (seulement accroupi et
  immobile) et **Vomir** (debout ou accroupi selon la posture) ;
- puis 214 animations du jeu, avec leur numéro : coups, CQC, chutes,
  réveils, échelles, suspendu, électrocuté, « ça sent mauvais »…

Les actions partent dans n'importe quelle posture, sans dégâts ni son, et
Snake reprend ensuite sa posture (accroupi, allongé, face contre le sol,
sur le dos). Les animations prévues pour une autre posture peuvent donner
un résultat étrange.

## Nouveautés de la V2.5.1

### Onglet Jauges

Les jauges quittent l'onglet "État de jeu", devenu trop long, pour un
onglet à elles, rangées par groupe (Snake, Véhicules, Alliés), toujours
visibles et sur une page qui défile.

### Alliés : Meryl et Johnny

- Vie et endurance de **Meryl** et de **Johnny** (actes 1 et 5), "absent"
  quand ils ne sont pas là.
- Leurs deux jauges verrouillées : le jeu ignore les coups qu'ils
  reçoivent. Seuls eux sont protégés, les soldats autour prennent leurs
  dégâts normalement.
- Vie à 0 : ils meurent (à l'acte 5, la mort de Meryl fait échouer la
  mission). Endurance à 0 : K.O. aussitôt, sans attendre un coup.

### Divers

- Toute la zone : Assommer (soldats) et Enrager confirmés en jeu.
- Première mise à jour par petits fichiers : depuis la V2.5, le bouton
  "Mise à jour" installe cette version sans tout retélécharger.

## Nouveautés de la V2.5

### Toute la zone

Nouveau groupe dans l'onglet "État de jeu" : une action sur toute la
zone d'un clic, par les fonctions du jeu lui-même, quel que soit l'état
en cours (un ennemi endormi peut être tué, un Gekko endormi détruit).

- **Cible** : Ennemis, Rebelles ou Tous les PNJ (jamais les civils ni les
  boss). Les machines comptent comme ennemis.
- **Tuer** : soldats, Gekko, mini Gekko, véhicules, tanks et
  hélicoptères.
- **Assommer** : soldats K.O., Gekko au sol, mini Gekko paralysés.
- **Endormir** : soldats et Gekko (les mini Gekko ne dorment pas).
- **Rire, Pleurer, Enrager, Crier** : les émotions des Beauty sur les
  soldats éveillés, pendant une trentaine de secondes.
- **Rebelles : Neutres / Hostiles** : impose l'attitude des rebelles
  envers Snake tant que la case est cochée.
- Réglages enregistrés dans les profils F1 à F11.

À confirmer en jeu : Assommer sur les soldats, et Enrager.

### Mise à jour intégrée

Nouveau bouton **Mise à jour** (vert quand une version plus récente
existe). Le trainer ne télécharge que les fichiers modifiés, quelques
centaines de Ko au lieu du zip complet, vérifie leur empreinte, puis les
installe au redémarrage. La recherche au lancement se désactive dans la
même fenêtre. Pour cela, l'exe ne contient plus que le moteur (Python et
l'interface) ; le code du trainer est à côté, dans `app/`. Cette V2.5 se
télécharge donc encore en entier ; les suivantes non. Détails dans la
[FAQ](faq.md#comment-marche-la-mise-à-jour-).

### Un coup, un mort et alerte refaits

- **Un coup, un mort** est maintenant entièrement notre propre code :
  en Non létal, les soldats et les Gekko sont endormis au premier coup,
  quelle que soit l'arme ; le Mosin-Nagant détruit aussi les Gekko.
- **Alerte forcée** : revenu en Automatique, le jeu reprend son
  décompte là où il en est (avant : retour immédiat en Normal).
- **Pas d'alerte** et **Pas de rechargement** passent par des mécanismes
  du jeu lui-même (le second utilise son chargeur infini).
- Le trainer n'utilise plus aucun code repris de la table Cheat Engine
  MGS4.CT (voir les crédits du README).

## Nouveautés de la V2.4.1

- **Correctif mini Gekko** : en "Un coup, un mort" Non létal, marcher sur
  un groupe de mini Gekko pouvait faire planter le jeu. Le contact de
  Snake leur envoyait une paralysie relancée à chaque image ; ils
  sursautent maintenant normalement, et un tir les paralyse toujours.
- **Correctif OctoCamo** : les motifs qui ont leurs propres couleurs
  (Cadavre et motifs spéciaux) avaient un rendu délavé quand on les
  équipait depuis le trainer : le trainer remplaçait leurs teintes par
  celles de la table de la sauvegarde. Ils sont maintenant identiques à
  ceux du menu.
- **Invisible** : un tir sans silencieux ne fait plus passer les ennemis
  en alerte. Ils peuvent encore entendre et venir voir, et le hold-up
  reste possible.
- **Code** : le trainer est maintenant découpé en plusieurs fichiers
  (paquet `mgs4trainer/`) ; `python live_trainer.py` se lance comme avant.

## Nouveautés de la V2.4

### Profils F1 à F11 et raccourcis clavier

Toute la configuration de l'onglet "État de jeu" (et les accessoires des
armes) rangée sous une touche F1 à F11, utilisable même jeu au premier
plan, avec le son "GO" du jeu et un bandeau par-dessus le jeu ; touche
Pause et pavé numérique + / − / 0 pour la vitesse. Mode d'emploi complet
dans le [guide](guide.md#profils-f1-à-f11).

### Armes : personnaliser les accessoires

- Nouvelle colonne **Accessoires** dans l'onglet Armes, avec un bouton
  **Personnaliser** sur chaque arme qui a des emplacements. Il ouvre une
  fenêtre avec une liste par emplacement, comme le menu du jeu :
  Silencieux, Lumière, Laser, Visée, Sous le canon (avec "Aucun"). Le
  choix s'applique tout de suite, même sur l'arme que Snake a en main,
  et le menu de personnalisation du jeu se met à jour s'il est ouvert.
  Les accessoires que ta partie ne possède pas sont grisés.
- Dans la section **Accessoires**, la colonne **Munitions / Quantité**
  affiche et modifie le nombre de silencieux que tu possèdes et les
  munitions des lance-grenades montés (Masterkey, XM320, GP-30).
- Nouvelle case **Silencieux illimités** (onglet "État de jeu") : le
  silencieux monté ne s'use plus à chaque tir, quelle que soit l'arme.

### Alerte forcée : une vraie alerte

Forcer **Alerte** fait maintenant donner l'alerte par un vrai soldat de
la zone : musique, renforts, recherche, comme si Snake avait été repéré,
et le compte à rebours reste à 99.99 tant que l'alerte est forcée (avant,
il affichait 0.00). De retour en **Automatique**, le jeu reprend la main
et enchaîne normalement Évasion, Prudence puis Normal. Dans une zone sans
aucun soldat, le jeu ne gère pas d'alerte : la forcer n'a aucun effet.

### Jauges : verrouillées pour de bon, et deux nouvelles

- **Plus aucune variation** : avant, une jauge verrouillée était
  réécrite par le trainer à chaque rafraîchissement, et le jeu avait le
  temps de la faire bouger entre deux (stress qui passe de 0 à 0,1, vie
  qui baisse et remonte quand Snake est touché). Maintenant, verrouiller
  la vie, l'endurance, le stress, la batterie du Solid Eye, le Drebin
  893, le Van ou Metal Gear REX empêche le jeu lui-même d'écrire dans la
  jauge : elle ne bouge plus du tout.
- **Drebin 893** : la vie du véhicule de l'acte 2. **Van** : la vie du
  van à protéger à l'acte 3. Deux nouvelles lignes, verrouillables, qui
  affichent "absent" en dehors de leur séquence.
- **Grip et oxygène** : un verrou ne peut plus rester bloqué à 0 % (ce
  qui arrivait avec un profil enregistré alors que la jauge n'était pas
  active, et laissait la barre descendre). Verrouiller une de ces jauges
  quand elle n'est pas active la verrouille à 100 %.

### Un coup, un mort : quelle que soit l'arme, dans les deux modes

La règle est maintenant la même partout, comme pour les soldats :

- **Létal** : tout coup tue, avec n'importe quelle arme, y compris le
  pistolet tranquillisant Mk.2 ;
- **Non létal** : tout coup met K.O. en vidant l'endurance, sans jamais
  toucher à la vie, y compris avec une arme létale.

Ce qui n'a pas d'endurance est **détruit dans les deux modes** : Gekko,
tanks, hélicoptères, véhicules de Millennium Park, Metal Gear RAY et
objets destructibles. Le Mk.2 les touche aussi maintenant (hélicoptères,
Gekko, portails confirmés ; tanks préparés mais pas testés faute de
tank).

**Mini Gekko** : détruits net au premier coup en Létal (Mk.2 compris,
sans passer par la paralysie) ; **paralysés** en Non létal, avec
n'importe quelle arme (avant, une balle de Mk.23 les détruisait).

**Portails et objets destructibles** : ils tombent en un coup, mais
seulement quand le jeu l'autorise. Certains portails sont protégés par
le scénario tant que la séquence prévue n'est pas arrivée ; les forcer
plus tôt bloquait la progression (déclencheur de script jamais atteint).
Le trainer respecte donc ce verrou : le portail résiste tant que le jeu
le protège, puis cède au premier tir dès que le moment est venu.

**Boss**, toujours via la mise à mort prévue par le jeu (transitions de
phase et fins de combat gérées par le jeu) :

| Boss | Létal | Non létal |
|---|---|---|
| Laughing Octopus | un coup par phase | endurance vidée, un coup par phase (confirmé) |
| Raging Raven | un coup | endurance vidée en un coup, formes bête et Beauty (confirmé) |
| Crying Wolf | un coup, toute arme (confirmé) | endurance vidée en un coup, formes bête et Beauty (confirmé) |
| Screaming Mantis | un coup avec la poupée (confirmé) | endurance vidée en un coup avec la poupée (confirmé) |
| Les quatre Beauty | un coup (Screaming Beauty confirmée) | endurance vidée en un coup (confirmé) |
| Metal Gear RAY | détruit en un coup (confirmé) | détruit en un coup (confirmé) |
| Vamp | à terre en un tir, la seringue reste nécessaire | non couvert |
| Liquid Ocelot | voir ci-dessous | voir ci-dessous |

Pour Octopus, Raven et les Beauty, le Létal "toute arme" (Mk.2 compris)
est préparé mais n'a pas été revu en jeu.

**Liquid Ocelot** (combat final, aux poings, donc pareil dans les deux
modes) : au premier coup, sa vie **et** son endurance tombent au
plancher de la phase ; le coup suivant lance la phase suivante. Les 7
derniers coups scénarisés ne sont pas couverts.

### Metal Gear REX

- **Vie** : verrouillable (ligne "Santé Metal Gear REX"), elle ne baisse
  plus du tout.
- **Mitrailleuse** : avec **Pas de rechargement**, elle ne surchauffe
  plus. La chaleur monte normalement à chaque tir, et l'arme se bloque un
  moment à 100 % ; le trainer empêche la chaleur de monter.
- **Missiles** : avec **Munitions infinies**, toujours 15/15. REX a 15
  tubes, chacun avec son propre temps de rechargement après un tir (c'est
  pour ça que le compteur remonte tout seul) ; les tubes restent toujours
  prêts.
- **Laser** : avec **Rail Gun / Solar Gun toujours chargés**, il passe
  au niveau 5 (le maximum, avec son son) dès que tu commences à charger,
  au lieu de passer par les niveaux 1 à 5. Le laser a aussi une réserve
  d'énergie (le "x/100" du HUD) que chaque tir consomme : elle ne baisse
  plus, donc chaque tir part au niveau 5. Le rayon garde sa durée
  normale.
- La téléportation ne déplace pas REX (seulement la caméra).

### Invisible : les mini Gekko aussi

Les mini Gekko ne détectent plus Snake : leurs lasers ne le reconnaissent
plus (pas de laser rouge, pas d'alerte), et ni la proximité ni le contact
ne les font réagir (plus de "!"). Il reste un passage en Prudence si
Snake reste immobile au milieu d'eux ; "Pas d'alerte" le bloque.
