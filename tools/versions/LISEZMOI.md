# Portage des adresses vers une nouvelle version du jeu

Le code du trainer garde les adresses de la version de référence (avant 1.4.2).
Pour une autre version, `mgs4trainer/versions/<version>.json` donne leurs
nouvelles valeurs ; `mgs4trainer/core/versions.py` les applique à la connexion,
d'après l'horodatage PE de l'exe.

Le .text de l'exe sur disque est chiffré (protection Steam) : on compare des
images mémoire (`dump.py`, jeu lancé). Images de référence hors dépôt, dans
`D:\Documents\GitHub\mgs4_versions` (`old/`, `1.4.2/`).

1. `inventory.py` : constantes du trainer qui sont des adresses (inventory.json).
2. `port_all.py <image>` : portage par signatures (port_<version>.json).
3. `manual_<version>.json` : corrections vérifiées à la main (prioritaires).
4. `build_table.py <version> <horodatage> <image> <port.json> > mgs4trainer/versions/<version>.json`

La DLL (`native/speedhack.c`) trouve ses points d'accroche par motifs : vérifier
que chacun est unique dans la nouvelle image, la recompiler sinon.
