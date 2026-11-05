"""Menu Charger en 1.4.2 : sites, retours, LM_ACTION et LM_CODE.

Les fonctions du menu sont identiques dans les deux versions (desassemblage
compare) : 4E3A20 -> 39E450, 4D7E60 -> 394DF0, 4D5C10 -> 392C90,
4E3430 -> 39DE60, 4E3690 -> 39E0C0. Tables de cles lues dans 4D7E60."""
import json, struct, sys
sys.path.insert(0, r"D:\Documents\GitHub\MGS4-Trainer")
from mgs4trainer.live import MGS4Live as L

FUNCS = {0x4E3A20: 0x39E450, 0x4D7E60: 0x394DF0, 0x4D5C10: 0x392C90, 0x4E3430: 0x39DE60, 0x4E3690: 0x39E0C0}
def moved(rva):
    f = max(f for f in FUNCS if f <= rva)
    return FUNCS[f] + (rva - f)
SITES = (0x4E34FA, 0x4E3A2A, 0x4D7E74, 0x4D8039, 0x4E3AB3, 0x4E37B7)
TABLES = {0x1C2CFE8: 0x157EDA8, 0x1C2D008: 0x157EDC8, 0x1C2D048: 0x157EE08, 0x1C2D068: 0x157EE28}
CALL_OPEN, CALL_SCREEN = 0x393CA0, 0x383990  # 4D6D10 (64 instructions identiques), 4C5150

manual = json.load(open("manual_1.4.2.json"))
for rva in SITES:
    manual[hex(rva)] = [moved(rva), "manuel : menu Charger, fonction identique en 1.4.2 (meme decalage)"]
manual[hex(0x1C2CFE8)] = [TABLES[0x1C2CFE8], "manuel : table de cles du menu, lue dans 4D7E60 (identique)"]
json.dump(manual, open("manual_1.4.2.json", "w"), indent=1)

table = tuple(None if r is None else (moved(r) if r in (0x4D5C2D, 0x4D803E, 0x4E3AB8, 0x4E3A31, 0x4D7E7A) else None)
              for r in L.LM_TABLE)
port = json.load(open("port_1.4.2.json"))
table = [None if r is None else (moved(r) if r in (0x4D5C2D, 0x4D803E, 0x4E3AB8, 0x4E3A31, 0x4D7E7A) else port[hex(r)][0])
         for r in L.LM_TABLE]
site = moved(0x4E34FA)
action = (b"\xe8" + struct.pack("<i", CALL_OPEN - (site + 5)) + b"\x8b\xc8"
          + b"\xe8" + struct.pack("<i", CALL_SCREEN - (site + 12)) + b"\x90" * 5 + L.LM_ACTION[-2:])
assert len(action) == len(L.LM_ACTION) and L.LM_ACTION[-2:] == bytes.fromhex("eb44")
code = L.LM_CODE
for old, new in TABLES.items():
    code = code.replace(struct.pack("<I", old), struct.pack("<I", new))
assert code.count(struct.pack("<I", 0x1C2CFE8)) == 0 and len(code) == len(L.LM_CODE)
replace = json.load(open("replace_1.4.2.json"))
replace.update({"LM_TABLE": table, "LM_ACTION": {"hex": action.hex()}, "LM_CODE": {"hex": code.hex()}})
json.dump(replace, open("replace_1.4.2.json", "w"))
print("sites", {hex(r): hex(moved(r)) for r in SITES})
print("table", [hex(x) if x else None for x in table])
print("action", action.hex())
