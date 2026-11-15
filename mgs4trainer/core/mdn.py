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


def build_hybrid(source: bytes, skeleton: bytes) -> bytes:
    """Geometrie de source sur la table d'os de skeleton (palettes renumerotees)."""
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
    out += skeleton[skel.bone_offset:skel.bone_offset + skel.bone_count * BONE_SIZE]
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
