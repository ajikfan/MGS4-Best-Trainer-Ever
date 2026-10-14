"""Chemins : fichiers embarques (assets, locales, DLL) et donnees ecrites a cote de l'exe."""
import os
import sys


# Dossier de live_trainer.py : racine du depot en mode developpement,
# dossier app/ a cote de l'exe en mode empaquete (launcher.py).
SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _bundled_path(*parts):
    """Fichier livre avec le code (assets, locales, DLL : voir
    release_files.py), dans le meme dossier que lui."""
    return os.path.join(SOURCE_ROOT, *parts)


TRAINER_ICON = _bundled_path("assets", "MGS4_Best_Trainer.ico")
DEFAULT_TELEPORT_POINTS_FILE = _bundled_path("assets", "default_teleport_points.json")
# Profils fournis (F1 Normal, F2 God mode), charges tant que l'utilisateur
# n'a pas son propre profiles.json (cree au premier enregistrement).
DEFAULT_PROFILES_FILE = _bundled_path("assets", "default_profiles.json")


def _writable_data_path(*parts):
    """A cote de l'exe en mode empaquete (PAS sys._MEIPASS, qui est un
    dossier temporaire en lecture jetable a chaque lancement) ou du script
    en mode developpement - pour les donnees que le trainer doit ecrire
    lui-meme et retrouver au lancement suivant (ex. points de teleport)."""
    base = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) \
        else SOURCE_ROOT
    return os.path.join(base, *parts)


TELEPORT_POINTS_FILE = _writable_data_path("teleport_points.json")
SETTINGS_FILE = _writable_data_path("settings.json")
PROFILES_FILE = _writable_data_path("profiles.json")
