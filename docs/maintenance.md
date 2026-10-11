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
recalibrer ce décalage.

## Empaqueter en .exe autonome

```
python -m PyInstaller --noconfirm MGS4Trainer.spec
```

Utiliser le fichier `.spec` fourni (pas une commande PyInstaller "à la
main") est important : il embarque l'icône et le dossier `assets/`
(nécessaire à l'icône affichée dans la fenêtre au runtime). Le résultat
est dans `dist/MGS4Trainer/` (dossier complet à copier, pas juste
l'exe).

L'exe n'est pas signé : Windows SmartScreen affichera un avertissement
au premier lancement ("Windows a protégé votre PC") — c'est normal pour
un outil indépendant non signé, il suffit de cliquer "Informations
complémentaires" → "Exécuter quand même".

## Organisation du code

Depuis la V2.4.1, `live_trainer.py` n'est plus que le point d'entrée ; le
code est dans le paquet `mgs4trainer/` :

- `core/` : chemins (`paths.py`), réglages et traductions (`i18n.py`),
  accès au processus (`winproc.py`), adresses et tables du jeu
  (`gamedata.py`), injection de la DLL et mémoire partagée avec elle
  (`speedhack.py`) ;
- `live/` : la classe `MGS4Live` (accès au jeu en cours), assemblée à
  partir de mixins par thème : accrochage (`base.py`), DLL et hooks
  (`hooks.py`), joueur et jauges (`player.py`), boss (`bosses.py`), armes
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
