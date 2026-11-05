"""Portage d'adresses (RVA) d'une version de mgs4.exe a une autre, par signatures.

Ancienne version : image memoire a partir de la RVA 0x1000 (old/image_rva1000.bin).
Nouvelle version : mgs4.exe, sections placees a leur RVA.

Code : octets a partir de l'adresse, operandes relatifs masques, cherches dans
le nouveau code. Donnee : instructions de l'ancien code qui la citent (rip+disp),
retrouvees dans le nouveau code ; vote sur la nouvelle adresse."""
import collections
import re
import struct
import sys

import capstone

OLD_BASE = 0x1000
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True


def load_old(path):
    return open(path, "rb").read()


def load_new(path):
    d = open(path, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    s = pe + 24 + opt
    sections = {}
    size = 0
    for i in range(n):
        name = d[s + i * 40:s + i * 40 + 8].rstrip(b"\0").decode()
        vs, va, rs, ro = struct.unpack_from("<IIII", d, s + i * 40 + 8)
        sections[name] = (va, vs, rs, ro)
        size = max(size, va + min(vs, rs))
    image = bytearray(size)
    for va, vs, rs, ro in sections.values():
        image[va:va + min(vs, rs)] = d[ro:ro + min(vs, rs)]
    return bytes(image), sections


class Version:
    def __init__(self, image, base, text_start, text_end):
        self.image, self.base, self.text_start, self.text_end = image, base, text_start, text_end

    def read(self, rva, size):
        o = rva - self.base
        return self.image[max(o, 0):max(o, 0) + size] if 0 <= o < len(self.image) else b""


def masked(code, rva, length):
    """Motif regex des instructions a partir de rva, operandes relatifs masques."""
    out = b""
    total = 0
    for ins in md.disasm(code, rva):
        raw = bytearray(ins.bytes)
        mask = [False] * len(raw)
        if ins.disp_offset and (ins.disp_size == 4):
            for k in range(ins.disp_offset, ins.disp_offset + 4): mask[k] = True
        if ins.group(capstone.CS_GRP_JUMP) or ins.group(capstone.CS_GRP_CALL):
            if ins.imm_offset and ins.imm_size == 4:
                for k in range(ins.imm_offset, ins.imm_offset + 4): mask[k] = True
        out += b"".join(b"." if m else re.escape(bytes((b,))) for b, m in zip(raw, mask))
        total += len(raw)
        if total >= length or ins.mnemonic in ("ret", "int3", "jmp"):
            break
    return out, total


def find_code(old, new, rva, lengths=(24, 40, 64, 96)):
    code = old.read(rva, 128)
    if not code:
        return None, "hors image"
    for length in lengths:
        pattern, got = masked(code, rva, length)
        if got < 12:
            return None, "trop court"
        hits = [m.start() for m in re.finditer(pattern, new.image[new.text_start - new.base:new.text_end - new.base], re.S)]
        if len(hits) == 1:
            return new.text_start + hits[0], f"unique ({got} o)"
        if not hits:
            return None, f"absent ({got} o)"
    return None, f"ambigu ({len(hits)})"


def find_data(old, new, target, index):
    votes = collections.Counter()
    for pos, tail in index.get(target, [])[:16]:
        ins_start = None
        for back in range(2, 8):
            s = pos - back
            ins = next(md.disasm(old.read(s, 16), s), None)
            if ins and ins.disp_offset == back and ins.disp_size == 4 and s + ins.size == pos + 4 + tail:
                ins_start = s
                break
        if ins_start is None:
            continue
        for before in (0, 16, 32):
            code = old.read(ins_start - before, 160)
            pattern, got = masked(code, ins_start - before, before + 40)
            hits = [m.start() for m in re.finditer(pattern, new.image[new.text_start - new.base:new.text_end - new.base], re.S)]
            if len(hits) == 1:
                ns = new.text_start + hits[0] + before
                ni = next(md.disasm(new.read(ns, 16), ns), None)
                if ni and ni.disp_size == 4:
                    votes[ns + ni.size + ni.disp] += 1
                break
    if not votes:
        return None, "aucune reference retrouvee"
    best, n = votes.most_common(1)[0]
    return best, f"{n}/{sum(votes.values())} votes"


def build_index(old, targets):
    """target -> [(pos disp, tail)] pour les disp32 rip-relatifs de l'ancien code."""
    import numpy as np
    img = old.image
    start, end = old.text_start - old.base, old.text_end - old.base
    n = end - start - 4
    disp = np.ndarray((n,), dtype="<i4", buffer=img, offset=start, strides=(1,)).astype(np.int64)
    pos = np.arange(n, dtype=np.int64) + old.base + start
    wanted = np.array(sorted(set(targets)), dtype=np.int64)
    index = collections.defaultdict(list)
    for tail in (0, 1, 4):
        t = pos + 4 + tail + disp
        for k in np.nonzero(np.isin(t, wanted))[0]:
            index[int(t[k])].append((int(pos[k]), tail))
    return index
