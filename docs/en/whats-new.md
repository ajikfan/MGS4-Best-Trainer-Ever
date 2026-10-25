# What's new in each version

[← Back to the README](../../README.en.md) · *[Version française](../nouveautes.md)*

Details of the latest versions. The full history is also in the trainer's **Help** button and on the [releases](https://github.com/ajikfan/MGS4-Best-Trainer-Ever/releases) page.

## What's new in V2.7.0

### Bosses tab

New tab: one box per boss, in game order. Laughing Octopus, Raging
Raven, Crying Wolf and Screaming Mantis have their **Beast** and
**Beauty** forms side by side (with the **White room** button on the
Beauty side); then **Vamp**, **Metal Gear RAY** (health only, he has no
stamina) and **Liquid Ocelot**, with the **Final fight phases** (phases 1
to 4 and last 3 punches, through the game's transitions), moved from the
Gauges tab.

Each form has its health and stamina, slider and **Lock** checkbox. The
box of the current boss reads "in progress", and its on-screen bars
follow the slider. Releasing **health at 0** finishes the boss,
**stamina at 0** knocks it out: the trainer makes it take a shot from
Snake and the game plays the rest normally (Beauties included, whatever
their phase; Vamp: down, then the syringe triggers by itself). Liquid and
Mantis's beast stay at 1 minimum.

### Load from the pause menu

The pause menu gets a **Load** entry, right above Save (in place of
Database). It opens the game's load screen; after loading, a fade to
black, the menu closes, and the game resumes without counting a continue.

### One Shot, One Kill

- **Laughing Octopus**: defeated by the first shot, her phases are
  skipped (Lethal and Non-lethal).
- **Screaming Mantis**: one bullet on a doll makes her drop it, one
  bullet on Mantis defeats her, no Mantis doll needed.
- **Vamp**: down on the first shot, then defeated without the syringe
  once he is on the ground (Non-lethal too).
- **Liquid Ocelot**: the first hit ends the fight.

### Untouchable

Against Screaming Mantis, her strings no longer hold Snake, as after the
syringe.

### Whole area

Kill also targets the SMP and Gekko of the bike chase, the mounted
soldiers and the SMP on the van in act 3, and the **Sliders** (bike chase
and Raging Raven). Vehicles are filtered by side: the escort's allied
bikes are spared. Mini Gekko are now called **Dwarf Gekko**.

### Cutscene pause menu

The line now shows the game's own text, "Return to the title screen", in
the game's language. The game's confirmation opens in front of the menu,
a fade to black comes before returning to the main menu, and the line
disappears together with the menu.

### Photo mode

Left click to **go down**, right click to **go up**. W and S no longer
zoom in some cutscenes, a click is no longer taken for a game key, and
the banner color is fixed. The DLL changed: restart the game after
updating.

### Misc

- Load and the cutscene menu line work again after the trainer was
  closed abruptly.
- English documentation, and an **Online guide** button in the help.

## What's new in V2.6.0

### Photo mode

New checkbox in the **Game Tools** group, or numpad **\***: a free
camera, driven with the game's controls, with a controller as well as
with keyboard and mouse (the **Photo Mode Controls…** button lists
them):

- **left stick** (WASD): move;
- **right stick** (mouse): aim the camera;
- **RB or RT** (left click): go up;
- **LB or LT** (right click): go down;
- hold **X** (**Q** or **Shift** on the keyboard): go fast;
- **Ctrl** + WASD: go slow;
- **D-pad up / down** (wheel): zoom, the cutscene zooms being
  neutralized during the mode;
- **Y** (**E** or **Pause** on the keyboard): freeze or resume time;
- **A** (**Space** on the keyboard): teleport Snake to the camera's
  position, without leaving photo mode, time frozen or not (not during
  cutscenes).

Time is frozen when the mode starts (the world stops but the camera
moves); Y resumes it to shoot a moving scene, cutscenes included. When
leaving, the Pause box goes back to its previous state. While the mode is
on, Snake receives no input and the game's HUD (health, radar, weapons,
items) is hidden. The camera is moved by the trainer's DLL, at every game
frame: after the update, restart the game to load the new DLL.

### Pause

