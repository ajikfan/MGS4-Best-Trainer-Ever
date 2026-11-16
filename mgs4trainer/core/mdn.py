"""Modeles MDN de MGS4 (grand-boutiste, tels que dans les archives).

Format d'apres Codec (zoft123/codec, Codec.MGS/Files/MdnFile.cs, licence
MIT) : en-tete (signature "MDN ", identifiant, 8 nombres puis positions
des os, groupes, maillages, faces, definitions de sommets, materiaux,
textures, skins, tampon de sommets (+taille), tampon de faces (+taille),
bourrage, taille du fichier) ; os de 0x50 octets (identifiant, drapeaux,
parent, ?, positions) ; skins de 0x28 octets (?, nombre, bourrage, palette
de 32 numeros d'os globaux). Les sommets designent un os par sa place dans
la palette du skin de leur maillage.

Corps hybride (2026-11-14) : la geometrie d'un autre personnage sur le
squelette de Snake. Les squelettes humains du jeu partagent leurs os par
identifiant (PMC : 62 os, tous presents chez Snake avec le meme parent,
numerotes autrement apres le 30e) : on donne au modele la table d'os de
Snake (ajoutee en fin de fichier) et on renumerote ses palettes."""

import struct

HEADER = struct.Struct(">4s21I")  # signature, identifiant, 8 nombres, 12 positions/tailles
BONE_SIZE = 0x50
SKIN_SIZE = 0x28
SKIN_PALETTE = 8  # palette de 32 octets apres (?, nombre u16, bourrage u16)


class MdnHeader:
    FIELDS = ("id", "bone_count", "group_count", "mesh_count", "face_count", "vertex_def_count",
              "material_count", "texture_count", "skin_count", "bone_offset", "group_offset",
              "mesh_offset", "face_offset", "vertex_def_offset", "material_offset", "texture_offset",
              "skin_offset", "vertex_buffer_offset", "vertex_buffer_size", "face_buffer_offset",
              "face_buffer_size")

    def __init__(self, data: bytes):
        values = HEADER.unpack_from(data, 0)
        if values[0] != b"MDN ":
            raise ValueError("pas un modele MDN")
        for name, value in zip(self.FIELDS, values[1:]):
            setattr(self, name, value)
        self.file_size = struct.unpack_from(">I", data, HEADER.size + 4)[0]


def bone_ids(data: bytes) -> list[tuple[int, int]]:
    """[(identifiant, parent)] des os."""
    header = MdnHeader(data)
    return [struct.unpack_from(">Ii", data, header.bone_offset + i * BONE_SIZE)[:1]
            + struct.unpack_from(">i", data, header.bone_offset + i * BONE_SIZE + 8)
            for i in range(header.bone_count)]


MIN_SHARED = 0.5  # part des os de source presents tels quels dans skeleton


def skeleton_mapping(source: bytes, skeleton: bytes) -> dict[int, int] | None:
    """Numero d'os de source -> numero dans skeleton, par identifiant ; un
    os absent suit son ancetre le plus proche present (doigts, visage,
    accessoires d'un autre personnage : s03a70l, 120 os dont 110 communs).
    None si la racine n'est pas commune ou trop peu d'os en commun."""
    target = {bone: index for index, (bone, _parent) in enumerate(bone_ids(skeleton))}
    source_bones = bone_ids(source)
    if not source_bones or sum(bone in target for bone, _p in source_bones) < MIN_SHARED * len(source_bones):
        return None
    mapping = {}
    for index in range(len(source_bones)):
        current, steps = index, 0
        while current >= 0 and source_bones[current][0] not in target and steps < len(source_bones):
            current, steps = source_bones[current][1], steps + 1
        if current < 0 or steps >= len(source_bones):
            return None
        mapping[index] = target[source_bones[current][0]]
    return mapping


def skeleton_compatible(source: bytes, skeleton: bytes) -> bool:
    return skeleton_mapping(source, skeleton) is not None


