"""Table de version pour le trainer, depuis l'inventaire et le portage.

python build_table.py 1.4.2 0x6AE07392 image.bin port.json > mgs4trainer/versions/1.4.2.json"""
import json
import re
import sys

version, stamp, image_path, port_path = sys.argv[1:5]
DISABLED = ["load_menu", "photo"]  # code machine embarque avec des adresses du jeu : a porter a part
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
table = {"version": version, "timestamp": f"{int(stamp, 16):#x}", "disabled": DISABLED,
         "values": values, "signatures": sigs}
json.dump(table, sys.stdout, indent=1, sort_keys=True)
print(f"{sum(len(v) for v in values.values())} valeurs, {sum(len(v) for v in sigs.values())} signatures, "
      f"{len(failed)} non portees", file=sys.stderr)
