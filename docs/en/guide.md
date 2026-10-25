# Tabs and profiles guide

[← Back to the README](../../README.en.md) · *[Version française](../guide.md)*

What each tab and each setting does, and how to use profiles F1 to F11.

### Top bar (always visible)

- **Status**: connected to the game or not (the trainer attaches itself
  to `mgs4.exe` as soon as a save is loaded).
- **Advanced mode (raw values)**: shows the "Raw Value" and "Set (raw)"
  columns in the tables, and the internal items hidden by default (some
  crash the game: only use it if you know what you are doing).
- **Refresh Now** / **(Re)connect**: reads everything again right away /
  re-attaches to the game (after restarting the game, for example).
- **Update**: looks for a new trainer version on GitHub (the button turns
  green when there is one). Only the changed files are downloaded,
  checked, then installed when the trainer restarts (**Restart now** or
  **Later**). A checkbox turns off the check at startup.
- **Help**: summary, compatible version and version history.
- **Profile**: the last applied profile, and **Save as Fx** to store the
  current setup under a key (see "Profiles F1 to F11" below).
- **Language**: French or English (the trainer restarts).
- **Drebin Points**: current balance and total sales, each with a field
  and an OK button.

### Stats

The game's statistics, as stored in the save, sorted by theme:
**Combat** (enemies killed, headshots...), **Infiltration** (alerts,
enemies put to sleep...), **Movement**, **Items**, **Flashbacks**,
**Time** (in hours, minutes, seconds). Each value can be edited
directly.

### Game State

The live settings tab, in several groups:

- **Game Speed**: slider from 10 % to 300 % (100 % in the middle),
  **Pause** checkbox (in game, the game's own pause: the world is frozen
  but the game stays displayed; in the menus, full freeze), **Freeze
  Countdown** checkbox (the game's countdown no longer goes down: the 5
  minutes of the Metal Gear REX escape in act 4, the time limit of the
  Beauty fights), **Difficulty** list (Liquid to The Boss; changes the
  difficulty stored at the next save).
  On the keyboard, even with the game in front: **Pause** key for the
  pause, numpad **+** / **−** for ±10 % and **0** to go back to 100 %
  (a "Speed: x %" banner over the game).
