# MGS4 Trainer — V2.6.0

Trainer en direct pour Metal Gear Solid 4 (portage PC Steam) : il lit et
écrit la mémoire du jeu pendant que tu joues. Armes, objets, statistiques
et jauges modifiables, tenue, visage, gilet, motif OctoCamo ou arme
changés sans passer par les menus, Snake intouchable ou invisible,
ennemis et boss en un coup, toute la zone neutralisée d'un clic, vitesse
du jeu, téléportation, et toute une configuration rappelée d'une touche
(profils F1 à F11).

Interface en français et en anglais. Usage solo uniquement.

Projet frère de [MGS4-SaveStats](https://github.com/ajikfan/MGS4-SaveStats)
(lecture seule des fichiers de sauvegarde), dont ce dépôt réutilise
`mgs4save.py`.

## Installation

**Avec l'exe (le plus simple)**

1. Télécharge le zip de la [dernière version](https://github.com/ajikfan/MGS4-Best-Trainer-Ever/releases/latest).
2. Décompresse-le n'importe où (garde le dossier complet).
3. Lance MGS4 (version Steam **1.4.1**) avec une partie chargée, puis
   `MGS4Trainer.exe`.
4. Ensuite, le bouton **Mise à jour** du trainer installe les nouvelles
   versions sans retélécharger le zip (à partir de la V2.5).

L'exe n'est pas signé : voir la [FAQ](docs/faq.md) si Windows ou ton
antivirus le signale.

**Depuis le code source** (Windows, Python 3.12, PySide6)

```
python live_trainer.py
```

Sans le jeu, les onglets restent consultables (contenu grisé) pour
parcourir l'interface et lire les infobulles. Le bouton **Aide** du
trainer résume la version compatible, les avertissements et l'historique
des versions.

## Documentation

- [Guide des onglets et des profils](docs/guide.md)
- [Un coup, un mort : les boss](docs/boss.md)
- [FAQ et problèmes courants](docs/faq.md)
- [Nouveautés par version](docs/nouveautes.md)
- [Comment ça marche](docs/fonctionnement.md)
- [Maintenance](docs/maintenance.md) (compatibilité, build, organisation du code)

## Dernière version : V2.6.0

- **Mode photo** : caméra libre pilotée à la manette ou au clavier et à
  la souris, Snake immobile.
- **Salle blanche** et **Menu principal** : deux nouveaux boutons.
- **Metal Gear REX** : la téléportation déplace REX lui-même quand tu le
  pilotes, et Intouchable le protège aussi.
- **Chrono figé** : le compte à rebours du jeu ne descend plus.
- **Toute la zone** : Tuer et Assommer marchent sur les Gekko de la fuite
  de REX.
- Livrée par la **mise à jour intégrée** (petits fichiers).

Détail dans [Nouveautés par version](docs/nouveautes.md).

## ⚠️ Avertissements

- **Mise à jour du jeu** : le trainer est calibré pour MGS4 Steam
  **1.4.1**. Après une mise à jour du jeu, attends une nouvelle version
  du trainer avant de l'utiliser (voir la [FAQ](docs/faq.md)).
- **Connexion** : au lancement, le trainer interroge GitHub pour savoir
  s'il existe une nouvelle version (rien n'est téléchargé sans ton
  accord, désactivable dans la fenêtre **Mise à jour**).
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

## Crédits et sources

Ce trainer s'appuie sur le travail d'autres personnes, en plus de nos
propres recherches :

- **[zexk/bbtracker](https://github.com/zexk/bbtracker)** (licence MIT) :
  chaîne de pointeurs vers la structure de jeu (voir [Comment ça marche](docs/fonctionnement.md)).
- **Table Cheat Engine communautaire `MGS4.CT`, par RMLSNK** (version
  7.7 du fichier utilisé ici). Cette table n'est **pas redistribuée**
  dans ce dépôt (aucune licence n'y est indiquée). Jusqu'à la V2.4.1, le
  trainer réutilisait plusieurs de ses scripts, réécrits en C et en
  Python ; depuis, **tous ont été remplacés par notre propre code** :
  - "Un coup, un mort" / "Non létal" sur les soldats : script "aob
    Damage" et sa logique "Remove Lethal" ;
  - "Un coup, un mort" sur les Gekko et les tanks : script "aob Damage
    Gecko" ;
  - "Pas de rechargement" : script "No Reload" ;
  - suivi des boss (jusqu'à la V2.4.1, retiré depuis) : scripts
    "Bosses 2" et "Bosses Laughing Octopus" ;
  - Téléportation (jusqu'à la V2.2, retiré depuis) : script "aob
    Coordinates" ;
  - alerte forcée (jusqu'à la V2.4.1, remplacée depuis par nos propres
    minuteries de soldats) : script "Alert -- Ignore" ;
  - "Pas d'alerte" (jusqu'à la V2.4.1) : script "aob No Alerts". Depuis,
    patch de code issu de notre propre analyse, sur la même fonction du
    jeu (voir [Comment ça marche](docs/fonctionnement.md)) ;
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
