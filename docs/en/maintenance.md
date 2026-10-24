# Maintenance

[← Back to the README](../../README.en.md) · *[Version française](../maintenance.md)*

To evolve the trainer: compatibility with game versions, build, code layout, debugging.

## Compatibility / game updates

**Not to be confused: two independent numberings.** The trainer's own
version (see the changelog in the "Help" button) has nothing to do with
the MGS4 game version mentioned below.

The memory addresses used depend on the exact version of `mgs4.exe`: a
Steam update of the game can shift every address. It already happened
once (update of 24 September 2026): a whole block of data shifted by a
fixed amount, without changing the internal structure — fixed through a
single constant (`MODULE_PATCH_SHIFT` in `live_trainer.py`, see
MGS4-SaveStats'
[notes.md](https://github.com/ajikfan/MGS4-SaveStats/blob/main/notes.md)
for the full diagnosis method).

**Trainer calibrated and tested on the current Steam version of MGS4:
1.4.1.** If a future game update breaks the detection (the trainer stays
stuck on "Not connected", or the sanity check keeps failing after
reconnecting), it is probably the same cause: this shift will have to be
recalibrated, the code patches checked (each one refuses to apply if its
original bytes are no longer there) and a new trainer version released.
On the players' side, the [FAQ](faq.md) advises them to wait for that
update rather than recalibrate themselves.

## Packaging as a standalone .exe

```
python -m PyInstaller --noconfirm MGS4Trainer.spec
```

Using the provided `.spec` file (not a PyInstaller command "by hand")
matters. Since V2.5, the result (`dist/MGS4Trainer/`, a whole folder to
copy, not just the exe) has two parts:

- `MGS4Trainer.exe` and `_internal/`: the **engine** (`launcher.py`),
  that is Python, PySide6 and the standard modules listed in
  `release_files.RUNTIME_MODULES`. It doesn't contain the trainer's code;
- `app/`: the trainer's **code** (`live_trainer.py`, `mgs4trainer/`,
  `mgs4save.py`, `locales/`, `assets/`, the DLL), copied as is by the
  `.spec` according to `release_files.app_files()`. This is the folder the
  update replaces, file by file.

At startup, the exe first installs a pending update (`update/` folder
validated by `update/ready.json`, see `launcher.py`), then starts
`app/live_trainer.py`. If the code needs a module missing from the
engine, add it to `RUNTIME_MODULES` and increase `LAUNCHER_VERSION` in
`launcher.py`: that version will require the full zip.

The exe is not signed: Windows SmartScreen will show a warning at first
launch ("Windows protected your PC") — that's normal for an unsigned
independent tool, just click "More info" → "Run anyway".

## Nexus build (without updates)

Nexus Mods refuses an exe that connects to the Internet to update
itself. One source code, two variants, chosen at build time:

```
set MGS4_FLAVOR=nexus
python -m PyInstaller --noconfirm MGS4Trainer.spec
set MGS4_FLAVOR=
```

The `nexus` variant (see `release_files.py`) doesn't copy
`core/updater.py` or `ui/update_dialog.py` into `app/`, doesn't bundle
the network modules in the exe (`ssl`, `http.client`, `urllib.*`,
`webbrowser`) and writes `app/build.json`; the trainer (`core/build.py`)
then hides the "Update" button and does no check at startup. Without the
variable (or `MGS4_FLAVOR=github`), the usual GitHub build. Both builds
write to `dist/MGS4Trainer/`: redo the GitHub build before a GitHub
release. Zip the Nexus variant under another name (e.g.
`MGS4Trainer-V2.5.3-Nexus.zip`); no `manifest.json` for Nexus.

## Releasing a version (with the small-file update)

The trainer's "Update" button (`core/updater.py`) reads the latest GitHub
release, downloads its `manifest.json`, then only the code files whose
fingerprint differs, **from the repository at the release's tag**
(raw.githubusercontent.com). Hence the order:

1. Update `TRAINER_VERSION` (`mgs4trainer/ui/help.py`) and the changelog
   (`locales/fr/` and `locales/en/`), as well as the documentation in
   both languages (`README.md` / `README.en.md`, `docs/` / `docs/en/`),
   then commit. All the code must be committed: `make_manifest.py`
   refuses otherwise.
2. `python -m PyInstaller --noconfirm MGS4Trainer.spec`, then zip
   `dist/MGS4Trainer/`.
3. `python make_manifest.py` → `dist/manifest.json` (fingerprints taken
   from the repository at the current commit; text files compared after
   CRLF → LF, since Git checks them out as CRLF on Windows).
4. Create the tag (same name as `TRAINER_VERSION`, e.g. `V2.5`) **on this
   commit**, push the commit and the tag.
5. Create the GitHub release on this tag, with the zip **and**
   `manifest.json` (exact name) attached.

A release without `manifest.json` is still seen by the button, which then
only offers the download page.

## Code layout

Since V2.4.1, `live_trainer.py` is only the entry point; the code is in
the `mgs4trainer/` package:

- `core/`: paths (`paths.py`), settings and translations (`i18n.py`),
  process access (`winproc.py`), game addresses and tables
  (`gamedata.py`), DLL injection and shared memory with it
  (`speedhack.py`);
- `live/`: the `MGS4Live` class (access to the running game), built from
  mixins by theme: attaching (`base.py`), DLL and hooks (`hooks.py`),
  player and gauges (`player.py`), weapons and accessories
  (`weapons.py`), **code patches** (`code_patches.py`, the
  `CODE_PATCHES` list), sound and alert (`sound_alert.py`), stats and
  location (`state.py`), live equipping (`equip.py`), Whole area
  (`zone.py`), camera and photo mode (`camera.py`), QUIT line of the
  cutscene pause menu (`cutscene_menu.py`);
- `ui/`: one file per tab, plus the help, the profiles and the banner,
  the photo mode controls (`photo_help.py`), the QUIT line drawn over the
  game (`cutscene_menu_overlay.py`) and the main window
  (`main_window.py`).

## Recompiling the DLL

Only if you modify `native/speedhack.c`: the DLL is provided already
compiled (`native/speedhack_x64.dll`), in the repository as in the zip,
and the trainer uses it as is. Players never need a compiler.

You need a C compiler targeting Windows, tested with
`x86_64-w64-mingw32-gcc` through [MSYS2](https://www.msys2.org/)
(mingw64):

```
x86_64-w64-mingw32-gcc -shared -O2 -municode -o native/speedhack_x64.dll native/speedhack.c -lkernel32 -lwinmm
```

MinGW pitfall: MSYS2's `mingw64/bin` folder must be in the Windows PATH,
otherwise `cc1.exe` fails without printing any message.

After modifying the DLL, redo the exe build (see above) so that it is
bundled. The DLL already injected into a running game doesn't change:
restart the game to load the new one.

## Code patches: rules

- Each `CODE_PATCHES` entry is a list of sites `(RVA, original bytes,
  patch bytes)`. `set_code_patch` checks **all** sites before writing
  anything: if a single one matches neither the original nor the patch,
  nothing is written (protection against another game version).
- Two patches can share a site (Lethal / Non-lethal): the trainer always
  removes the inactive mode's patch before placing the other.

## Debugging with x64dbg: known pitfalls

- A software breakpoint writes the `0xCC` byte into the game's code:
  while it is there, the trainer refuses to place a patch at the same
  spot. Always type `bc` (and `bphc` for hardware breakpoints) **before**
  detaching, otherwise the game crashes the next time it gets there.
- For a hardware breakpoint, give the already computed address, not a
  sum (`base+offset`), otherwise x64dbg may show "Breakpoint reached not
  in list" and freeze the game.
- The base address of `mgs4.exe` can change from one launch to the next:
  recompute the absolute addresses from the RVAs at each session.