- **Game Tools**: **Photo Mode** checkbox (or numpad *: free camera, see
  the **Photo Mode Controls…** button and what's new in V2.6.0), **White
  Room** button (against a Beauty, after the Beast form: the fight moves
  to the white room right away), **Main Menu** button (back to the main
  menu at any time during a game, after confirmation: unsaved progress is
  lost). The cutscene pause menu also gets a **QUIT** line while the
  trainer is open.
- **Alert**:
  - **Real state**: the current alert state (Normal, Alert, Evasion,
    Caution);
  - **Force**: imposes the alert state of your choice, or "Automatic" to
    let the game decide. The game stays in the chosen phase until you go
    back to Automatic, then resumes its countdown where it is (Alert →
    Evasion → Caution → Normal). From Normal, Alert, Evasion and Caution
    make a real soldier of the area raise the alert (music,
    reinforcements, search); Normal ends the current alert. Without
    soldiers in the area, the game handles no alert: forcing has no
    effect;
  - **No Alerts**: the general alert never goes off, whatever the cause
    (sight, noise, body found, Dwarf Gekko lasers...). Enemies still react
    individually: a soldier who sees you shows his "!", aims and may shoot
    at you, but with no general alert, reinforcements or alert music.
- **Weapons & Combat**:
  - **Infinite Ammo**: the game's own infinite ammo on every weapon
    (infinity symbol on the HUD);
  - **No Reload**: the magazine no longer empties (and the Metal Gear
    REX machine gun no longer overheats);
  - **Unlimited Suppressors**: the mounted suppressor no longer wears
    out;
  - **One Shot, One Kill**, with the **Lethal / Non-lethal** choice,
    whatever the weapon: in Lethal, any enemy hit goes down in one shot;
    in Non-lethal, soldiers and Gekko are put to sleep at the first hit,
    and bosses are knocked out (stamina drained, health untouched).
    Other machines (tanks, helicopters, vehicles, Metal Gear RAY,
    destructible objects) are destroyed in both modes, Dwarf Gekko
    destroyed in Lethal and paralyzed in Non-lethal. Bosses: see [the
    bosses page](boss.md);
  - **Rail Gun / Solar Gun Always Charged**: fully charged shot as soon
    as you pull the trigger (and Metal Gear REX's laser at level 5).
- **Snake**:
  - **Untouchable**: no impact affects Snake (no damage, no knockback, no
    knockout); when piloting Metal Gear REX, REX ignores hits too (no
    damage, no reaction);
  - **Invisible**: soldiers, Gekko and Dwarf Gekko no longer see him, even
    standing right in front of them, and an unsuppressed shot no longer
    puts them on alert (hold-ups still work). Combine with "No Alerts" so
    that nothing triggers the general alert;
  - **No Back Pain**: Snake no longer holds his back, neither after a high
    fall (normal landing, the fall damage remains) nor after crouching
    for a long time;
  - **Trigger**: pick an action in the list and click **Trigger** to make
    Snake play it. At the top: **High fall**, **Crouching back pain**
    (only crouching and still) and **Vomit** (standing or crouching
    version depending on the posture), then 214 of the game's animations
    (hits, CQC, falls, wake-ups, ladders, hanging, electrocuted,
    "something stinks"...), each with its number. Actions start in any
    posture, with no damage or sound; Snake then goes back to his posture
    (crouching, prone, face down, on his back). Animations meant for
    another posture (ladder, hanging...) can look strange.
- **Whole area**: acts in one click on the whole area, through the game's
  own functions, whatever the current state (a sleeping enemy can be
  killed).
  - **Target**: **Enemies**, **Rebels**, **All NPCs** (civilians, bosses
    and the Rat Patrol are never targeted) or **Rat Patrol** (Kill, Knock
    out and Sleep only);
  - **Kill**: soldiers, Gekko, Dwarf Gekko, vehicles, tanks,
    helicopters and Sliders (machines count as enemies, vehicles
    according to their side);
  - **Knock out**: soldiers fall unconscious, Gekko fall to the ground,
    Dwarf Gekko are paralyzed for a few seconds, the Gekko of the Metal
    Gear REX escape (act 4) crouch for a few seconds;
  - **Sleep**: soldiers and Gekko (neither Dwarf Gekko nor the Gekko of
    the REX escape sleep);
  - **Laugh**, **Cry**, **Rage**, **Scream**: the Beauties' emotions, on
    awake soldiers, for about thirty seconds;
  - **Rebels: Neutral / Hostile**: when checked, imposes the rebels'
    attitude towards Snake (an alert already under way runs its course).

### Gauges

All the gauges, always visible, sorted by group (the page scrolls if the
window is small):

- **Snake**: Health, Stamina, **Grip** (hanging from a ledge), **Oxygen**
  (underwater), Stress, Solid Eye battery;
- **Vehicles**: **Drebin 893** (the act 2 vehicle), **Van** (the one to
  protect in act 3), Metal Gear REX health;
- **Rat Patrol Team 01**: one box per member (**Meryl**, **Johnny**,
  **Jonathan**, **Ed**; acts 1 and 5 for Meryl and Johnny, act 1 for
  Jonathan and Ed), with their live state (active, hit, asleep, knocked
  out, dead), a **Wake up / Put to sleep / Knock out / Kill** list and
  the **Apply** button, then their health and stamina.

For each one: a percentage slider to set it, and a **Lock** checkbox
that keeps it at that level (Health locked at 100 % = infinite health,
Grip at 100 % = infinite grip...). A locked gauge no longer moves at all:
the game no longer writes to it. Missing gauges show "not hanging", "not
underwater" or "not present"; locking them then locks them at 100 %,
ready for when they are used.

Rat Patrol: a locked gauge is no longer written by the game, for that
member only (health and stamina separately; the soldiers around take
their damage normally). Their health at 0 kills them (Meryl's death in
act 5 fails the mission), their stamina at 0 knocks them out at once.
Wake up gets them up right away; Put to sleep makes them fall slowly
("Z"s); Knock out makes them fall suddenly (stars); a teammate may come
and wake them up.

### Bosses

One box per boss, in game order: **Laughing Octopus**, **Raging Raven**,
**Crying Wolf** and **Screaming Mantis** (**Beast** and **Beauty**
columns, with the **White room** button on the Beauty side), **Vamp**,
**Metal Gear RAY** and **Liquid Ocelot** (with the **Final fight
phases**). Each form has its health and stamina, slider and **Lock**
checkbox as in the Gauges tab; the box of the current boss reads "in
progress", the others show "not present".

The on-screen bars follow the slider at once. The lock brings the gauge
back up at each refresh: a short dip remains visible after a hit. Releasing
the health slider at 0 finishes the boss, the stamina slider knocks it
out: the trainer makes it take a shot from Snake (lethal or not), and
the game plays the rest normally (Beauties included, whatever their
phase). For Laughing Octopus's beast, Screaming Mantis's
beast, Vamp and Liquid Ocelot, health and stamina never go below 1 (their
phases and scripts depend on health). Locked health prevents the phase
changes tied to health. Confirmed on Raging Raven and Laughing Octopus;
the other bosses are recognized by their class name in the game.

### Weapons

All the game's weapons, sorted by category (handguns, assault rifles,
sniper rifles, explosives, accessories...). For each weapon:

- **State**: Not owned / Locked / Usable;
- **Ammo**: the reserve, editable;
- **Equip**: puts the weapon in hand immediately, without a menu. Only
  active for owned weapons;
- **Customize** (weapons with accessory slots): one choice per slot
  (suppressor, light, laser, sight, underbarrel), applied right away,
  even on the weapon in hand. Accessories you don't own are greyed out.

In the **Accessories** section, the **Ammo / Quantity** column gives the
number of suppressors and the grenade launchers' ammo (Masterkey, XM320,
GP-30), editable.