BONE_LOCAL, BONE_WORLD, BONE_MAX, BONE_MIN = 0x10, 0x20, 0x30, 0x40  # positions (x, y, z, w)
MESH_SIZE, MESH_BOUNDS = 0x50, (0x20, 0x30, 0x40)  # maillage : max, min, position (vec4)
MESH_VERTEX_DEF, MESH_VERTEX_COUNT = 0x10, 0x18
VERTEX_DEF_SIZE = 0x30  # ?, nombre de champs, pas, position ; 16 types ; 16 positions
VERTEX_POSITION = 0     # type de champ (4 bits bas) : position, 3 flottants
SCALE_MIN, SCALE_MAX = 1.3, 3.0  # enfants et singe (1,47 a 2,7) ; pas les adultes (<= 1,25) ni les petits modeles (poule : 5,2)


def leg_scale(source: bytes, skeleton: bytes) -> float:
    """Rapport des jambes (os commun le plus bas, sous le bassin a
    l'origine) : les animations de Snake placent le bassin a sa hauteur ;
    un petit modele (singe de Drebin 0xC13923 : 371 contre 1000, enfants)
    leviterait (2026-11-15)."""
    src = {bone: i for i, (bone, _p) in enumerate(bone_ids(source))}
    sh, kh = MdnHeader(skeleton), MdnHeader(source)
    best = None
    for i, (bone, _p) in enumerate(bone_ids(skeleton)):
        if bone not in src:
            continue
        y = struct.unpack_from(">f", skeleton, sh.bone_offset + i * BONE_SIZE + BONE_WORLD + 4)[0]
        if best is None or y < best[0]:
            best = (y, src[bone])
    if best is None or best[0] >= 0:
        return 1.0
    y = struct.unpack_from(">f", source, kh.bone_offset + best[1] * BONE_SIZE + BONE_WORLD + 4)[0]
    return best[0] / y if y < 0 else 1.0


def scaled(source: bytes, factor: float) -> bytes:
    """Modele agrandi autour de l'origine : sommets, os, bornes des maillages."""
    header = MdnHeader(source)
    out = bytearray(source)

    def scale(offset: int, count: int = 3) -> None:
        values = struct.unpack_from(f">{count}f", out, offset)
        struct.pack_into(f">{count}f", out, offset, *(v * factor for v in values))

    for i in range(header.bone_count):
        base = header.bone_offset + i * BONE_SIZE
        for field in (BONE_LOCAL, BONE_WORLD, BONE_MAX, BONE_MIN):
            scale(base + field)
    for m in range(header.mesh_count):
        base = header.mesh_offset + m * MESH_SIZE
        for field in MESH_BOUNDS:
            scale(base + field)
    done = set()
    for m in range(header.mesh_count):
        base = header.mesh_offset + m * MESH_SIZE
        definition, = struct.unpack_from(">I", out, base + MESH_VERTEX_DEF)
        vertices, = struct.unpack_from(">I", out, base + MESH_VERTEX_COUNT)
        vdef = header.vertex_def_offset + definition * VERTEX_DEF_SIZE
        _pad, fields, stride, start = struct.unpack_from(">4I", out, vdef)
        kinds = out[vdef + 0x10:vdef + 0x10 + fields]
        offsets = out[vdef + 0x20:vdef + 0x20 + fields]
        for kind, at in zip(kinds, offsets):
            if kind & 0x0F != VERTEX_POSITION:
                continue
            for v in range(vertices):
                position = header.vertex_buffer_offset + start + v * stride + at
                if position not in done:
                    done.add(position)
                    scale(position)
    return bytes(out)


