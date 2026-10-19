# Maintenance

[← Retour au README](../README.md)

Pour faire évoluer le trainer : compatibilité avec les versions du jeu, build, organisation du code, débogage.

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
recalibrer ce décalage, vérifier les patchs de code (chacun refuse de
s'appliquer si ses octets d'origine ne sont plus là) et publier une
nouvelle version du trainer. Côté joueurs, la [FAQ](faq.md) leur
conseille d'attendre cette mise à jour plutôt que de recalibrer
eux-mêmes.

## Empaqueter en .exe autonome

```
python -m PyInstaller --noconfirm MGS4Trainer.spec
```

Utiliser le fichier `.spec` fourni (pas une commande PyInstaller "à la
main") est important. Depuis la V2.5, le résultat (`dist/MGS4Trainer/`,
dossier complet à copier, pas juste l'exe) est en deux parties :

- `MGS4Trainer.exe` et `_internal/` : le **moteur** (`launcher.py`),
  c'est-à-dire Python, PySide6 et les modules standard listés dans
  `release_files.RUNTIME_MODULES`. Il ne contient pas le code du trainer ;
- `app/` : le **code** du trainer (`live_trainer.py`, `mgs4trainer/`,
  `mgs4save.py`, `locales/`, `assets/`, la DLL), copié tel quel par le
  `.spec` d'après `release_files.app_files()`. C'est ce dossier que la
  mise à jour remplace, fichier par fichier.

Au lancement, l'exe installe d'abord une mise à jour en attente (dossier
`update/` validé par `update/ready.json`, voir `launcher.py`), puis lance
`app/live_trainer.py`. Si le code a besoin d'un module absent du moteur,
l'ajouter à `RUNTIME_MODULES` et augmenter `LAUNCHER_VERSION` dans
`launcher.py` : cette version demandera le zip complet.

L'exe n'est pas signé : Windows SmartScreen affichera un avertissement
au premier lancement ("Windows a protégé votre PC") — c'est normal pour
un outil indépendant non signé, il suffit de cliquer "Informations
complémentaires" → "Exécuter quand même".

## Build Nexus (sans mise à jour)

Nexus Mods refuse un exe qui se connecte à Internet pour se mettre à
jour. Un seul code source, deux variantes, choisies au build :

```
set MGS4_FLAVOR=nexus
python -m PyInstaller --noconfirm MGS4Trainer.spec
set MGS4_FLAVOR=
```

La variante `nexus` (voir `release_files.py`) ne copie pas
`core/updater.py` ni `ui/update_dialog.py` dans `app/`, n'embarque pas les
modules réseau dans l'exe (`ssl`, `http.client`, `urllib.*`,
`webbrowser`) et écrit `app/build.json` ; le trainer
(`core/build.py`) masque alors le bouton « Mise à jour » et ne fait
aucune vérification au lancement. Sans la variable (ou
`MGS4_FLAVOR=github`), le build GitHub habituel. Les deux builds
écrivent dans `dist/MGS4Trainer/` : refaire le build GitHub avant une
release GitHub. Zipper la variante Nexus sous un autre nom (ex.
`MGS4Trainer-V2.5.3-Nexus.zip`) ; pas de `manifest.json` pour Nexus.

## Publier une version (avec la mise à jour par petits fichiers)

Le bouton « Mise à jour » du trainer (`core/updater.py`) lit la dernière
release GitHub, télécharge son `manifest.json`, puis seulement les
fichiers du code dont l'empreinte diffère, **depuis le dépôt au tag de la
release** (raw.githubusercontent.com). D'où l'ordre :

1. Mettre `TRAINER_VERSION` (`mgs4trainer/ui/help.py`) et le changelog à
   jour, puis commiter. Tout le code doit être commité : `make_manifest.py`
   refuse sinon.
2. `python -m PyInstaller --noconfirm MGS4Trainer.spec`, puis zipper
   `dist/MGS4Trainer/`.
