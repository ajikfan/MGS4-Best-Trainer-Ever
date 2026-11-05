"""Versions du jeu : les constantes du trainer sont celles de la version de
reference (avant 1.4.2). Pour une autre version, une table (versions/*.json,
produite par l'outil de portage) donne, constante par constante, la nouvelle
valeur de chaque adresse et les nouveaux octets de chaque signature.

Une adresse non portee vaut 0 (en-tete du module : lecture sans effet,
ecriture refusee) ; les fonctions qui en dependent echouent sans rien ecrire.
Les fonctions listees dans "disabled" restent coupees sur cette version."""
import json
import os
import struct
import sys


REFERENCE = "reference"
_original: dict[tuple[object, str], object] = {}  # (proprietaire, nom) -> valeur d'origine
_active: dict | None = None


def tables() -> list[dict]:
    folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "versions")
    out = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if name.endswith(".json"):
                with open(os.path.join(folder, name), encoding="utf-8") as handle:
                    out.append(json.load(handle))
    return out


def image_timestamp(proc, base: int) -> int:
    """Horodatage de l'en-tete PE du module en memoire."""
    header = struct.unpack("<I", proc.read_bytes(base + 0x3C, 4))[0]
    return struct.unpack("<I", proc.read_bytes(base + header + 8, 4))[0]


def detect(proc, base: int) -> dict | None:
    """Table de la version en cours, None pour la version de reference ou une
    version inconnue (le controle de coherence tranche alors)."""
    stamp = image_timestamp(proc, base)
    return next((t for t in tables() if int(t["timestamp"], 16) == stamp), None)


def name() -> str:
    return _active["version"] if _active else REFERENCE


def disabled(feature: str) -> bool:
    return bool(_active) and feature in _active.get("disabled", ())


def _owners():
    for module_name, module in list(sys.modules.items()):
        if not module_name.startswith("mgs4trainer") or module is None:
            continue
        yield module, vars(module)
        for value in list(vars(module).values()):
            if isinstance(value, type) and value.__module__ == module_name:
                yield value, value.__dict__


def _remap(value, mapping: dict[int, int], sigs: dict[str, str]):
    if type(value) is int:
        return mapping.get(value, value)
    if isinstance(value, str):
        return sigs.get(value.lower(), value)
    if isinstance(value, bytes):
        new = sigs.get(value.hex())
        return bytes.fromhex(new) if new is not None else value
    if isinstance(value, (tuple, list, set, frozenset)):
        return type(value)(_remap(v, mapping, sigs) for v in value)
    if isinstance(value, dict):
        return {_remap(k, mapping, sigs): _remap(v, mapping, sigs) for k, v in value.items()}
    return value


def _as_tuples(value):
    """Listes JSON -> tuples (les constantes du trainer sont des tuples)."""
    if isinstance(value, list):
        return tuple(_as_tuples(v) for v in value)
    return value


def activate(table: dict | None) -> None:
    """Remet les constantes d'origine puis applique la table (None : reference)."""
    global _active
    for (owner, attr), value in _original.items():
        setattr(owner, attr, value)
    _original.clear()
    _active = table
    if not table:
        return
    replace = {n: _as_tuples(v) for n, v in table.get("replace", {}).items()}
    values = {n: {int(k, 16): int(v, 16) for k, v in m.items()} for n, m in table["values"].items()}
    sigs = table.get("signatures", {})
    for owner, namespace in _owners():
        for attr in list(namespace):
            if attr not in values and attr not in replace:
                continue
            old = namespace[attr]
            if attr in replace:  # constante entiere propre a la version (ex. liste de longueur differente)
                new = replace[attr]
            else:
                new = _remap(old, values[attr], {k.lower(): v for k, v in sigs.get(attr, {}).items()})
            if new != old:
                _original[(owner, attr)] = old
                setattr(owner, attr, new)
