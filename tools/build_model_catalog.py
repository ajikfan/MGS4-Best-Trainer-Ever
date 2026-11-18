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
NECK_BONE = 0xF8D3CC   # cou : racine des tetes a part (visages de Old Snake, tete de Naomi)
LIGHT_GEOMETRY = 100000  # octets de sommets sous lesquels un modele n'est pas un personnage (blessure de Big Mama 0x88811d : 16 Ko)
ALSO_SHARED = 0.15      # parente faible : nom deduit avec un point d'interrogation
KIN_SHARED = 0.6        # part de textures communes pour reprendre le nom d'un autre modele
ANIMAL_SHARED = 0.8    # part d'os communs avec Snake sous laquelle un petit modele sans tete est un animal
LAYER_WINDOW = 20      # lignes du data.cnf autour du modele (queue de cheval de Raven : +16)
# Couches ajoutees a la main, la ou les regles ne suffisent pas (elles
# aggravaient d'autres modeles quand on les elargissait, 2026-11-16) :
# modele -> couches de sa zone du catalogue.
MANUAL_LAYERS = {
    0xB531B9: (0x2A9FA2,),  # Old Snake des cinematiques : sa tete (visage et cheveux)
    # Screaming Mantis (Bete) : ses bras (3 de chaque cote par modele), ses
    # 4 couteaux et ses poupees de The Sorrow et de Psycho Mantis (piece_poses)
    # (couteaux 0xE48402 de s05a20l abandonnes : gel du jeu apres quelques pas, 2026-11-17)
    0x273008: (0xE4B650, 0xE4B656, 0x073440, 0x773388),
    0x203008: (0x205BD6,),  # Laughing Octopus (Bete) : ses pieuvres (mdn.MANUAL_ATTACHMENTS)
    0x263008: (0xEAD962, 0xE56F84),  # Raging Raven (Bete) : ailes et 6 missiles (mdn.MANUAL_ATTACHMENTS)
}
# Couches venues d'une autre zone que celle du modele (meme squelette,
# txn pris dans la zone de la couche, qui doit etre au catalogue) :
CROSS_ZONE_LAYERS = {
    0x25DDE5: (0x88811D,),  # Big Mama : sa blessure par balle (s03a65l)
    0xA13175: (0x88811D,),
}
# Couches que les regles trouvent a tort (2026-11-17) : jambe en
# camouflage pastèque de Old Snake (0x51A499, effet de cinematique) et
# piece mal placee dans la tete de Jonathan (0xCBA575).
# 0x63C031 : tete et cheveux a part (39 os, 17 textures a elle) pris pour les
# cheveux de Laughing Octopus (Beauty) 0x70300a, 2026-11-18.
# 0xCE9BCD : effet d'eau rouge, pris pour une couche de Crying Wolf (Beauty).
NOT_LAYERS = {0x51A499, 0xCBA575, 0x63C031, 0xCE9BCD}


HEADED_VERTICES = 200
HEAD_REGION = 150


