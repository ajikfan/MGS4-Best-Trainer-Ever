# FAQ and common issues

[← Back to the README](../../README.en.md) · *[Version française](../faq.md)*

### Windows shows "Windows protected your PC"

The exe is not signed. Click "More info", then "Run anyway".

### My antivirus flags the trainer

It reads and writes the game's memory, and injects a small DLL into the
game for some settings: antiviruses often spot this kind of technique.
The full source code is in this repository.

### What do I need to use the trainer?

64-bit Windows 10 or 11, and Metal Gear Solid 4 (Steam) version 1.4.1.
Nothing else to install: Python, the interface and the Visual C++
runtime are included in the trainer's folder. Keep the whole folder (the
exe doesn't start without its `_internal` folder).

### Where should I unzip the trainer?

In a personal folder (Desktop, Documents…), **not in `Program Files`**:
the trainer saves its profiles, settings and your teleport points next to
the exe, and Windows may block these writes in `Program Files`.

### The trainer doesn't attach although the game is running

If MGS4 runs **as administrator**, run the trainer as administrator too
(right-click the exe → "Run as administrator"): otherwise Windows
prevents it from accessing the game. In the normal case (game started
from Steam without special rights), no administrator rights are needed.

### The trainer stays on "Not connected"

Start the game and load a save: the trainer attaches by itself.

If it no longer attaches after a **Steam update of the game**, the game's
addresses have probably moved and the trainer must be recalibrated. Best
is to **wait for a trainer update**: recalibrating requires debugging
tools and in-game checks (details in [Maintenance](maintenance.md), for
those who want to try). Meanwhile, don't use the trainer on the new game
version: even if some features seem to work, values could be read or
written at the wrong place. Code patches, for their part, refuse to apply
if they don't find the expected code.

To avoid being caught off guard, you can turn off MGS4's automatic
updates in Steam (game Properties → Updates).

### An "Equip" button is refused during a cutscene

Changing outfit or face in the middle of a cutscene crashes the game:
these buttons are refused while a cutscene is playing. The OctoCamo
pattern and the vest do work in cutscenes (the pattern only applies with
the OctoCamo suit).

### Hold-ups don't work

With **Invisible**, hold-ups still work. If they don't, check that no
other setting blocks the soldiers' reaction, and restart the trainer if
it predates V2.4.1.

### Teleporting Metal Gear REX

When piloting REX, teleporting moves REX itself (Snake follows, in the
cockpit). It is placed a little above the point (saved as REX, at
cockpit height) and falls back to the ground right away.

### An item only shows up in "Advanced mode"

Some internal items crash the game when equipped (for example "Destabil.
SOP", a leftover from Metal Gear Online): they are hidden in simple mode.

### Where are my profiles, settings and teleport points?

Next to the exe: `profiles.json`, `settings.json` and
`teleport_points.json`. The built-in update (since V2.5) doesn't touch
them. If you download a full zip, copy them next to the new exe.

### How does the update work?

Since V2.5, the **Update** button asks GitHub (a single request, nothing
else is contacted). If there is a new version, it only downloads the
changed files of the `app/` folder, checks their fingerprint, then
installs them when the trainer restarts. The result is logged in
`update.log`, next to the exe.

- To stop checking at startup, uncheck the box in the update window (the
  button still works).
- If the new version changes the DLL injected into the game, restart the
  game to benefit from it.
- Some versions require downloading the full zip again (when the exe
  itself changes): the button then opens the download page.
- Started from the source code (`python live_trainer.py`), the trainer
  reports new versions but doesn't update itself: use `git pull`.
