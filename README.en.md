# MGS4 Trainer — V2.7.0

*[Version française](README.md)*

Live trainer for Metal Gear Solid 4 (Steam PC port): it reads and writes
the game's memory while you play. Editable weapons, items, stats and
gauges, outfit, face, vest, OctoCamo pattern or weapon changed without
going through the menus, untouchable or invisible Snake, enemies and
bosses in one hit, the whole area neutralized in one click, game speed,
teleportation, and a whole setup recalled with one key (profiles F1 to
F11).

Interface in French and English. Single-player only.

Sister project of [MGS4-SaveStats](https://github.com/ajikfan/MGS4-SaveStats)
(read-only save file viewer), whose `mgs4save.py` this repository reuses.

## Installation

**With the exe (easiest)**

1. Download the zip of the [latest version](https://github.com/ajikfan/MGS4-Best-Trainer-Ever/releases/latest).
2. Unzip it anywhere (keep the whole folder).
3. Start MGS4 (Steam version **1.4.1**) with a save loaded, then
   `MGS4Trainer.exe`.
4. Afterwards, the trainer's **Update** button installs new versions
   without downloading the zip again (from V2.5 on).

The exe is not signed: see the [FAQ](docs/en/faq.md) if Windows or your
antivirus flags it.

**From the source code** (Windows, Python 3.12, PySide6)

```
python live_trainer.py
```

Without the game, the tabs can still be browsed (greyed out) to explore
the interface and read the tooltips. The trainer's **Help** button sums
up the compatible version, the warnings and the version history.

## Documentation

- [Tabs and profiles guide](docs/en/guide.md)
- [One Shot, One Kill: the bosses](docs/en/boss.md)
- [FAQ and common issues](docs/en/faq.md)
- [What's new in each version](docs/en/whats-new.md)
- [How it works](docs/en/how-it-works.md)
- [Maintenance](docs/en/maintenance.md) (compatibility, build, code layout)

## Latest version: V2.7.0

- **Bosses tab**: health and stamina of every boss (Beast and Beauty side
  by side), on-screen bars kept in sync; a gauge released at 0 = the boss
  is finished or knocked out by the game.
- **Load** from the pause menu, with a fade to black.
- **One Shot, One Kill**: Laughing Octopus, Screaming Mantis (no Mantis
  doll needed), Vamp (no syringe) and Liquid defeated by the first hit.
- **Untouchable**: Screaming Mantis's strings no longer hold Snake.
- **Whole area**: act 3 enemies and Sliders; allied bikes spared.
- **Cutscene pause menu**: the game's text in its language, fade to black
  before returning to the title.
- **Photo mode**: mouse clicks swapped and fixes.
- Delivered by the **built-in update**; DLL changed: restart the game.

Details in [What's new in each version](docs/en/whats-new.md).

## ⚠️ Warnings

- **Game updates**: the trainer is calibrated for MGS4 Steam **1.4.1**.
  After a game update, wait for a new trainer version before using it
  (see the [FAQ](docs/en/faq.md)).
- **Connection**: at startup, the trainer asks GitHub whether a new
  version exists (nothing is downloaded without your consent; can be
  turned off in the **Update** window).
- **Single-player only, at your own risk.** This is not an official
  tool: it reads/writes another process's memory, which an antivirus may
  wrongly flag.
- The speed control goes further: it **injects code** into `mgs4.exe`
  (a "speedhack"-type technique, close to Cheat Engine) — more likely to
  be flagged by an antivirus/EDR than plain memory reads/writes, and
  never tested beyond occasional slow-motion/fast-forward (no long
  sessions).
- "One Shot, One Kill"/"Non-lethal" goes further still: it is no longer a
  function redirection but a **real patch of the game's instructions**.
  Protected against being applied to the player, but it remains the
  trainer's most invasive technique. Its effects are confirmed in game
  case by case, but an untested enemy could react differently.
  Untouchable and Invisible are instruction patches too.
- The "Equip" buttons call the game's internal functions outside their
  normal context (menus). Each case was tested in game, but a particular
  situation (cutscene, loading, scripted sequence) could still cause a
  crash: save before experimenting.
- Some fields are still low-confidence or not tested individually
  (documented case by case in MGS4-SaveStats' `notes.md`): a value may
  behave differently from what is described.
- "Advanced mode" hides by default some internal/debug items whose
  in-game behaviour is uncertain or dangerous (e.g. an item whose
  equipping crashes the game, confirmed several times) — only turn it on
  if you know what you are doing.

## Credits and sources

This trainer builds on other people's work, in addition to our own
research:

- **[zexk/bbtracker](https://github.com/zexk/bbtracker)** (MIT license):
  pointer chain to the game structure (see [How it works](docs/en/how-it-works.md)).
- **Community Cheat Engine table `MGS4.CT`, by RMLSNK** (version 7.7 of
  the file used here). This table is **not redistributed** in this
  repository (no license is stated in it). Up to V2.4.1, the trainer
  reused several of its scripts, rewritten in C and Python; since then,
  **all of them have been replaced by our own code**:
  - "One Shot, One Kill" / "Non-lethal" on soldiers: "aob Damage" script
    and its "Remove Lethal" logic;
  - "One Shot, One Kill" on Gekko and tanks: "aob Damage Gecko" script;
  - "No Reload": "No Reload" script;
  - boss tracking (up to V2.4.1, removed since): "Bosses 2" and "Bosses
    Laughing Octopus" scripts;
  - Teleportation (up to V2.2, removed since): "aob Coordinates" script;
  - forced alert (up to V2.4.1, replaced since by our own soldier
    timers): "Alert -- Ignore" script;
  - "No Alerts" (up to V2.4.1): "aob No Alerts" script. Since then, a code
    patch from our own analysis, on the same game function (see
    [How it works](docs/en/how-it-works.md));
  - several address formulas (item table, stats, alert state) were found
    by reading its scripts (details in the code comments), then
    **checked in game by our own tests** before being used.

Thanks to their authors. If you are the author of one of these sources
and would like a correction or a removal, open an issue.

## License

The code in this repository is released under the MIT license (see the
[LICENSE](LICENSE) file). It does not cover the material taken from the
other sources cited above, nor the game itself (Metal Gear Solid 4,
Konami).