3. `python make_manifest.py` → `dist/manifest.json` (empreintes prises
   dans le dépôt au commit courant ; fichiers texte comparés après
   CRLF → LF, car Git les extrait en CRLF sous Windows).
4. Créer le tag (même nom que `TRAINER_VERSION`, ex. `V2.5`) **sur ce
   commit**, pousser commit et tag.
5. Créer la release GitHub sur ce tag, avec le zip **et**
   `manifest.json` (nom exact) en pièces jointes.

Une release sans `manifest.json` reste visible par le bouton, qui propose
alors seulement la page de téléchargement.

## Organisation du code

Depuis la V2.4.1, `live_trainer.py` n'est plus que le point d'entrée ; le
code est dans le paquet `mgs4trainer/` :

- `core/` : chemins (`paths.py`), réglages et traductions (`i18n.py`),
  accès au processus (`winproc.py`), adresses et tables du jeu
  (`gamedata.py`), injection de la DLL et mémoire partagée avec elle
  (`speedhack.py`) ;
- `live/` : la classe `MGS4Live` (accès au jeu en cours), assemblée à
  partir de mixins par thème : accrochage (`base.py`), DLL et hooks
  (`hooks.py`), joueur et jauges (`player.py`), armes
  et accessoires (`weapons.py`), **patchs de code** (`code_patches.py`,
  la liste `CODE_PATCHES`), son et alerte (`sound_alert.py`),
  statistiques et lieu (`state.py`), équipement en direct (`equip.py`) ;
- `ui/` : un fichier par onglet, plus l'aide, les profils et le bandeau,
  et la fenêtre principale (`main_window.py`).

## Recompiler la DLL

Uniquement si tu modifies `native/speedhack.c` : la DLL est fournie déjà
compilée (`native/speedhack_x64.dll`), dans le dépôt comme dans le zip,
et le trainer l'utilise telle quelle. Les joueurs n'ont jamais besoin de
compilateur.

Il faut un compilateur C ciblant Windows, testé avec
`x86_64-w64-mingw32-gcc` via [MSYS2](https://www.msys2.org/) (mingw64) :

```
x86_64-w64-mingw32-gcc -shared -O2 -municode -o native/speedhack_x64.dll native/speedhack.c -lkernel32 -lwinmm
```

Piège propre à MinGW : le dossier `mingw64/bin` de MSYS2 doit être dans
le PATH de Windows, sinon `cc1.exe` échoue sans afficher aucun message.

Après une modification de la DLL, refaire le build de l'exe (voir plus
haut) pour qu'elle soit embarquée. La DLL déjà injectée dans un jeu en
cours ne change pas : relancer le jeu pour charger la nouvelle.

## Patchs de code : règles

- Chaque entrée de `CODE_PATCHES` est une liste de sites
  `(RVA, octets d'origine, octets du patch)`. `set_code_patch` vérifie
  **tous** les sites avant d'écrire quoi que ce soit : si un seul ne
  correspond ni à l'original ni au patch, rien n'est écrit (protection
  contre une autre version du jeu).
- Deux patchs peuvent partager un site (Létal / Non létal) : le trainer
  retire toujours celui du mode inactif avant de poser l'autre.

## Débogage avec x64dbg : pièges connus

- Un point d'arrêt logiciel écrit l'octet `0xCC` dans le code du jeu :
  tant qu'il est là, le trainer refuse de poser un patch au même endroit.
  Toujours taper `bc` (et `bphc` pour les points d'arrêt matériels)
  **avant** de se détacher, sinon le jeu plante au prochain passage.
- Pour un point d'arrêt matériel, donner l'adresse déjà calculée, pas
  une addition (`base+offset`), sinon x64dbg peut afficher « Breakpoint
  reached not in list » et bloquer le jeu.
- L'adresse de base de `mgs4.exe` peut changer d'un lancement à l'autre :
  recalculer les adresses absolues à partir des RVA à chaque session.
