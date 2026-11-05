"""Inventaire des constantes du trainer qui peuvent etre des adresses (RVA),
classees a l'aide de l'image de l'ancienne version."""
import ast
import json
import os
import re
import sys

import numpy as np

ROOT = r"D:\Documents\GitHub\MGS4-Trainer\mgs4trainer"
OLD = open(os.path.join(os.path.dirname(__file__), "old", "image_rva1000.bin"), "rb").read()
BASE = 0x1000
CODE_END = 0x165F000
NOT_ADDRESSES = {"SNAKE_MOTIONS", "ALERT_SECOND_TIMER"}  # identifiants d'animation, duree
NAME_HINT = re.compile(r"RVA|SITE|FUNC|ADDR|ENTRY|CALL|VTABLE|TABLE|HOOK|PATCH|ROOT|LOOKUP|APPLY|PLAY|FIND|_SET\b|STATE|GLOBAL|LIST|PTR|MANAGER|CTOR|UPDATE|PROC", re.I)


def targets():
    """RVA ciblees dans l'ancien code : call/jmp rel32 et disp32 rip-relatifs (fin d'instruction +0/+1/+4)."""
    n = len(OLD) - 5
    pos = np.arange(n, dtype=np.int64) + BASE
    rel = np.ndarray((n,), dtype="<i4", buffer=OLD, offset=1, strides=(1,)).astype(np.int64)
    op = np.frombuffer(OLD, dtype=np.uint8)[:n]
    calls = set((pos[(op == 0xE8) | (op == 0xE9)] + 5 + rel[(op == 0xE8) | (op == 0xE9)]).tolist())
    disp = np.ndarray((n,), dtype="<i4", buffer=OLD, offset=0, strides=(1,)).astype(np.int64)
    refs = set()
    for tail in (0, 1, 4):
        refs |= set((pos + 4 + tail + disp).tolist())
    return calls, refs


def name_of(stack):
    for node in reversed(stack):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            t = node.targets[0] if isinstance(node, ast.Assign) else node.target
            return ast.unparse(t)
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            return node.name + "()"
    return "?"


def sig_near(stack, node):
    """Chaine hexadecimale accolee (tuple (rva, "sig") ou dict rva: "sig")."""
    parent = stack[-1] if stack else None
    items = []
    if isinstance(parent, ast.Tuple):
        items = parent.elts
    elif isinstance(parent, ast.Dict) and node in parent.keys:
        v = parent.values[parent.keys.index(node)]
        items = v.elts if isinstance(v, ast.Tuple) else [v]
    for it in items:
        if isinstance(it, ast.Call) and getattr(it.func, "attr", "") == "fromhex" and it.args and isinstance(it.args[0], ast.Constant):
            it = it.args[0]
        if isinstance(it, ast.Constant) and isinstance(it.value, str) and re.fullmatch(r"([0-9a-fA-F?]{2})+", it.value or "x"):
            return it.value
    return None


def walk(tree):
    out = []
    def visit(node, stack):
        if isinstance(node, ast.Constant) and type(node.value) is int and 0x10000 <= node.value < 0x30000000:
            out.append((node, list(stack)))
        for child in ast.iter_child_nodes(node):
            visit(child, stack + [node])
    visit(tree, [])
    return out


def main():
    calls, refs = targets()
    rows = []
    for dirpath, _, files in os.walk(ROOT):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            src = open(path, encoding="utf-8").read()
            lines = src.splitlines()
            for node, stack in walk(ast.parse(src)):
                v = node.value
                name = name_of(stack)
                sig = sig_near(stack, node)
                old = OLD[v - BASE:v - BASE + 16] if BASE <= v < BASE + len(OLD) else b""
                why = []
                if sig is not None:
                    exp = sig.lower().replace("??", "..")
                    ok = re.fullmatch(exp, old[:len(sig) // 2].hex()) is not None if old else False
                    why.append("sig OK" if ok else "sig DIFF")
                if v in calls: why.append("call/jmp")
                if v in refs: why.append("ref")
                if old and v < CODE_END and OLD[v - BASE - 1] in (0xCC, 0xC3) and old[0] != 0xCC: why.append("debut fn")
                if NAME_HINT.search(name): why.append("nom")
                if name in NOT_ADDRESSES:
                    cls = "autre"
                elif "sig OK" in why or "call/jmp" in why or ("ref" in why and v >= CODE_END):
                    cls = "adresse"
                elif "sig DIFF" in why:
                    cls = "a voir"
                elif why and ("debut fn" in why or ("nom" in why and v >= 0x1000000) or "ref" in why):
                    cls = "probable"
                else:
                    cls = "autre"
                rows.append({"file": os.path.relpath(path, ROOT), "line": node.lineno, "name": name, "value": v,
                             "kind": "code" if v < CODE_END else "data", "class": cls, "why": why, "sig": sig,
                             "text": lines[node.lineno - 1].strip()[:110]})
    json.dump(rows, open(os.path.join(os.path.dirname(__file__), "inventory.json"), "w"), indent=0)
    from collections import Counter
    print(len(rows), "constantes ; valeurs distinctes", len({r["value"] for r in rows}))
    print(Counter(r["class"] for r in rows))
    print(Counter((r["class"], r["kind"]) for r in rows))
    for cls in ("a voir", "probable"):
        print("==", cls)
        for r in [r for r in rows if r["class"] == cls][:25]:
            print(f'  {r["file"]}:{r["line"]} {r["name"]} {r["value"]:#x} {r["why"]} | {r["text"][:70]}')


main()