def head_vertices(data: bytes) -> int:
    """Sommets a plus de HEAD_REGION au-dessus du cou (0 sans cou)."""
    neck = dict(mdn._bone_worlds(data)).get(NECK_BONE)
    if neck is None:
        return 0
    header = mdn.MdnHeader(data)
    count = 0
    for m in range(header.mesh_count):
        base = header.mesh_offset + m * mdn.MESH_SIZE
        vdef, = struct.unpack_from(">I", data, base + mdn.MESH_VERTEX_DEF)
        vertices, = struct.unpack_from(">I", data, base + mdn.MESH_VERTEX_COUNT)
        at_def = header.vertex_def_offset + vdef * mdn.VERTEX_DEF_SIZE
        _pad, fields, stride, start = struct.unpack_from(">4I", data, at_def)
        at = dict(zip([k & 15 for k in data[at_def + 16:at_def + 16 + fields]], data[at_def + 32:at_def + 32 + fields]))
        if mdn.VERTEX_POSITION not in at:
            continue
        for v in range(vertices):
            y, = struct.unpack_from(">f", data, header.vertex_buffer_offset + start + v * stride + at[mdn.VERTEX_POSITION] + 4)
            count += y > neck[1] + HEAD_REGION
    return count


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
    # pieces accrochees par le .cnp du modele (os racine cite comme point
    # d'attache, aucun os commun avec le corps : cheveux de Big Mama 0x78A3F2
    # sur la tete, leur .eqpp ne cite pas le corps) ; une par racine (deux
    # coiffures partagent la sienne : la premiere listee)
    cnp_path = dict(resources).get(0x11000000 | model)
    if cnp_path:
        if cnp_path not in cache:
            cache[cnp_path] = files.read(cnp_path)
        attachments = mdn.cnp_attachments(cache[cnp_path])
        body_bones = {bone for bone, _p in mdn.bone_ids(files.read(mdns[model]))} if model in mdns else set()
        roots = set()
        for other, other_path in mdns.items():
            if other == model or other in pieces:
                continue
            key = ("os", other_path)
            if key not in cache:
                try:
                    cache[key] = [bone for bone, _p in mdn.bone_ids(files.read(other_path))]
                except (ValueError, struct.error, IndexError):
                    cache[key] = []
            bones = cache[key]
            if bones and bones[0] in attachments and bones[0] not in roots and not body_bones & set(bones):
                roots.add(bones[0])
                pieces[other] = other_path
    return sorted(pieces.items())


