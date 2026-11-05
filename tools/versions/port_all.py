"""Porte toutes les adresses de l'inventaire vers la nouvelle version.

Code : signature directe, sinon fonction englobante portee + meme decalage
(controle : memes instructions au site). Donnee : instructions qui la citent,
sinon adresse referencee voisine (moins de 0x400 avant) + meme ecart."""
import bisect
import collections
import json
import re
import sys

import numpy as np

from port import Version, OLD_BASE, build_index, find_code, find_data, masked

sys.path.insert(0, r"D:\Documents\GitHub\MGS4-Trainer")
from mgs4trainer.live import MGS4Live

oldimg = bytearray(open("old/image_rva1000.bin", "rb").read())
restored = 0
def restore(rva, orig):
    global restored
    o = rva - OLD_BASE
    if 0 <= o < len(oldimg) and oldimg[o:o + len(orig)] != orig:
        oldimg[o:o + len(orig)] = orig
        restored += 1
for patches in MGS4Live.CODE_PATCHES.values():
    for rva, orig, _patch in patches:
        restore(rva, orig)
for rva, orig in MGS4Live._STEALTH_CHECK_CALLS.items():
    restore(rva, bytes.fromhex(orig))
print("sites restaures dans l'ancienne image :", restored)
OLD_CODE_END = 0x165F000
old = Version(bytes(oldimg), OLD_BASE, 0x1000, OLD_CODE_END)
new = Version(open(sys.argv[1] if len(sys.argv) > 1 else "1.4.2/image_rva1000.bin", "rb").read(), OLD_BASE, 0x1000, 0x10A3200)
rows = json.load(open("inventory.json"))
values = sorted({r["value"] for r in rows if r["class"] in ("adresse", "probable", "a voir")})
code = [v for v in values if v < OLD_CODE_END]
data = [v for v in values if v >= OLD_CODE_END]

# toutes les cibles rip-relatives de l'ancien code, pour les voisins
img = old.image
n = OLD_CODE_END - 0x1000 - 4
disp = np.ndarray((n,), dtype="<i4", buffer=img, offset=0, strides=(1,)).astype(np.int64)
pos = np.arange(n, dtype=np.int64) + 0x1000
refset = set()
for tail in (0, 1, 4):
    t = pos + 4 + tail + disp
    refset |= set(t[(t >= OLD_CODE_END) & (t < 0x30000000)].tolist())
refs = sorted(refset)


def fn_start(rva):
    o = rva - OLD_BASE
    for back in range(0, 0x8000):
        if o - back - 1 < 0:
            return None
        if img[o - back - 1] == 0xCC and img[o - back] != 0xCC:
            return rva - back
    return None


def site_ok(orig_rva, new_rva):
    pattern, got = masked(old.read(orig_rva, 32), orig_rva, 12)
    return got >= 2 and re.match(pattern, new.read(new_rva, 32), re.S) is not None


result = {}
for v in code:
    r, why = find_code(old, new, v)
    if r is None:
        fs = fn_start(v)
        if fs is not None and fs != v:
            nf, w2 = find_code(old, new, fs)
            if nf is not None:
                cand = nf + (v - fs)
                if site_ok(v, cand):
                    r, why = cand, f"fonction {fs:#x} +{v - fs:#x}"
                else:
                    why += f" ; fonction trouvee mais site different"
    result[v] = (r, why)

# code restant : emplacement predit par les voisines portees (ordre conserve),
# motif court cherche seulement autour
done = sorted((v, r) for v, (r, w) in result.items() if r is not None)
dv = [d[0] for d in done]
newcode = new.image[new.text_start - new.base:new.text_end - new.base]
for v in code:
    if result[v][0] is not None:
        continue
    i = bisect.bisect_left(dv, v)
    guesses = [done[j][1] + (v - done[j][0]) for j in (i - 1, i) if 0 <= j < len(done)]
    if not guesses:
        continue
    lo, hi = min(guesses) - 0x400, max(guesses) + 0x400
    if hi - lo > 0x10000:
        continue
    for length in (12, 8, 5):
        pattern, got = masked(old.read(v, 64), v, length)
        if got < 4:
            break
        hits = [m.start() + new.text_start for m in re.finditer(pattern, newcode[lo - new.text_start:hi - new.text_start], re.S)]
        hits = [h + lo - new.text_start for h in hits]
        if len(hits) == 1:
            result[v] = (hits[0], f"local ({got} o, fenetre {hi - lo:#x})")
            break
        if not hits:
            break

