"""Releve en jeu la pose d'une piece accrochee par le code du jeu (pieuvres
de Laughing Octopus 0x205BD6 sur l'os 0x14B512 de son corps 0x203008) et
l'ajoute a mgs4trainer/core/piece_poses.py : la piece est figee dans cette
pose sur le modele hybride (Snake n'a pas ses os, 2026-11-17).

Lecture seule du jeu (aucun appel, aucune ecriture). A lancer pendant le
combat, la piece a l'ecran, jeu en pause :

    python tools/capture_piece_pose.py 0x203008 0x205BD6 0x14B512

Pour trouver les pieces d'un corps (instances proches, os d'attache le
plus proche de leur racine) :

    python tools/capture_piece_pose.py --find 0x263008

Piece en plusieurs exemplaires (missiles de Raging Raven) : --all apres les
trois identifiants releve chaque exemplaire proche du corps (COPIES).

Les poses deja relevees sont gardees (une par piece, mdn.piece_key).

Instances : tableau global (1.4.2 0x18D2C10), +0x14 identifiant du mdn,
matrices des os en +0x1E0 (0x40 chacune, vecteur ligne, translation en
derniere ligne). Pose par os de la piece, dans le repere de l'os d'attache
du corps : v' = v * R + t pour un sommet v du modele (pose de repos : os
sans rotation, a leur position du mdn).
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from mgs4trainer.core import mdn  # noqa: E402
from mgs4trainer.core.gamedata import PROCESS_NAME  # noqa: E402
from mgs4trainer.core.vpak import StageFiles  # noqa: E402
from mgs4trainer.core.winproc import ProcessHandle, find_module_base, find_pid  # noqa: E402

GAME = "E:/SteamLibrary/steamapps/common/METAL GEAR SOLID 4/MGS4"
INSTANCE_LIST_RVA = 0x18D2C10  # 1.4.2
INSTANCE_SLOTS = 0x400
INSTANCE_ID, INSTANCE_BONES = 0x14, 0x1E0
FIND_DISTANCE = 1500
COPY_DISTANCE = 5000  # missiles au bout des ailes de Raven (envergure ~7400)
OUT = os.path.join(os.path.dirname(__file__), "..", "mgs4trainer", "core", "piece_poses.py")


def matrices(proc, instance: int, count: int):
    raw = proc.read_bytes(instance + INSTANCE_BONES, 0x40 * count)
    return [struct.unpack_from("<16f", raw, i * 0x40) for i in range(count)]


def find_mdn(files, model: int) -> bytes:
    suffix = f"/{model:08x}.mdn"
    return files.read(next(p for p in files.entries if p.endswith(suffix)))


def attach():
    pid = find_pid(PROCESS_NAME)
    return ProcessHandle(pid), find_module_base(pid, PROCESS_NAME), StageFiles(GAME)


RESOURCES_RVA = 0x2367B9D0  # 1.4.2 : dictionnaire des ressources (16 arbres)
SCAN_REGION_MAX = 0x40000000


def scan_instances(proc, base: int, models) -> dict[int, list[int]]:
    """Instances hors du tableau global (Screaming Mantis, comme d'autres
    boss) : balayage de la memoire sur les donnees du mdn (+0x70)."""
    import numpy as np
    q = lambda a: struct.unpack("<Q", proc.read_bytes(a, 8))[0]  # noqa: E731
    nodes, stack = {}, [q(base + RESOURCES_RVA + i * 8) for i in range(16)]
    while stack:
        node = stack.pop()
        if node and node not in nodes.values():
            nodes[struct.unpack("<I", proc.read_bytes(node + 0x10, 4))[0] & 0x7FFFFFFF] = node
            stack += [q(node), q(node + 8)]
    data = {}
    for model in models:
        node = nodes.get(0x0D000000 | model)
        if node:
            data[q(node + 0x20)] = model
    found = {model: [] for model in models}
    if not data:
        return found
    wanted = np.array(sorted(data), dtype=np.uint64)
    for region, size in proc._writable_regions():
        if size > SCAN_REGION_MAX:
            continue
        try:
            chunk = proc.read_bytes(region, size)
        except OSError:
            continue
        values = np.frombuffer(chunk[:len(chunk) // 8 * 8], dtype=np.uint64)
        for i in np.nonzero(np.isin(values, wanted))[0]:
            at = int(i) * 8 - 0x70
            model = data[int(values[i])]
            if at >= 0 and struct.unpack_from("<I", chunk, at + INSTANCE_ID)[0] == model:
                found[model].append(region + at)
    return found


def sane(proc, instance: int) -> bool:
    """Instance plausible : premiere matrice d'os = rotation (lignes unitaires).
    Le balayage trouve aussi des faux positifs 0x20 plus loin (normes ~1e8)."""
    try:
        m = matrices(proc, instance, 1)[0]
    except OSError:
        return False
    return all(abs(sum(m[r * 4 + i] ** 2 for i in range(3)) - 1.0) < 0.05 for r in range(3))


def instances(proc, base: int, models=()) -> dict[int, list[int]]:
    table = struct.unpack(f"<{INSTANCE_SLOTS}Q", proc.read_bytes(base + INSTANCE_LIST_RVA, INSTANCE_SLOTS * 8))
    found = {}
    for pointer in table:
        if 0x10000 <= pointer < 0x7FF000000000:
            try:
                ident = struct.unpack("<I", proc.read_bytes(pointer + INSTANCE_ID, 4))[0]
            except OSError:
                continue
            if pointer not in found.setdefault(ident, []):
                found[ident].append(pointer)
    if models:
        # aussi en memoire : exemplaires hors du tableau (couteaux de Mantis : 1 sur 4 dedans)
        for model, pointers in scan_instances(proc, base, list(models)).items():
            found.setdefault(model, []).extend(x for x in pointers if x not in found[model])
    return {model: [x for x in pointers if sane(proc, x)] for model, pointers in found.items()}


def find(body: int) -> None:
    """Instances dont la racine est a moins de FIND_DISTANCE d'un os du corps."""
    proc, base, files = attach()
    body_bones = [bone for bone, _p in mdn.bone_ids(find_mdn(files, body))]
    found = instances(proc, base, [body])
    if not found.get(body):
        raise SystemExit("corps absent du tableau des instances")
    for b in found[body]:
        worlds = matrices(proc, b, len(body_bones))
        print(f"corps {body:#08x} instance {b:#x} racine {[round(x) for x in worlds[0][12:15]]}")
        for ident, pointers in sorted(found.items()):
            if ident == body:
                continue
            for p in pointers:
                try:
                    root = matrices(proc, p, 1)[0][12:15]
                except OSError:
                    continue
                gap, i = min((sum((w[12 + k] - root[k]) ** 2 for k in range(3)) ** 0.5, i)
                             for i, w in enumerate(worlds))
                if gap < FIND_DISTANCE:
                    print(f"  {ident:#08x} instance {p:#x} : os {body_bones[i]:#08x} a {gap:.0f}")


