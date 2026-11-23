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


def skeleton_mapping(source: bytes, skeleton: bytes, min_shared: float = MIN_SHARED) -> dict[int, int] | None:
    """Numero d'os de source -> numero dans skeleton, par identifiant ; un
    os absent suit son ancetre le plus proche present (doigts, visage,
    accessoires d'un autre personnage : s03a70l, 120 os dont 110 communs).
    None si la racine n'est pas commune ou trop peu d'os en commun."""
    target = {bone: index for index, (bone, _parent) in enumerate(bone_ids(skeleton))}
    source_bones = bone_ids(source)
    if not source_bones or sum(bone in target for bone, _p in source_bones) < min_shared * len(source_bones):
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


NPC_COVER = 0.8  # part des os du PNJ presents dans le modele


def npc_compatible(source: bytes, skeleton: bytes) -> bool:
    """Modele posable sur le squelette d'un PNJ (2026-11-23) : il en couvre
    presque tous les os (corps d'un soldat : 62 os sur 71 pour Meryl, Mei Ling
    et Naomi), et chacun de ses os en plus suit un parent commun. La regle de
    Snake (moitie des os du MODELE dans le squelette) refusait Naomi en blouse
    (62/128) alors que tout son corps a ses os chez le soldat."""
    target = bone_ids(skeleton)
    have = {bone for bone, _p in bone_ids(source)}
    if not target or sum(bone in have for bone, _p in target) < NPC_COVER * len(target):
        return False
    return skeleton_mapping(source, skeleton, 0.0) is not None


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


def build_hybrid(source: bytes, skeleton: bytes, min_shared: float = MIN_SHARED) -> bytes:
    """Geometrie de source sur la table d'os de skeleton (palettes renumerotees),
    agrandie si ses jambes sont nettement plus courtes (enfants, singe)."""
    factor = leg_scale(source, skeleton)
    # agrandi (enfants, singe) ou reduit (Psycho Mantis 0x6D31AE : squelette
    # deux fois plus grand, il s'enfoncait dans le sol), meme bornes inversees
    if SCALE_MIN <= factor <= SCALE_MAX or 1 / SCALE_MAX <= factor <= 1 / SCALE_MIN:
        source = scaled(source, factor)
    remap = skeleton_mapping(source, skeleton, min_shared)
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


def _pose_vertices(piece: bytes, poses) -> bytes:
    """Sommets de la piece figes dans une pose relevee en jeu : par os, une
    matrice (R 3x3 en lignes, t), v' = v * R + t, ponderee par les poids
    du sommet (pieuvres de Laughing Octopus, core/piece_poses.py)."""
    header = MdnHeader(piece)
    out = bytearray(piece)
    done = set()
    for m in range(header.mesh_count):
        base = header.mesh_offset + m * MESH_SIZE
        definition, = struct.unpack_from(">I", out, base + MESH_VERTEX_DEF)
        skin_index, = struct.unpack_from(">I", out, base + 0x14)
        vertices, = struct.unpack_from(">I", out, base + MESH_VERTEX_COUNT)
        palette = [0]
        if header.skin_count:
            skin = header.skin_offset + skin_index * SKIN_SIZE
            count, = struct.unpack_from(">H", piece, skin + 4)
            palette = list(piece[skin + SKIN_PALETTE:skin + SKIN_PALETTE + min(count, 32)]) or [0]
        vdef = header.vertex_def_offset + definition * VERTEX_DEF_SIZE
        _pad, fields, stride, start = struct.unpack_from(">4I", out, vdef)
        at = dict(zip([k & 0x0F for k in out[vdef + 0x10:vdef + 0x10 + fields]], out[vdef + 0x20:vdef + 0x20 + fields]))
        if VERTEX_POSITION not in at:
            continue
        for v in range(vertices):
            vertex = header.vertex_buffer_offset + start + v * stride
            position = vertex + at[VERTEX_POSITION]
            if position in done:
                continue
            done.add(position)
            slots = list(out[vertex + at[VERTEX_BONES]:vertex + at[VERTEX_BONES] + 4]) if VERTEX_BONES in at else [0]
            weights = [w / 255 for w in out[vertex + at[VERTEX_WEIGHT]:vertex + at[VERTEX_WEIGHT] + 4]]                 if VERTEX_WEIGHT in at else [1.0]
            total = sum(weights[:len(slots)]) or 1.0
            x, y, z = struct.unpack_from(">3f", out, position)
            moved = [0.0, 0.0, 0.0]
            for slot, weight in zip(slots, weights):
                if not weight:
                    continue
                bone = palette[slot] if slot < len(palette) else palette[0]
                pose = poses[bone] if bone < len(poses) else poses[0]
                for k in range(3):
                    moved[k] += weight / total * (x * pose[k] + y * pose[3 + k] + z * pose[6 + k] + pose[9 + k])
            struct.pack_into(">3f", out, position, *moved)
    return bytes(out)


