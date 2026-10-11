"""Trainer de recherche/edition memoire live : lit/ecrit en direct la
memoire du processus mgs4.exe (armes, objets, stats, vitesse du
jeu...), a l'origine pour identifier les ID encore inconnus des
tableaux objets/armes sans avoir a save/reload a chaque test, devenu au
fil du temps l'appli complete de ce depot (voir README.md).

Outil separe de MGS4SaveStats (autre depot, lecture seule des fichiers
de sauvegarde) - aucun lien entre les deux, volontairement publies a
part pour ne pas les confondre (voir README.md). Reutilise seulement
mgs4save.py (table des noms d'armes/objets) de ce depot frere.

    python live_trainer.py

Mecanisme : chaine de pointeurs documentee par le depot externe
zexk/bbtracker (docs/mgs4_research.md, licence MIT) - "module base +
0x1C28B28 -> pointeur linkvarbuf actif" et "module base + 0x1C28B38 ->
pointeur varbuf actif" (situe a linkvarbuf - 0x2800). Les deux structures
ont la meme disposition interne, serialisee telle quelle dans MGS4.SAV aux
memes offsets que ceux deja utilises par mgs4save.py (confirme
independamment par nos propres recherches, voir notes.md) : ITEM_STATE_OFFSET
(0x0526) et WEAPON_STATE_OFFSET (0x1d4) s'appliquent donc identiquement en
memoire live, relatifs a l'une ou l'autre adresse plutot qu'au debut du
fichier. Teste en direct (2026-09-22) : `linkvarbuf` retourne un stock de
Ration perime (ne reflete pas la consommation reelle en jeu), alors que
`varbuf` correspond exactement a ce que le joueur voit sur son HUD au meme
instant - donc `varbuf` est le buffer utilise ici pour lire/ecrire, pas
`linkvarbuf` (probablement un buffer de serialisation prepare pour la
sauvegarde, pas l'etat de jeu temps reel).

Le script original de zexk/bbtracker (scripts/probe-mgs4-memory.py) cible
Linux/Proton (lecture via /proc/[pid]/mem) - inutilisable tel quel sur
Windows natif. Ce fichier en est une reimplementation Windows (ctypes +
API kernel32/psapi, comme le reste du projet qui evite les dependances
externes), PAS une copie du code original.

La chaine de pointeurs n'a jamais ete verifiee sur notre build exacte -
d'ou le controle de coherence (`sanity_check`) avant d'autoriser la
moindre ecriture : item[0x00] et item[0x13] sont confirmes a 0 sur
absolument toutes les saves connues (voir STRUCTURAL_ITEM_IDS dans
mgs4save.py) ; si ce n'est pas le cas en memoire live, la chaine de
pointeurs est consideree non fiable et l'ecriture reste desactivee.
"""

from mgs4trainer.ui.main_window import main


if __name__ == "__main__":
    main()
