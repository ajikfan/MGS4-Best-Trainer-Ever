"""Point d'entree de l'exe (MGS4Trainer.spec) : installe une mise a jour en
attente, puis lance le code du trainer depuis le dossier app/ a cote de
l'exe (voir release_files.py). En developpement, lancer live_trainer.py.

Mise a jour en attente : dossier update/ a cote de l'exe, prepare par le
trainer (fichiers verifies) et valide par update/ready.json (liste des
fichiers) ; sans ce fichier, le dossier est un telechargement inacheve et
n'est pas applique."""
import ctypes
import json
import os
import runpy
import shutil
import sys

# A augmenter quand l'exe change (nouveau module embarque, nouvelle version
# de Python ou de PySide6) : le manifeste d'une version qui en a besoin
# l'exige ("min_launcher") et la mise a jour renvoie alors au zip complet.
LAUNCHER_VERSION = 1

ROOT = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
APP_DIR = os.path.join(ROOT, "app")
UPDATE_DIR = os.path.join(ROOT, "update")
READY_FILE = os.path.join(UPDATE_DIR, "ready.json")
LOG_FILE = os.path.join(ROOT, "update.log")


def _log(message):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except OSError:
        pass


def _replace(source, target):
    """Remplace target par source ; une DLL encore chargee par le jeu ne
    peut pas etre ecrasee mais peut etre renommee : l'ancienne devient
    .old (supprimee a un prochain lancement), le jeu la garde jusqu'a sa
    fermeture et la prochaine injection prend la nouvelle."""
    os.makedirs(os.path.dirname(target), exist_ok=True)
    try:
        os.replace(source, target)
    except PermissionError:
        old = target + ".old"
        if os.path.exists(old):
            os.remove(old)
        os.replace(target, old)
        os.replace(source, target)


def _apply_pending_update():
    if not os.path.isfile(READY_FILE):
        return
    try:
        with open(READY_FILE, encoding="utf-8") as f:
            ready = json.load(f)
        for path in ready["files"]:
            _replace(os.path.join(UPDATE_DIR, *path.split("/")), os.path.join(APP_DIR, *path.split("/")))
        for path in ready.get("removed", []):
            target = os.path.join(APP_DIR, *path.split("/"))
            if os.path.isfile(target):
                os.remove(target)
        _log(f"mise a jour {ready.get('version', '?')} appliquee ({len(ready['files'])} fichiers)")
    except (OSError, ValueError, KeyError) as exc:
        _log(f"mise a jour non appliquee : {exc!r}")
    shutil.rmtree(UPDATE_DIR, ignore_errors=True)


def _remove_old_files():
    for folder, _, files in os.walk(APP_DIR):
        for name in files:
            if name.endswith(".old"):
                try:
                    os.remove(os.path.join(folder, name))
                except OSError:
                    pass  # encore chargee par le jeu


def main():
    _apply_pending_update()
    _remove_old_files()
    entry = os.path.join(APP_DIR, "live_trainer.py")
    if not os.path.isfile(entry):
        ctypes.windll.user32.MessageBoxW(
            None, f"Dossier du trainer incomplet : {entry} introuvable.\n"
                  "Retelecharge le trainer complet.", "MGS4 Trainer", 0x10)
        return
    sys.path.insert(0, APP_DIR)
    sys.mgs4_launcher_version = LAUNCHER_VERSION
    runpy.run_path(entry, run_name="__main__")


if __name__ == "__main__":
    main()