def _bones_with_source_rest(source: bytes, skeleton: bytes) -> bytes:
    """Table d'os de skeleton (identifiants, parents, ordre) aux positions de
    repos de source pour les os communs ; les autres gardent leur decalage
    par rapport a leur parent. Sans cela, un petit modele (enfant ; singe de
    Drebin s01a20l 0xC13923, tete a 382 contre 560 chez Snake) est deforme
    par des os d'adulte : membres etires (2026-11-15)."""
    src = MdnHeader(source)
    skel = MdnHeader(skeleton)
    table = bytearray(skeleton[skel.bone_offset:skel.bone_offset + skel.bone_count * BONE_SIZE])
    rest = {}
    for i in range(src.bone_count):
        base = src.bone_offset + i * BONE_SIZE
        rest[struct.unpack_from(">I", source, base)[0]] = source[base + BONE_LOCAL:base + BONE_SIZE]
    world = {}
    pending = list(range(skel.bone_count))
    while pending:
        progress = False
        for i in list(pending):
            base = i * BONE_SIZE
            bone, _flags, parent = struct.unpack_from(">IIi", table, base)
            if parent >= 0 and parent not in world:
                continue
            old_world = struct.unpack_from(">3f", table, base + BONE_WORLD)
            if bone in rest:
                table[base + BONE_LOCAL:base + BONE_SIZE] = rest[bone]
            else:
                local = struct.unpack_from(">3f", table, base + BONE_LOCAL)
                origin = world[parent] if parent >= 0 else (0.0, 0.0, 0.0)
                new_world = tuple(o + v for o, v in zip(origin, local))
                shift = tuple(n - o for n, o in zip(new_world, old_world))
                struct.pack_into(">3f", table, base + BONE_WORLD, *new_world)
                for field in (BONE_MAX, BONE_MIN):
                    bounds = struct.unpack_from(">3f", table, base + field)
                    struct.pack_into(">3f", table, base + field, *(b + s for b, s in zip(bounds, shift)))
            world[i] = struct.unpack_from(">3f", table, base + BONE_WORLD)
            pending.remove(i)
            progress = True
        if not progress:
            raise ValueError("hierarchie d'os circulaire")
    return bytes(table)


def build_hybrid(source: bytes, skeleton: bytes) -> bytes:
    """Geometrie de source sur la table d'os de skeleton (palettes renumerotees),
    agrandie si ses jambes sont nettement plus courtes (enfants, singe)."""
    factor = leg_scale(source, skeleton)
    if SCALE_MIN <= factor <= SCALE_MAX:
        source = scaled(source, factor)
    remap = skeleton_mapping(source, skeleton)
    if remap is None:
        raise ValueError("squelettes incompatibles")
    src = MdnHeader(source)
    skel = MdnHeader(skeleton)
    if max(remap.values()) > 0xFF:
        raise ValueError("palette sur un octet : trop d'os")
    out = bytearray(source)
    for s in range(src.skin_count):
        base = src.skin_offset + s * SKIN_SIZE
        count = struct.unpack_from(">H", out, base + 4)[0]
        for k in range(min(count, 32)):
            out[base + SKIN_PALETTE + k] = remap[out[base + SKIN_PALETTE + k]]
    # table d'os de skeleton en fin de fichier (alignee sur 16)
    while len(out) % 16:
        out.append(0)
    new_bone_offset = len(out)
    out += _bones_with_source_rest(source, skeleton)
    struct.pack_into(">I", out, 8, skel.bone_count)                       # nombre d'os
    struct.pack_into(">I", out, 4 + 4 + 8 * 4, new_bone_offset)           # position des os
    struct.pack_into(">I", out, HEADER.size + 4, len(out))                # taille du fichier
    return bytes(out)


def hidden(source: bytes) -> bytes:
    """Copie invisible : tampon des faces mis a zero (tous les triangles
    aplatis sur le sommet 0), structures intactes (points d'attache, os)."""
    header = MdnHeader(source)
    out = bytearray(source)
    out[header.face_buffer_offset:header.face_buffer_offset + header.face_buffer_size] = bytes(header.face_buffer_size)
    return bytes(out)