In game, the **Pause** key (or the box of the same name) now uses the
game's own pause instead of freezing the whole process: the world is
frozen, but the game stays displayed and responsive, and photo mode
works while paused. In the menus, the game is frozen as before.

### Cutscene pause menu

The cutscene pause menu (SKIP / CONTINUE) gets a **QUIT** line:
selecting it takes you back to the main menu. No game file is modified:
the trainer adds the line in memory while it is open (the game handles
the navigation and the selection bar, the trainer draws the word on top).

### Metal Gear REX

- **Teleportation**: when you pilot REX (act 4 escape, fight against
  Ray), it moves REX itself, Snake in the cockpit. It is placed a little
  above the point and falls back to the ground, with no fall damage.
  Points are taken as REX: save them while piloting it.
- **Untouchable**: attacks no longer cause REX any damage or reaction
  (only contact pushes, Ray shoving it, remain).

### Freeze Countdown

New checkbox in the Game Speed group: the game's countdown no longer
goes down: the 5 minutes to get out of the tunnel during the REX escape,
or the time limit of the Beauty fights (white room). It resumes from the
same value once the box is unchecked. The invisible 3-minute delay that
leads to the white room keeps running, though.

### White Room

New button in the Game Tools group: against a Beauty, after the Beast
form, the fight moves to the white room right away, without waiting for
the 3 minutes. In the white room itself, it does nothing (the same
counter is used as the timer there: setting it to 0 would kill the
Beauty).

### Main Menu

New button in the Game Tools group: back to the game's main menu at any
time during a game, even during a cutscene, like the pause menu's "Yes".
A confirmation reminds you that anything unsaved will be lost; outside a
game (main menu, loading), the button does nothing.

### Whole area

- The Gekko of the REX escape are finally targeted: **Kill** blows them
  up, **Knock out** makes them crouch for a few seconds (they get up by
  themselves, as with One Shot, One Kill in Non-lethal). They don't
  sleep: Sleep ignores them.

## What's new in V2.5.3

### Rat Patrol Team 01

- New: **Jonathan** and **Ed** (act 1).
- One box per member: their live state (active, hit, asleep, knocked
  out, dead) and the **Wake up**, **Put to sleep**, **Knock out**,
  **Kill** actions, above their health and stamina.
- A locked gauge is no longer rewritten constantly: the game no longer
  writes to it at all, for that member only.

### Whole area

- Kill, Knock out and Sleep work on act 1 PMCs.
- New **Rat Patrol** target (Kill, Knock out, Sleep); **All NPCs** never
  targets the Rat Patrol anymore.

### Misc

- Locked Snake gauges: no more rewriting at every refresh, the game
  freeze is enough.

## What's new in V2.5.2

### No Back Pain

New checkbox in the Snake group: Snake no longer holds his back, neither
when landing from a high fall (normal landing, the fall damage remains)
nor after crouching for a long time. Saved in profiles F1 to F11.

### Trigger an action

New list in the Snake group, with a **Trigger** button:

- **High fall**, **Crouching back pain** (only crouching and still) and
  **Vomit** (standing or crouching depending on the posture);
- then 214 of the game's animations, with their number: hits, CQC,
  falls, wake-ups, ladders, hanging, electrocuted, "something stinks"…

Actions start in any posture, with no damage or sound, and Snake then
goes back to his posture (crouching, prone, face down, on his back).
Animations meant for another posture can look strange.

## What's new in V2.5.1

### Gauges tab

The gauges leave the "Game State" tab, which had become too long, for a
tab of their own, sorted by group (Snake, Vehicles, Allies), always
visible and on a scrolling page.

### Allies: Meryl and Johnny

- Health and stamina of **Meryl** and **Johnny** (acts 1 and 5), "not
  present" when they aren't there.
- Both their gauges locked: the game ignores the hits they take. Only
  they are protected, the soldiers around take their damage normally.
- Health at 0: they die (in act 5, Meryl's death fails the mission).
  Stamina at 0: knocked out at once, without waiting for a hit.

### Misc

- Whole area: Knock out (soldiers) and Rage confirmed in game.
- First update by small files: since V2.5, the "Update" button installs
  this version without downloading everything again.

## What's new in V2.5

### Whole area

New group in the "Game State" tab: one action on the whole area in one
click, through the game's own functions, whatever the current state (a
sleeping enemy can be killed, a sleeping Gekko destroyed).

