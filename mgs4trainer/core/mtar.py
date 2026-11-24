"""Archives d'animations (.mtar), format grand-boutiste (releve du
2026-11-24 sur 00815BAE, rebelles) :

- en-tete (0x20) : "Mtar" (octets 72 61 74 4d), +0x8 nombre d'os (u16),
  +0xA nombre d'animations (u16), +0x10 debut des donnees (= fin de la
  table), +0x14 debut des en-tetes d'animation, +0x18 liste des os (0x20),
  +0x1C table (0xC0) ;
- table : 16 octets par animation : position et taille dans les donnees,
  position et taille dans les en-tetes (positions relatives a chaque zone) ;
- chaque zone du jeu a sa version : meme liste, mais les animations dont elle
  n'a pas besoin sont videes (bloc commun de 0x70 octets, en-tete de taille
  0). Mains sur la tete des rebelles (n 481) : pleine en s02a10l, videe en
  s02a20l.
"""
import struct

TABLE_ENTRY = 16


def _layout(data: bytes):
    if data[:4] != b"raTM" and data[:4] != bytes.fromhex("7261744d"):
        raise ValueError("pas une archive d'animations")
    count = struct.unpack_from(">H", data, 0xA)[0]
    start, headers, _bones, table = struct.unpack_from(">4I", data, 0x10)
    entries = [struct.unpack_from(">4I", data, table + TABLE_ENTRY * i) for i in range(count)]
    return count, start, headers, table, entries


def animation_sizes(data: bytes) -> list[int]:
    """Taille des donnees de chaque animation (0 si videe)."""
    _count, _start, _headers, _table, entries = _layout(data)
    return [size if header_size else 0 for _pos, size, _hpos, header_size in entries]


def merge(versions: list[bytes]) -> bytes:
    """Une archive ou chaque animation vient de la version qui l'a complete
    (la plus grande) ; en-tete, os et table repris de la premiere version.
    Les versions doivent avoir la meme liste (nombre d'animations, os)."""
    base = versions[0]
    count, start, _headers, table, _entries = _layout(base)
    layouts = []
    same = lambda d: d[:0x14] + d[0x18:table]  # en-tete (sauf +0x14, propre a chaque version) et os
    for data in versions:
        c, s, h, t, e = _layout(data)
        if c != count or s != start or t != table or same(data) != same(base):
            raise ValueError("versions differentes de l'archive")
        layouts.append((data, s, h, e))
    body, heads, rows = bytearray(), bytearray(), []
    placed_body, placed_head = {}, {}  # blocs partages (animations videes : un seul bloc)
    for i in range(count):
        best = max(range(len(layouts)), key=lambda k: (layouts[k][3][i][3] > 0, layouts[k][3][i][1]))
        data, s, h, e = layouts[best]
        pos, size, hpos, header_size = e[i]
        if (best, pos, size) not in placed_body:
            placed_body[(best, pos, size)] = len(body)
            body += data[s + pos:s + pos + size]
        new_head = 0
        if header_size:
            if (best, hpos, header_size) not in placed_head:
                placed_head[(best, hpos, header_size)] = len(heads)
                heads += data[h + hpos:h + hpos + header_size]
            new_head = placed_head[(best, hpos, header_size)]
        rows.append((placed_body[(best, pos, size)], size, new_head, header_size))
    out = bytearray(base[:start])
    struct.pack_into(">I", out, 0x14, start + len(body))
    for i, row in enumerate(rows):
        struct.pack_into(">4I", out, table + TABLE_ENTRY * i, *row)
    return bytes(out + body + heads)


def most_complete(versions: list[bytes]) -> bytes:
    """Version la plus complete d'une archive. Une version deja complete (ou
    a laquelle les autres n'ajoutent rien) est rendue TELLE QUELLE ; sinon
    fusion des versions compatibles, seulement si la reconstruction de cette
    archive redonne exactement le fichier (sinon la meilleure version telle
    quelle) : une archive mal reconstruite empechait Meryl d'apparaitre
    (2026-11-24 ; blocs partages dupliques, 713E38 de 472 a 710 Ko)."""
    ranked = sorted(versions, key=lambda d: sum(1 for v in animation_sizes(d) if v), reverse=True)
    best = ranked[0]
    group = [best]
    for data in ranked[1:]:
        try:
            merge([best, data])
        except ValueError:
            continue
        group.append(data)
    filled = lambda d: {i for i, v in enumerate(animation_sizes(d)) if v}
    if set().union(*(filled(d) for d in group)) <= filled(best):
        return best
    try:
        if merge([best]) != best:
            return best
        return merge(group)
    except ValueError:
        return best
