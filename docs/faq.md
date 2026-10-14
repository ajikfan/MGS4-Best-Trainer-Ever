# FAQ et problèmes courants

[← Retour au README](../README.md)

### Windows affiche « Windows a protégé votre PC »

L'exe n'est pas signé. Clique sur « Informations complémentaires », puis
« Exécuter quand même ».

### Mon antivirus signale le trainer

Il lit et écrit la mémoire du jeu, et injecte une petite DLL dans le jeu
pour certains réglages : les antivirus repèrent souvent ce genre de
technique. Le code source complet est dans ce dépôt.

### De quoi ai-je besoin pour utiliser le trainer ?

Windows 10 ou 11 en 64 bits, et Metal Gear Solid 4 (Steam) en version
1.4.1. Rien d'autre à installer : Python, l'interface et le runtime
Visual C++ sont inclus dans le dossier du trainer. Garde le dossier
complet (l'exe ne démarre pas sans son dossier `_internal`).

### Où décompresser le trainer ?

Dans un dossier personnel (le Bureau, Documents…), **pas dans
`Program Files`** : le trainer enregistre ses profils, ses réglages et
tes points de téléportation à côté de l'exe, et Windows peut bloquer ces
écritures dans `Program Files`.

### Le trainer ne s'accroche pas alors que le jeu tourne

Si MGS4 est lancé **en administrateur**, lance aussi le trainer en
administrateur (clic droit sur l'exe → « Exécuter en tant
qu'administrateur ») : sinon Windows l'empêche d'accéder au jeu. Dans
le cas normal (jeu lancé depuis Steam sans droits particuliers), aucun
droit administrateur n'est nécessaire.

### Le trainer reste sur « Non connecté »

Lance le jeu et charge une partie : le trainer s'accroche tout seul.

S'il ne s'accroche plus après une **mise à jour Steam du jeu**, les
adresses du jeu ont probablement bougé et le trainer doit être recalibré.
Le mieux est d'**attendre une mise à jour du trainer** : le recalibrage
demande des outils de débogage et des vérifications en jeu (le détail
est dans [Maintenance](maintenance.md), pour qui veut s'y essayer).
En attendant, n'utilise pas le trainer sur la nouvelle version du jeu :
même si certaines fonctions semblent marcher, des valeurs pourraient
être lues ou écrites au mauvais endroit. Les patchs de code, eux,
refusent de s'appliquer s'ils ne retrouvent pas le code attendu.

Pour éviter d'être pris de court, tu peux désactiver la mise à jour
automatique de MGS4 dans Steam (Propriétés du jeu → Mises à jour).

### Un bouton « Équiper » est refusé pendant une cinématique

Changer de tenue ou de visage en pleine cinématique fait planter le jeu :
ces boutons sont refusés tant qu'une cinématique est en cours. Le motif
OctoCamo et le gilet, eux, marchent en cinématique (le motif ne s'applique
qu'avec la combinaison OctoCamo).

### Le hold-up ne marche pas

Avec **Invisible**, le hold-up reste possible. S'il ne marche pas, vérifie
qu'aucun autre réglage ne bloque la réaction des soldats, et relance le
trainer s'il date d'avant la V2.4.1.

### La téléportation ne déplace pas Metal Gear REX

Dans REX, la position que modifie le trainer est celle de Snake (la
caméra la suit) ; le corps de REX garde la sienne. Ce cas n'est pas géré.

### Un objet n'apparaît qu'en « Mode avancé »

Certains objets internes font planter le jeu si on les équipe (par
exemple « Déstabil. SOP », un reste de Metal Gear Online) : ils sont
masqués en mode simple.

### Où sont mes profils, réglages et points de téléportation ?

À côté de l'exe : `profiles.json`, `settings.json` et
`teleport_points.json`. La mise à jour intégrée (depuis la V2.5) n'y
touche pas. Si tu télécharges un zip complet, copie-les à côté du nouvel
exe.

### Comment marche la mise à jour ?

Depuis la V2.5, le bouton **Mise à jour** interroge GitHub (une seule
requête, rien d'autre n'est contacté). S'il y a une nouvelle version, il
ne télécharge que les fichiers modifiés du dossier `app/`, vérifie leur
empreinte, puis les installe au redémarrage du trainer. Le résultat est
noté dans `update.log`, à côté de l'exe.

- Pour ne plus chercher au lancement, décoche la case dans la fenêtre de
  mise à jour (le bouton reste utilisable).
- Si la nouvelle version modifie la DLL injectée dans le jeu, relance le
  jeu pour en profiter.
- Certaines versions demandent de retélécharger le zip complet (quand
  l'exe lui-même change) : le bouton ouvre alors la page de
  téléchargement.
- Lancé depuis le code source (`python live_trainer.py`), le trainer
  signale les nouvelles versions mais ne se met pas à jour seul : utilise
  `git pull`.