def model_layers(files, zone: str, resources, model: int, pieces, cache: dict) -> list[tuple[int, str]]:
    """Couches du modele (2026-11-16) : modeles a part que rien ne relie au
    corps mais que le jeu dessine avec lui, listes pres de lui dans le
    data.cnf (Naomi en noir 0x2DA964 : foulard 0x6C29C2, cheveux 0xD8B3EE).
    Cheveux : 12 a 45 os, l'os de la tete, au moins 30 % d'os communs.
    Couche complete : meme squelette (90 %), aucune texture commune (les
    variantes de soldats partagent toutes les leurs), 4 textures au plus.
    Couche partielle : au moins 5 os dont 25 % communs (tous si moins de
    60 os : la queue de cheval de Raven 0xAFBAB est sur son squelette),
    sans la tete, au moins la moitie de ses textures prises au corps (torse
    de Vamp en manteau 0xB979AF sous 0xD38F5A : sans lui, la tete flotte). Sans .cnp a elles, et rattachees au personnage (mdn + .cnp, humain) le
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
                header = mdn.MdnHeader(data)
                infos[ident] = ({bone for bone, _p in mdn.bone_ids(data)}, set(texture_ids(data)),
                                header.bone_count, paths[ident], header.material_count)
            except (ValueError, struct.error, IndexError):
                continue
        cnps = {key & 0xFFFFFF for key, _path in resources if key >> 24 == 0x11}
        owners = [(index, ident) for index, ident in entries
                  if ident in cnps and ident in infos and infos[ident][2] >= 60 and HEAD_BONE in infos[ident][0]]
        cache[zone] = (entries, infos, cnps, owners)
    entries, infos, cnps, owners = cache[zone]
    manual = [(other, infos[other][3]) for other in MANUAL_LAYERS.get(model, ()) if other in infos]
    line = next((index for index, ident in entries if ident == model), None)
    if line is None or model not in infos or not owners:
        return manual
    bones, textures = infos[model][:2]
    found = []
    for index, other in entries:
        if (other == model or other in pieces or other in cnps or other not in infos or other in NOT_LAYERS
                or abs(index - line) > LAYER_WINDOW):
            continue
        other_bones, other_textures, count, path, materials = infos[other]
        shared = len(other_bones & bones)
        hair = 12 <= count <= 45 and HEAD_BONE in other_bones and shared >= 0.3 * count
        # fantome : tout le squelette, une seule matiere et une seule texture
        # (silhouette lumineuse des soldats 0x63F843, 0x43F843, de Jonathan 0xE3F5F9)
        ghost = materials == 1 and len(other_textures) == 1
        full = (count >= 60 and shared >= 0.9 * count and not (other_textures & textures) and len(other_textures) <= 4
                and not ghost)
        partial = (count >= 5 and shared >= 0.25 * count and (shared < 0.9 * count or count < 60)
                   and HEAD_BONE not in other_bones
                   and other_textures and len(other_textures & textures) >= 0.5 * len(other_textures))
        if (hair or full or partial) and min(owners, key=lambda owner: abs(owner[0] - index))[1] == model:
            if other not in [ident for ident, _p in found]:
                found.append((other, path))
    for other in MANUAL_LAYERS.get(model, ()):
        path = infos[other][3] if other in infos else None
        if path and other not in [ident for ident, _p in found]:
            found.append((other, path))
    return found


# Noms d'origine des modeles (2026-11-17) : l'identifiant d'un mdn est
# l'empreinte StrCode (24 bits, celle des anciens Metal Gear) de son nom,
# <personnage>_<tenue>_<variante> (sna_def = corps de Snake 0x413AA8,
# sna_face_def = son visage, otc_def_dmo = Otacon des cinematiques, dmo =
# cinematique). Les noms sont retrouves en essayant les codes de
# personnage ci-dessous avec des formes courantes ; un code inconnu donne
# trop de coincidences sur 24 bits pour etre essaye.
CHARACTER_CODES = (
    "sna", "rai", "otc", "mei", "bmm", "vmp", "dre", "oce", "cam", "big", "zro", "psy", "jny", "jhn",
    "edo", "mrl", "ros", "sny", "boy", "mky", "hen", "pgn", "rvn", "mep", "sap", "eep", "mem", "res",
    "reb", "kgm", "nao", "bbs", "bbl", "bbr", "bbw", "sac", "pwd",
)
NAME_FORMS = (["_def", "_def_dmo", "_coat_dmo", "_coat", "_armr", "_def_low", "_dmo", "_bst_def", "_bty_def",
               "_low", "_suit_dmo", "_suit",
               "_psy_def", "_sor_def", "_bst_armr", "_bst_arml", "_face_def"]
              + [f"_def_{c}" for c in "abcdefgh"] + [f"_def_dmo_{c}" for c in "abcd"]
              # niveaux de detail (2026-11-17) : civils sac_def_a_low / _mid /
              # sac_def_a (homme), b femme, c fillette ; miliciens mem_def_a_low...
              + ["_mid", "_def_mid"] + [f"_def_{c}_{lod}" for c in "abcdefgh" for lod in ("low", "mid")])


def strcode(text: str) -> int:
    value = 0
    for char in text.encode():
        value = ((value >> 19) | (value << 5)) & 0xFFFFFF
        value = (value + char) & 0xFFFFFF
    return value


def original_names(models) -> dict[int, str]:
    out = {}
    for code in CHARACTER_CODES:
        for form in NAME_FORMS:
            ident = strcode(code + form)
            if ident in models and ident not in out:
                out[ident] = code + form
    return out


def main(root: str) -> None:
    files = StageFiles(root)
    skeleton = files.read(next(p for p in files.entries if p.endswith(SNAKE_BODY)))
    zones = sorted({p.split("/")[-2] for p in files.entries if p.endswith("/data.cnf")})
    catalog = {}
    with_head, animals, light, ghosts = set(), set(), set(), set()
    every = set()  # tous les mdn des zones (noms d'origine, meme hors catalogue)
    snake_bones = {bone for bone, _p in mdn.bone_ids(skeleton)}
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
        every |= {key & 0xFFFFFF for key, _p in resources if key >> 24 == 0x0D}
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
            # txn du modele et de ses pieces d'abord, puis les plus petits :
            # le premier venu pouvait etre celui de toute la zone (pieuvres
            # de Laughing Octopus : 41 Mo au lieu de 7 textures, au-dela de
            # la reserve du trainer, 2026-11-17)
            own = {model} | {piece for piece, _p in pieces + layers}
            sizes = {}
            for txn_key, txn_path in resources:
                if txn_key >> 24 == 0x03 and txn_path not in sizes:
                    if txn_path not in txn_cache:
                        txn_cache[txn_path] = files.read(txn_path)
                    sizes[txn_path] = len(txn_cache[txn_path])
            ordered = sorted((r for r in resources if r[0] >> 24 == 0x03),
                             key=lambda r: ((r[0] & 0xFFFFFF) not in own, sizes[r[1]]))
            for txn_key, txn_path in ordered:
                if not wanted:
                    continue
                if txn_path not in txn_cache:
                    txn_cache[txn_path] = files.read(txn_path)
                found = {t for t in wanted if struct.pack(">I", t) in txn_cache[txn_path]}
                if found:
                    needed.append(txn_key)
                    wanted -= found
            if not wanted:
                own_bones = {bone for bone, _p in mdn.bone_ids(data)}
                if mdn.MdnHeader(data).vertex_buffer_size < LIGHT_GEOMETRY:
                    light.add(model)
                # fantome : tout un squelette, une matiere, une texture (silhouette lumineuse)
                if mdn.MdnHeader(data).material_count == 1 and len(set(texture_ids(data))) == 1 and mdn.MdnHeader(data).bone_count >= 60:
                    ghosts.add(model)
                if HEAD_BONE in own_bones:
                    with_head.add(model)
                elif (mdn.MdnHeader(data).bone_count < 60
                      and len(own_bones & snake_bones) < ANIMAL_SHARED * len(own_bones)):
                    animals.add(model)
                catalog[model] = (zone, mdn.MdnHeader(data).bone_count, tuple(needed),
                                  tuple(piece for piece, _path in pieces),
                                  tuple(layer for layer, _path in layers) + CROSS_ZONE_LAYERS.get(model, ()))
    # couches d'autres zones absentes du catalogue (couteaux de Mantis : 1 os) :
    # zone qui les range et txn qui decrivent leurs textures
    sources = {}
    for layer in sorted({x for layers in CROSS_ZONE_LAYERS.values() for x in layers} - set(catalog)):
        for zone in zones:
            if not ZONE.match(zone):
                continue
            try:
                resources = files.zone_resources(zone)
            except (StopIteration, ValueError):
                continue
            path = dict(resources).get(0x0D000000 | layer)
            if path is None:
                continue
            wanted, needed = set(texture_ids(files.read(path))), []
            for txn_key, txn_path in resources:
                if txn_key >> 24 == 0x03 and wanted:
                    found = {t for t in wanted if struct.pack(">I", t) in files.read(txn_path)}
                    if found:
                        needed.append(txn_key)
                        wanted -= found
            if not wanted:
                sources[layer] = (zone, tuple(needed))
                break
    # tetes : visage complet a part (os de la tete, racine au cou, 30 os ou plus)
    heads = set()
    for owner, (zone, _b, _t, pieces_of, layers_of) in catalog.items():
        paths = dict(files.zone_resources(zone))
        for model in (owner,) + pieces_of + layers_of:
            path = paths.get(0x0D000000 | model)
            if path is None or model in heads:
                continue
            ids = mdn.bone_ids(files.read(path))
            if len(ids) >= 30 and ids[0][0] == NECK_BONE and HEAD_BONE in {b for b, _p in ids}:
                heads.add(model)
    # tete dans la geometrie : 200 sommets ou plus a 150 au-dessus du cou (le FROG,
    # les formes Bete de Raven et de Mantis n'ont pas l'os de la tete mais une tete)
    headed = set()
    for model, (zone, _b, _t, _p, _l) in catalog.items():
        path = dict(files.zone_resources(zone)).get(0x0D000000 | model)
        if path and head_vertices(files.read(path)) >= HEADED_VERTICES:
            headed.add(model)
    textures = {}
    for model, (zone, _b, _t, _p, _l) in catalog.items():
        path = dict(files.zone_resources(zone)).get(0x0D000000 | model)
        textures[model] = set(texture_ids(files.read(path))) if path else set()
    kin = {}
    for model, own in textures.items():
        if not own or catalog[model][1] < 60:
            continue
        near = sorted(((len(own & other) / len(own), m) for m, other in textures.items()
                       if m != model and catalog[m][1] >= 60 and len(own & other) >= KIN_SHARED * len(own)), reverse=True)
        if near:
            kin[model] = tuple(m for _s, m in near[:4])
    also = {}
    for model, own in textures.items():
        near = sorted(((len(own & other) / len(own), m) for m, other in textures.items()
                       if own and m != model and len(own & other) >= ALSO_SHARED * len(own)), reverse=True)
        if near:
            also[model] = tuple((m, round(s * 100)) for s, m in near[:12])
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
        names = original_names(every)
        handle.write("\n# Noms d'origine retrouves (identifiant = empreinte StrCode 24 bits du\n"
                     "# nom ; seuls les codes de personnage connus, voir CHARACTER_CODES).\n"
                     "NAMES = {\n")
        for model in sorted(names):
            handle.write(f"    {model:#08x}: {names[model]!r},\n")
        handle.write("}\n")
        handle.write("\n# Modeles dont le squelette a l'os de la tete (classement de la liste :\n"
                     "# petit modele avec tete = tete ou cheveux, sans tete = animal).\n"
                     "WITH_HEAD = {\n")
        for model in sorted(with_head & set(catalog)):
            handle.write(f"    {model:#08x},\n")
        handle.write("}\n")
        handle.write("\n# Animaux : moins de 60 os, sans tete, moins de 80 % d'os communs avec\n"
                     "# Snake (poule 17/28, pigeon 17/32) ; les civils simplifies de s02a90l\n"
                     "# (32 os sans tete, 30 a 32 communs) restent des humains.\n"
                     "ANIMALS = {\n")
        for model in sorted(animals & set(catalog)):
            handle.write(f"    {model:#08x},\n")
        handle.write("}\n")
        handle.write("\n# Geometrie legere (moins de 100 Ko de sommets) : piece ou accessoire,\n"
                     "# pas un personnage (blessure par balle de Big Mama 0x88811d, robe de Sunny).\n"
                     "LIGHT = {\n")
        for model in sorted(light & set(catalog)):
            handle.write(f"    {model:#08x},\n")
        handle.write("}\n")
        handle.write("\n# Couches d'autres zones hors catalogue (pas dans la liste) : zone, txn.\nLAYER_SOURCES = {\n")
        for model in sorted(sources):
            zone, txns = sources[model]
            handle.write(f"    {model:#08x}: ({zone!r}, ({''.join(f'{t:#010x}, ' for t in txns)})),\n")
        handle.write("}\n")
        handle.write("\n# Fantomes : squelette complet, une matiere, une texture (silhouettes lumineuses).\nGHOSTS = {\n")
        for model in sorted(ghosts & set(catalog)):
            handle.write(f"    {model:#08x},\n")
        handle.write("}\n")
        # Parente par les textures (2026-11-18) : un modele sans nom qui partage
        # au moins KIN_SHARED de ses textures avec un autre est le meme personnage
        # (Naomi en blouse 0xAC5108 / 0xE28B85 : 94 %, Raiden 0x432305 / 0x1D31B4 : 100 %)
        handle.write("\n# Parente par les textures : modele -> autres modeles du catalogue (60 os ou plus)\n"
                     "# qui ont au moins 60 % de ses textures, du plus proche au moins proche.\nKIN = {\n")
        for model in sorted(kin):
            handle.write(f"    {model:#08x}: ({''.join(f'{x:#08x}, ' for x in kin[model])})," + "\n")
        handle.write("}\n")
        handle.write("\n# Parente faible (15 % des textures ou plus) : modele -> ((autre, %), ...).\nALSO = {\n")
        for model in sorted(also):
            handle.write(f"    {model:#08x}: ({''.join(f'({m:#08x}, {s}), ' for m, s in also[model])})," + "\n")
        handle.write("}\n")
        handle.write("\n# Tetes a part (visage complet sur le cou) : choix exclusif dans l'onglet Apparence.\nHEADS = {\n")
        for model in sorted(heads):
            handle.write(f"    {model:#08x}," + "\n")
        handle.write("}\n")
        handle.write("\n# Modeles qui ont une tete dans leur geometrie (choix par defaut : tete du modele seule).\nHEADED = {\n")
        for model in sorted(headed):
            handle.write(f"    {model:#08x}," + "\n")
        handle.write("}\n")
    print(len(catalog), "modeles,", len(names), "noms d'origine,", len(with_head & set(catalog)), "avec tete")


if __name__ == "__main__":
    main(sys.argv[1])
