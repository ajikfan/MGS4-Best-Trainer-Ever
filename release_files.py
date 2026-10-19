"""Fichiers du code du trainer, livres a part de l'exe (dossier app/) et
remplacables par la mise a jour : une seule liste pour le build
(MGS4Trainer.spec) et pour le manifeste des releases.

L'exe (launcher.py, empaquete par PyInstaller) ne contient que Python,
PySide6 et les modules standard de RUNTIME_MODULES : il ne change que si le
code a besoin d'un module qui n'y est pas (LAUNCHER_VERSION de launcher.py,
a augmenter alors, et "min_launcher" du manifeste)."""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

# Fichiers et dossiers du code, relatifs a la racine du depot.
APP_ENTRIES = (
    "live_trainer.py",
    "mgs4save.py",
    "mgs4trainer",
    "locales",
    "assets",
    "native/speedhack_x64.dll",
)
# Variantes de build (2026-10-19) : "github" (par defaut) avec la mise a jour
# integree ; "nexus" sans elle (Nexus Mods refuse un exe qui se connecte a
# Internet pour se mettre a jour) : ses fichiers ne sont pas copies dans app/,
# les modules reseau ne sont pas embarques dans l'exe, et le trainer masque
# alors le bouton (voir mgs4trainer/core/build.py). Un seul code source :
# rien a supprimer ni a refaire d'un build a l'autre.
FLAVORS = ("github", "nexus")
UPDATE_FILES = ("mgs4trainer/core/updater.py", "mgs4trainer/ui/update_dialog.py")
NETWORK_MODULES = ("ssl", "http.client", "urllib.request", "urllib.error", "urllib.parse", "webbrowser")
_SKIPPED_DIRS = {"__pycache__"}
_SKIPPED_SUFFIXES = (".pyc",)

# Modules embarques dans l'exe : ceux qu'importe le code, plus ceux dont
# la mise a jour a besoin, plus quelques modules standard courants pour
# que les prochaines versions du code n'exigent pas un nouvel exe.
RUNTIME_MODULES = (
    "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
    "argparse", "ctypes", "ctypes.wintypes", "json", "os", "re", "struct", "sys",
    "threading", "time", "winsound",
    # mise a jour
    "hashlib", "ssl", "http.client", "urllib.request", "urllib.error", "urllib.parse",
    "shutil", "tempfile", "webbrowser",
    # reserve
    "base64", "bisect", "collections", "contextlib", "copy", "csv", "dataclasses",
    "datetime", "enum", "functools", "glob", "heapq", "html", "io", "itertools",
    "logging", "math", "pathlib", "queue", "random", "string", "subprocess",
    "textwrap", "traceback", "typing", "uuid", "zipfile",
)


def runtime_modules(flavor: str = "github"):
    """Modules a embarquer dans l'exe pour la variante `flavor`."""
    if flavor == "nexus":
        return tuple(m for m in RUNTIME_MODULES if m not in NETWORK_MODULES)
    return RUNTIME_MODULES


def app_files(flavor: str = "github"):
    """Chemins relatifs (separateur "/") des fichiers du code de la variante
    `flavor` (sans ceux de la mise a jour pour "nexus")."""
    out = []
    for entry in APP_ENTRIES:
        path = os.path.join(ROOT, entry)
        if os.path.isfile(path):
            out.append(entry)
            continue
        for folder, dirs, files in os.walk(path):
            dirs[:] = sorted(d for d in dirs if d not in _SKIPPED_DIRS)
            for name in sorted(files):
                if not name.endswith(_SKIPPED_SUFFIXES):
                    out.append(os.path.relpath(os.path.join(folder, name), ROOT).replace(os.sep, "/"))
    if flavor == "nexus":
        out = [path for path in out if path not in UPDATE_FILES]
    return out
