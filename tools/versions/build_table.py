"""Table de version pour le trainer, depuis l'inventaire et le portage.

python build_table.py 1.4.2 0x6AE07392 image.bin port.json > mgs4trainer/versions/1.4.2.json"""
import json
import re
import sys

version, stamp, image_path, port_path = sys.argv[1:5]
DISABLED = []
new = open(image_path, "rb").read()
read = lambda rva, n: new[rva - 0x1000:rva - 0x1000 + n]
port = {int(k, 16): v[0] for k, v in json.load(open(port_path)).items()}
# corrections verifiees a la main (manual_<version>.json), prioritaires
try:
    port.update({int(k, 16): v[0] for k, v in json.load(open(f"manual_{version}.json")).items()})
except FileNotFoundError:
    pass
rows = json.load(open("inventory.json"))

values, sigs, failed = {}, {}, set()
for r in rows:
    if r["class"] == "autre":
        continue
    names = [n.strip() for n in r["name"].strip("()").split(",")] if r["name"].startswith("(") else [r["name"]]
    old = r["value"]
    newv = port.get(old)
    if newv is None:
        failed.add(f'{r["name"]}={old:#x}')
    for n in names:
        if not re.fullmatch(r"[A-Za-z_]\w*", n):
            continue
        values.setdefault(n, {})[f"{old:#x}"] = f"{newv or 0:#x}"
        if r["sig"] and newv:
            s = r["sig"].lower()
            raw = read(newv, len(s) // 2).hex()
            ns = "".join("??" if s[i:i + 2] == "??" else raw[i:i + 2] for i in range(0, len(s), 2))
            if ns != s:
                sigs.setdefault(n, {})[s] = ns
# constantes calculees a partir d'autres au chargement : memes correspondances
DERIVED = {"CODE_PATCHES": ["_STEALTH_CHECK_CALLS"], "CSM_ORIGINAL": ["CSM_ENTRY", "CSM_CONFIRM", "CSM_COUNT", "CSM_TABLE_LEA"]}
for target, sources in DERIVED.items():
    for src in sources:
        values.setdefault(target, {}).update(values.get(src, {}))
        if src in sigs:
            sigs.setdefault(target, {}).update(sigs[src])
# dictionnaires {adresse: octets d'origine} (CSM_ORIGINAL, LM_SITES...) : octets relus a la nouvelle adresse
sys.path.insert(0, r"D:\Documents\GitHub\MGS4-Trainer")
from mgs4trainer.live import MGS4Live
for attr in dir(MGS4Live):
    value = getattr(MGS4Live, attr, None)
    if not (isinstance(value, dict) and value and all(type(k) is int and isinstance(v, bytes) for k, v in value.items())):
        continue
    mapping = {int(k, 16): int(v, 16) for k, v in values.get(attr, {}).items()}
    for old_rva, orig in value.items():
        new_rva = mapping.get(old_rva, port.get(old_rva))
        if new_rva:
            nb = read(new_rva, len(orig)).hex()
            values.setdefault(attr, {})[f"{old_rva:#x}"] = f"{new_rva:#x}"
            if nb != orig.hex():
                sigs.setdefault(attr, {})[orig.hex()] = nb
# constantes calculees au chargement a partir d'une adresse portee
PAD_A = 0x23D2AEA0
if f"{PAD_A:#x}" in values.get("PHOTO_PAD_A_RVA", {}):
    values["PHOTO_PAD_LO"] = {f"{PAD_A - 0x40:#x}": f"{int(values['PHOTO_PAD_A_RVA'][f'{PAD_A:#x}'], 16) - 0x40:#x}"}
# constantes entieres propres a la version (replace_<version>.json : {nom: valeur JSON})
try:
    replace = json.load(open(f"replace_{version}.json"))
except FileNotFoundError:
    replace = {}
table = {"version": version, "timestamp": f"{int(stamp, 16):#x}", "disabled": DISABLED,
         "values": values, "signatures": sigs, "replace": replace}
json.dump(table, sys.stdout, indent=1, sort_keys=True)
print(f"{sum(len(v) for v in values.values())} valeurs, {sum(len(v) for v in sigs.values())} signatures, "
      f"{len(failed)} non portees", file=sys.stderr)