# dernier recours (jumelles, fonctions courtes) : candidats dans une large
# fenetre, le plus proche de la prediction s'il l'est nettement plus que le suivant
done = sorted((v, r) for v, (r, w) in result.items() if r is not None)
dv = [d[0] for d in done]
for v in code:
    if result[v][0] is not None:
        continue
    i = bisect.bisect_left(dv, v)
    guesses = [done[j][1] + (v - done[j][0]) for j in (i - 1, i) if 0 <= j < len(done)]
    if not guesses:
        continue
    expected = sum(guesses) // len(guesses)
    lo, hi = max(expected - 0x40000, new.text_start), min(expected + 0x40000, new.text_end)
    pattern, got = masked(old.read(v, 64), v, 12)
    if got < 4:
        continue
    hits = sorted((abs(m.start() + lo - expected), m.start() + lo)
                  for m in re.finditer(pattern, newcode[lo - new.text_start:hi - new.text_start], re.S))
    if hits and (len(hits) == 1 or hits[0][0] * 2 < hits[1][0]):
        result[v] = (hits[0][1], f"plus proche ({got} o, {len(hits)} candidats, ecart {hits[0][0]:#x})")

anchors = set()
for v in data:
    i = bisect.bisect_right(refs, v) - 1
    if i >= 0 and v - refs[i] < 0x400:
        anchors.add(refs[i])
index = build_index(old, set(data) | anchors)
cache = {}
def port_data(v):
    if v not in cache:
        cache[v] = find_data(old, new, v, index)
    return cache[v]
for v in data:
    r, why = port_data(v)
    if r is None:
        i = bisect.bisect_right(refs, v) - 1
        if i >= 0 and v - refs[i] < 0x400 and refs[i] != v:
            a = refs[i]
            na, w2 = port_data(a)
            if na is not None:
                r, why = na + (v - a), f"voisin {a:#x} +{v - a:#x} ({w2})"
    result[v] = (r, why)

# donnees restantes : ecart des voisines portees qui les encadrent
pairs = sorted((v, r) for v, (r, w) in result.items() if v >= OLD_CODE_END and r is not None)
olds = [p[0] for p in pairs]
for v in data:
    if result[v][0] is not None:
        continue
    i = bisect.bisect_right(olds, v)
    if 0 < i < len(pairs):
        (a, na), (c, nc) = pairs[i - 1], pairs[i]
        if na - a == nc - c:
            result[v] = (v + na - a, f"encadre {a:#x}..{c:#x}")
        elif v - a < 0x1000:
            result[v] = (v + na - a, f"proche {a:#x} +{v - a:#x} (ecart non confirme)")

json.dump({f"{k:#x}": [v[0], v[1]] for k, v in result.items()}, open("port_1.4.2.json", "w"), indent=0)
c = collections.Counter()
for v, (r, why) in result.items():
    kind = "code" if v < OLD_CODE_END else "data"
    mode = "echec" if r is None else ("direct" if why.startswith(("unique", "1/", "2/", "3/")) or "votes" in why and not why.startswith("voisin") else why.split()[0])
    c[(kind, mode)] += 1
print(len(result), "valeurs")
for k, n in sorted(c.items()): print(" ", k, n)
fails = [(v, w) for v, (r, w) in result.items() if r is None]
byfile = collections.defaultdict(list)
for r in rows:
    if r["value"] in dict(fails):
        byfile[r["file"]].append(f'{r["name"]}={r["value"]:#x}')
print("echecs par fichier :")
for f, l in sorted(byfile.items(), key=lambda x: -len(x[1])):
    print(f"  {f} {len(l)} : {', '.join(sorted(set(l))[:8])}")
