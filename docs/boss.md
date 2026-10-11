# Un coup, un mort : les boss

[← Retour au README](../README.md)

La règle générale de "Un coup, un mort" : en **Létal**, tout coup tue ; en
**Non létal**, tout coup met K.O. en vidant l'endurance, sans toucher à la
vie, quelle que soit l'arme (Mk.2 compris). Le trainer passe par la mise
à mort prévue par le jeu : transitions de phase et fins de combat restent
gérées par le jeu.

| Boss | Létal | Non létal |
|---|---|---|
| Laughing Octopus | un coup par phase (arme létale : confirmé ; arme non létale : préparé, à confirmer) | endurance vidée, un coup par phase (confirmé) |
| Laughing Beauty | un coup (confirmé) | endurance vidée (confirmé) |
| Raging Raven | un coup (arme létale : confirmé ; arme non létale : préparé, à confirmer) | endurance vidée (confirmé) |
| Raging Beauty | un coup, toute arme (confirmé) | endurance vidée (confirmé) |
| Crying Wolf | un coup, toute arme (confirmé) | endurance vidée, toute arme (confirmé) |
| Crying Beauty | un coup, toute arme (confirmé) | endurance vidée, toute arme (confirmé) |
| Screaming Mantis (bête et Beauty) | un coup avec la poupée (confirmé) | endurance vidée avec la poupée (confirmé) |
| Metal Gear RAY | détruit en un coup (confirmé) | détruit en un coup (confirmé) |
| Vamp | à terre en un tir, la seringue reste nécessaire | non couvert |
| Liquid Ocelot (combat final) | vie et endurance au plancher de la phase au premier coup | pareil (combat aux poings) |

Remarques :

- **Screaming Mantis** : seule la poupée Mantis l'atteint, comme dans le
  jeu.
- **Liquid Ocelot** : le coup suivant lance la phase suivante ; les 7
  derniers coups scénarisés ne sont pas couverts.
- **Machines** (Gekko, tanks, hélicoptères, véhicules, RAY) : détruites
  dans les deux modes ; **mini Gekko** : détruits en Létal, paralysés en
  Non létal.

Le détail technique (fonctions de dégâts de chaque boss, patchs) est dans
[Comment ça marche](fonctionnement.md#un-coup-un-mort--non-létal).