# Points d'attache du .cnp (2026-11-16) : nombre en +8, entrees de 0x40 en
# +0x10 : point, os du corps, os racine d'une piece (ou 1), drapeaux (0 si
# piece) ; decalage (x, y, z, w) en +0x10, rotation (quaternion x, y, z, w)
# en +0x20. Les pieces de Raven sans os commun avec son corps (queue de
# cheval 0xC0D252 : racine 0xDFDCA5 sur la tete, 148 plus haut et 142 en
# arriere ; cables de la tete, des bras, des jambes) y sont accrochees.
CNP_ENTRY = 0x40


# Points d'attache que le code du jeu pose lui-meme (aucun fichier) :
# os racine d'une piece -> (os du corps, decalage, rotation). Lus en jeu sur
# les matrices des os (instance +0x1E0, 0x40 par os) : la racine de chaque
# bras de Screaming Mantis (Bete, 0x273008) est sur un os du corps, sans
# decalage ni rotation (2026-11-17).
# Une chaine d'os du corps (4e element) : chaque os de la piece suit le plus
# proche d'entre eux au lieu de l'os d'attache, pour que la piece reprenne
# les mouvements de ce membre (bras mecaniques de Mantis sur les bras de
# Snake : epaule, bras, avant-bras, main ; Snake n'a pas leurs os a eux).
ARM_LEFT = (0x19543, 0x27A4C, 0xFAFA8B, 0xFBFA42)
ARM_RIGHT = (0x619D43, 0x62824C, 0x5B028C, 0x5C0243)
MANUAL_ATTACHMENTS = {
    0x1C35C4: (0x2236C4, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), ARM_LEFT),   # bras 0xE4B650
    0xDC35C4: (0xE246C4, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), ARM_RIGHT),  # bras 0xE4B656
    # pieuvres de Laughing Octopus (Bete, 0x203008) : racine de 0x205BD6 sur
    # l'os 0x14B512 du corps (pose de repos : meme position, 2026-11-17)
    0xF842DA: (0x14B512, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)),
    # cheveux de Crying Wolf (Beauty, 0x673113) 0x4525E8 : racine absente de son .cnp
    # (au bassin sinon) ; sommet du crane, comme ses autres pieces de tete (2026-11-18)
    0x392452: (0xF5D387, (0.0, 110.0, 0.0), (0.0, 0.0, 0.0, 1.0)),
    # ailes de Raging Raven (Bete, 0x263008) 0xEAD962 et ses 6 missiles 0xE56F84 :
    # sur l'os 0x7011C4 du dos (poses relevees en combat, 2026-11-17)
    0xCFE4DD: (0x7011C4, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)),
    0x1D370E: (0x7011C4, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)),
}


