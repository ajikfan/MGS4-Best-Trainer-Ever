"""Genere dist/manifest.json, a joindre a la release GitHub (fichier nomme
manifest.json) : version, version minimale du moteur, empreinte SHA-256
de chaque fichier du code (release_files.app_files) TELLE QUE DANS LE
DEPOT au commit donne - c'est ce que la mise a jour telecharge
(raw.githubusercontent.com au tag de la release).

    python make_manifest.py [commit]      (HEAD par defaut)

Refuse si un fichier du code a des modifications non commitees (le zip
et la mise a jour ne contiendraient pas la meme chose). Le tag de la
release doit pointer sur ce commit."""
import hashlib
import json
import os
import re
import subprocess
import sys

from launcher import LAUNCHER_VERSION
from release_files import ROOT, app_files

TEXT_SUFFIXES = (".py", ".json", ".md", ".txt")  # meme regle que core/updater.py


def file_sha256(path, data):
    if path.endswith(TEXT_SUFFIXES):
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def git(*args, binary=False):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True,
                          text=not binary).stdout


def main():
    commit = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
    paths = app_files()
    dirty = git("status", "--porcelain", "--", *paths).strip()
    if dirty:
        sys.exit("Modifications non commitees dans le code :\n" + dirty)
    help_source = git("show", f"{commit}:mgs4trainer/ui/help.py")
    version = re.search(r'TRAINER_VERSION = "([^"]+)"', help_source).group(1)
    files = {}
    for path in paths:
        data = git("show", f"{commit}:{path}", binary=True)
        files[path] = {"sha256": file_sha256(path, data), "size": len(data)}
    manifest = {"version": version, "commit": git("rev-parse", commit).strip(),
                "min_launcher": LAUNCHER_VERSION, "files": files}
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    out = os.path.join(ROOT, "dist", "manifest.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    print(f"{out} : {version}, {len(files)} fichiers, moteur >= {LAUNCHER_VERSION}")


if __name__ == "__main__":
    main()
