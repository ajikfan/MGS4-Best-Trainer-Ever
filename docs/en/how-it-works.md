# How it works

[← Back to the README](../../README.en.md) · *[Version française](../fonctionnement.md)*

How each feature acts on the game, its limits, and what was checked in game.

## Overview

Uses the pointer chain documented by the external repository
[zexk/bbtracker](https://github.com/zexk/bbtracker) (MIT license) to
locate the current game structure (`varbuf`) directly in memory, without
scanning. A sanity check (`sanity_check`, based on two fields always at 0
in every known save) runs before allowing the slightest write — if the
game doesn't respond as expected, the trainer refuses to write rather
than risk corrupting the game's memory.

## Technical details

The following sections explain how each feature works, its limits, and
what was checked in game.

### Game speed control

"Game State" tab: slider centred on normal speed (100%), which can be
dragged left to slow down (down to 10%) or right to speed up (up to
300%), plus a separate "Pause" checkbox.

- **Pause**: in game (V2.6.0), the game's internal pause, the one it
  uses itself to reload Snake's model, called by the DLL: the world is
  frozen but the game keeps drawing every frame (photo mode remains
  usable). In the menus, or if it fails, full freeze of the process
  (`NtSuspendProcess`), as before.
- **Slow-motion/fast-forward**: requires injecting a small DLL
  (`native/speedhack_x64.dll`, already compiled and provided in this
  repository — no compiler needed to use it as is) into `mgs4.exe`, which
  patches its import table to fool its internal clock
  (`QueryPerformanceCounter`/`timeGetTime`) into believing time flows
  faster or slower. Confirmed working in game both ways (2026-09-26).
  Since V2.2, the DLL is injected as soon as the trainer attaches to the
  game (it starts at normal speed, with no effect until a setting is
  turned on): the "Equip" buttons and the other patches are ready without
  touching a setting first.

The DLL stays in the game when the trainer is closed, with its settings.
Since V2.3, at each attach, the trainer sends it the actual state of the
"Game State" tab's checkboxes: a setting left active from a previous
session is turned off if its box is unchecked.

### Difficulty

"Game State" tab: "Difficulty" list (Liquid, Naked, Solid, Big Boss, The
Boss), read and written live. Checked effect: this is the difficulty
stored at the next save (rank and end screen included). No change seen in
game: a bullet removes the same health in Liquid and in The Boss
(measured), and enemies don't seem more vigilant.

### Infinite Ammo / No Reload

"Game State" tab: two separate checkboxes.

- **Infinite Ammo (V2.3)**: turns on the **game's own** infinite ammo.
  Each weapon has an "infinite reserve" flag, which the game already uses
  for the Solar Gun and the Patriot; the trainer sets it on every weapon
  with ammo (69, grenades and explosives included). The reserve no longer
  goes down and the HUD shows the infinity symbol, without touching the
  equipped item (the Solid Eye stays active). The Solar Gun, whose
  "reserve" is the magazine recharged by sunlight, switches to an
  infinite magazine and stays full. Unchecking restores the weapons.
  (Before V2.3: reserves rewritten in a loop, which slowed the trainer
  down.)
- **No Reload**: code patch that removes the write of the magazine's new
  ammo count after a shot, whatever the weapon.

### One Shot, One Kill / Non-lethal

"Game State" tab: "One Shot, One Kill" checkbox + Lethal/Non-lethal
selector. These are code patches (game instructions modified, original
bytes checked before writing).

**Soldiers (redone on 13 October 2026).** The soldiers' damage function
(found with a hardware breakpoint on a soldier's health) already knows a
"kill": a special damage value that empties the whole targeted gauge.
The trainer gives this value to every hit, whatever its type, then picks
the gauge:

- **Lethal**: health — the soldier dies at the first hit, tranquilizer
  darts included;
- **Non-lethal**: sleep — the soldier falls asleep at once, bullets
  included, without ever losing health.

The player has their own damage function, they are never affected. Up to
V2.4.1, soldiers went through a hook ported from the "aob Damage" script
of the `MGS4.CT` table (RMLSNK), which forced health to 0 when it was
written.

**Bosses (V2.3): the game's own kill.** Each boss has its own damage
function, found in the debugger starting from its HUD gauge. When
possible, the patch makes each hit go through the "kill" planned by the
game (special damage that removes all remaining health): phase
transitions and ending sequences are still handled by the game.
Confirmed in game (2026-10-04):

- **Laughing Octopus**: one shot per phase (the game resets health to
  the phase threshold);
- **Raging Raven**, **Crying Wolf**, **Metal Gear RAY**: one shot;
- **the four Beauty forms**: one shot;
- **Vamp**: down in one shot, the syringe is still needed (fight
  mechanic, not bypassed);
- **Liquid Ocelot** (final fight): two hits per phase (health drops to
  the phase floor, then the next phase). The last phase of 7 scripted
  hits is not covered;
- **Screaming Mantis**, Beast form: her health can't go below 50, only
  her stamina triggers the defeat; the patch empties both in one hit
  (confirmed in V2.4). Only the Mantis doll can reach her, as in the
  game.

The old system (health forced in steps, synchronized on a real hit) was
removed on 12 October 2026, along with the boss tracking hooks it used
(taken from the "Bosses 2" and "Bosses Laughing Octopus" scripts of the
`MGS4.CT` table): it only served as a fallback if the patches refused to
apply.

**Gekko and tanks (redone on 13 October 2026).** They share the same
damage function, which also knows the game's "kill": the trainer makes
every hit go through it in Lethal (tanks: in both modes). In Non-lethal,
a Gekko falls asleep at the first hit, any weapon, wherever it is hit:
the trainer treats each hit as a Mk.2 dart in the leg and empties both
its tranquilizer gauges at once. Up to V2.4.1, Gekko and tanks went
through a hook ported from the "aob Damage Gecko" script of the `MGS4.CT`
table.

**Tanks: any weapon (V2.1).** Normally, a tank ignores most weapons: its
collision code only registers hits from 4 specific weapons, and all
other shots (bullets included) are discarded before even being counted,
so "One Shot, One Kill" couldn't apply. Two extra code patches, active
only when "One Shot, One Kill" is checked, lift this filter for the
**player's** shots and send the hit down the damage path: a simple rifle
bullet then destroys a tank (confirmed in game, 2026-10-03). Only the
rifle has been tested so far; a particular weapon could still be
filtered further down the chain.

**Helicopters, vehicles, mini Gekko, gates (V2.3).** Same principles,
each with its own patches (confirmed in game, 2026-10-04):

- **helicopters**: originally, only rocket launchers, explosives, the
  M82A2 and the Rail Gun hit them; all weapons now count and each hit
  removes all their health;
- **Millennium Park vehicle**: its weapon filter is lifted;
- **mini Gekko**: destroyed at the first impact (V2.4: paralyzed in
  Non-lethal);
- **destructible objects** (gates to bring down with the tank cannon...):
  give way at the first impact. The minimum imposed by the level
  (possible story lock) is kept.

The DLL is provided already compiled (`native/speedhack_x64.dll`): no
compiler is needed to use the trainer. To modify it, see [Recompiling
the DLL](maintenance.md#recompiling-the-dll).

**V2.4: whatever the weapon, in both modes.** General rule: in Lethal
every hit kills, in Non-lethal every hit knocks out through stamina
without touching health, as for soldiers, Mk.2 and lethal weapons
included. Confirmed in game (2026-10-10):

- **machines** (no stamina) destroyed in both modes: Gekko, tanks,
  helicopters, vehicles, **Metal Gear RAY**, destructible objects; the
  Mk.2 hits them too (helicopters, Gekko, gates confirmed; tanks not
  tested for lack of a tank), as well as the Mosin-Nagant's tranquilizer
  rounds (Gekko confirmed);
- **mini Gekko**: destroyed at the first hit in Lethal, paralyzed in
  Non-lethal, Mk.2 included;
- **Crying Wolf**, **Raging Raven**, **Screaming Mantis** (with the doll,
  Beast and Beauty forms), **Laughing Octopus** and the Beauties: stamina
  drained in Non-lethal; in Lethal, Crying Wolf and Screaming Mantis
  confirmed with any weapon, Octopus, Beauty and Raven prepared for
  stamina weapons but not checked again in game yet;
- **Liquid Ocelot** (final fight, with fists): in both modes, health
  **and** stamina at the phase floor at the first hit, the next one starts
  the next phase. The last 7 scripted hits are not covered.

The Lethal and Non-lethal patches share some sites (Crying Wolf): when
switching modes, those of the inactive mode are removed before placing
the others.

### Rail Gun / Solar Gun Always Charged

"Game State" tab, "Weapons & Combat" group. Code patch: the Rail Gun's
and the Solar Gun's charge is full as soon as the trigger is pulled, with
the visual effect and Snake's shout of a real fully charged shot, and
without depending on the Solar Gun's solar energy. The game converts the
charge time into a level (1 to 3) in a single function, used both for the
effects and for the projectile's flags; the patch makes it return the
maximum level as soon as charging has started. Two complementary patches
also force the maximum level in the flags of the received hit (soldiers
and tanks), so that a fully charged shot's damage applies everywhere.
Confirmed in game (2026-10-03), including a tank destroyed by a single
quick Rail Gun shot.

### Snake: Untouchable, Invisible, gauges (V2.3)

"Game State" tab, "Snake" group and the gauges table.

- **Untouchable**: code patch that makes Snake ignore all impacts
  (bullets, explosions, mines, hits, non-lethal attacks): no damage, no
  knockback, no knockout.
- **Invisible**: soldiers and Gekko no longer see Snake, even standing
  right in front of them, as with the Stealth Camo but without the
  transparency (the camo index shows 99 %). Since V2.4, mini Gekko no
  longer detect him either (lasers, proximity, contact); a switch to
  Caution remains if Snake stays still among them. Since V2.4.1, an
  unsuppressed shot no longer causes an alert: the game stores all
  noises in a shared table that soldiers check, and the trainer prevents
  shots from being recorded there. Other noises (knocks on a wall,
  footsteps) stay active, since the hold-up's "Freeze!" goes through the
  same table. Also check **"No Alerts"** so that nothing triggers the
  general alert: the two settings complement each other.
- **Grip** and **Oxygen**: new rows in the gauges table, with a slider
  and a "Lock" box like the others. They only exist while hanging from a
  ledge or underwater ("not hanging" / "not underwater" otherwise).
  Locked at 100 %: infinite grip or oxygen.

### No Alerts: how it works

The game's alert state is recomputed every frame by a function that goes
through the soldier units: each one proposes a state and gives its
timers (Alert countdown, Evasion and Caution timers). The function keeps
the most serious one and copies the highest timers. The trainer
neutralizes these three takes (code patch, original bytes checked): the
function still runs, but returns Normal with timers at 0. Soldiers keep
their individual reactions ("!", aiming, shooting) without the general
alert going off.

It is the same function as the "aob No Alerts" script of the `MGS4.CT`
table, which short-circuited it at its entry (method used up to V2.4.1);
we found it on our own by going back up from the instruction that writes
the alert state (12 October 2026).

### Profiles, shortcuts, banner and forced alert (V2.4): how it works

- **Global shortcuts**: the F1 to F11 keys that have a profile, the Pause
  key and numpad + / − / 0 are registered with Windows
  (`RegisterHotKey`): they work whatever program is in front. F keys
  without a profile are not taken.
- **Going back**: when the first profile is turned on, the trainer keeps
  a copy of the current setup; the active profile's key restores it and
  forgets the copy.
- **"GO" sound**: the trainer asks the game to play its own sound (the
  game's FMOD audio engine, through the injected DLL), hence the game's
  volume and audio output. If the game isn't attached, a Windows beep
  replaces it.
- **Banner**: a small transparent window, always on top, that takes
  neither focus nor clicks, centred at the top of the game window.
- **Forced alert** (redone on 12 October 2026): each soldier taking part
  in the alert has two timers, the Alert countdown (99.99, which goes
  down when nobody sees Snake anymore) then the Evasion and Caution one
  (switch to Caution halfway, to Normal at 0). The game copies the
  maximum every frame to decide the state. The trainer places the
  soldiers' timers in the chosen phase and keeps them there; in
  Automatic, it no longer writes anything and the game resumes its
  countdown where it is. If the area isn't on alert, it first has a
  soldier report Snake (game function called by the DLL). The old method,
  which short-circuited the alert calculation function ("Alert --
  Ignore" script of `MGS4.CT`), is no longer used: back in Automatic, the
  game dropped straight to Normal.
- **Frozen gauges**: for each gauge, all the game instructions that write
  it (damage, regeneration, natural decrease…) were found in the
  debugger, then neutralized while the row is locked; the trainer is the
  only one writing the locked value.
- **Accessories**: each weapon has a bit field of mounted accessories,
  which the trainer edits directly; it then calls the game functions
  that rebuild and redraw the customization menu. Unlimited Suppressors:
  the shooting function removes 1 from the mounted suppressor and 1 from
  the reserve, both removals are neutralized.

### Metal Gear REX (V2.4): how it works

- **Machine gun**: the heat (0 to 4000, shown in %) is read, increased at
  each shot then written back; the weapon locks when it reaches the
  maximum. The patch removes the write-back: the heat stays at 0 and the
  threshold is never reached.
- **Missiles**: 15 tubes, each with a reload timer; the displayed counter
  is the number of ready tubes, recounted every frame. A shot decrements
  this counter and arms the tube's timer: both are neutralized.
- **Laser**: the charge (0 to 10000, levels 1 to 5) is capped by an
  energy reserve (the HUD's "x/100"). While charging, the "charge +
  speed, capped" calculation is replaced by "charge = reserve"; while
  firing, the charge goes down normally (beam duration) but the reserve
  is no longer reduced.
- **Teleportation**: inside REX, the player's position is only an
  invisible point that the game brings back to REX every frame. The
  trainer finds the real REX in the game's actor list (right after
  Snake) and shifts its base position (six copies, all together); Snake
  follows. The cockpit is placed a little above the point, REX falls back
  to the ground by itself.

### Live equipping, without a menu (V2.2)

An "Equip" button per row in the OctoCamo, Outfits and Weapons tabs: the
change applies in game immediately, menu closed, as if you had picked it
in the menu. The trainer calls the game's own functions, in the game's
thread, through the injected DLL (after checking that each function has
the expected bytes: on another game version, it refuses rather than call
anything).

- **OctoCamo pattern**: immediate, all known patterns (special ones and
  the game's saved patterns included). The trainer drives the game's
  auto-camouflage controller, the one that changes the suit against a
  wall. "Forced" patterns (Olive, Corpse, Tears...) stay in place even
  against a wall, as in the game; captured patterns fade in and the
  auto-camouflage takes over again. If another outfit is worn, the
  OctoCamo suit is put back first. Golden and Preorder can only be
  equipped if the game has unlocked them on your account.
- **Face (FaceCamo) and outfits** (Middle East, South America, Eastern
  Europe disguises, Snake's suit, Altaïr): the game must reload Snake's
  model, which it only does while paused. The trainer therefore pauses
  the game with its own function (without showing a menu), equips, waits
  for the reload to finish then resumes: the game freezes for a fraction
  of a second. As in the menu, the face switches to "none" if the outfit
  doesn't allow it (Altaïr). An act's disguises also work in the other
  acts.
- **Vest**: immediate.
- **Weapon**: immediate if the weapon is in your quick weapon submenu (5
  slots). Otherwise, the trainer does like the pause menu: it places it
  in a free slot of the submenu, or failing that in the **5th slot** (the
  first 4 are never touched), loads its model then equips it — the game
  freezes while reading the weapon's file. If the weapon in the 5th slot
  is the one you hold, Snake puts it away first for a fraction of a
  second. Only owned weapons have an active button.

**In cutscenes (V2.3)**: the OctoCamo pattern changes in the middle of a
cutscene (the cutscene Snake has its own camouflage task, driven
directly), and so does the vest. Changing outfit or face in a cutscene
crashed the game: these buttons are refused while a cutscene is playing.
A weapon equipped during a cutscene isn't put in hand, but placed in the
quick submenu.

Known limits: the number of slots in the weapon submenu can't be
increased (the menu crashes when displayed beyond 5); forcing into the
hand a weapon whose model isn't loaded crashes the game, hence going
through the 5th slot.

### Photo mode (V2.6.0)

- **Camera**: the game function that sets the camera copies its position
  and orientation every frame; the trainer neutralizes this copy, and the
  DLL moves the camera, once per frame in the game's thread (a loop in
  the trainer was interrupted by the rest of the interface, hence
  stutters).
- **Controls**: the game fills a virtual controller (PS3 format) from the
  controller and the keyboard/mouse. During the mode, its writes are
  redirected to a copy read by the DLL: Snake receives nothing, and the
  camera is driven with the usual controls. During some cutscenes, the
  game no longer puts the keyboard and mouse into this controller: the
  DLL then reads them itself (the mouse through a low-level hook, the
  cursor position not being reliable).
- **Frozen time**: the game's internal pause (see Pause above), resumed
  or frozen again with Y / E / Pause.
- **Zoom**: the camera function receives the zoom as an argument; a
  detour replaces it with a trainer value, which the D-pad and the wheel
  change. Cutscene zooms are neutralized that way.
- **HUD**: each HUD element checks a global flag word; the DLL imposes it
  every frame, then the trainer puts it back as before.
- **Teleportation**: the camera's position is written as Snake's
  position (refused during cutscenes).

### Cutscene pause menu: QUIT line (V2.6.0)

The menu is a game task whose number of entries (2) is hard-coded. The
trainer raises it to 3, gives it a three-entry highlight table (the
third one starts no animation) and redirects the confirmation: the third
entry takes you back to the main menu. The menu's interface comes from a
game file, compressed in an archive: rather than modify it, the trainer
draws the word in a transparent window over the game. When the cursor is
on it, the trainer moves the game's selection bar down one line and greys
out the two other texts, directly in the interface scene in memory. The
patches are removed when the trainer closes.

### Teleportation

"Teleportation" tab: saves Snake's current position (X/Y/Z) under a
name, then teleports instantly to a saved point (double-click or
dedicated button). The 3 axes can also be edited manually (direct input
+ "Teleport Here" button), and the list of points can be exported/
imported as a JSON file.

**Since V2.3:**

- **Act and area** shown live ("Act 2 - Cove Valley Village"), with the
  game's official names in French and English (taken from its text
  files).
- **Points sorted by area**: each point remembers its area, and the list
  only shows those of the current area ("Show points from all areas"
  checkbox to see everything). The "Link to current area" button sorts
  old points.
- **File by act and area**: `teleport_points.json` only contains game
  values (act number, area code), so the same file works in French and
  English. The old format can still be read.
- **Provided points**: without a personal file, the trainer loads
  bundled default points (`assets/default_teleport_points.json`). The
  personal file is created at the first save.
- **Reliable position**: it is read from the game's player table, which
  always follows the current Snake. The old pointer (captured in passing
  in a distance routine) stayed on the old Snake after an act change
  (position at 0).

Absolute level coordinates: the Y axis is the height (the game may
cancel an invalid position, e.g. under the ground), X/Z the horizontal
plane. Points are saved in `teleport_points.json` (next to the exe/the
script, not versioned in this repository).
