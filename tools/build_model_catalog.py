"""Catalogue des modeles que Snake peut porter (corps hybride, onglet
Evenements « Apparence de Snake »), toutes zones confondues.

Lit les archives du jeu installe (lecture seule) et ecrit
mgs4trainer/core/model_catalog.py : identifiant du mdn -> (zone, os,
cles des txn de la zone qui decrivent ses textures). Le trainer enregistre
ces txn et le modele sous le nom de la zone (le jeu en deduit le dossier
des textures HD, comme pour l'apparition d'ennemis).

    python tools/build_model_catalog.py "E:/.../METAL GEAR SOLID 4/MGS4"
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from mgs4trainer.core import mdn  # noqa: E402
from mgs4trainer.core.vpak import StageFiles  # noqa: E402

SNAKE_BODY = "00413aa8.mdn"  # corps de Snake (paquet de tenue), squelette de reference
ZONE = re.compile(r"s\d\d[a-z]\d\d[a-z]$")
TEXTURE_SIZE = 0x20


def texture_ids(data: bytes) -> list[int]:
    header = mdn.MdnHeader(data)
    return [struct.unpack_from(">I", data, header.texture_offset + i * TEXTURE_SIZE)[0]
            for i in range(header.texture_count)]


def main(root: str) -> None:
    files = StageFiles(root)
    skeleton = files.read(next(p for p in files.entries if p.endswith(SNAKE_BODY)))
    zones = sorted({p.split("/")[-2] for p in files.entries if p.endswith("/data.cnf")})
    catalog = {}
    checked = set()
    txn_cache = {}
    for zone in zones:
        if not ZONE.match(zone):
            continue
        try:
            resources = files.zone_resources(zone)
        except (StopIteration, ValueError):
            continue
        for key, path in resources:
            model = key & 0xFFFFFF
            if key >> 24 != 0x0D or model in catalog or model == int(SNAKE_BODY[:8], 16):
                continue
            try:
                data = files.read(path)
                if (model, None) not in checked:
                    checked.add((model, None))
                    if mdn.MdnHeader(data).bone_count < 20 or not mdn.skeleton_compatible(data, skeleton):
                        checked.add((model, False))
                if (model, False) in checked:
                    continue
                wanted = set(texture_ids(data))
            except (ValueError, struct.error, IndexError):
                continue
            needed = []
            for txn_key, txn_path in resources:
                if txn_key >> 24 != 0x03 or not wanted:
                    continue
                if txn_path not in txn_cache:
                    txn_cache[txn_path] = files.read(txn_path)
                found = {t for t in wanted if struct.pack(">I", t) in txn_cache[txn_path]}
                if found:
                    needed.append(txn_key)
                    wanted -= found
            if not wanted:
                catalog[model] = (zone, mdn.MdnHeader(data).bone_count, tuple(needed))
    out = os.path.join(os.path.dirname(__file__), "..", "mgs4trainer", "core", "model_catalog.py")
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write('"""Genere par tools/build_model_catalog.py : modeles portables par Snake.\n\n'
                     'identifiant du mdn -> (zone d\'origine, nombre d\'os, cles des txn\n'
                     'de cette zone qui decrivent ses textures)."""\n\nMODELS = {\n')
        for model in sorted(catalog, key=lambda m: (catalog[m][0], m)):
            zone, bones, txns = catalog[model]
            handle.write(f"    {model:#08x}: ({zone!r}, {bones}, ({''.join(f'{t:#010x}, ' for t in txns)})),\n")
        handle.write("}\n")
    print(len(catalog), "modeles")


if __name__ == "__main__":
    main(sys.argv[1])
