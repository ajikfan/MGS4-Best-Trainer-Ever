# MGS4 Trainer — V2.4.1

Trainer en direct pour Metal Gear Solid 4 (portage PC Steam) : il lit et
écrit la mémoire du jeu pendant que tu joues. Armes, objets, statistiques
et jauges modifiables, tenue, visage, gilet, motif OctoCamo ou arme
changés sans passer par les menus, Snake intouchable ou invisible,
ennemis et boss en un coup, vitesse du jeu, téléportation, et toute une
configuration rappelée d'une touche (profils F1 à F11).

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

## Dernière version : V2.4.1

- Correctif : en "Un coup, un mort" Non létal, marcher sur un groupe de
  mini Gekko pouvait faire planter le jeu.
- Correctif : les motifs OctoCamo à couleurs propres (Cadavre, motifs
  spéciaux) ne sont plus délavés quand on les équipe depuis le trainer.
- Invisible : un tir sans silencieux ne fait plus passer en alerte, le
  hold-up reste possible.

Détail dans [Nouveautés par version](docs/nouveautes.md).

## ⚠️ Avertissements

- **Mise à jour du jeu** : le trainer est calibré pour MGS4 Steam
  **1.4.1**. Après une mise à jour du jeu, attends une nouvelle version
  du trainer avant de l'utiliser (voir la [FAQ](docs/faq.md)).
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