def cnp_attachments(cnp: bytes) -> dict[int, tuple[int, tuple, tuple]]:
    """os racine d'une piece -> (os du corps, decalage, rotation)."""
    count, = struct.unpack_from(">I", cnp, 8)
    out = {}
    for i in range(count):
        base = 0x10 + i * CNP_ENTRY
        _point, bone, root, flags = struct.unpack_from(">4I", cnp, base)
        if flags == 0:
            out[root] = (bone, struct.unpack_from(">3f", cnp, base + 0x10), struct.unpack_from(">4f", cnp, base + 0x20))
    return out


def _rotate(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    # v' = v + 2w (q x v) + 2 q x (q x v)
    cx, cy, cz = y * vz - z * vy, z * vx - x * vz, x * vy - y * vx
    ex, ey, ez = y * cz - z * cy, z * cx - x * cz, x * cy - y * cx
    return (vx + 2 * (w * cx + ex), vy + 2 * (w * cy + ey), vz + 2 * (w * cz + ez))


def _place_piece(piece: bytes, rotation, translation) -> bytes:
    """Positions des sommets tournees puis deplacees (piece accrochee)."""
    header = MdnHeader(piece)
    out = bytearray(piece)
    done = set()
    for m in range(header.mesh_count):
        base = header.mesh_offset + m * MESH_SIZE
        definition, = struct.unpack_from(">I", out, base + MESH_VERTEX_DEF)
        vertices, = struct.unpack_from(">I", out, base + MESH_VERTEX_COUNT)
        vdef = header.vertex_def_offset + definition * VERTEX_DEF_SIZE
        _pad, fields, stride, start = struct.unpack_from(">4I", out, vdef)
        at = dict(zip([k & 0x0F for k in out[vdef + 0x10:vdef + 0x10 + fields]], out[vdef + 0x20:vdef + 0x20 + fields]))
        if VERTEX_POSITION not in at:
            continue
        for v in range(vertices):
            position = header.vertex_buffer_offset + start + v * stride + at[VERTEX_POSITION]
            if position in done:
                continue
            done.add(position)
            moved = _rotate(rotation, struct.unpack_from(">3f", out, position))
            struct.pack_into(">3f", out, position, *(p + t for p, t in zip(moved, translation)))
    return bytes(out)


NECK_BONE = 0xF8D3CC  # cou : racine des modeles de tete (visage de Snake, tetes a part)


def piece_key(data: bytes) -> tuple[int, int, int]:
    """Empreinte d'un mdn : (os racine, nombre d'os, taille des sommets).
    Pas l'identifiant d'en-tete : il change d'une copie a l'autre du meme
    fichier (pieuvres 0x205BD6 : 0x51778F en s02a50l, 0x205BD6 ailleurs)."""
    header = MdnHeader(data)
    root = struct.unpack_from(">I", data, header.bone_offset)[0] if header.bone_count else 0
    return root, header.bone_count, header.vertex_buffer_size


def merge(body: bytes, piece: bytes, cnp: bytes | None = None, _pose=None, _anchor=None) -> bytes:
    """Corps + piece liee ou couche, sur les os du corps (piece ramenee dans
    le repere du corps si ses os communs sont ailleurs ; sans os commun,
    placee au point d'attache du .cnp du corps qui cite son os racine).
    Pieces relevees en jeu (piece_poses, par empreinte du mdn, mdn.piece_key)
    : figees sur leur os
    d'attache ; en plusieurs exemplaires (COPIES : 6 missiles sous les ailes
    de Raging Raven), une fois par pose."""
    from mgs4trainer.core.piece_poses import ANCHORS, COPIES, COPY_ANCHORS, POSES
    ident = piece_key(piece)
    if _pose is None and ident in COPIES:
        anchors = COPY_ANCHORS.get(ident, (ANCHORS.get(ident),) * len(COPIES[ident]))
        for pose, anchor_bone in zip(COPIES[ident], anchors):
            body = merge(body, piece, cnp, pose, anchor_bone)
        return body
    if _anchor is None:
        _anchor = ANCHORS.get(ident)
    body_bones = _bone_worlds(body)
    by_id = {bone: i for i, (bone, _w) in enumerate(body_bones)}

    def nearest(position) -> int:
        return min(range(len(body_bones)),
                   key=lambda i: sum((a - b) ** 2 for a, b in zip(body_bones[i][1], position)))

    piece_bones = _bone_worlds(piece)
    attachments = dict(MANUAL_ATTACHMENTS)
    if cnp:
        attachments.update(cnp_attachments(cnp))
    attach = attachments.get(piece_bones[0][0]) if piece_bones else None
    if _anchor is not None:
        attach = (_anchor, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))  # piece relevee : son os d'attache
    # piece relevee : posee sur son os meme si elle partage des os avec le corps
    if attach and attach[0] in by_id and (_anchor is not None or not any(bone in by_id for bone, _w in piece_bones)):
        bone, offset, rotation = attach[:3]
        anchor = body_bones[by_id[bone]][1]
        shift = tuple(a + o for a, o in zip(anchor, offset))
        # pose relevee en combat : sommets deja dans le repere de l'os d'attache
        # (figee : plus de chaine d'os, la piece suit l'os d'attache)
        pose = _pose or POSES.get(ident)
        posed = pose is not None
        if posed:
            piece = _pose_vertices(piece, pose)
            rotation, shift = (0.0, 0.0, 0.0, 1.0), anchor
        piece = _place_piece(piece, rotation, shift)
        chain = [by_id[b] for b in (attach[3] if len(attach) > 3 and not posed else ()) if b in by_id]
        if chain:
            placed = [tuple(p + t for p, t in zip(_rotate(rotation, world), shift)) for _b, world in piece_bones]
            bone_map = [min(chain, key=lambda i: sum((a - b) ** 2 for a, b in zip(body_bones[i][1], position)))
                        for position in placed]
        else:
            # chaque os de la piece cite par le .cnp suit son os du corps, les
            # autres celui de leur parent (pans de veste du costume de Snake
            # 0xF5ABDB : racine sur le bassin, deux os sur la colonne)
            parents = [parent for _bone, parent in bone_ids(piece)]
            bone_map = []
            for i, (piece_bone, _w) in enumerate(piece_bones):
                target = attachments.get(piece_bone) if not posed and i else None
                if target and target[0] in by_id:
                    bone_map.append(by_id[target[0]])
                elif 0 <= parents[i] < i:
                    bone_map.append(bone_map[parents[i]])
                else:
                    bone_map.append(by_id[bone])
    else:
        offsets = _piece_offsets(body, piece)
        if any(any(abs(c) > 0.01 for c in o) for o in offsets):
            piece = _shift_vertices(piece, offsets)
        worlds = [(bone, tuple(w + o for w, o in zip(world, offset)))
                  for (bone, world), offset in zip(piece_bones, offsets)]
        bone_map = [by_id[bone] if bone in by_id else nearest(world) for bone, world in worlds]
    a, b = _sections(body), _sections(piece)
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
    return _assemble(body, order)


def _assemble(model: bytes, order) -> bytes:
    """Fichier MDN refait : en-tete de model, sections dans l'ordre, alignees sur 16."""
    out = bytearray(model[:HEADER_END])
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
    struct.pack_into(">21I", out, 4, MdnHeader(model).id, n["bones"], n["groups"], n["meshes"], n["faces"],
                     n["vdefs"], n["materials"], n["textures"], n["skins"],
                     offsets["bones"][0], offsets["groups"][0], offsets["meshes"][0], offsets["faces"][0],
                     offsets["vdefs"][0], offsets["materials"][0], offsets["textures"][0], offsets["skins"][0],
                     offsets["vbuf"][0], offsets["vbuf"][1], offsets["fbuf"][0], offsets["fbuf"][1])
    struct.pack_into(">I", out, HEADER.size + 4, len(out))
    return bytes(out)


def texture_ids(data: bytes) -> list[int]:
    header = MdnHeader(data)
    return [struct.unpack_from(">I", data, header.texture_offset + i * TEXTURE_SIZE)[0]
            for i in range(header.texture_count)]
