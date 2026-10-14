"""Mise a jour du trainer par petits fichiers (V2.5) : la derniere release
GitHub porte un manifeste (manifest.json, make_manifest.py) avec l'empreinte
SHA-256 de chaque fichier du code ; seuls les fichiers differents sont
telecharges, depuis le depot au tag de la release, verifies, puis ranges
dans update/ a cote de l'exe. launcher.py les installe au lancement suivant
(update/ready.json ecrit en dernier : sans lui, rien n'est applique).

Sans Qt : appele depuis un fil separe par ui/update_dialog.py."""
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request

from mgs4trainer.core.paths import SOURCE_ROOT, _writable_data_path

REPOSITORY = "ajikfan/MGS4-Best-Trainer-Ever"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RAW_FILE_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/{{tag}}/{{path}}"
RELEASES_PAGE_URL = f"https://github.com/{REPOSITORY}/releases/latest"
MANIFEST_ASSET = "manifest.json"
DLL_PATH = "native/speedhack_x64.dll"
REQUIRED_FILES = {"live_trainer.py", "mgs4trainer/ui/main_window.py", "mgs4trainer/core/updater.py", DLL_PATH}
UPDATE_DIR = _writable_data_path("update")
TIMEOUT = 15

# Fichiers texte : le depot les stocke en LF, Git les extrait en CRLF sous
# Windows ; l'empreinte se calcule apres CRLF -> LF (meme regle dans
# make_manifest.py). Les binaires (DLL, icone) sont compares tels quels.
TEXT_SUFFIXES = (".py", ".json", ".md", ".txt")


class UpdateError(Exception):
    """Echec lisible (reseau, manifeste invalide, fichier corrompu)."""


def file_sha256(path: str, data: bytes) -> str:
    if path.endswith(TEXT_SUFFIXES):
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def parse_version(text: str) -> tuple[int, ...]:
    """"V2.4.1" -> (2, 4, 1) ; () si illisible."""
    match = re.fullmatch(r"[vV]?(\d+(?:\.\d+)*)", text.strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else ()


def is_newer(remote: str, local: str) -> bool:
    remote_parts, local_parts = parse_version(remote), parse_version(local)
    return bool(remote_parts) and remote_parts > local_parts


def launcher_version() -> int | None:
    """Version du moteur (launcher.py), None en mode developpement (lance
    par python live_trainer.py : pas de mise a jour automatique)."""
    return getattr(sys, "mgs4_launcher_version", None)


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "MGS4-Trainer-updater",
                                                   "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read()
    except (urllib.error.URLError, OSError) as exc:
        raise UpdateError(str(getattr(exc, "reason", exc))) from exc


def fetch_latest_release() -> dict:
    """{"version", "notes", "page_url", "manifest_url" (None si absent)}."""
    try:
        release = json.loads(_get(LATEST_RELEASE_URL))
    except ValueError as exc:
        raise UpdateError("reponse GitHub illisible") from exc
    manifest_url = next((asset.get("browser_download_url") for asset in release.get("assets", [])
                         if asset.get("name") == MANIFEST_ASSET), None)
    return {
        "version": release.get("tag_name", ""),
        "notes": release.get("body") or "",
        "page_url": release.get("html_url") or RELEASES_PAGE_URL,
        "manifest_url": manifest_url,
    }


def fetch_manifest(release: dict) -> dict:
    if not release.get("manifest_url"):
        raise UpdateError("cette version n'a pas de manifeste : telechargement complet necessaire")
    try:
        manifest = json.loads(_get(release["manifest_url"]))
        files = manifest["files"]
        if not all(isinstance(entry.get("sha256"), str) for entry in files.values()):
            raise KeyError("sha256")
        # Garde : les fichiers locaux absents du manifeste sont supprimes ;
        # un manifeste vide ou tronque viderait le trainer.
        if not REQUIRED_FILES <= files.keys():
            raise KeyError("fichiers essentiels")
    except (ValueError, KeyError, AttributeError) as exc:
        raise UpdateError("manifeste invalide") from exc
    return manifest


def _local_files() -> list[str]:
    out = []
    for folder, dirs, files in os.walk(SOURCE_ROOT):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if not name.endswith((".pyc", ".old")):
                out.append(os.path.relpath(os.path.join(folder, name), SOURCE_ROOT).replace(os.sep, "/"))
    return out


def plan_update(manifest: dict) -> tuple[list[str], list[str]]:
    """(fichiers a telecharger, fichiers locaux a supprimer)."""
    changed = []
    for path, entry in manifest["files"].items():
        local = os.path.join(SOURCE_ROOT, *path.split("/"))
        try:
            with open(local, "rb") as f:
                same = file_sha256(path, f.read()) == entry["sha256"]
        except OSError:
            same = False
        if not same:
            changed.append(path)
    removed = [path for path in _local_files() if path not in manifest["files"]]
    return changed, removed


def prepare_update(release: dict, manifest: dict, progress=None) -> dict:
    """Telecharge et verifie les fichiers modifies dans update/, puis ecrit
    update/ready.json. Renvoie {"files", "removed", "dll_changed"}."""
    current = launcher_version()
    if current is None:
        raise UpdateError("mode developpement : mettre a jour le depot (git pull)")
    if manifest.get("min_launcher", 1) > current:
        raise UpdateError("cette version demande le telechargement complet du trainer")
    changed, removed = plan_update(manifest)
    shutil.rmtree(UPDATE_DIR, ignore_errors=True)
    tag = urllib.parse.quote(release["version"])
    for index, path in enumerate(changed):
        if progress:
            progress(index, len(changed), path)
        data = _get(RAW_FILE_URL.format(tag=tag, path=urllib.parse.quote(path)))
        if file_sha256(path, data) != manifest["files"][path]["sha256"]:
            shutil.rmtree(UPDATE_DIR, ignore_errors=True)
            raise UpdateError(f"fichier corrompu : {path}")
        target = os.path.join(UPDATE_DIR, *path.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(data)
    if progress:
        progress(len(changed), len(changed), "")
    if changed or removed:
        os.makedirs(UPDATE_DIR, exist_ok=True)
        with open(os.path.join(UPDATE_DIR, "ready.json"), "w", encoding="utf-8") as f:
            json.dump({"version": release["version"], "files": changed, "removed": removed}, f, indent=1)
    return {"files": changed, "removed": removed, "dll_changed": DLL_PATH in changed}