# Pieces liees (2026-11-16) : un .eqpp de la zone cite le corps et une piece
# a part (foulard de Naomi 0x44911B pour 0xE28B85, physique de tissu) ; le
# jeu l'accroche au corps. Fusionnees dans le corps avant le modele hybride :
# leurs sections sont ajoutees a la suite (memes tailles d'entrees), leurs os
# propres (ceux de la physique) suivent l'os du corps le plus proche au
# repos (le foulard suit le cou, pas le bassin) : piece raide, sans tissu.
GROUP_SIZE, FACE_SIZE, MATERIAL_SIZE, TEXTURE_SIZE = 0x10, 0x10, 0x70, 0x20
HEADER_END = 0x80  # en-tete : ..., bourrage, taille du fichier, boite englobante
NO_PARENT = 0xFFFFFFFF


def _sections(data: bytes) -> dict[str, bytes]:
    h = MdnHeader(data)
    return {
        "bones": data[h.bone_offset:h.bone_offset + h.bone_count * BONE_SIZE],
        "groups": data[h.group_offset:h.group_offset + h.group_count * GROUP_SIZE],
        "meshes": data[h.mesh_offset:h.mesh_offset + h.mesh_count * MESH_SIZE],
        "faces": data[h.face_offset:h.face_offset + h.face_count * FACE_SIZE],
        "vdefs": data[h.vertex_def_offset:h.vertex_def_offset + h.vertex_def_count * VERTEX_DEF_SIZE],
        "materials": data[h.material_offset:h.material_offset + h.material_count * MATERIAL_SIZE],
        "textures": data[h.texture_offset:h.texture_offset + h.texture_count * TEXTURE_SIZE],
        "skins": data[h.skin_offset:h.skin_offset + h.skin_count * SKIN_SIZE],
        "vbuf": data[h.vertex_buffer_offset:h.vertex_buffer_offset + h.vertex_buffer_size],
        "fbuf": data[h.face_buffer_offset:h.face_buffer_offset + h.face_buffer_size],
    }


def _bone_worlds(data: bytes) -> list[tuple[int, tuple[float, float, float]]]:
    h = MdnHeader(data)
    return [(struct.unpack_from(">I", data, h.bone_offset + i * BONE_SIZE)[0],
             struct.unpack_from(">3f", data, h.bone_offset + i * BONE_SIZE + BONE_WORLD))
            for i in range(h.bone_count)]


def _pad16(data: bytes) -> bytes:
    return data + bytes(-len(data) % 16)


VERTEX_WEIGHT, VERTEX_BONES = 1, 7  # types de champ : poids (4 octets /255), os (4 numeros de palette)


def _piece_offsets(body: bytes, piece: bytes) -> list[tuple[float, float, float]]:
    """Decalage (corps - piece) de chaque os de la piece : par identifiant
    pour les os communs, celui du parent pour les autres. Les cheveux de
    Naomi en noir (0xD8B3EE) sont 240 plus bas que son corps (bassin a 0
    au lieu de 240) ; son foulard (0x6C29C2) a les memes positions."""
    body_world = dict(_bone_worlds(body))
    worlds = _bone_worlds(piece)
    parents = [parent for _bone, parent in bone_ids(piece)]
    offsets = [None] * len(worlds)

    def offset(i: int, depth: int = 0):
        if offsets[i] is None:
            bone, world = worlds[i]
            if bone in body_world:
                offsets[i] = tuple(b - p for b, p in zip(body_world[bone], world))
            elif 0 <= parents[i] < len(worlds) and depth < len(worlds):
                offsets[i] = offset(parents[i], depth + 1)
            else:
                offsets[i] = (0.0, 0.0, 0.0)
        return offsets[i]

    return [offset(i) for i in range(len(worlds))]