def pose_of(a, m, rest):
    """Pose de la piece (matrices m) dans le repere de l'os d'attache (matrice a)."""
    ra = [a[0:3], a[4:7], a[8:11]]
    ta = a[12:15]

    def times_ra_t(v):  # v * RA^T
        return tuple(sum(v[j] * ra[i][j] for j in range(3)) for i in range(3))

    poses = []
    for i, mat in enumerate(m):
        rb = [mat[0:3], mat[4:7], mat[8:11]]
        tb = mat[12:15]
        rows = [times_ra_t(row) for row in rb]  # R_b * RA^T
        r = rest[i]
        moved_rest = tuple(sum(r[j] * rb[j][k] for j in range(3)) for k in range(3))
        t = times_ra_t(tuple(-moved_rest[k] + tb[k] - ta[k] for k in range(3)))
        poses.append(tuple(round(x, 5) for row in rows for x in row) + tuple(round(x, 3) for x in t))
    return tuple(poses)


def main(body: int, piece: int, anchors: list[int], every_copy: bool = False) -> None:
    """anchors : os d'attache ; avec --all, chaque exemplaire prend le plus
    proche (couteaux de Mantis : bras gauches 0x2236C4 ou droits 0xE246C4)."""
    proc, base, files = attach()
    body_bones = [bone for bone, _p in mdn.bone_ids(find_mdn(files, body))]
    piece_data = find_mdn(files, piece)
    rest = [world for _bone, world in mdn._bone_worlds(piece_data)]
    anchor = anchors[0]
    anchor_index = body_bones.index(anchor)
    every = instances(proc, base, [body, piece])
    # paire corps/piece : piece animee d'abord, racine la plus proche de l'os d'attache
    best = None
    for b in every.get(body, []):
        a = matrices(proc, b, len(body_bones))[anchor_index]
        for p in every.get(piece, []):
            m = matrices(proc, p, len(rest))
            gap = sum((a[12 + k] - m[0][12 + k]) ** 2 for k in range(3)) ** 0.5
            moved = any(abs(row[k] - (1.0 if k in (0, 5, 10) else 0.0)) > 1e-3 for row in m for k in range(12))
            if best is None or (moved, -gap) > (best[0], -best[1]):
                best = (moved, gap, a, m, b)
    if best is None:
        raise SystemExit("corps ou piece absent du tableau des instances")
    moved, gap, a, m, body_instance = best
    print(f"paire retenue : ecart racine/attache {gap:.1f}, animee {moved}")
    copies, copy_anchors = [], []
    if every_copy:
        # tous les exemplaires dont la racine est a moins de COPY_DISTANCE de
        # l'os d'attache ; chacun sur l'os d'attache le plus proche
        worlds = matrices(proc, body_instance, len(body_bones))
        for p in every.get(piece, []):
            mp = matrices(proc, p, len(rest))

            def gap_to(bone):
                w = worlds[body_bones.index(bone)]
                return sum((w[12 + k] - mp[0][12 + k]) ** 2 for k in range(3)) ** 0.5
            near = min(anchors, key=gap_to)
            if gap_to(near) < COPY_DISTANCE:
                copies.append(pose_of(worlds[body_bones.index(near)], mp, rest))
                copy_anchors.append(near)
        print(len(copies), "exemplaires sur", [f"{x:#08x}" for x in copy_anchors])
    poses = pose_of(a, m, rest)
    from mgs4trainer.core.piece_poses import ANCHORS, COPIES, COPY_ANCHORS, NOTES, POSES
    key = mdn.piece_key(piece_data)
    COPY_ANCHORS.pop(key, None)
    ANCHORS[key] = anchor
    if copies:
        COPIES[key] = tuple(copies)
        if len(set(copy_anchors)) > 1:
            COPY_ANCHORS[key] = tuple(copy_anchors)
        POSES.pop(key, None)
    else:
        POSES[key] = poses
        COPIES.pop(key, None)
    NOTES[key] = f"{piece:#08x} sur {anchor:#08x} ({body:#08x})" + (f", {len(copies)} exemplaires" if copies else "")
    write(NOTES, ANCHORS, POSES, COPIES, COPY_ANCHORS)
    print("ecrit :", os.path.normpath(OUT), len(poses), "os")


