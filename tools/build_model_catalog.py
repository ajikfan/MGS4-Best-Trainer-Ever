"""Catalogue des modeles (et de leurs pieces liees) que Snake peut porter (corps hybride, onglet
Evenements « Apparence de Snake »), toutes zones confondues.

Lit les archives du jeu installe (lecture seule) et ecrit
mgs4trainer/core/model_catalog.py : identifiant du mdn -> (zone, os,
cles des txn de la zone qui decrivent ses textures, pieces liees,
couches). Le trainer enregistre
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
from mgs4trainer.core.vpak import RESOURCE_ENTRY, StageFiles  # noqa: E402

SNAKE_BODY = "00413aa8.mdn"  # corps de Snake (paquet de tenue), squelette de reference
ZONE = re.compile(r"s\d\d[a-z]\d\d[a-z]$")
TEXTURE_SIZE = 0x20
HEAD_BONE = 0x29A56C   # os de la tete (identifiant commun aux squelettes humains)
LAYER_WINDOW = 12      # lignes du data.cnf autour du modele


def texture_ids(data: bytes) -> list[int]:
    header = mdn.MdnHeader(data)
    return [struct.unpack_from(">I", data, header.texture_offset + i * TEXTURE_SIZE)[0]
            for i in range(header.texture_count)]


def linked_pieces(files, resources, model: int, cache: dict) -> list[tuple[int, str]]:
    """[(identifiant, chemin)] des mdn de la zone cites avec model par un
    .eqpp de la zone (Naomi : 0xA8BA98 cite 0xE28B85 et 0x44911B)."""
    mdns = {key & 0xFFFFFF: path for key, path in resources if key >> 24 == 0x0D}
    pieces = {}
    for key, path in resources:
        if key >> 24 != 0x19:
            continue
        if path not in cache:
            cache[path] = files.read(path)
        data = cache[path]
        if struct.pack(">I", model) not in data:
            continue
        for other, other_path in mdns.items():
            if other != model and struct.pack(">I", other) in data:
                pieces[other] = other_path
    return sorted(pieces.items())


def model_layers(files, zone: str, resources, model: int, pieces, cache: dict) -> list[tuple[int, str]]:
    """Couches du modele (2026-11-16) : modeles a part que rien ne relie au
    corps mais que le jeu dessine avec lui, listes pres de lui dans le
    data.cnf (Naomi en noir 0x2DA964 : foulard 0x6C29C2, cheveux 0xD8B3EE).
    Cheveux : 12 a 45 os, l'os de la tete, au moins 30 % d'os communs.
    Couche complete : meme squelette (90 %), aucune texture commune (les
    variantes de soldats partagent toutes les leurs), 4 textures au plus.
    Couche partielle : 25 a 90 % d'os communs, sans la tete, au moins la
    moitie de ses textures prises au corps (torse de Vamp en manteau
    0xB979AF sous 0xD38F5A : sans lui, la tete flotte). Sans .cnp a elles, et rattachees au personnage (mdn + .cnp, humain) le
    plus proche dans la liste."""
    if zone not in cache:
        config = next(p for p in files.entries if p.endswith(f"/{zone}/data.cnf"))
        lines = [line.strip() for line in files.read(config).decode("latin-1").splitlines()]
        paths = {key & 0xFFFFFF: path for key, path in resources if key >> 24 == 0x0D}
        entries = []
        for index, line in enumerate(lines):
            match = RESOURCE_ENTRY.search(line)
            if match and match.group(3) == "mdn" and int(match.group(2), 16) in paths:
                entries.append((index, int(match.group(2), 16)))
        infos = {}
        for _index, ident in entries:
            try:
                data = files.read(paths[ident])
                infos[ident] = ({bone for bone, _p in mdn.bone_ids(data)}, set(texture_ids(data)),
                                mdn.MdnHeader(data).bone_count, paths[ident])
            except (ValueError, struct.error, IndexError):
                continue
        cnps = {key & 0xFFFFFF for key, _path in resources if key >> 24 == 0x11}
        owners = [(index, ident) for index, ident in entries
                  if ident in cnps and ident in infos and infos[ident][2] >= 60 and HEAD_BONE in infos[ident][0]]
        cache[zone] = (entries, infos, cnps, owners)
    entries, infos, cnps, owners = cache[zone]
    line = next((index for index, ident in entries if ident == model), None)
    if line is None or model not in infos or not owners:
        return []
    bones, textures, _count, _path = infos[model]
    found = []
    for index, other in entries:
        if other == model or other in pieces or other in cnps or other not in infos or abs(index - line) > LAYER_WINDOW:
            continue
        other_bones, other_textures, count, path = infos[other]
        shared = len(other_bones & bones)
        hair = 12 <= count <= 45 and HEAD_BONE in other_bones and shared >= 0.3 * count
        full = count >= 60 and shared >= 0.9 * count and not (other_textures & textures) and len(other_textures) <= 4
        partial = (count >= 20 and 0.25 * count <= shared < 0.9 * count and HEAD_BONE not in other_bones
                   and other_textures and len(other_textures & textures) >= 0.5 * len(other_textures))
        if (hair or full or partial) and min(owners, key=lambda owner: abs(owner[0] - index))[1] == model:
            if other not in [ident for ident, _p in found]:
                found.append((other, path))
    return found


def main(root: str) -> None:
    files = StageFiles(root)
    skeleton = files.read(next(p for p in files.entries if p.endswith(SNAKE_BODY)))
    zones = sorted({p.split("/")[-2] for p in files.entries if p.endswith("/data.cnf")})
    catalog = {}
    checked = set()
    txn_cache = {}
    eqpp_cache = {}
    layer_cache = {}
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
                pieces = linked_pieces(files, resources, model, eqpp_cache)
                layers = model_layers(files, zone, resources, model, {piece for piece, _p in pieces}, layer_cache)
                for _piece, piece_path in pieces + layers:
                    wanted |= set(texture_ids(files.read(piece_path)))
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
                catalog[model] = (zone, mdn.MdnHeader(data).bone_count, tuple(needed),
                                  tuple(piece for piece, _path in pieces), tuple(layer for layer, _path in layers))
    out = os.path.join(os.path.dirname(__file__), "..", "mgs4trainer", "core", "model_catalog.py")
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write('"""Genere par tools/build_model_catalog.py : modeles portables par Snake.\n\n'
                     'identifiant du mdn -> (zone d\'origine, nombre d\'os, cles des txn\n'
                     'de cette zone qui decrivent ses textures et celles de ses pieces,\n'
                     'pieces liees : mdn de la zone cites avec lui par un .eqpp,\n'
                     'couches : modeles dessines avec lui, sans lien (cheveux, foulard))."""\n\nMODELS = {\n')
        for model in sorted(catalog, key=lambda m: (catalog[m][0], m)):
            zone, bones, txns, pieces, layers = catalog[model]
            handle.write(f"    {model:#08x}: ({zone!r}, {bones}, ({''.join(f'{t:#010x}, ' for t in txns)}), "
                         f"({''.join(f'{x:#08x}, ' for x in pieces)}), ({''.join(f'{x:#08x}, ' for x in layers)})),\n")
        handle.write("}\n")
    print(len(catalog), "modeles")


if __name__ == "__main__":
    main(sys.argv[1])