def _shift_vertices(piece: bytes, offsets) -> bytes:
    """Sommets de la piece deplaces du decalage de leurs os (ponderes)."""
    header = MdnHeader(piece)
    out = bytearray(piece)
    done = set()
    for m in range(header.mesh_count):
        base = header.mesh_offset + m * MESH_SIZE
        definition, skin_index, vertices = struct.unpack_from(">I", out, base + MESH_VERTEX_DEF)[0], \
            struct.unpack_from(">I", out, base + 0x14)[0], struct.unpack_from(">I", out, base + MESH_VERTEX_COUNT)[0]
        palette = [0]
        if header.skin_count:
            skin = header.skin_offset + skin_index * SKIN_SIZE
            count, = struct.unpack_from(">H", piece, skin + 4)
            palette = list(piece[skin + SKIN_PALETTE:skin + SKIN_PALETTE + min(count, 32)]) or [0]
        vdef = header.vertex_def_offset + definition * VERTEX_DEF_SIZE
        _pad, fields, stride, start = struct.unpack_from(">4I", out, vdef)
        kinds = [k & 0x0F for k in out[vdef + 0x10:vdef + 0x10 + fields]]
        at = dict(zip(kinds, out[vdef + 0x20:vdef + 0x20 + fields]))
        if VERTEX_POSITION not in at:
            continue
        for v in range(vertices):
            vertex = header.vertex_buffer_offset + start + v * stride
            if vertex + at[VERTEX_POSITION] in done:
                continue
            done.add(vertex + at[VERTEX_POSITION])
            slots = list(out[vertex + at[VERTEX_BONES]:vertex + at[VERTEX_BONES] + 4]) if VERTEX_BONES in at else [0]
            weights = [w / 255 for w in out[vertex + at[VERTEX_WEIGHT]:vertex + at[VERTEX_WEIGHT] + 4]] \
                if VERTEX_WEIGHT in at else [1.0]
            total = sum(weights[:len(slots)]) or 1.0
            shift = [0.0, 0.0, 0.0]
            for slot, weight in zip(slots, weights):
                bone = palette[slot] if slot < len(palette) else palette[0]
                for k in range(3):
                    shift[k] += weight / total * offsets[bone][k]
            position = vertex + at[VERTEX_POSITION]
            values = struct.unpack_from(">3f", out, position)
            struct.pack_into(">3f", out, position, *(p + s for p, s in zip(values, shift)))
    return bytes(out)


