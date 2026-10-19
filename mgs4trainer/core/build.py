"""Variante du build (2026-10-19) : "github" ou "nexus" (sans mise a jour,
voir release_files.py). Lue dans app/build.json, ecrit par MGS4Trainer.spec ;
en developpement (python live_trainer.py), "github"."""
import json
import os

from mgs4trainer.core.paths import SOURCE_ROOT


def build_flavor() -> str:
    try:
        with open(os.path.join(SOURCE_ROOT, "build.json"), encoding="utf-8") as f:
            return json.load(f).get("flavor", "github")
    except (OSError, ValueError, AttributeError):
        return "github"


def updates_available() -> bool:
    """Vrai si ce build contient la mise a jour integree (absente du build
    Nexus : ses fichiers ne sont pas livres)."""
    if build_flavor() == "nexus":
        return False
    try:
        import mgs4trainer.core.updater  # noqa: F401
        import mgs4trainer.ui.update_dialog  # noqa: F401
    except ImportError:
        return False
    return True
