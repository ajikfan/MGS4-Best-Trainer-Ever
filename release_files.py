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


def app_files():
    """Chemins relatifs (separateur "/") de tous les fichiers du code."""
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
    return out