def merge(body: bytes, piece: bytes) -> bytes:
    """Corps + piece liee ou couche, sur les os du corps (piece ramenee dans
    le repere du corps si ses os communs sont ailleurs)."""
    body_bones = _bone_worlds(body)
    by_id = {bone: i for i, (bone, _w) in enumerate(body_bones)}

    def nearest(position) -> int:
        return min(range(len(body_bones)),
                   key=lambda i: sum((a - b) ** 2 for a, b in zip(body_bones[i][1], position)))

    offsets = _piece_offsets(body, piece)
    if any(any(abs(c) > 0.01 for c in o) for o in offsets):
        piece = _shift_vertices(piece, offsets)
    worlds = [(bone, tuple(w + o for w, o in zip(world, offset)))
              for (bone, world), offset in zip(_bone_worlds(piece), offsets)]
    bone_map = [by_id[bone] if bone in by_id else nearest(world) for bone, world in worlds]
    a, b = _sections(body), _sections(piece)
    ha = MdnHeader(body)
    counts = {name: len(a[name]) // size for name, size in (
        ("groups", GROUP_SIZE), ("faces", FACE_SIZE), ("vdefs", VERTEX_DEF_SIZE),
        ("materials", MATERIAL_SIZE), ("textures", TEXTURE_SIZE), ("skins", SKIN_SIZE))}
    vbuf_a, fbuf_a = _pad16(a["vbuf"]), _pad16(a["fbuf"])

    groups = bytearray(b["groups"])
    for i in range(0, len(groups), GROUP_SIZE):
        parent, = struct.unpack_from(">I", groups, i + 8)
        if parent != NO_PARENT:
            struct.pack_into(">I", groups, i + 8, parent + counts["groups"])
    meshes = bytearray(b["meshes"])
    for i in range(0, len(meshes), MESH_SIZE):
        group, flags, nfaces, face, vdef, skin = struct.unpack_from(">6I", meshes, i)
        struct.pack_into(">6I", meshes, i, group + counts["groups"], flags, nfaces,
                         face + counts["faces"], vdef + counts["vdefs"], skin + counts["skins"])
    faces = bytearray(b["faces"])
    for i in range(0, len(faces), FACE_SIZE):
        offset, material = struct.unpack_from(">II", faces, i + 4)
        struct.pack_into(">II", faces, i + 4, offset + len(fbuf_a), material + counts["materials"])
    vdefs = bytearray(b["vdefs"])
    for i in range(0, len(vdefs), VERTEX_DEF_SIZE):
        offset, = struct.unpack_from(">I", vdefs, i + 0xC)
        struct.pack_into(">I", vdefs, i + 0xC, offset + len(vbuf_a))
    materials = bytearray(b["materials"])
    for i in range(0, len(materials), MATERIAL_SIZE):
        count, = struct.unpack_from(">I", materials, i + 8)
        for t in range(min(count, 8)):
            texture, = struct.unpack_from(">I", materials, i + 0x10 + t * 4)
            struct.pack_into(">I", materials, i + 0x10 + t * 4, texture + counts["textures"])
    skins = bytearray(b["skins"])
    for i in range(0, len(skins), SKIN_SIZE):
        count, = struct.unpack_from(">H", skins, i + 4)
        for k in range(min(count, 32)):
            skins[i + SKIN_PALETTE + k] = bone_map[skins[i + SKIN_PALETTE + k]]
    if max(bone_map, default=0) > 0xFF:
        raise ValueError("palette sur un octet : trop d'os")

    order = (("bones", a["bones"]), ("groups", a["groups"] + groups), ("meshes", a["meshes"] + meshes),
             ("faces", a["faces"] + faces), ("vdefs", a["vdefs"] + vdefs),
             ("materials", a["materials"] + materials), ("textures", a["textures"] + b["textures"]),
             ("skins", a["skins"] + skins), ("vbuf", vbuf_a + b["vbuf"]), ("fbuf", fbuf_a + b["fbuf"]))
    out = bytearray(body[:HEADER_END])
    offsets = {}
    for name, data in order:
        out += bytes(-len(out) % 16)
        offsets[name] = (len(out), len(data))
        out += data
    out += bytes(-len(out) % 16)
    n = {name: offsets[name][1] // size for name, size in (
        ("bones", BONE_SIZE), ("groups", GROUP_SIZE), ("meshes", MESH_SIZE), ("faces", FACE_SIZE),
        ("vdefs", VERTEX_DEF_SIZE), ("materials", MATERIAL_SIZE), ("textures", TEXTURE_SIZE),
        ("skins", SKIN_SIZE))}
    struct.pack_into(">21I", out, 4, ha.id, n["bones"], n["groups"], n["meshes"], n["faces"], n["vdefs"],
                     n["materials"], n["textures"], n["skins"],
                     offsets["bones"][0], offsets["groups"][0], offsets["meshes"][0], offsets["faces"][0],
                     offsets["vdefs"][0], offsets["materials"][0], offsets["textures"][0], offsets["skins"][0],
                     offsets["vbuf"][0], offsets["vbuf"][1], offsets["fbuf"][0], offsets["fbuf"][1])
    struct.pack_into(">I", out, HEADER.size + 4, len(out))
    return bytes(out)


def texture_ids(data: bytes) -> list[int]:
    header = MdnHeader(data)
    return [struct.unpack_from(">I", data, header.texture_offset + i * TEXTURE_SIZE)[0]
            for i in range(header.texture_count)]