def write(notes, anchors, poses, copies, copy_anchors) -> None:
    def lit(k):
        return f"({k[0]:#08x}, {k[1]}, {k[2]})"
    out = ['"""Genere par tools/capture_piece_pose.py : poses figees des pieces',
           "accrochees par le code du jeu (releve en combat).", "",
           "empreinte du mdn de la piece (mdn.piece_key) -> une matrice par os (R 3x3",
           "en lignes, puis t), dans le repere de son os d'attache (ANCHORS) :", "v' = v * R + t." + '"""', "",
           "NOTES = {"]
    out += [f"    {lit(k)}: {notes.get(k, '')!r}," for k in sorted(anchors)]
    out += ["}", "", "# os d'attache du corps", "ANCHORS = {"]
    out += [f"    {lit(k)}: {anchors[k]:#08x}," for k in sorted(anchors)]
    out += ["}", "", "POSES = {"]
    for k in sorted(poses):
        out.append(f"    {lit(k)}: (")
        out += ["        (" + ", ".join(repr(x) for x in pose) + ")," for pose in poses[k]]
        out.append("    ),")
    out += ["}", "", "# pieces en plusieurs exemplaires : (pose de chaque exemplaire)", "COPIES = {"]
    for k in sorted(copies):
        out.append(f"    {lit(k)}: (")
        for copy in copies[k]:
            out.append("        (")
            out += ["            (" + ", ".join(repr(x) for x in pose) + ")," for pose in copy]
            out.append("        ),")
        out.append("    ),")
    out += ["}", "", "# os d'attache de chaque exemplaire, quand ils different", "COPY_ANCHORS = {"]
    out += [f"    {lit(k)}: ({''.join(f'{x:#08x}, ' for x in copy_anchors[k])})," for k in sorted(copy_anchors)]
    out += ["}", ""]
    nl = chr(10)
    with open(OUT, "w", encoding="utf-8", newline=nl) as handle:
        handle.write(nl.join(out))


if __name__ == "__main__":
    if sys.argv[1] == "--find":
        find(int(sys.argv[2], 16))
    else:
        main(int(sys.argv[1], 16), int(sys.argv[2], 16), [int(x, 16) for x in sys.argv[3].split(",")],
             every_copy="--all" in sys.argv[4:])