A name filter finds a weapon quickly.

### Items

Items (rations, medicine, Solid Eye, iPod, special items...), with their
state (Locked / Obtained) and, for consumables, the quantity. The Solid
Eye battery is shown on its row.

### OctoCamo

- **Equipped**: the OctoCamo pattern worn right now.
- **FaceCamo**: the faces, with their state and an **Equip** button.
- **Vest**: the vests, with an **Equip** button.
- **Octocamo**: the 21 patterns of the camouflage menu, with an
  **Equip** button (special patterns included). The patterns given from
  the start can be hidden from the game's menu.
- **Saved patterns**: the 10 slots of patterns captured on a surface and
  then saved, with their name when known (Concrete, Tile, Hand...), an
  **Equip** button, and a way to forget a pattern.

Equipping a pattern also works in the middle of a cutscene.

### Outfits

Outfits and disguises (Middle East, South America, Eastern Europe,
Snake's suit, Altaïr...), with their state and an **Equip** button. An
act's disguises work in the other acts.

### Figures, Songs, Unclassified

Figures and iPod songs to unlock or remove, and the items not identified
yet (research tab).

### Teleportation

- **Current location**: the current act and area (official names from
  the game).
- Snake's **Current position**, and **Save Here...** to keep it under a
  name.
- **X / Y / Z**: manual input, **Refresh From Game**, and **Teleport
  Here**.
- **List of points** in the current area (name, area, coordinates):
  double-click or **Teleport to Selected Point**, **Delete Selected
  Point**, **Link to current area** (for a point without an area).
- When piloting **Metal Gear REX**, teleporting moves REX itself (placed
  a little above the point, it falls back to the ground).
- **Show points from all areas**.
- **Export** / **Import** points as a JSON file.

Default points are provided on first launch.

## Profiles F1 to F11

A profile is a snapshot of the "Game State" tab stored under a keyboard
key, from F1 to F11.

**Creating a profile**

1. Set the "Game State" tab the way you want (checked boxes, Lethal or
   Non-lethal, locked gauges and their level, speed, difficulty, forced
   alert…) and mount the accessories you want on your weapons.
2. Click **Save as Fx** in the top bar.
3. Pick the key (F1 to F11), give a name ("godmode", "vanilla"…), then
   **Save**. A key already in use can be replaced (the trainer asks for
   confirmation) or freed with **Delete**.

What is saved: the speed, the difficulty, the forced alert, all the
checkboxes (No Alerts, Infinite Ammo, No Reload, Unlimited Suppressors,
One Shot One Kill, Rail Gun / Solar Gun Always Charged, Untouchable,
Invisible, No Back Pain), the Lethal / Non-lethal choice, each gauge's
lock and level, and the accessories mounted on each weapon. What is not:
the pause, the items and the weapons themselves (a profile doesn't give
you a weapon; when applied, only the accessories your game owns are
mounted).

**Using a profile**

- **When the trainer starts**, a window lets you pick the session's
  profile (or none).
- **In game**, press the profile's key: it applies right away, even with
  the game in front. Only the keys that have a profile are taken from the
  game; the other F keys stay with the game, and F12 stays free for Steam
  screenshots.
- **The same key a second time** turns the profile off and restores the
  setup you had before turning one on. Pressing another key switches
  directly to the other profile (and its key turns it off in turn, back
  to the starting setup).
- **Confirmation**: at each key press, the game itself plays its "GO"
  sound (the Solar Gun charged shot one, at the game's volume), and a
  banner shows for 2 seconds at the top of the game window: "F2 ·
  godmode — on" (green border) or "— off" (red border). The banner takes
  neither the keyboard nor the mouse. It shows in windowed and borderless
  fullscreen; exclusive fullscreen may hide it (not tested).
- The top bar shows the last applied profile.

**Two profiles are provided** as long as you haven't saved your own:
**F1 "Normal"** (everything off, no locked gauge: the original game) and
**F2 "God mode"** (all boxes checked, Non-lethal, all gauges locked full,
stress at 0). They touch neither the difficulty nor the accessories. You
can replace or delete them like the others.

Profiles are stored in `profiles.json`, next to the exe (or the script),
created at the first save.

## Keyboard shortcuts

- **Pause** (the keyboard key): checks or unchecks the Pause box (in
  game, the game's own pause; in the menus, full freeze).
- **Numpad +** / **−**: game speed +10 % / −10 % (from 10 % to 300 %;
  held key = repeated). **Numpad 0**: back to 100 %. The same banner shows
  "Speed: x %" over the game.
- **Numpad \***: turns photo mode on or off (the controls are listed in
  the **Photo Mode Controls…** window).