- **Target**: Enemies, Rebels or All NPCs (never civilians or bosses).
  Machines count as enemies.
- **Kill**: soldiers, Gekko, mini Gekko, vehicles, tanks and
  helicopters.
- **Knock out**: soldiers knocked out, Gekko on the ground, mini Gekko
  paralyzed.
- **Sleep**: soldiers and Gekko (mini Gekko don't sleep).
- **Laugh, Cry, Rage, Scream**: the Beauties' emotions on awake soldiers,
  for about thirty seconds.
- **Rebels: Neutral / Hostile**: imposes the rebels' attitude towards
  Snake while the box is checked.
- Settings saved in profiles F1 to F11.

To be confirmed in game: Knock out on soldiers, and Rage.

### Built-in update

New **Update** button (green when a newer version exists). The trainer
only downloads the changed files, a few hundred KB instead of the full
zip, checks their fingerprint, then installs them at restart. The check
at startup can be turned off in the same window. For this, the exe now
only contains the engine (Python and the interface); the trainer's code
is next to it, in `app/`. This V2.5 is therefore still downloaded in
full; the next ones won't be. Details in the
[FAQ](faq.md#how-does-the-update-work).

### One Shot, One Kill and alert redone

- **One Shot, One Kill** is now entirely our own code: in Non-lethal,
  soldiers and Gekko are put to sleep at the first hit, whatever the
  weapon; the Mosin-Nagant also destroys Gekko.
- **Forced alert**: back to Automatic, the game resumes its countdown
  where it is (before: immediate return to Normal).
- **No Alerts** and **No Reload** go through the game's own mechanisms
  (the latter uses its infinite magazine).
- The trainer no longer uses any code taken from the MGS4.CT Cheat
  Engine table (see the README credits).

## What's new in V2.4.1

- **Mini Gekko fix**: in Non-lethal "One Shot, One Kill", walking into a
  group of mini Gekko could crash the game. Snake's contact sent them a
  paralysis restarted at every frame; they now flinch normally, and a
  shot still paralyzes them.
- **OctoCamo fix**: patterns with their own colours (Corpse and special
  patterns) looked washed out when equipped from the trainer: the trainer
  replaced their tints with those of the save's table. They are now
  identical to the menu's.
- **Invisible**: an unsuppressed shot no longer puts enemies on alert.
  They can still hear and come to look, and hold-ups still work.
- **Code**: the trainer is now split into several files (`mgs4trainer/`
  package); `python live_trainer.py` starts as before.

## What's new in V2.4

### Profiles F1 to F11 and keyboard shortcuts

The whole setup of the "Game State" tab (and the weapons' accessories)
stored under a key F1 to F11, usable even with the game in front, with
the game's "GO" sound and a banner over the game; Pause key and numpad
+ / − / 0 for the speed. Full instructions in the
[guide](guide.md#profiles-f1-to-f11).

### Weapons: customize the accessories

- New **Accessories** column in the Weapons tab, with a **Customize**
  button on each weapon that has slots. It opens a window with one list
  per slot, like the game's menu: Suppressor, Light, Laser, Sight,
  Underbarrel (with "None"). The choice applies right away, even on the
  weapon Snake holds, and the game's customization menu updates if it is
  open. Accessories your game doesn't own are greyed out.
- In the **Accessories** section, the **Ammo / Quantity** column shows
  and edits the number of suppressors you own and the ammo of the
  mounted grenade launchers (Masterkey, XM320, GP-30).
- New **Unlimited Suppressors** checkbox ("Game State" tab): the mounted
  suppressor no longer wears out with each shot, whatever the weapon.

### Forced alert: a real alert

Forcing **Alert** now makes a real soldier of the area raise the alert:
music, reinforcements, search, as if Snake had been spotted, and the
countdown stays at 99.99 while the alert is forced (before, it showed
0.00). Back to **Automatic**, the game takes over and goes through
Evasion, Caution then Normal as usual. In an area without any soldier,
the game handles no alert: forcing it has no effect.

### Gauges: locked for good, and two new ones

- **No more fluctuation**: before, a locked gauge was rewritten by the
  trainer at every refresh, and the game had time to move it in between
  (stress going from 0 to 0.1, health dropping and coming back up when
  Snake is hit). Now, locking health, stamina, stress, the Solid Eye
  battery, the Drebin 893, the Van or Metal Gear REX prevents the game
  itself from writing to the gauge: it no longer moves at all.
- **Drebin 893**: the health of the act 2 vehicle. **Van**: the health
  of the van to protect in act 3. Two new lockable rows, showing "not
  present" outside their sequence.
- **Grip and oxygen**: a lock can no longer stay stuck at 0 % (which
  happened with a profile saved while the gauge was inactive, and let
  the bar go down). Locking one of these gauges while it is inactive
  locks it at 100 %.

### One Shot, One Kill: whatever the weapon, in both modes

The rule is now the same everywhere, as for soldiers:

- **Lethal**: every hit kills, with any weapon, including the Mk.2
  tranquilizer pistol;
- **Non-lethal**: every hit knocks out by draining stamina, never
  touching health, even with a lethal weapon.

What has no stamina is **destroyed in both modes**: Gekko, tanks,
helicopters, Millennium Park vehicles, Metal Gear RAY and destructible
objects. The Mk.2 now hits them too (helicopters, Gekko, gates
confirmed; tanks prepared but not tested for lack of a tank).

**Mini Gekko**: destroyed outright at the first hit in Lethal (Mk.2
included, without going through paralysis); **paralyzed** in
Non-lethal, with any weapon (before, a Mk.23 bullet destroyed them).

**Gates and destructible objects**: they fall in one hit, but only when
the game allows it. Some gates are protected by the story until the
planned sequence has happened; forcing them earlier blocked progress
(script trigger never reached). The trainer therefore respects this
lock: the gate resists while the game protects it, then gives way at the
first shot once the time has come.

**Bosses**, still through the kill planned by the game (phase
transitions and fight endings handled by the game):

| Boss | Lethal | Non-lethal |
|---|---|---|
| Laughing Octopus | one hit per phase | stamina drained, one hit per phase (confirmed) |
| Raging Raven | one hit | stamina drained in one hit, Beast and Beauty forms (confirmed) |
| Crying Wolf | one hit, any weapon (confirmed) | stamina drained in one hit, Beast and Beauty forms (confirmed) |
| Screaming Mantis | one hit with the doll (confirmed) | stamina drained in one hit with the doll (confirmed) |
| The four Beauties | one hit (Screaming Beauty confirmed) | stamina drained in one hit (confirmed) |
| Metal Gear RAY | destroyed in one hit (confirmed) | destroyed in one hit (confirmed) |
| Vamp | down in one shot, the syringe is still needed | not covered |
| Liquid Ocelot | see below | see below |

For Octopus, Raven and the Beauties, the "any weapon" Lethal (Mk.2
included) is prepared but has not been checked again in game.

**Liquid Ocelot** (final fight, with fists, so the same in both modes):
at the first hit, his health **and** stamina drop to the phase floor;
the next hit starts the next phase. The last 7 scripted hits are not
covered.

### Metal Gear REX

- **Health**: lockable ("Metal Gear REX Health" row), it no longer goes
  down at all.
- **Machine gun**: with **No Reload**, it no longer overheats. Heat
  normally rises with each shot, and the weapon locks for a while at
  100 %; the trainer prevents the heat from rising.
- **Missiles**: with **Infinite Ammo**, always 15/15. REX has 15 tubes,
  each with its own reload time after a shot (that's why the counter
  goes back up by itself); the tubes always stay ready.
- **Laser**: with **Rail Gun / Solar Gun Always Charged**, it goes to
  level 5 (the maximum, with its sound) as soon as you start charging,
  instead of going through levels 1 to 5. The laser also has an energy
  reserve (the HUD's "x/100") that each shot uses: it no longer goes
  down, so every shot fires at level 5. The beam keeps its normal
  duration.
- Teleportation didn't move REX (only the camera): fixed since, it moves
  REX itself.

### Invisible: mini Gekko too

Mini Gekko no longer detect Snake: their lasers no longer recognize him
(no red laser, no alert), and neither proximity nor contact makes them
react (no more "!"). A switch to Caution remains if Snake stays still
among them; "No Alerts" blocks it.
