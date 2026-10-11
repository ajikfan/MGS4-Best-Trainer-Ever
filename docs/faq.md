# FAQ et problèmes courants

[← Retour au README](../README.md)

### Windows affiche « Windows a protégé votre PC »

L'exe n'est pas signé. Clique sur « Informations complémentaires », puis
« Exécuter quand même ».

### Mon antivirus signale le trainer

Il lit et écrit la mémoire du jeu, et injecte une petite DLL dans le jeu
pour certains réglages : les antivirus repèrent souvent ce genre de
technique. Le code source complet est dans ce dépôt.

### Le trainer reste sur « Non connecté »

Lance le jeu et charge une partie : le trainer s'accroche tout seul. S'il
ne s'accroche toujours pas après une mise à jour Steam du jeu, les
adresses ont probablement bougé : voir [Maintenance](maintenance.md).

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
`teleport_points.json`. Copie-les à côté du nouvel exe quand tu changes
de version.
