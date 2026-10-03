"""Trainer de recherche/edition memoire live : lit/ecrit en direct la
memoire du processus mgs4.exe (armes, objets, stats, vitesse du
jeu...), a l'origine pour identifier les ID encore inconnus des
tableaux objets/armes sans avoir a save/reload a chaque test, devenu au
fil du temps l'appli complete de ce depot (voir README.md).

Outil separe de MGS4SaveStats (autre depot, lecture seule des fichiers
de sauvegarde) - aucun lien entre les deux, volontairement publies a
part pour ne pas les confondre (voir README.md). Reutilise seulement
mgs4save.py (table des noms d'armes/objets) de ce depot frere.

    python live_trainer.py

Mecanisme : chaine de pointeurs documentee par le depot externe
zexk/bbtracker (docs/mgs4_research.md, licence MIT) - "module base +
0x1C28B28 -> pointeur linkvarbuf actif" et "module base + 0x1C28B38 ->
pointeur varbuf actif" (situe a linkvarbuf - 0x2800). Les deux structures
ont la meme disposition interne, serialisee telle quelle dans MGS4.SAV aux
memes offsets que ceux deja utilises par mgs4save.py (confirme
independamment par nos propres recherches, voir notes.md) : ITEM_STATE_OFFSET
(0x0526) et WEAPON_STATE_OFFSET (0x1d4) s'appliquent donc identiquement en
memoire live, relatifs a l'une ou l'autre adresse plutot qu'au debut du
fichier. Teste en direct (2026-09-22) : `linkvarbuf` retourne un stock de
Ration perime (ne reflete pas la consommation reelle en jeu), alors que
`varbuf` correspond exactement a ce que le joueur voit sur son HUD au meme
instant - donc `varbuf` est le buffer utilise ici pour lire/ecrire, pas
`linkvarbuf` (probablement un buffer de serialisation prepare pour la
sauvegarde, pas l'etat de jeu temps reel).

Le script original de zexk/bbtracker (scripts/probe-mgs4-memory.py) cible
Linux/Proton (lecture via /proc/[pid]/mem) - inutilisable tel quel sur
Windows natif. Ce fichier en est une reimplementation Windows (ctypes +
API kernel32/psapi, comme le reste du projet qui evite les dependances
externes), PAS une copie du code original.

La chaine de pointeurs n'a jamais ete verifiee sur notre build exacte -
d'ou le controle de coherence (`sanity_check`) avant d'autoriser la
moindre ecriture : item[0x00] et item[0x13] sont confirmes a 0 sur
absolument toutes les saves connues (voir STRUCTURAL_ITEM_IDS dans
mgs4save.py) ; si ce n'est pas le cas en memoire live, la chaine de
pointeurs est consideree non fiable et l'ecriture reste desactivee.
"""

import ctypes
import json
import os
import struct
import sys
import threading
import time
from ctypes import wintypes

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import mgs4save


def _bundled_path(*parts):
    """Fichier embarque dans l'exe (PyInstaller --add-data, voir
    MGS4Trainer.spec), ou a cote du script en mode developpement - meme
    convention que gui_app.py."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


TRAINER_ICON = _bundled_path("assets", "MGS4_Best_Trainer.ico")


def _writable_data_path(*parts):
    """A cote de l'exe en mode empaquete (PAS sys._MEIPASS, qui est un
    dossier temporaire en lecture jetable a chaque lancement) ou du script
    en mode developpement - pour les donnees que le trainer doit ecrire
    lui-meme et retrouver au lancement suivant (ex. points de teleport)."""
    base = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) \
        else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


TELEPORT_POINTS_FILE = _writable_data_path("teleport_points.json")
SETTINGS_FILE = _writable_data_path("settings.json")

# ---------------------------------------------------------------------------
# Internationalisation (FR/EN, demande utilisateur 2026-10-01, V2.0) -
# fichiers JSON embarques (_bundled_path, comme l'icone) plutot que des
# dictionnaires en dur dans ce fichier deja volumineux. Changement de
# langue = redemarrage automatique du process (pas de retraduction a
# chaud des widgets deja construits - bien plus simple, choix explicite
# de l'utilisateur plutot que de doubler la complexite pour un gain mineur
# sur un outil solo). Choix persiste dans SETTINGS_FILE (a cote de l'exe,
# comme teleport_points.json), pas dans le dossier temporaire PyInstaller.
DEFAULT_LANGUAGE = "fr"
SUPPORTED_LANGUAGES = {"fr": "Français", "en": "English"}


def _load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_settings(settings: dict) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def current_language() -> str:
    lang = _load_settings().get("language", DEFAULT_LANGUAGE)
    return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def set_language(lang: str) -> None:
    settings = _load_settings()
    settings["language"] = lang
    _save_settings(settings)


def restart_trainer() -> None:
    """Relance le process a l'identique (meme exe/script, memes
    arguments) - utilise apres un changement de langue. os.execv
    remplace le process en place (meme PID), fonctionne aussi bien en
    mode developpement (sys.executable = python.exe) qu'empaquete
    (sys.executable = l'exe du trainer, voir _writable_data_path)."""
    os.execv(sys.executable, [sys.executable] + sys.argv)


def _load_locale_file(category: str, lang: str) -> dict:
    """locales/<lang>/<category>.json - structure symetrique : chaque
    langue a exactement les memes fichiers (pas de "francais en dur dans
    le code, anglais en overlay" - les deux viennent de JSON, demande
    utilisateur 2026-10-01)."""
    path = _bundled_path("locales", lang, f"{category}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def load_locale_category(category: str) -> dict:
    """Charge un fichier de locales/<langue active>/<category>.json, avec
    repli sur le francais si la langue active n'a pas (encore) ce fichier
    ou certaines de ses cles - jamais de texte brut en dur en remplacement,
    uniquement un autre fichier JSON."""
    data = _load_locale_file(category, _LANG)
    if _LANG == DEFAULT_LANGUAGE:
        return data
    fallback = _load_locale_file(category, DEFAULT_LANGUAGE)
    merged = dict(fallback)
    merged.update(data)
    return merged


_LANG = current_language()
_STRINGS = load_locale_category("strings")
CHANGELOG_STRINGS = load_locale_category("changelog")
_WEAPON_NAMES_LOCALE = load_locale_category("weapons")
_ITEM_NAMES_LOCALE = load_locale_category("items")
_FIGURES_LOCALE = load_locale_category("figures")
_FACECAMO_LOCALE = load_locale_category("facecamo")
_VESTS_LOCALE = load_locale_category("vests")
_OUTFITS_LOCALE = load_locale_category("outfits")
_OCTOCAMO_LOCALE = load_locale_category("octocamo")

# Cles stables (pas d'ID numerique reel pour les motifs OctoCamo, voir
# mgs4save.OCTOCAMO_INFO) - doit rester synchronise avec les cles de
# locales/*/octocamo.json.
OCTOCAMO_SLUGS = {
    "Infiltration": "infiltration", "Olive": "olive", "Tigré": "tiger_stripe",
    "Forêt": "forest", "3 Couleurs Désert": "desert_3color", "Marpat": "marpat",
    "Cadavre": "corpse", "Pleurs": "crying", "Digit. B": "digital_b",
    "Digit. R": "digital_r", "Mouche": "fly", "Gear": "gear", "Haven": "haven",
    "Rire": "laughing", "Metal": "metal", "Snake": "snake", "Rage": "raging",
    "Hurler": "screaming", "Beauté": "beauty", "Précommande": "preorder", "Doré": "golden",
}


def weapon_name(weapon_id: int) -> str:
    entry = _WEAPON_NAMES_LOCALE.get(str(weapon_id))
    return entry if entry else mgs4save.WEAPON_NAMES.get(weapon_id, f"Arme #{weapon_id}")


def item_name(item_id: int) -> str:
    entry = _ITEM_NAMES_LOCALE.get(str(item_id))
    return entry if entry else mgs4save.GENERAL_ITEM_NAMES.get(item_id, f"Objet #{item_id:02d}")


def figure_name(figure_id: int) -> str:
    entry = _FIGURES_LOCALE.get(str(figure_id))
    return entry["name"] if entry else mgs4save.FIGURE_NAMES.get(figure_id, f"#{figure_id}")


def figure_condition(figure_id: int) -> str:
    entry = _FIGURES_LOCALE.get(str(figure_id))
    return entry["condition"] if entry else ""


def facecamo_name(facecamo_id: int) -> str:
    entry = _FACECAMO_LOCALE.get(str(facecamo_id))
    return entry["name"] if entry else mgs4save.FACECAMO_NAMES.get(facecamo_id, f"#{facecamo_id}")


def facecamo_condition(facecamo_id: int) -> str:
    entry = _FACECAMO_LOCALE.get(str(facecamo_id))
    return entry["condition"] if entry else ""


def vest_name(vest_id: int) -> str:
    entry = _VESTS_LOCALE.get(str(vest_id))
    return entry["name"] if entry else mgs4save.VEST_NAMES.get(vest_id, f"#{vest_id}")


def vest_condition(vest_id: int) -> str:
    entry = _VESTS_LOCALE.get(str(vest_id))
    return entry["condition"] if entry else ""


def outfit_name(outfit_id: int) -> str:
    entry = _OUTFITS_LOCALE.get(str(outfit_id))
    return entry["name"] if entry else mgs4save.OUTFIT_NAMES.get(outfit_id, f"#{outfit_id}")


def outfit_condition(outfit_id: int) -> str:
    entry = _OUTFITS_LOCALE.get(str(outfit_id))
    return entry["condition"] if entry else ""


def octocamo_name(fr_key: str) -> str:
    slug = OCTOCAMO_SLUGS.get(fr_key)
    entry = _OCTOCAMO_LOCALE.get(slug) if slug else None
    return entry["name"] if entry else fr_key


def octocamo_description(fr_key: str) -> str:
    slug = OCTOCAMO_SLUGS.get(fr_key)
    entry = _OCTOCAMO_LOCALE.get(slug) if slug else None
    return entry["description"] if entry else mgs4save.OCTOCAMO_INFO.get(fr_key, "")


# Cles stables pour les categories d'armes (mgs4save.WEAPON_GROUP_ORDER) -
# meme principe que OCTOCAMO_SLUGS.
WEAPON_GROUP_SLUGS = {
    "Arme de poing": "handgun", "Fusil d'assaut": "assault_rifle",
    "Fusil Sniper": "sniper_rifle", "Fusil à pompe": "shotgun",
    "Pistolet-mitrailleur": "smg", "Lance-grenade": "grenade_launcher",
    "Mitrailleuse": "machine_gun", "Lance-roquette": "rocket_launcher",
    "Grenade": "grenade", "Explosif": "explosive", "Magazine": "magazine",
    "Autre": "other", "Accessoire": "accessory", "Non identifiée": "unidentified",
}
_WEAPON_GROUPS_LOCALE = load_locale_category("weapon_groups")


def weapon_group_label(fr_name: str) -> str:
    slug = WEAPON_GROUP_SLUGS.get(fr_name)
    return _WEAPON_GROUPS_LOCALE.get(slug, fr_name) if slug else fr_name


def alert_state_name(value: int) -> str:
    return tr(f"alert.state_{value}")


_VITALS_LOCALE = load_locale_category("vitals")


def vital_display_name(internal_name: str) -> str:
    """internal_name reste la cle stable (VITALS, read_vital/write_vital...)
    - seul l'affichage est traduit."""
    return _VITALS_LOCALE.get(internal_name, internal_name)


def warn_dialog(parent, title: str, text: str) -> None:
    """Equivalent de QMessageBox.warning() avec un bouton OK traduit -
    le bouton standard de Qt s'affiche sinon dans la langue par defaut
    de Qt, pas la notre (meme souci que Oui/Non sur QMessageBox.question(),
    voir TrainerWindow._on_language_changed)."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(title)
    box.setText(text)
    box.addButton(tr("button.ok"), QMessageBox.AcceptRole)
    box.exec()


def tr(key: str, **kwargs) -> str:
    """Traduction par cle plate (ex. "window.title") - la cle elle-meme
    sert de repli ultime si elle manque des deux langues (repere
    visuellement les oublis pendant le developpement plutot qu'un crash
    ou un texte vide)."""
    text = _STRINGS.get(key, key)
    return text.format(**kwargs) if kwargs else text

# ---------------------------------------------------------------------------
# Acces memoire Windows bas niveau (ctypes pur, pas de pywin32/psutil/pymem -
# coherent avec le reste du projet, voir gui_app.py/save_finder.py).
# ---------------------------------------------------------------------------

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", ctypes.c_char * 256),
        ("szExePath", ctypes.c_char * 260),
    ]


kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
kernel32.Process32First.restype = wintypes.BOOL
kernel32.Process32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
kernel32.Process32Next.restype = wintypes.BOOL
kernel32.Module32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32)]
kernel32.Module32First.restype = wintypes.BOOL
kernel32.Module32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32)]
kernel32.Module32Next.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE, wintypes.LPCVOID, wintypes.LPVOID, ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.ReadProcessMemory.restype = wintypes.BOOL
kernel32.WriteProcessMemory.argtypes = [
    wintypes.HANDLE, wintypes.LPVOID, wintypes.LPCVOID, ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.WriteProcessMemory.restype = wintypes.BOOL


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


kernel32.VirtualQueryEx.argtypes = [
    wintypes.HANDLE, wintypes.LPCVOID, ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t,
]
kernel32.VirtualQueryEx.restype = ctypes.c_size_t

MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
PAGE_READWRITE = 0x04
PAGE_EXECUTE_READWRITE = 0x40
PAGE_WRITECOPY = 0x08
PAGE_EXECUTE_WRITECOPY = 0x80
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01
WRITABLE_PROTECT = PAGE_READWRITE | PAGE_EXECUTE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_WRITECOPY
USERMODE_ADDRESS_CEILING = 0x7FFFFFFF0000  # limite haute usuelle de l'espace utilisateur 64 bits


def find_pid(process_name: str) -> int | None:
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return None
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        found = kernel32.Process32First(snapshot, ctypes.byref(entry))
        while found:
            if entry.szExeFile.decode("mbcs", "ignore").lower() == process_name.lower():
                return entry.th32ProcessID
            found = kernel32.Process32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return None


def find_module_base(pid: int, module_name: str) -> int | None:
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid)
    if snapshot == INVALID_HANDLE_VALUE:
        return None
    try:
        entry = MODULEENTRY32()
        entry.dwSize = ctypes.sizeof(MODULEENTRY32)
        found = kernel32.Module32First(snapshot, ctypes.byref(entry))
        while found:
            if entry.szModule.decode("mbcs", "ignore").lower() == module_name.lower():
                return ctypes.cast(entry.modBaseAddr, ctypes.c_void_p).value
            found = kernel32.Module32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return None


class ProcessHandle:
    def __init__(self, pid: int):
        access = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION
        self.handle = kernel32.OpenProcess(access, False, pid)
        if not self.handle:
            raise OSError(f"OpenProcess a echoue (code {ctypes.get_last_error()}) - relancer en administrateur ?")

    def read_bytes(self, address: int, size: int) -> bytes:
        buf = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t(0)
        ok = kernel32.ReadProcessMemory(self.handle, ctypes.c_void_p(address), buf, size, ctypes.byref(read))
        if not ok or read.value != size:
            raise OSError(f"ReadProcessMemory a echoue a l'adresse {address:#x}")
        return buf.raw

    def write_bytes(self, address: int, data: bytes) -> None:
        written = ctypes.c_size_t(0)
        ok = kernel32.WriteProcessMemory(self.handle, ctypes.c_void_p(address), data, len(data), ctypes.byref(written))
        if not ok or written.value != len(data):
            raise OSError(f"WriteProcessMemory a echoue a l'adresse {address:#x}")

    def close(self):
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None

    def _writable_regions(self):
        """Enumere les plages memoire commises, accessibles en ecriture
        (State=MEM_COMMIT, Protect writable, sans PAGE_GUARD) - la ou vit
        l'etat de jeu. Inclut MEM_PRIVATE (heap classique) ET MEM_MAPPED :
        ce jeu s'appuie probablement sur un emulateur qui garde la RAM
        emulee dans une zone mappee (~280 Mo mesures ici, coherent avec de
        la RAM de console emulee) - un premier essai limite a MEM_PRIVATE
        n'a jamais retrouve le vrai compteur de Rations, cette zone etait
        tout simplement ignoree."""
        address = 0
        mbi = MEMORY_BASIC_INFORMATION()
        size = ctypes.sizeof(mbi)
        while address < USERMODE_ADDRESS_CEILING:
            ret = kernel32.VirtualQueryEx(self.handle, ctypes.c_void_p(address), ctypes.byref(mbi), size)
            if ret == 0:
                break
            base = mbi.BaseAddress or 0
            region_size = mbi.RegionSize or 0x1000
            if (mbi.State == MEM_COMMIT
                    and (mbi.Protect & WRITABLE_PROTECT) and not (mbi.Protect & PAGE_GUARD)):
                yield base, region_size
            address = base + region_size

    def scan_u16(self, value: int) -> set[int]:
        """Premier passage : cherche `value` (u16 LE, adresses paires
        uniquement - alignement standard des champs u16) dans toute la
        memoire heap accessible en ecriture. Retourne les adresses
        candidates (potentiellement nombreuses - a affiner avec
        refine_u16)."""
        pattern = struct.pack("<H", value & 0xFFFF)
        matches: set[int] = set()
        for base, size in self._writable_regions():
            try:
                data = self.read_bytes(base, size)
            except OSError:
                continue
            start = 0
            while True:
                idx = data.find(pattern, start)
                if idx == -1:
                    break
                if idx % 2 == 0:  # base est toujours alignee (VirtualAlloc)
                    matches.add(base + idx)
                start = idx + 1
        return matches

    def refine_u16(self, candidates: set[int], value: int) -> set[int]:
        """Passages suivants : refait un scan complet (rapide, ~qq secondes)
        et intersecte avec les candidats precedents - bien plus rapide que
        relire des millions d'adresses une par une via des appels separes."""
        return candidates & self.scan_u16(value)


# ---------------------------------------------------------------------------
# Specifique MGS4 : chaine de pointeurs + tables objets/armes.
# Source de la RVA : zexk/bbtracker, docs/mgs4_research.md (licence MIT).
# ---------------------------------------------------------------------------

PROCESS_NAME = "mgs4.exe"
# 4 pointeurs documentes par zexk/bbtracker a ces RVA. "linkvarbuf" a la
# meme disposition interne que MGS4.SAV (d'ou la reutilisation directe de
# ITEM_STATE_OFFSET/WEAPON_STATE_OFFSET pour le tableau objets/armes tel
# que serialise dans la save). MAIS teste en direct (2026-09-22/23) : ni
# linkvarbuf, ni varbuf (linkvarbuf-0x2800), ni les 2 "snapshots" ne
# suivent le stock de Ration en temps reel (tous restent figes pendant
# qu'un ramassage/consommation change reellement le stock affiche en jeu).
# Ces 4 buffers restent utilises pour items/armes (aucune meilleure piste
# pour l'instant), mais avec une grosse reserve de fiabilite - voir
# CONFIRMED_LIVE_RVAS ci-dessous pour les champs realmenet verifies en
# direct par scan memoire (technique Cheat Engine, pas la chaine de
# pointeurs documentee).
LINKVARBUF_POINTER_RVA = 0x1C28B28
VARBUF_POINTER_RVA = 0x1C28B38

# Mise a jour du jeu le 2026-09-24 : toutes les adresses trouvees le
# 2026-09-23 (table objets ET armes) se sont decalees d'un montant
# UNIFORME - confirme par test (Ration retombe exactement sur la bonne
# valeur avec ce decalage, item[0x00]/item[0x13] restent a 0, 5 armes
# confirmees revues par l'utilisateur en jeu). PAS applique a
# LINKVARBUF_POINTER_RVA/VARBUF_POINTER_RVA ci-dessus, qui eux n'ont pas
# bouge (sanity_check passe sans ce decalage). Si une future mise a jour
# decale a nouveau tout d'un bloc, chercher le meme genre de decalage
# constant avant de tout rescanner individuellement - beaucoup plus
# rapide (voir notes.md, session 2026-09-24).
MODULE_PATCH_SHIFT = 0x20

# Table objets (99 entrees) : formule FIXE et validee, trouvee dans
# MGS4.CT (table Cheat Engine communautaire de RMLSNK, non redistribuee
# ici, voir la section "Credits et sources" du README) via deux fonctions assembleur
# differentes du jeu ("objSongs"/6CEAC et "objItems"/900AE6) qui lisent
# toutes les deux [base_struct+0x14] apres avoir localise le struct d'un
# item par id (bound check "cmp ecx,62" = 0x62 = notre ITEM_STATE_COUNT-1
# exactement). Base statique a l'interieur de l'image du module (donc
# stable d'un lancement a l'autre, pas de pointeur a suivre) :
#   struct_base(id) = 0x1D84310 + id*0x48
#   etat(id)         = struct_base(id) + 0x14   (u16, meme convention
#                       0/1/65535 que le fichier de save)
# Valide le 2026-09-23 : correspond EXACTEMENT a l'adresse de Ration
# retrouvee independamment par scan memoire "valeur exacte" sur 5
# changements reels en jeu (0x1D8436C = 0x1D84310 + 1*0x48 + 0x14).
ITEM_STRUCT_BASE_RVA = 0x1D84310
ITEM_STRUCT_STRIDE = 0x48
ITEM_STRUCT_STATE_OFFSET = 0x14


def item_state_rva(item_id: int) -> int:
    return ITEM_STRUCT_BASE_RVA + item_id * ITEM_STRUCT_STRIDE + ITEM_STRUCT_STATE_OFFSET + MODULE_PATCH_SHIFT


# Table armes (95 entrees, WEAPON_STATE_OFFSET dans le fichier de save) :
# formule lineaire trouvee le 2026-09-24 (voir notes.md), sur le meme
# principe que la table objets ci-dessus mais avec une foulee differente
# et PAS de structure imbriquee (u16 directement, pas de sous-champ) :
#   etat(id) = 0x1D8258A + id*0x50   (u16, convention 0/1/2 : non
#              possedee/verrouillee/utilisable)
# Validee sur les 11 RVA deja confirmees individuellement par scan
# memoire/isolation manuelle (CONFIRMED_WEAPON_RVAS ci-dessous) : 9
# collaient exactement, les 2 restantes (0x0a/0x0b, lot Otacon) collaient
# apres un echange qui a ensuite ete confirme par double test en jeu de
# l'utilisateur (voir notes.md, correction WEAPON_NAMES dans
# mgs4save.py). Remplace donc l'ancienne piste MGS4.CT ("Weapons",
# foulee 0x18, testee et infirmee le 2026-09-23 - numerotation differente
# de nos ID de fichier de save, valeurs absurdes hors MK.17).
# CONFIRMED_WEAPON_RVAS ci-dessous est conserve comme trace d'audit : la
# liste des IDs dont l'identite reelle (quelle arme se cache derriere ce
# numero) a ete confirmee par observation en jeu, independamment de la
# formule - la formule donne un RVA fiable pour N'IMPORTE QUEL id, mais
# ne dit rien sur la fiabilite du NOM attribue a cet id dans
# mgs4save.py.WEAPON_NAMES (voir les commentaires "confiance basse"
# restants la-bas, notamment pour le lot Otacon : Mk.2 Pistol vs
# Operator, DSR-1, Sachet a gaz somnifere - Tanegashima confirme le
# 2026-09-24 grace a cette meme formule, bascule d'etat + verification en
# jeu).
WEAPON_ETAT_BASE_RVA = 0x1D8258A
WEAPON_ETAT_STRIDE = 0x50


def weapon_state_rva(weapon_id: int) -> int:
    return WEAPON_ETAT_BASE_RVA + weapon_id * WEAPON_ETAT_STRIDE + MODULE_PATCH_SHIFT


# Munitions dans le chargeur (pas la reserve) : +6 octets par rapport a
# l'etat, dans le meme struct par arme - voir MGS4Live.read_weapon_magazine.
WEAPON_MAGAZINE_OFFSET = 6
# Capacite max du chargeur (+8, juste apres le courant) - confirme
# 2026-09-26 : reste a 7 pendant qu'un tir fait descendre +6 de 7 a 6,
# meme technique que les paires courant/max de VITALS.
WEAPON_MAGAZINE_MAX_OFFSET = 8

# Objet special actuellement equipe (Bandana=0x0f, Camouflage optique=
# 0x10, 0=aucun) - PAS un flag booleen, un vrai ID d'objet lu par le
# moteur du jeu en temps reel (confirme 2026-09-26 : l'ecrire equipe
# reellement l'objet en jeu, pas seulement en memoire - le HUD et le
# comportement suivent). Trouve par scan exact (15 puis 16 en alternant
# Bandana/Camouflage optique, cf. la methode habituelle) apres l'echec
# d'une premiere piste booleen (corrélée mais pas causale, voir notes.md).
# PAS utilise par "Munitions infinies" (VitalsTab) au final : forcer le
# Bandana ne marche que si le joueur le possede reellement (sinon le jeu
# rejette silencieusement), et entre en conflit avec un autre objet
# special reellement equipe (ex. Camouflage optique) - trop fragile pour
# un usage general, voir notes.md. Constante gardee en audit trail (RE
# confirmee) au cas ou une future fonctionnalite dediee au Bandana en
# aurait besoin.
SPECIAL_ITEM_EQUIPPED_RVA = 0x23FED44A
BANDANA_ITEM_ID = 0x0f


def special_item_equipped_rva() -> int:
    return SPECIAL_ITEM_EQUIPPED_RVA + MODULE_PATCH_SHIFT


CONFIRMED_WEAPON_RVAS: dict[int, int] = {
    # MK.17 (0x1e) : confirme le 2026-09-23, scan sur transition reelle
    # verrouille(1)->utilisable(2) apres deverrouillage chez Drebin. Seul
    # candidat survivant dans la zone stable de l'image du module apres
    # intersection avec le scan initial (2 894 191 -> 410 -> 1).
    # CONFIANCE MAXIMALE : contrairement a CONFIRMED_WEAPON_AMMO_RVAS
    # ci-dessous, l'ecriture a ete verifiee visuellement en jeu (forcer a
    # verrouille/utilisable change reellement l'etat dans la roue
    # d'equipement), pas juste une relecture memoire.
    0x1e: 0x1D82EEA,
    # Couteau paralysant (0x01) : RVA 0x1D825DA, confirme le 2026-09-23 par
    # isolation manuelle (10 candidats "deja utilisables" forces a
    # verrouille sauf un a la fois, utilisateur confirme quelle arme
    # redevient utilisable a chaque tour). Effet verifie visuellement en
    # jeu par construction de la methode elle-meme.
    0x01: 0x1D825DA,
    # Mk.2 Pistol (0x02) : RVA 0x1D8262A, confirme le 2026-09-23 par la
    # meme methode d'isolation - resout enfin l'ambiguite du "lot Otacon"
    # (0x02/0x03/0x0a/0x0b/0x4d, jamais isole individuellement avant, voir
    # notes.md). Reconfirme independamment le 2026-09-24 par bascule
    # d'etat via weapon_state_rva (comme pour 0x1d/Tanegashima).
    0x02: 0x1D8262A,
    # Operator (0x03) : RVA 0x1D8267A, confirme le 2026-09-23, meme methode
    # d'isolation - lot Otacon.
    0x03: 0x1D8267A,
    # Thor .45-70 (0x0a) : RVA 0x1D828AA, confirme le 2026-09-23, meme
    # methode d'isolation - lot Otacon. IDs 0x0a/0x0b corriges le
    # 2026-09-24 : la formule lineaire du tableau d'etat (voir plus haut,
    # RVA = 0x1D8258A + id*0x50 + MODULE_PATCH_SHIFT) predisait un
    # echange par rapport a l'attribution initiale, confirme par double
    # test en jeu de l'utilisateur (verrouiller cette adresse verrouille
    # bien le Thor .45-70, pas le 1911). Voir notes.md.
    0x0a: 0x1D828AA,
    # 1911 Modifie (0x0b) : RVA 0x1D828FA, confirme le 2026-09-23, meme
    # methode d'isolation - lot Otacon. ID corrige le 2026-09-24 (voir
    # commentaire ci-dessus).
    0x0b: 0x1D828FA,
    # M4 (0x18) : RVA 0x1D82D0A, confirme le 2026-09-23, meme methode
    # d'isolation. Munitions deja connues (partagees avec AK-102).
    0x18: 0x1D82D0A,
    # AK-102 (0x19) : RVA 0x1D82D5A, confirme le 2026-09-23, meme methode
    # d'isolation. Munitions deja connues (partagees avec M4).
    0x19: 0x1D82D5A,
    # Mine a gaz somnifere (0x41) : RVA 0x1D839DA, confirme le 2026-09-23,
    # meme methode d'isolation. Munitions deja connues.
    0x41: 0x1D839DA,
    # Magazine Playboy (0x45) : RVA 0x1D83B1A, confirme le 2026-09-23, meme
    # methode d'isolation. Munitions deja connues.
    0x45: 0x1D83B1A,
    # Grenade paralysante (0x36) : confirme le 2026-09-23, scan sur
    # transition reelle verrouillee(1)->utilisable(2) apres deverrouillage
    # chez Drebin (2 870 831 -> 512 -> 1 candidat stable). Ecriture testee
    # en aller-retour (relecture memoire uniquement, pas encore verifiee
    # visuellement en jeu pour celle-ci specifiquement).
    0x36: 0x1D8366A,
    # Tanegashima (0x1d) : RVA 0x1D82E9A (= weapon_state_rva(0x1d), pas de
    # scan necessaire), confirme le 2026-09-24 en basculant l'etat via le
    # trainer et en observant en jeu que c'est bien le Tanegashima qui se
    # verrouille/deverrouille - resout la "confiance basse" historique de
    # cet ID (voir WEAPON_NAMES dans mgs4save.py et notes.md).
    0x1d: 0x1D82E9A,
    # Masterkey (0x4a) : RVA 0x1D83CAA (= weapon_state_rva(0x4a), pas de
    # scan necessaire), confirme le 2026-09-24 - forcer l'etat a 0 rend
    # bien le Masterkey indisponible/non equipable en jeu. 1 et 2 se
    # comportent pareil (pas de palier "verrouille chez Drebin" pour cette
    # arme a declencheur scenaristique unique - contrairement aux armes
    # achetees), d'ou l'absence d'effet observee au premier essai (etat
    # force a 1 au lieu de 0).
    0x4a: 0x1D83CAA,
    # Silencieux Operator (0x4d) : RVA 0x1D83D9A (=
    # weapon_state_rva(0x4d), pas de scan necessaire), confirme le
    # 2026-09-24 - meme test que le Masterkey (forcer l'etat a 0, pas 1)
    # : le silencieux devient bien indisponible en jeu. Resout enfin le
    # dernier morceau du lot Otacon (0x02/0x03/0x0a/0x0b/0x4d).
    0x4d: 0x1D83D9A,
    # Silencieux Mk.23 (0x4e) : RVA 0x1D83DEA (= weapon_state_rva(0x4e),
    # pas de scan necessaire), confirme le 2026-09-24 - tous les
    # accessoires forces a 0 puis rachetes un par un chez Drebin,
    # seul 0x4e est repasse a 2 au moment de racheter le Silencieux
    # Mk.23. Resout la "confiance basse" historique sur cette identite.
    0x4e: 0x1D83DEA,
    # Silencieux 1911 (0x4f) : RVA 0x1D83E3A (= weapon_state_rva(0x4f)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute depuis un test isole du 2026-09-05).
    0x4f: 0x1D83E3A,
    # Silencieux P90 (0x51) : RVA 0x1D83EDA (= weapon_state_rva(0x51)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute depuis un test isole du 2026-09-05).
    0x51: 0x1D83EDA,
    # Visee laser (M4) (0x58) : RVA 0x1D8410A (= weapon_state_rva(0x58)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute depuis un test isole du 2026-09-06).
    0x58: 0x1D8410A,
    # Lumiere Fusil (M4) (0x57) : RVA 0x1D840BA (= weapon_state_rva(0x57)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (nom exact deja confirme par capture d'ecran, 2026-09-02).
    0x57: 0x1D840BA,
    # Silencieux M10 (0x50) : RVA 0x1D83E8A (= weapon_state_rva(0x50)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute depuis un test isole du 2026-09-05).
    0x50: 0x1D83E8A,
    # Visee point rouge (MP7) (0x56) : RVA 0x1D8406A (=
    # weapon_state_rva(0x56)), reconfirme le 2026-09-24 par le meme
    # rachat un par un chez Drebin (deja confirmee, test isole propre sur
    # partie fraiche).
    0x56: 0x1D8406A,
    # Lunette de fusil (0x54) : RVA 0x1D83FCA (= weapon_state_rva(0x54)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute).
    0x54: 0x1D83FCA,
    # GP-30 (0x4c) : RVA 0x1D83D4A (= weapon_state_rva(0x4c)), reconfirme
    # le 2026-09-24 par le meme rachat un par un chez Drebin (deja
    # confiance haute).
    0x4c: 0x1D83D4A,
    # Visee point rouge (M4) (0x55) : RVA 0x1D8401A (=
    # weapon_state_rva(0x55)), reconfirme le 2026-09-24 par le meme
    # rachat un par un chez Drebin (deja confirmee).
    0x55: 0x1D8401A,
    # Silencieux M4 (0x52) : RVA 0x1D83F2A (= weapon_state_rva(0x52)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute - voir aussi DREBIN_LOCK_EXCEPTIONS dans
    # mgs4save.py pour son comportement "faux verrouille" connu).
    0x52: 0x1D83F2A,
    # XM320 (0x4b) : RVA 0x1D83CFA (= weapon_state_rva(0x4b)), reconfirme
    # le 2026-09-24 par le meme rachat un par un chez Drebin (deja
    # confiance haute).
    0x4b: 0x1D83CFA,
    # Poignee avant A. (0x5a) : RVA 0x1D841AA (= weapon_state_rva(0x5a)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute).
    0x5a: 0x1D841AA,
    # Poignee avant B. (0x5b) : RVA 0x1D841FA (= weapon_state_rva(0x5b)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute).
    0x5b: 0x1D841FA,
    # Silencieux M14EBR (0x53) : RVA 0x1D83F7A (= weapon_state_rva(0x53)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute). Dernier accessoire de la plage 0x4a-0x5b a
    # etre reconfirme individuellement - les 18 sont desormais tous
    # confirmes.
    0x53: 0x1D83F7A,
    # Desert Eagle (Canon Long) (0x09) : RVA 0x1D8285A (=
    # weapon_state_rva(0x09)), decouvert via le trainer le 2026-09-24
    # (ID auparavant sans nom).
    0x09: 0x1D8285A,
    # Type 17 (0x10) : RVA 0x1D82A8A (= weapon_state_rva(0x10)),
    # decouvert via le trainer le 2026-09-24 (ID auparavant sans nom).
    # Etat actuel = 1 malgre 878 munitions en stock (pool .45 ACP
    # partage) - possible cas de "faux verrouille" comme les silencieux
    # (voir DREBIN_LOCK_EXCEPTIONS dans mgs4save.py), pas encore
    # confirme par un test dedie.
    0x10: 0x1D82A8A,
    # Patriot (0x16) : RVA 0x1D82C6A (= weapon_state_rva(0x16)),
    # decouvert via le trainer le 2026-09-24 (ID auparavant sans nom).
    # Arme bonus a munitions illimitees, pas de pool de munitions a
    # suivre dans CONFIRMED_WEAPON_AMMO_RVAS. Etat actuel = 1 malgre
    # possession confirmee - meme pattern que le Type 17 (0x10).
    0x16: 0x1D82C6A,
    # "Destabil.SOP" (0x44) : RVA 0x1D83ACA (= weapon_state_rva(0x44)),
    # decouvert via le trainer le 2026-09-24 - objet inedit "POSER" (pas
    # une arme), jamais documente ailleurs. Etat=2 (possede) au moment de
    # la decouverte.
    0x44: 0x1D83ACA,
}

# Table MUNITIONS par arme (separee de la table possession/etat ci-dessus -
# coherent avec le tableau 0x352 "munitions par emplacement d'equipement"
# deja documente dans notes.md pour le fichier de save). PAS reliee au
# flag "possedee" : poser toutes ses mines n'a fait bouger aucun des
# candidats de la table etat/possession (voir notes.md, session
# 2026-09-23) - la possession reste vraie une fois obtenue, seul le stock
# varie ici.
# ATTENTION - RAFRAICHISSEMENT DIFFERE, PAS INSTANTANE : l'ecriture est
# bien la bonne adresse (confirme par l'utilisateur, 2026-09-23), mais le
# HUD/inventaire ne se met a jour qu'au moment d'EQUIPER l'arme concernee
# - pas en continu ni immediatement apres l'ecriture. Premiere impression
# "l'ecriture ne fait rien" corrigee : juste besoin d'equiper l'arme pour
# forcer le rafraichissement de l'affichage.
#   - Mine a gaz somnifere (arme 0x41) : RVA 0x1D82420, confirme par scan
#     "valeur exacte" sur un achat de 36 puis pose de 2 (36->34), seul
#     candidat stable dans l'image du module apres intersection
#     (248 089 -> 3 -> 1).
#   - AK-102 (0x19) / M4 (0x18) : meme adresse (RVA 0x1D820C0) pour les
#     deux, confirme (2026-09-23) - pool de munitions .5.56mm PARTAGE entre
#     armes du meme calibre, comme deja documente dans notes.md pour le
#     fichier de save (tableau 0x352). Scan "valeur exacte" 278->270 :
#     11 014 -> 33 candidats stables -> 1 seul apres le changement reel.
CONFIRMED_WEAPON_AMMO_RVAS: dict[int, int] = {
    0x41: 0x1D82420,
    0x18: 0x1D820C0,
    0x19: 0x1D820C0,
    # XM8 (0x1f) et Mk.46 MOD1 (0x20) partagent le MEME pool 5,56mm (avec
    # M4/AK-102) - confirme (2026-09-24) via capture d'ecran du menu
    # "boutique" affichant ces armes a la meme valeur (829), qui
    # correspondait exactement a la valeur deja lue en memoire, pas de
    # scan separe necessaire.
    0x1f: 0x1D820C0,
    0x20: 0x1D820C0,
    # AN-94 (0x1b) : RVA 0x1D820A8, confirme (2026-09-24) - scan "valeur
    # exacte" sur 180 (calibre 5,45x39mm propre, non partage avec une
    # arme deja connue), filtre zone proche connue -> 1 seul candidat
    # direct.
    0x1b: 0x1D820A8,
    # Tanegashima (0x1d, identite desormais confiance haute - confirmee le
    # 2026-09-24 via weapon_state_rva, voir WEAPON_NAMES dans mgs4save.py)
    # : RVA 0x1D82198, confirme (2026-09-24) - scan "valeur exacte" sur
    # 300 (balle plomb, calibre propre), filtre zone proche connue -> 1
    # seul candidat direct.
    0x1d: 0x1D82198,
    # DSR-1 (0x29, identite exacte confiance basse - jamais confirmee
    # individuellement, voir WEAPON_NAMES dans mgs4save.py) : RVA
    # 0x1D82180, confirme (2026-09-24) - scan "valeur exacte" sur 365
    # (7,62x67mm, calibre propre), filtre zone proche connue -> 1 seul
    # candidat direct.
    0x29: 0x1D82180,
    # SVD (0x2c) : RVA 0x1D82120, confirme (2026-09-24) - scan "valeur
    # exacte" sur 936 (7,62x54mm R, calibre propre), filtre zone proche
    # connue -> 1 seul candidat direct. PKM (0x22) partage le MEME pool -
    # confirme via capture d'ecran boutique (936, correspondance directe),
    # pas de scan separe necessaire.
    0x2c: 0x1D82120,
    0x22: 0x1D82120,
    # Mosin-Nagant (0x2b) : RVA 0x1D81FA0, confirme (2026-09-24) - scan
    # "valeur exacte" sur 320 (fleche anesthesiante 7,62mm, calibre
    # propre), filtre zone proche connue -> 1 seul candidat direct.
    0x2b: 0x1D81FA0,
    # VSS (0x27) : RVA 0x1D82168, confirme (2026-09-24) par scan "valeur
    # exacte" sur 110 (9x39mm), 2 candidats stables -> 1 seul confirme par
    # une vraie consommation (110->104), l'autre candidat restant fige a
    # 110.
    0x27: 0x1D82168,
    # M82A2 (0x28) : RVA 0x1D82078, confirme (2026-09-24) par scan "valeur
    # exacte" sur 80 (.50 BMR), 3 candidats stables -> 1 seul confirme par
    # une vraie consommation (80->70), les 2 autres restes figes a 80.
    0x28: 0x1D82078,
    # Rail Gun (0x2d) : RVA 0x1D824B0, confirme (2026-09-24) par scan
    # "valeur exacte" sur 100 (munitions Rail Gun), 8 candidats stables ->
    # 1 seul confirme par une vraie consommation (100->98), les 7 autres
    # restes figes a 100.
    0x2d: 0x1D824B0,
    # Double canon (0x24) : RVA 0x1D821B0, confirme (2026-09-24) - scan
    # "valeur exacte" sur 152 (12GA chevrotine 00, calibre propre), filtre
    # zone proche connue -> 1 seul candidat direct. M870 Modifie (0x25) et
    # Saiga-12 (0x26) partagent le MEME pool - confirme via capture
    # d'ecran boutique (152, correspondance directe pour les 3 armes),
    # pas de scan separe necessaire.
    0x24: 0x1D821B0,
    0x25: 0x1D821B0,
    0x26: 0x1D821B0,
    # Masterkey (0x4a) : meme pool 12GA - confirme (2026-09-24) par
    # correspondance directe (152) puis vraie consommation simultanee
    # sur le pool (152->148).
    0x4a: 0x1D821B0,
    # MGL-140 (0x2e) : RVA 0x1D82210, confirme (2026-09-24) par scan
    # "valeur exacte" sur 63 (40mm GRD), 2 candidats stables -> 1 seul
    # confirme par une vraie consommation (63->60), l'autre reste fige.
    # XM320 (0x4b) partage le MEME pool 40mm - confirme par une vraie
    # consommation simultanee sur les deux (65->61).
    0x2e: 0x1D82210,
    0x4b: 0x1D82210,
    # GP-30 (0x4c) : RVA 0x1D821F8, confirme (2026-09-24) par scan
    # "valeur exacte" sur 65, 2 candidats stables -> 1 seul confirme par
    # une vraie consommation (65->63), l'autre reste fige a 65.
    0x4c: 0x1D821F8,
    # RPG-7 (0x32) : RVA 0x1D822B8, confirme (2026-09-24) par scan "valeur
    # exacte" sur 64, 12 candidats stables -> 1 seul confirme par une
    # vraie consommation (64->63), les 11 autres restes figes a 64.
    0x32: 0x1D822B8,
    # XM25 (0x2f) : RVA 0x1D82270, confirme (2026-09-24) par scan "valeur
    # exacte" sur 2 (valeur tres basse, 132 candidats stables initiaux) ->
    # affine via 2 consommations reelles successives (2->1 puis 1->51,
    # rechargement) -> 1 seul candidat survivant a chaque etape.
    0x2f: 0x1D82270,
    # FIM-92A (0x30) : RVA 0x1D82288, confirme (2026-09-24) par scan
    # "valeur exacte" sur 54, 2 candidats stables -> 1 seul confirme par
    # une vraie consommation (54->51), l'autre reste fige a 54.
    0x30: 0x1D82288,
    # FGM-148 Javelin (0x31) : RVA 0x1D822A0, confirme (2026-09-24) par
    # scan "valeur exacte" sur 36, 2 candidats stables -> 1 seul confirme
    # par une vraie consommation (36->34), l'autre reste fige a 36. Notee
    # convergence de valeur avec M72A3 (les deux terminent a 34) mais
    # adresses distinctes suivies independamment depuis des valeurs de
    # depart differentes (35 vs 36) - pas un pool partage, coincidence.
    0x31: 0x1D822A0,
    # M72A3 (0x33) : RVA 0x1D822D0, confirme (2026-09-24) par scan "valeur
    # exacte" sur 35, 2 candidats stables -> 1 seul confirme par une
    # vraie consommation (35->34), l'autre reste fige a 35.
    0x33: 0x1D822D0,
    # Grenade (0x34) : RVA 0x1D822E8, confirme (2026-09-24) par scan
    # "valeur exacte" sur 85, 2 candidats stables -> 1 seul confirme par
    # une vraie consommation (85->84), l'autre reste fige a 85.
    0x34: 0x1D822E8,
    # Cocktail Molotov (0x3d) : RVA 0x1D823C0, confirme (2026-09-24) par
    # scan "valeur exacte" sur 60, 8 candidats stables -> 1 seul confirme
    # par une vraie consommation (60->57), les 7 autres restes figes a 60.
    0x3d: 0x1D823C0,
    # Grenade au phosphore blanc (0x35) : RVA 0x1D82300, confirme
    # (2026-09-24) par scan "valeur exacte" sur 75, 2 candidats stables ->
    # 1 seul confirme par une vraie consommation (75->70), l'autre reste
    # fige a 75.
    0x35: 0x1D82300,
    # Grenade a particules metalliques / "Electro" (0x37) : RVA 0x1D82330,
    # confirme (2026-09-24) par scan "valeur exacte" sur 22, 3 candidats
    # stables -> 1 seul confirme par une vraie consommation (22->18), les
    # 2 autres restes figes a 22.
    0x37: 0x1D82330,
    # Grenade fumigene generique (0x38) : RVA 0x1D82348, confirme
    # (2026-09-24) par scan "valeur exacte" sur 77, 2 candidats stables ->
    # 1 seul confirme par une vraie consommation (77->75), l'autre reste
    # fige a 77.
    0x38: 0x1D82348,
    # Grenade fumigene (Jaune) (0x3b) : RVA 0x1D82390, confirme
    # (2026-09-24) par scan "valeur exacte" sur 28, 6 candidats stables ->
    # 1 seul confirme par une vraie consommation (28->27), les 5 autres
    # restes figes a 28.
    0x3b: 0x1D82390,
    # Grenade fumigene (Rouge) (0x39) : RVA 0x1D82360, confirme
    # (2026-09-24) par scan "valeur exacte" sur 7, 9 candidats stables ->
    # 1 seul confirme par une vraie consommation (7->5), les 8 autres
    # restes figes a 7.
    0x39: 0x1D82360,
    # Grenade fumigene (Bleue) (0x3c) : RVA 0x1D823A8, confirme
    # (2026-09-24) par scan "valeur exacte" sur 35, 2 candidats stables ->
    # 1 seul confirme par une vraie consommation (35->32), l'autre reste
    # fige a 35.
    0x3c: 0x1D823A8,
    # Grenade fumigene (Verte) (0x3a) : RVA 0x1D82378, confirme
    # (2026-09-24) par scan "valeur exacte" sur 70, 2 candidats stables ->
    # 1 seul confirme par une vraie consommation (70->66), l'autre etait
    # un faux positif coincidant avec l'adresse deja connue du M82A2
    # (0x1D82078), reste fige a 70.
    0x3a: 0x1D82378,
    # Claymore (0x40) : RVA 0x1D82408, confirme (2026-09-24) par scan
    # "valeur exacte" sur 59, 2 candidats stables -> 1 seul confirme par
    # une vraie consommation (59->58), l'autre reste fige a 59.
    0x40: 0x1D82408,
    # C4 (0x42) : RVA 0x1D82438, confirme (2026-09-24) par scan "valeur
    # exacte" sur 18, 7 candidats stables -> 1 seul confirme par une
    # vraie consommation (18->17), les 6 autres restes figes a 18
    # (dont 0x1D82330, coincidence avec l'adresse deja connue de la
    # grenade Electro).
    0x42: 0x1D82438,
    # Sachet a gaz somnifere (0x43, identite confiance basse - voir
    # WEAPON_NAMES dans mgs4save.py) : RVA 0x1D82450, confirme
    # (2026-09-24) par scan "valeur exacte" sur 12, 10 candidats stables
    # -> 1 seul confirme par une vraie consommation (12->11), les 9
    # autres restes figes a 12.
    0x43: 0x1D82450,
    # Chargeur (0x3e, objet de diversion, pas une arme) : RVA 0x1D823D8,
    # confirme (2026-09-24) - scan "valeur exacte" sur 110, filtre zone
    # proche connue -> 1 seul candidat direct.
    0x3e: 0x1D823D8,
    # Magazine Emotion (0x46) : RVA 0x1D82498, confirme (2026-09-24) par
    # scan "valeur exacte" sur 19, 5 candidats stables -> 1 seul confirme
    # par une vraie consommation (19->18), les 4 autres restes figes a
    # 19.
    0x46: 0x1D82498,
    # "Destabil.SOP" (0x44) : RVA 0x1D82468, calcule via la formule
    # lineaire du bloc explosifs/etc (0x1D81E08 + id*0x18, voir
    # commentaire plus haut sur ce bloc) plutot que scanne - confirme
    # (2026-09-24) : lisait bien 0 (l'utilisateur n'en avait aucun),
    # ecrit a 10 pour permettre un test en jeu.
    # ATTENTION DANGER (2026-09-24) : tenter d'EQUIPER/UTILISER cet objet
    # en jeu (meme avec un stock force via cette adresse) a fait PLANTER
    # le jeu (fatal error, dump genere). Objet probablement pas prevu
    # pour etre reellement utilise en solo. Lire/ecrire cette valeur en
    # memoire reste sans danger en soi - c'est l'usage EN JEU qui pose
    # probleme. Voir notes.md.
    0x44: 0x1D82468,
    # Magazine Playboy (0x45) : RVA 0x1D82480, confirme (2026-09-23) par
    # scan "valeur exacte" sur un vrai changement de stock (2->11), filtre
    # zone proche connue puis intersection - 1 seul survivant direct.
    0x45: 0x1D82480,
    # Grenade paralysante (0x36) : RVA 0x1D82318, confirme (2026-09-23) par
    # scan "valeur exacte" sur une vraie consommation (5->4), filtre zone
    # proche connue puis intersection - 1 seul survivant direct.
    0x36: 0x1D82318,
    # MK.17 (0x1e) : RVA 0x1D82108, confirme (2026-09-23) par scan "valeur
    # exacte" sur une vraie consommation (37->29), filtre zone proche
    # connue - 2 candidats, 1 seul confirme par le vrai changement.
    # G3A3 (0x1a), FAL (0x1c), M14EBR (0x2a), HK21E (0x21) et M60E4 (0x23)
    # partagent le MEME pool 7,62x51mm - confirme (2026-09-24) via capture
    # d'ecran du menu "boutique" affichant ces armes a la meme valeur
    # (2214), qui correspondait exactement a la valeur deja lue en
    # memoire pour MK.17, pas de scan separe necessaire.
    0x1e: 0x1D82108,
    0x1a: 0x1D82108,
    0x1c: 0x1D82108,
    0x2a: 0x1D82108,
    0x21: 0x1D82108,
    0x23: 0x1D82108,
    # Thor .45-70 (0x0a, ID corrige le 2026-09-24 - voir CONFIRMED_WEAPON_RVAS
    # et notes.md) : RVA 0x1D82048, confirme (2026-09-23) par scan "valeur
    # exacte" sur une vraie consommation (10->8), filtre zone proche
    # connue - 7 candidats, 1 seul confirme. Munition propre (.45-70
    # Government, distincte du .45 ACP), coherent avec le fait que cette
    # adresse ne partage PAS le pool avec Operator/1911/Mk.23.
    0x0a: 0x1D82048,
    # Mk.2 Pistol (0x02) : RVA 0x1D81F28, confirme (2026-09-23) - scan
    # "valeur exacte" sur 95, filtre zone proche connue -> 1 seul candidat
    # directement (pas besoin de transition supplementaire).
    0x02: 0x1D81F28,
    # Operator (0x03) : RVA 0x1D82030, confirme (2026-09-23) - scan "valeur
    # exacte" sur 98, filtre zone proche connue -> 1 seul candidat direct.
    # 1911 Modifie (0x0b, ID corrige le 2026-09-24 - voir notes.md) partage
    # le MEME pool (.45 ACP) - confirme par l'utilisateur (tir avec
    # Operator, 98->97 visible aussi sur le 1911), pas de scan separe
    # necessaire. Mk.23 (0x04) aussi confirme dans le
    # meme pool (2026-09-24) : scan sur 933, meme adresse.
    # M-10 (0x13) : aussi dans le pool .45 ACP - confirme par l'utilisateur
    # (938, correspondance directe avec la valeur deja lue), pas de scan
    # separe necessaire. GSR (0x07, SIG Sauer GSR .45 ACP) : idem,
    # confirme (2026-09-24) par correspondance directe (938).
    0x03: 0x1D82030,
    0x0b: 0x1D82030,
    0x04: 0x1D82030,
    0x13: 0x1D82030,
    0x07: 0x1D82030,
    # Type 17 (0x10) : aussi dans le pool .45 ACP - confirme (2026-09-24)
    # par correspondance directe (878), pas de scan separe necessaire.
    0x10: 0x1D82030,
    # Five-Seven (0x06) : RVA 0x1D820D8, confirme (2026-09-24, post mise a
    # jour) - scan "valeur exacte" sur 2062, filtre zone proche connue ->
    # 1 seul candidat direct. P90 (0x14) partage le MEME pool (5.7x28mm,
    # coherent avec le calibre reel partage entre ces deux armes) -
    # confirme par l'utilisateur (2058->2038 visible sur les deux a la
    # fois), pas de scan separe necessaire.
    0x06: 0x1D820D8,
    0x14: 0x1D820D8,
    # PMM (0x05) : RVA 0x1D82138, confirme (2026-09-24, post mise a jour) -
    # scan "valeur exacte" sur 494, filtre zone proche connue -> 1 seul
    # candidat direct. Vz. 83 (0x17) et PP-19 Bizon (0x15) partagent le
    # MEME pool (9x18mm Makarov) - confirme par l'utilisateur (490->484
    # visible sur les trois a la fois ; le tout premier scan sur 490 avait
    # d'abord ete ecarte par prudence car identique a la valeur PMM du
    # moment), pas de scan separe necessaire.
    0x05: 0x1D82138,
    0x17: 0x1D82138,
    0x15: 0x1D82138,
    # PSS (0x0e) : RVA 0x1D820F0, confirme (2026-09-24) - scan "valeur
    # exacte" sur une vraie consommation (77->75), 3 candidats -> 1 seul
    # confirme par le vrai changement.
    0x0e: 0x1D820F0,
    # G18C (0x0f) : RVA 0x1D82150, confirme (2026-09-24) - scan "valeur
    # exacte" sur 210, filtre zone proche connue -> 1 seul candidat direct.
    # MP5SD2 (0x12) partage le MEME pool (9x19mm Parabellum) - confirme par
    # l'utilisateur (188 visible sur les deux a la fois, premier scan sur
    # 210 avait d'abord ete ecarte par prudence car identique a la valeur
    # G18C du moment), pas de scan separe necessaire.
    0x0f: 0x1D82150,
    0x12: 0x1D82150,
    # Arme de chasse (0x0c) : RVA 0x1D82018, confirme (2026-09-24) par 4
    # changements reels (18->15->14->7->37). Un 2e candidat (0x1D82950)
    # etait reste synchronise sur les 3 premiers tours (coincidence), puis
    # a diverge au 4e (reste bloque a 7 pendant que 0x1D82018 passait a
    # 37) - confirme que ce n'etait qu'un faux positif, pas un pool
    # partage. Identite de 0x1D82950 non poursuivie (sans interet).
    0x0c: 0x1D82018,
    # D.E. / Desert Eagle (0x08) : RVA 0x1D82060, confirme (2026-09-24) par
    # scan sur une vraie consommation (11->8), 3 candidats -> 1 seul
    # confirme par le vrai changement. Desert Eagle (Canon Long) (0x09)
    # partage le MEME pool (variante canon long, meme calibre) -
    # confirme par l'utilisateur (correspondance directe, 8), pas de scan
    # separe necessaire.
    0x08: 0x1D82060,
    0x09: 0x1D82060,
    # MP7 (0x11) : RVA 0x1D82090, confirme (2026-09-24) - scan "valeur
    # exacte" sur 953, filtre zone proche connue -> 1 seul candidat direct.
    0x11: 0x1D82090,
}


# "Etat de jeu" (Vie/Endurance/Stress/Batterie Solid Eye/Metal Gear REX) -
# decouvert le 2026-09-25 via le fichier MGS4.CT (section "aob Statistics",
# PAS marquee WIP/Graveyard contrairement a d'autres pistes du meme fichier -
# utilisee pour de vraies triches "vie/endurance/batterie infinies", donc a
# priori fiable). Confirme : pStatistics (leur nom) = linkvarbuf (le notre) -
# meme pointeur mgs4.exe+1C28B28, et leurs offsets +0x34/+0x54/+0x1C0
# correspondent EXACTEMENT aux offsets deja etablis chez nous pour le
# fichier de save (zone/stage, scene/progression, Drebin actuel). Toutes
# les valeurs testees et confirmees par de vraies transitions en jeu (voir
# notes.md) : Vie/Endurance en dommages reels, Stress sur plusieurs valeurs
# distinctes avec correspondance precise a l'affichage HUD (brut/10 = %).
# (offset_actuel, offset_max_ou_None, taille en octets, max_fixe_si_pas_de_max_live)
# relatifs a linkvarbuf. Stress n'a pas de champ "max" en memoire (juste
# une plage fixe 0-1000 pour brut/10 = 0-100%).
VITALS: dict[str, tuple[int, int | None, int, int | None]] = {
    "Sante": (0xB48, 0xB4A, 2, None),
    "Stamina": (0xB4C, 0xB4E, 2, None),
    "Stress": (0xB50, None, 2, 1000),
    "Batterie Solid Eye": (0xB52, 0xB54, 2, None),
    "Sante Metal Gear REX": (0xB70, 0xB74, 4, None),
}

# Etat d'alerte : PAS relatif a linkvarbuf, adresse statique trouvee dans
# MGS4.CT (section "Alert -- Ignore", elle-meme WIP/Graveyard, mais
# l'adresse capturee a l'injection s'est revelee fiable EN LECTURE malgre
# tout - voir notes.md). PAS de MODULE_PATCH_SHIFT a appliquer (confirme :
# l'appliquer donne une valeur absurde). Confirme par transitions reelles
# successives : 0=Normal/non repere, 1=Alerte, 2=Evasion, 3=Prudence (le
# 4e etat manquant identifie le 2026-09-25 - lu en jeu pendant que
# l'utilisateur voyait "Prudence" affiche, valeur qui suit logiquement
# Evasion avant le retour a Normal, coherent avec la sequence habituelle
# des jeux MGS). L'ecriture ne "tient" pas (le jeu la recalcule en
# continu a partir de l'etat reel de l'IA), contrairement aux champs
# VITALS ci-dessus - lecture seule.
ALERT_STATE_RVA = 0x1D77AB8
ALERT_STATE_NAMES = {0: "Normal (non repere)", 1: "Alerte", 2: "Evasion", 3: "Prudence"}


# ---------------------------------------------------------------------------
# Controle de la vitesse du jeu (ralenti/accelere) + pause (2026-09-26).
#
# Pause : pas besoin d'injection, NtSuspendProcess/NtResumeProcess (ntdll)
# suffisent - gel complet du process (pas le menu pause du jeu), deja
# teste et confirme fonctionnel en amont (voir notes.md). Handle dedie
# temporaire (PROCESS_SUSPEND_RESUME, absent de ProcessHandle par
# defaut), ferme immediatement apres usage.
#
# Vitesse (ralenti fluide ET accelere, pas juste des pauses en rafale) :
# necessite d'injecter une DLL (native/speedhack.c, compilee en
# speedhack_x64.dll) dans mgs4.exe qui patche son IAT pour rediriger
# QueryPerformanceCounter vers un compteur "virtuel" avancant plus vite/
# lentement - technique standard de "speedhack" (proche de ce que fait
# Cheat Engine), mais jamais utilisee ailleurs dans ce projet (partout
# ailleurs : lecture/ecriture memoire externe pure, aucune injection de
# code). Communique avec le trainer via une memoire partagee nommee
# (double = multiplicateur, 1.0 = normal) plutot que reinjecter a chaque
# changement. Hypothese non confirmee : que mgs4.exe utilise bien QPC
# pour son delta-temps interne - a valider empiriquement en jeu, voir
# native/speedhack.c pour le detail et le plan de secours (autre API de
# temps) si sans effet.
# ---------------------------------------------------------------------------

ntdll = ctypes.WinDLL("ntdll")
ntdll.NtSuspendProcess.argtypes = [wintypes.HANDLE]
ntdll.NtSuspendProcess.restype = ctypes.c_long
ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
ntdll.NtResumeProcess.restype = ctypes.c_long

PROCESS_CREATE_THREAD = 0x0002
PROCESS_SUSPEND_RESUME = 0x0800

kernel32.VirtualAllocEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
kernel32.VirtualAllocEx.restype = wintypes.LPVOID
kernel32.VirtualFreeEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD]
kernel32.VirtualFreeEx.restype = wintypes.BOOL
kernel32.CreateRemoteThread.argtypes = [
    wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.CreateRemoteThread.restype = wintypes.HANDLE
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.GetExitCodeThread.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel32.GetExitCodeThread.restype = wintypes.BOOL
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetProcAddress.argtypes = [wintypes.HMODULE, ctypes.c_char_p]
kernel32.GetProcAddress.restype = wintypes.LPVOID
kernel32.CreateFileMappingW.argtypes = [
    wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR,
]
kernel32.CreateFileMappingW.restype = wintypes.HANDLE
kernel32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.OpenFileMappingW.restype = wintypes.HANDLE
kernel32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
kernel32.MapViewOfFile.restype = wintypes.LPVOID
kernel32.UnmapViewOfFile.argtypes = [wintypes.LPCVOID]
kernel32.UnmapViewOfFile.restype = wintypes.BOOL

FILE_MAP_ALL_ACCESS = 0x000F001F
INFINITE = 0xFFFFFFFF

SPEEDHACK_DLL_PATH = _bundled_path("native", "speedhack_x64.dll")
SPEEDHACK_DLL_NAME = "speedhack_x64.dll"
SPEEDHACK_SHM_NAME = "Local\\MGS4TrainerSpeedHack"


def _module_loaded(pid: int, module_name: str) -> bool:
    return find_module_base(pid, module_name) is not None


def _inject_dll(pid: int, dll_path: str) -> bool:
    """Injection classique LoadLibraryA + CreateRemoteThread. Handle
    temporaire dedie (droits d'injection non presents dans ProcessHandle
    par defaut), ferme a la fin quel que soit le resultat."""
    access = (PROCESS_CREATE_THREAD | PROCESS_VM_OPERATION | PROCESS_VM_WRITE
              | PROCESS_VM_READ | PROCESS_QUERY_INFORMATION)
    handle = kernel32.OpenProcess(access, False, pid)
    if not handle:
        return False
    try:
        path_bytes = dll_path.encode("mbcs") + b"\x00"
        remote_buf = kernel32.VirtualAllocEx(handle, None, len(path_bytes), MEM_COMMIT, PAGE_READWRITE)
        if not remote_buf:
            return False
        written = ctypes.c_size_t(0)
        ok = kernel32.WriteProcessMemory(handle, remote_buf, path_bytes, len(path_bytes), ctypes.byref(written))
        if not ok:
            kernel32.VirtualFreeEx(handle, remote_buf, 0, 0x8000)  # MEM_RELEASE
            return False
        load_library = kernel32.GetProcAddress(kernel32.GetModuleHandleW("kernel32.dll"), b"LoadLibraryA")
        thread = kernel32.CreateRemoteThread(handle, None, 0, load_library, remote_buf, 0, None)
        if not thread:
            kernel32.VirtualFreeEx(handle, remote_buf, 0, 0x8000)
            return False
        try:
            kernel32.WaitForSingleObject(thread, INFINITE)
            exit_code = wintypes.DWORD(0)
            kernel32.GetExitCodeThread(thread, ctypes.byref(exit_code))
            return exit_code.value != 0  # HMODULE renvoye par LoadLibraryA, 0 = echec
        finally:
            kernel32.CloseHandle(thread)
            kernel32.VirtualFreeEx(handle, remote_buf, 0, 0x8000)
    finally:
        kernel32.CloseHandle(handle)


class SpeedController:
    """Pause (NtSuspendProcess, pas d'injection) + vitesse (injection DLL,
    voir commentaire ci-dessus). Un seul multiplicateur ecrit en continu
    dans la memoire partagee - la DLL, une fois injectee, reste chargee
    et hookee pour toute la duree de vie du process jeu (pas de
    dechargement propre : remettre 1.0 suffit a redonner une vitesse
    normale)."""

    def __init__(self):
        self.injected_pid: int | None = None
        self.shm_view: ctypes.c_void_p | None = None
        self._game_call_lock = threading.Lock()

    def ensure_injected(self, pid: int) -> bool:
        if self.injected_pid == pid and self.shm_view:
            return True
        self.shm_view = None
        self.injected_pid = None
        if not os.path.isfile(SPEEDHACK_DLL_PATH):
            return False
        if not _module_loaded(pid, SPEEDHACK_DLL_NAME):
            if not _inject_dll(pid, SPEEDHACK_DLL_PATH):
                return False
        # Le thread d'initialisation de la DLL (native/speedhack.c) cree
        # la memoire partagee juste apres le retour de LoadLibraryA - pas
        # necessairement instantane, quelques tentatives rapprochees
        # plutot qu'un seul essai.
        for _attempt in range(20):
            handle = kernel32.OpenFileMappingW(FILE_MAP_ALL_ACCESS, False, SPEEDHACK_SHM_NAME)
            if handle:
                # 0 = toute la section (SharedState fait 326 octets depuis
                # octocamo_hidden, 2026-10-03). Sans risque avec une DLL plus
                # ancienne deja injectee : la section est arrondie a une page
                # de 4 Ko, les offsets au-dela de sa structure lisent 0.
                view = kernel32.MapViewOfFile(handle, FILE_MAP_ALL_ACCESS, 0, 0, 0)
                kernel32.CloseHandle(handle)  # la vue mappee reste valide, plus besoin du handle
                if view:
                    self.shm_view = view
                    self.injected_pid = pid
                    # La memoire partagee existe des la creation du
                    # mapping, mais le patch IAT proprement dit (qui
                    # prend un peu de temps, surtout la variante qui
                    # scanne tous les modules) se termine juste apres -
                    # laisse une petite marge pour que patched_mask()/
                    # hit_counts() ne lisent pas "0" par pure course de
                    # vitesse juste apres l'injection (deja observe en
                    # debug, voir notes.md - le hook lui-meme fonctionne
                    # quoi qu'il arrive, seul ce diagnostic pouvait
                    # mentir brievement).
                    for _settle in range(10):
                        if self.patched_mask():
                            break
                        time.sleep(0.05)
                    return True
            time.sleep(0.05)
        return False

    def set_speed(self, multiplier: float) -> bool:
        if not self.shm_view:
            return False
        ctypes.cast(self.shm_view, ctypes.POINTER(ctypes.c_double))[0] = multiplier
        return True

    def _read_u32_at(self, offset: int) -> int | None:
        if not self.shm_view:
            return None
        addr = ctypes.cast(self.shm_view, ctypes.c_void_p).value + offset
        return ctypes.cast(addr, ctypes.POINTER(ctypes.c_uint32))[0]

    def _read_u8_at(self, offset: int) -> int | None:
        if not self.shm_view:
            return None
        addr = ctypes.cast(self.shm_view, ctypes.c_void_p).value + offset
        return ctypes.cast(addr, ctypes.POINTER(ctypes.c_uint8))[0]

    def _write_u32_at(self, offset: int, value: int) -> bool:
        if not self.shm_view:
            return False
        addr = ctypes.cast(self.shm_view, ctypes.c_void_p).value + offset
        ctypes.cast(addr, ctypes.POINTER(ctypes.c_uint32))[0] = value & 0xFFFFFFFF
        return True

    def _write_u8_at(self, offset: int, value: int) -> bool:
        if not self.shm_view:
            return False
        addr = ctypes.cast(self.shm_view, ctypes.c_void_p).value + offset
        ctypes.cast(addr, ctypes.POINTER(ctypes.c_uint8))[0] = value
        return True

    def _read_u64_at(self, offset: int) -> int | None:
        if not self.shm_view:
            return None
        addr = ctypes.cast(self.shm_view, ctypes.c_void_p).value + offset
        return ctypes.cast(addr, ctypes.POINTER(ctypes.c_uint64))[0]

    def set_one_shot_kill(self, enabled: bool) -> bool:
        """Active/desactive le patch de code "one shot kill" (voir
        native/speedhack.c) - injecte comme le reste, donc soumis aux
        memes limites (silencieusement sans effet si le motif d'octets
        n'a pas ete trouve dans cette version du jeu, voir
        damage_hook_installed() pour le diagnostic)."""
        return self._write_u8_at(20, 1 if enabled else 0)

    def set_non_lethal(self, enabled: bool) -> bool:
        """Meme patch de code que one_shot_kill (partage le meme
        trampoline) mais effet oppose : n'applique plus du tout les
        degats normaux, efface aussi un champ voisin ([rdi+0x324]) -
        meme logique que "bRemoveLethal" du script CE original, sens
        exact non confirme individuellement."""
        return self._write_u8_at(23, 1 if enabled else 0)

    def damage_hook_installed(self) -> bool | None:
        """Diagnostic : le patch de code one-shot-kill a-t-il reussi a se
        poser (motif d'octets trouve + redirections dans la portee d'un
        jmp relatif 32 bits) - None si pas injecte, independant de
        one_shot_kill lui-meme (le hook peut etre pose sans etre actif)."""
        val = self._read_u8_at(21)
        return None if val is None else bool(val)

    def damage_hook_error(self) -> int | None:
        """0=succes ou pas encore tente, 1=motif introuvable,
        2=echec allocation trampoline, 3=hors de portee d'un jmp relatif -
        voir install_one_shot_kill_hook dans native/speedhack.c."""
        return self._read_u8_at(22)

    def last_damaged_actor(self) -> int | None:
        """Diagnostic : pointeur brut (rdi) vers le dernier personnage
        touche par le patch de degats, quelle que soit son equipe -
        permet d'inspecter sa structure (ex. [ptr+0x7C]) cote Python pour
        comprendre pourquoi one_shot_kill n'affecte pas certains
        personnages (boss). 0 si aucun coup enregistre depuis l'injection."""
        return self._read_u64_at(24)

    def boss_actor(self) -> int | None:
        """Diagnostic : pointeur brut vers l'acteur boss actif, capture
        par un second hook de lecture seule (voir install_boss_tracker_hook
        dans native/speedhack.c) - les boss ne passent pas par l'instruction
        patchee pour one_shot_kill, d'ou ce point d'injection distinct."""
        return self._read_u64_at(32)

    def boss_hook_installed(self) -> bool | None:
        val = self._read_u8_at(40)
        return None if val is None else bool(val)

    def boss_hook_error(self) -> int | None:
        """Memes codes que damage_hook_error()."""
        return self._read_u8_at(41)

    def boss_actor2(self) -> int | None:
        """Diagnostic : meme idee que boss_actor mais capture au niveau
        de la routine generique de recopie HP vers l'affichage (rcx),
        voir install_boss_tracker_hook2 dans native/speedhack.c."""
        return self._read_u64_at(42)

    def boss_hook2_installed(self) -> bool | None:
        val = self._read_u8_at(50)
        return None if val is None else bool(val)

    def boss_hook2_error(self) -> int | None:
        return self._read_u8_at(51)

    def coord_actor(self) -> int | None:
        """Diagnostic : pointeur brut capture par une routine generique de
        calcul de distance entre deux acteurs (voir install_coord_tracker_hook
        dans native/speedhack.c) - pas forcement toujours le joueur, test
        en cours (2026-09-27)."""
        return self._read_u64_at(52)

    def coord_hook_installed(self) -> bool | None:
        val = self._read_u8_at(60)
        return None if val is None else bool(val)

    def coord_hook_error(self) -> int | None:
        return self._read_u8_at(61)

    def gecko_hook_installed(self) -> bool | None:
        val = self._read_u8_at(62)
        return None if val is None else bool(val)

    def gecko_hook_error(self) -> int | None:
        return self._read_u8_at(63)

    def set_no_reload(self, enabled: bool) -> bool:
        """Patch de code (pas de reassertion en boucle) qui supprime
        l'ecriture du nouveau chargeur apres tir - voir
        install_no_reload_hook dans native/speedhack.c."""
        return self._write_u8_at(64, 1 if enabled else 0)

    def no_reload_hook_installed(self) -> bool | None:
        val = self._read_u8_at(65)
        return None if val is None else bool(val)

    def no_reload_hook_error(self) -> int | None:
        return self._read_u8_at(66)

    def set_no_alerts(self, enabled: bool) -> bool:
        """Court-circuite la fonction qui evalue si Snake doit etre
        repere/alerte - voir install_no_alerts_hook dans
        native/speedhack.c (motif CE "aob No Alerts")."""
        return self._write_u8_at(67, 1 if enabled else 0)

    def no_alerts_hook_installed(self) -> bool | None:
        val = self._read_u8_at(68)
        return None if val is None else bool(val)

    def no_alerts_hook_error(self) -> int | None:
        return self._read_u8_at(69)

    # Codes OctoCamo masques du menu du jeu (16 u32, 0 = libre) - voir
    # install_octocamo_hide_hook dans native/speedhack.c.
    OCTOCAMO_HIDDEN_OFFSET = 260
    OCTOCAMO_HIDDEN_SLOTS = 16

    def read_octocamo_hidden(self) -> list[int]:
        if not self.shm_view:
            return []
        values = [self._read_u32_at(self.OCTOCAMO_HIDDEN_OFFSET + 4 * i) for i in range(self.OCTOCAMO_HIDDEN_SLOTS)]
        return [v for v in values if v]

    def write_octocamo_hidden(self, codes: list[int]) -> bool:
        if not self.shm_view:
            return False
        codes = list(codes)[: self.OCTOCAMO_HIDDEN_SLOTS]
        for i in range(self.OCTOCAMO_HIDDEN_SLOTS):
            self._write_u32_at(self.OCTOCAMO_HIDDEN_OFFSET + 4 * i, codes[i] if i < len(codes) else 0)
        return True

    def octocamo_hide_hook_installed(self) -> bool | None:
        val = self._read_u8_at(324)
        return None if val is None else bool(val)

    # Appel d'une fonction du jeu dans son propre fil, au debut de l'image
    # suivante (rpc_* de install_main_loop_hook) : 4 arguments entiers,
    # renvoie rax ou None (DLL/hook absent, ou jeu fige au-dela du delai).
    def game_call(self, address: int, *args: int, timeout: float = 2.0) -> int | None:
        if not self.shm_view or not self.main_loop_hook_installed():
            return None
        base = ctypes.cast(self.shm_view, ctypes.c_void_p).value
        values = [a & 0xFFFFFFFFFFFFFFFF for a in args] + [0] * (4 - len(args))
        with self._game_call_lock:
            ctypes.cast(base + 344, ctypes.POINTER(ctypes.c_uint64))[0] = address
            for i, value in enumerate(values):
                ctypes.cast(base + 352 + 8 * i, ctypes.POINTER(ctypes.c_uint64))[0] = value
            self._write_u8_at(343, 0)
            self._write_u8_at(342, 1)
            deadline = time.monotonic() + timeout
            while not self._read_u8_at(343):
                if time.monotonic() > deadline:
                    # Annule si pas encore pris (sinon l'appel partira plus tard).
                    self._write_u8_at(342, 0)
                    return None
                time.sleep(0.005)
            return ctypes.cast(base + 384, ctypes.POINTER(ctypes.c_uint64))[0]

    def main_loop_hook_installed(self) -> bool | None:
        val = self._read_u8_at(340)
        return None if val is None else bool(val)

    def set_railgun_force_charge(self, enabled: bool) -> bool:
        """Force chaque tir de Rail Gun au palier de charge max (bits
        24-26 du champ [+0x10C], le meme que l'ID d'arme) - voir
        install_railgun_force_charge_hook dans native/speedhack.c."""
        return self._write_u8_at(213, 1 if enabled else 0)

    def force_charge_hook_installed(self) -> bool | None:
        val = self._read_u8_at(214)
        return None if val is None else bool(val)

    def force_charge_hook_error(self) -> int | None:
        return self._read_u8_at(215)

    def set_alert_mode_override(self, value: int | None) -> bool:
        """Force la variable d'etat d'alerte du jeu a `value`
        (0=Normal, 1=Alerte, 2=Evasion, 3=Prudence - voir
        ALERT_STATE_NAMES) juste avant qu'elle serve aux transitions,
        ou desactive le forcage si `value` est None - voir
        install_alert_override_hook dans native/speedhack.c (motif CE
        "Alert -- Ignore")."""
        return self._write_u32_at(70, 0xFFFF if value is None else value)

    def alert_override_hook_installed(self) -> bool | None:
        val = self._read_u8_at(74)
        return None if val is None else bool(val)

    def alert_override_hook_error(self) -> int | None:
        return self._read_u8_at(75)

    def patched_mask(self) -> int | None:
        """Diagnostic : quels hooks (voir native/speedhack.c, HOOK_*) ont
        reellement ete poses par la DLL injectee - None si pas injecte."""
        return self._read_u32_at(8)

    def hit_counts(self) -> tuple[int, int] | None:
        """Diagnostic : nombre de sites IAT patches (QPC, timeGetTime) -
        peut depasser 1 si plusieurs DLL du jeu importent chacune la
        fonction separement, voir patch_import_everywhere."""
        qpc = self._read_u32_at(12)
        tgt = self._read_u32_at(16)
        if qpc is None or tgt is None:
            return None
        return qpc, tgt

    @staticmethod
    def set_paused(pid: int, paused: bool) -> bool:
        handle = kernel32.OpenProcess(PROCESS_SUSPEND_RESUME, False, pid)
        if not handle:
            return False
        try:
            status = ntdll.NtResumeProcess(handle) if not paused else ntdll.NtSuspendProcess(handle)
            return status == 0
        finally:
            kernel32.CloseHandle(handle)


class MGS4Live:
    def __init__(self):
        self.proc: ProcessHandle | None = None
        self.pid: int | None = None
        self.base: int | None = None
        self.linkvarbuf: int | None = None
        self.varbuf: int | None = None
        self.sane = False
        self.status = tr("status.not_connected")
        self.speed = SpeedController()
        self._equip_lock = threading.Lock()  # un equipement en direct a la fois

    def attach(self) -> bool:
        self.detach()
        pid = find_pid(PROCESS_NAME)
        if pid is None:
            self.status = tr("status.process_not_found", process=PROCESS_NAME)
            return False
        self.pid = pid
        base = find_module_base(pid, PROCESS_NAME)
        if base is None:
            self.status = tr("status.module_not_found")
            return False
        try:
            self.proc = ProcessHandle(pid)
            self.base = base
            self.linkvarbuf = struct.unpack("<Q", self.proc.read_bytes(base + LINKVARBUF_POINTER_RVA, 8))[0]
            self.varbuf = struct.unpack("<Q", self.proc.read_bytes(base + VARBUF_POINTER_RVA, 8))[0]
            if self.varbuf == 0:
                self.status = tr("status.null_varbuf")
                return False
        except OSError as e:
            self.status = str(e)
            return False
        return self._sanity_check()

    def _sanity_check(self) -> bool:
        try:
            for item_id in sorted(mgs4save.STRUCTURAL_ITEM_IDS):
                raw = self.read_item(item_id)
                if raw != 0:
                    self.sane = False
                    self.status = tr("status.check_failed", item_id=f"{item_id:#04x}", raw=raw)
                    return False
        except OSError as e:
            self.sane = False
            self.status = tr("status.check_error", error=e)
            return False
        self.sane = True
        self.status = tr("status.connected", varbuf=f"{self.varbuf:#x}")
        return True

    def detach(self):
        if self.proc:
            self.proc.close()
            self.proc = None
        self.pid = None
        self.base = None
        self.linkvarbuf = None
        self.varbuf = None
        self.sane = False

    def check_alive(self) -> bool:
        """A appeler avant chaque rafraichissement : le statut ne se
        remettait jamais a jour tout seul si le jeu etait ferme apres une
        connexion reussie (les lectures echouent silencieusement, "sane"
        restait vrai indefiniment). Fait une lecture legere pour verifier
        que le process repond toujours ; sinon se detache proprement et
        met a jour le statut."""
        if not self.connected:
            return False
        try:
            self.proc.read_bytes(self.base, 2)
        except OSError:
            self.detach()
            self.status = tr("status.process_lost", process=PROCESS_NAME)
            return False
        return True

    @property
    def connected(self) -> bool:
        return self.proc is not None and self.varbuf is not None

    def set_game_speed(self, multiplier: float) -> bool:
        """multiplier=1.0 vitesse normale, <1.0 ralenti, >1.0 accelere -
        voir SpeedController. Injecte la DLL au premier appel (paresseux,
        pas au moment de la connexion : inutile de prendre ce risque tant
        que l'utilisateur ne touche pas au curseur)."""
        if not (self.connected and self.sane and self.pid):
            return False
        if not self.speed.ensure_injected(self.pid):
            return False
        return self.speed.set_speed(multiplier)

    def set_paused(self, paused: bool) -> bool:
        if not (self.connected and self.sane and self.pid):
            return False
        return SpeedController.set_paused(self.pid, paused)

    def set_one_shot_kill(self, enabled: bool) -> bool:
        """Injecte la DLL au premier appel (paresseux, comme set_game_speed) -
        voir SpeedController.set_one_shot_kill et native/speedhack.c."""
        if not (self.connected and self.sane and self.pid):
            return False
        if not self.speed.ensure_injected(self.pid):
            return False
        return self.speed.set_one_shot_kill(enabled)

    def one_shot_kill_hook_installed(self) -> bool | None:
        return self.speed.damage_hook_installed()

    def set_non_lethal(self, enabled: bool) -> bool:
        if not (self.connected and self.sane and self.pid):
            return False
        if not self.speed.ensure_injected(self.pid):
            return False
        return self.speed.set_non_lethal(enabled)

    def one_shot_kill_hook_error(self) -> int | None:
        return self.speed.damage_hook_error()

    def gecko_hook_installed(self) -> bool | None:
        """Diagnostic uniquement, voir install_gecko_one_shot_kill_hook
        dans native/speedhack.c - hook separe pour les Gecko, partage le
        flag one_shot_kill mais pas non_lethal (n'a pas de sens pour un
        robot)."""
        return self.speed.gecko_hook_installed()

    def gecko_hook_error(self) -> int | None:
        return self.speed.gecko_hook_error()

    def set_no_reload(self, enabled: bool) -> bool:
        """Injecte la DLL au premier appel (paresseux, comme
        set_game_speed) - voir SpeedController.set_no_reload."""
        if not (self.connected and self.sane and self.pid):
            return False
        if not self.speed.ensure_injected(self.pid):
            return False
        return self.speed.set_no_reload(enabled)

    def no_reload_hook_installed(self) -> bool | None:
        return self.speed.no_reload_hook_installed()

    def no_reload_hook_error(self) -> int | None:
        return self.speed.no_reload_hook_error()

    def set_no_alerts(self, enabled: bool) -> bool:
        """Injecte la DLL au premier appel (paresseux) - voir
        SpeedController.set_no_alerts."""
        if not (self.connected and self.sane and self.pid):
            return False
        if not self.speed.ensure_injected(self.pid):
            return False
        return self.speed.set_no_alerts(enabled)

    def no_alerts_hook_installed(self) -> bool | None:
        return self.speed.no_alerts_hook_installed()

    def no_alerts_hook_error(self) -> int | None:
        return self.speed.no_alerts_hook_error()

    def set_railgun_force_charge(self, enabled: bool) -> bool:
        """Injecte la DLL au premier appel (paresseux) - voir
        SpeedController.set_railgun_force_charge."""
        if not (self.connected and self.sane and self.pid):
            return False
        if not self.speed.ensure_injected(self.pid):
            return False
        return self.speed.set_railgun_force_charge(enabled)

    def force_charge_hook_installed(self) -> bool | None:
        return self.speed.force_charge_hook_installed()

    def force_charge_hook_error(self) -> int | None:
        return self.speed.force_charge_hook_error()

    def set_alert_mode_override(self, value: int | None) -> bool:
        """Injecte la DLL au premier appel (paresseux) - voir
        SpeedController.set_alert_mode_override."""
        if not (self.connected and self.sane and self.pid):
            return False
        if not self.speed.ensure_injected(self.pid):
            return False
        return self.speed.set_alert_mode_override(value)

    def alert_override_hook_installed(self) -> bool | None:
        return self.speed.alert_override_hook_installed()

    def alert_override_hook_error(self) -> int | None:
        return self.speed.alert_override_hook_error()

    def last_damaged_actor(self) -> int | None:
        """Diagnostic uniquement, voir SpeedController.last_damaged_actor."""
        return self.speed.last_damaged_actor()

    def boss_actor(self) -> int | None:
        """Diagnostic uniquement, voir SpeedController.boss_actor."""
        return self.speed.boss_actor()

    def boss_hook_installed(self) -> bool | None:
        return self.speed.boss_hook_installed()

    def boss_hook_error(self) -> int | None:
        return self.speed.boss_hook_error()

    def boss_actor2(self) -> int | None:
        return self.speed.boss_actor2()

    def boss_hook2_installed(self) -> bool | None:
        return self.speed.boss_hook2_installed()

    def boss_hook2_error(self) -> int | None:
        return self.speed.boss_hook2_error()

    def boss_hp(self) -> int | None:
        """Vie du boss actuellement suivi (boss_actor2, capture par
        install_boss_tracker_hook2) - None si aucun boss actif. Meme
        offset +0x314 que la vie des ennemis standards, mais alimente par
        un chemin de code totalement different (les boss ne passent pas
        par l'instruction patchee pour one_shot_kill, voir notes.md)."""
        addr = self.boss_actor2()
        if not addr:
            return None
        return struct.unpack("<i", self.proc.read_bytes(addr + 0x314, 4))[0]

    def set_boss_hp(self, value: int) -> bool:
        """Ecrit directement la vie du boss actuellement suivi. Utilise
        en continu (pas via un hook de code) car on n'a pas trouve
        l'instruction de degats propre aux boss - confirme fonctionnel en
        jeu : forcer 0 en boucle fait progresser/tomber le boss (2026-09-26)."""
        addr = self.boss_actor2()
        if not addr:
            return False
        self.proc.write_bytes(addr + 0x314, struct.pack("<i", value))
        return True

    def coord_actor(self) -> int | None:
        """Diagnostic uniquement, voir SpeedController.coord_actor."""
        return self.speed.coord_actor()

    def player_position(self) -> tuple[float, float, float] | None:
        """Position (X, Y, Z, floats) de l'acteur suivi par coord_actor -
        confirme etre Snake par teleportation reelle en jeu (2026-09-27,
        voir notes.md) : pointeur stable pendant le deplacement, ecriture
        de +0x10/+0x14/+0x18 deplace bien le joueur. Y semble etre la
        hauteur (le jeu annule une position invalide sous le sol), X/Z le
        plan horizontal en coordonnees absolues (pas relatives a
        l'orientation du joueur). Injecte la DLL au premier appel
        (paresseux, comme set_game_speed) - sans ca coord_actor() renvoie
        toujours None si aucune autre fonctionnalite n'a deja declenche
        l'injection."""
        if not (self.connected and self.sane and self.pid):
            return None
        if not self.speed.ensure_injected(self.pid):
            return None
        addr = self.coord_actor()
        if not addr:
            return None
        return struct.unpack("<fff", self.proc.read_bytes(addr + 0x10, 12))

    def set_player_position(self, x: float, y: float, z: float) -> bool:
        if not (self.connected and self.sane and self.pid):
            return False
        if not self.speed.ensure_injected(self.pid):
            return False
        addr = self.coord_actor()
        if not addr:
            return False
        self.proc.write_bytes(addr + 0x10, struct.pack("<fff", x, y, z))
        return True

    def raven_hp(self) -> int | None:
        """Vie de Raging Raven (offsets differents de Laughing Octopus,
        boss_hp/boss_stamina) : boss_actor+0xB0, confirme fonctionnel en
        jeu (2026-09-27) - meme pointeur que boss_actor() (hook generique
        "Bosses 1/2", pas boss_actor2 qui ne s'est jamais declenche pour
        ce boss). Les deux groupes (voir set_raven_hp) restent synchronises
        par le jeu lui-meme, donc la lecture d'un seul suffit."""
        addr = self.boss_actor()
        if not addr:
            return None
        return struct.unpack("<i", self.proc.read_bytes(addr + 0xB0, 4))[0]

    # Deuxieme groupe d'adresses (vie/stamina), separe de boss_actor, a un
    # ecart fixe mais negatif par rapport a lui - trouve par scan exact
    # (2026-09-27). Ecrire UNIQUEMENT dans boss_actor+0xB0/+0xE8 n'avait
    # aucun effet durable (le jeu re-synchronisait depuis ce second groupe
    # au coup suivant, jamais touche) - confirme qu'il faut ecrire les DEUX
    # pour que ca tienne reellement en jeu.
    RAVEN_SECOND_GROUP_OFFSET = -0x1576C

    # Crying Wolf : meme principe (+0xB0/+0xE8 confirmes fonctionnels en
    # lecture, mais ecrire uniquement la n'a pas suffi non plus) - second
    # groupe repere par elimination (candidat tombe a 0 pile au moment de
    # sa mort, 2026-09-27) mais PAS confirme causalement (combat termine
    # avant de pouvoir tester une ecriture). Ecart trouve : -0xB09C par
    # rapport a boss_actor - a valider sur un prochain combat avant de
    # cabler en dur comme RAVEN_SECOND_GROUP_OFFSET (l'ecart semble
    # specifique a chaque boss, pas une constante universelle : celui de
    # Raging Raven ne s'appliquait pas du tout ici).
    CRYING_WOLF_SECOND_GROUP_OFFSET_UNCONFIRMED = -0xB09C

    def set_raven_hp(self, value: int) -> bool:
        addr = self.boss_actor()
        if not addr:
            return False
        self.proc.write_bytes(addr + 0xB0, struct.pack("<i", value))
        self.proc.write_bytes(addr + self.RAVEN_SECOND_GROUP_OFFSET, struct.pack("<i", value))
        return True

    def raven_stamina(self) -> int | None:
        """Stamina de Raging Raven : boss_actor+0xE8, voir raven_hp."""
        addr = self.boss_actor()
        if not addr:
            return None
        return struct.unpack("<i", self.proc.read_bytes(addr + 0xE8, 4))[0]

    def set_raven_stamina(self, value: int) -> bool:
        addr = self.boss_actor()
        if not addr:
            return False
        self.proc.write_bytes(addr + 0xE8, struct.pack("<i", value))
        self.proc.write_bytes(addr + self.RAVEN_SECOND_GROUP_OFFSET + 8, struct.pack("<i", value))
        return True

    # Detection automatique du boss actif pour "Un coup, un mort" cote
    # boss (VitalsTab._reassert_boss_staged_damage) : deux boss testes a
    # ce jour, deux jeux d'offsets differents selon lequel des deux hooks
    # de tracking se declenche (2026-09-27) - Laughing Octopus passe par
    # boss_actor2 (+0x314/+0x31C), Raging Raven seulement par boss_actor
    # (+0xB0/+0xE8, boss_actor2 ne s'est jamais declenche pour elle).
    # Pas de mapping par niveau/acte (champ non mirroré de façon
    # exploitable dans varbuf, teste et abandonne) - on essaie juste les
    # deux hooks dans l'ordre et on garde celui qui repond.

    def active_boss_addr(self) -> int | None:
        return self.boss_actor2() or self.boss_actor()

    def active_boss_kind(self) -> str | None:
        """"octopus" (boss_actor2, connu multi-phases - voir notes.md,
        le forcage direct a 0 y a deja bloque un combat) ou "raven"
        (boss_actor seul, pas de phase connue - 2026-09-27) - permet de
        varier le comportement de _reassert_boss_staged_damage sans
        avoir besoin d'identifier le niveau/boss par son nom."""
        if self.boss_actor2():
            return "octopus"
        if self.boss_actor():
            return "raven"
        return None

    def active_boss_hp(self) -> int | None:
        return self.boss_hp() if self.boss_actor2() else self.raven_hp()

    def set_active_boss_hp(self, value: int) -> bool:
        return self.set_boss_hp(value) if self.boss_actor2() else self.set_raven_hp(value)

    def active_boss_stamina(self) -> int | None:
        return self.boss_stamina() if self.boss_actor2() else self.raven_stamina()

    def set_active_boss_stamina(self, value: int) -> bool:
        return self.set_boss_stamina(value) if self.boss_actor2() else self.set_raven_stamina(value)

    def boss_stamina(self) -> int | None:
        """Stamina/alerte du boss suivi (+0x31C) - mecanisme distinct de
        la vie (+0x314), constate actif sur au moins une phase (2026-09-26,
        ou tirer a balles reelles ne faisait pas baisser la vie mais les
        munitions non letales faisaient bien baisser la stamina - meme
        logique "assommer" que les soldats standards de MGS4). Offset
        corrige le meme jour : +0x320 (documente par le CE table communautaire
        comme "+31C+4") ne bougeait jamais en temps reel malgre des degats
        reels visibles - un scan par valeur exacte a montre que c'est
        +0x31C qui suit vraiment les degats, +0x320 restant fige (probable
        copie/reference statique voisine)."""
        addr = self.boss_actor2()
        if not addr:
            return None
        return struct.unpack("<i", self.proc.read_bytes(addr + 0x31C, 4))[0]

    def set_boss_stamina(self, value: int) -> bool:
        addr = self.boss_actor2()
        if not addr:
            return False
        self.proc.write_bytes(addr + 0x31C, struct.pack("<i", value))
        return True

    def read_item(self, item_id: int) -> int:
        return struct.unpack("<H", self.proc.read_bytes(self.base + item_state_rva(item_id), 2))[0]

    def write_item(self, item_id: int, value: int) -> None:
        self.proc.write_bytes(self.base + item_state_rva(item_id), struct.pack("<H", value & 0xFFFF))

    def read_weapon(self, weapon_id: int) -> int:
        return struct.unpack("<H", self.proc.read_bytes(self.base + weapon_state_rva(weapon_id), 2))[0]

    def write_weapon(self, weapon_id: int, value: int) -> None:
        self.proc.write_bytes(self.base + weapon_state_rva(weapon_id), struct.pack("<H", value & 0xFFFF))

    def read_weapon_ammo(self, weapon_id: int) -> int | None:
        """None = adresse munitions pas encore trouvee pour cette arme
        (voir CONFIRMED_WEAPON_AMMO_RVAS - a completer arme par arme par
        scan memoire, meme methode que pour l'etat/possession)."""
        rva = CONFIRMED_WEAPON_AMMO_RVAS.get(weapon_id)
        if rva is None:
            return None
        return struct.unpack("<H", self.proc.read_bytes(self.base + rva + MODULE_PATCH_SHIFT, 2))[0]

    def write_weapon_ammo(self, weapon_id: int, value: int) -> bool:
        """Retourne False sans rien ecrire si l'adresse munitions de cette
        arme n'est pas encore connue."""
        rva = CONFIRMED_WEAPON_AMMO_RVAS.get(weapon_id)
        if rva is None:
            return False
        self.proc.write_bytes(self.base + rva + MODULE_PATCH_SHIFT, struct.pack("<H", value & 0xFFFF))
        return True

    def read_weapon_magazine(self, weapon_id: int) -> int:
        """Munitions dans le chargeur (distinct de la reserve ci-dessus -
        se vide en tirant, declenche le rechargement a 0). Trouve le
        2026-09-26 par scan exact (7->5->3 confirme par l'utilisateur en
        tirant sur l'Operator, 4 candidats restants dont un seul dans la
        table d'etat des armes deja connue) : meme table que weapon_state_
        rva (WEAPON_MAGAZINE_OFFSET octets plus loin dans le meme struct
        par arme, stride 0x50) - formule non re-testee individuellement
        sur chaque arme, extrapolee de la formule d'etat deja confirmee
        fiable pour toutes."""
        return struct.unpack("<H", self.proc.read_bytes(self.base + weapon_state_rva(weapon_id)
                                                          + WEAPON_MAGAZINE_OFFSET, 2))[0]

    def write_weapon_magazine(self, weapon_id: int, value: int) -> None:
        self.proc.write_bytes(self.base + weapon_state_rva(weapon_id) + WEAPON_MAGAZINE_OFFSET,
                               struct.pack("<H", value & 0xFFFF))

    def read_weapon_magazine_max(self, weapon_id: int) -> int:
        return struct.unpack("<H", self.proc.read_bytes(self.base + weapon_state_rva(weapon_id)
                                                          + WEAPON_MAGAZINE_MAX_OFFSET, 2))[0]

    def read_special_item_equipped(self) -> int:
        return struct.unpack("<H", self.proc.read_bytes(self.base + special_item_equipped_rva(), 2))[0]

    def write_special_item_equipped(self, item_id: int) -> None:
        self.proc.write_bytes(self.base + special_item_equipped_rva(), struct.pack("<H", item_id & 0xFFFF))

    def read_stat(self, name: str) -> int:
        """Lit un champ de mgs4save.STATS via linkvarbuf (meme offset que
        le fichier de save, format u16 ou u32 selon l'entree). Fiabilite
        en lecture ET ecriture confirmee individuellement seulement pour
        drebin_actuel (2026-09-23) - les autres champs sont exposes pour
        exploration/test, pas encore verifies un par un."""
        offset, fmt = mgs4save.STATS[name]
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self.proc.read_bytes(self.linkvarbuf + offset, size))[0]

    def write_stat(self, name: str, value: int) -> None:
        offset, fmt = mgs4save.STATS[name]
        size = struct.calcsize(fmt)
        max_value = (1 << (size * 8)) - 1
        self.proc.write_bytes(self.linkvarbuf + offset, struct.pack(fmt, value & max_value))

    def read_vital(self, name: str) -> int:
        offset, _max_offset, size, _fixed_max = VITALS[name]
        return int.from_bytes(self.proc.read_bytes(self.linkvarbuf + offset, size), "little")

    def write_vital(self, name: str, value: int) -> None:
        offset, _max_offset, size, _fixed_max = VITALS[name]
        max_value = (1 << (size * 8)) - 1
        self.proc.write_bytes(self.linkvarbuf + offset, (value & max_value).to_bytes(size, "little"))

    def read_vital_max(self, name: str) -> int:
        """Valeur max (live si un offset dedie existe, sinon la borne fixe
        de VITALS - ex. Stress, toujours 0-1000)."""
        _offset, max_offset, size, fixed_max = VITALS[name]
        if max_offset is None:
            return fixed_max
        return int.from_bytes(self.proc.read_bytes(self.linkvarbuf + max_offset, size), "little")

    def read_vital_percent(self, name: str) -> float:
        maxi = self.read_vital_max(name)
        return (self.read_vital(name) / maxi * 100) if maxi else 0.0

    # OctoCamo (2026-10-03, voir mgs4save.OCTOCAMO_TABLE_OFFSET) : memes
    # offsets dans linkvarbuf que dans MGS4.SAV. Un motif de la table de 20
    # entrees y figure par son code (24 bits + octet de drapeaux), avec 6
    # caracteristiques (mots de 16 bits, 1000 chacune sur toutes les saves)
    # dans des tables paralleles indexees par emplacement. Seuls ces 6
    # motifs y vivent (les 14 autres sont charges par le jeu, hors save) :
    # code -> (emplacement habituel, drapeaux). Cadavre : bit 0x10 =
    # "nouveau", comme au deblocage reel.
    OCTOCAMO_STAT_TABLES = (0x4CB8, 0x4D38, 0x4DB8, 0x4E38, 0x4EB8, 0x4F38)
    OCTOCAMO_EDITABLE = {
        mgs4save.OCTOCAMO_CODES["Olive"]: (11, 0x02),
        mgs4save.OCTOCAMO_CODES["Tigré"]: (12, 0x02),
        mgs4save.OCTOCAMO_CODES["Forêt"]: (13, 0x02),
        mgs4save.OCTOCAMO_CODES["3 Couleurs Désert"]: (14, 0x02),
        mgs4save.OCTOCAMO_CODES["Marpat"]: (15, 0x02),
        mgs4save.OCTOCAMO_CODES["Cadavre"]: (16, 0x12),
    }
    OCTOCAMO_LOCKED = 65535  # meme convention que les FaceCamo/Gilets (binary_lock_value)
    # Bonus lies au compte/PC (2026-10-03) : le menu OctoCamo (mgs4+4F3789)
    # n'ajoute Dore/Precommande que si ces octets valent 1, positionnes au
    # demarrage (Precommande = possession du contenu Steam 3397310 ; Dore =
    # reglage charge au demarrage, tres probablement le bonus Master
    # Collection Vol.1 du lanceur). Lecture seule : les forcer reviendrait
    # a contourner un contenu payant. RVA de la version actuelle, sans
    # MODULE_PATCH_SHIFT.
    OCTOCAMO_ACCOUNT_FLAG_RVAS = {
        mgs4save.OCTOCAMO_CODES["Précommande"]: 0x1D7AB30,
        mgs4save.OCTOCAMO_CODES["Doré"]: 0x1D7AB31,
    }

    def read_equipped_octocamo_code(self) -> int:
        raw = self.proc.read_bytes(self.linkvarbuf + mgs4save.OCTOCAMO_EQUIPPED_OFFSET, 4)
        return struct.unpack("<I", raw)[0] & 0xFFFFFF

    def _octocamo_table(self) -> list[int]:
        raw = self.proc.read_bytes(self.linkvarbuf + mgs4save.OCTOCAMO_TABLE_OFFSET,
                                   4 * mgs4save.OCTOCAMO_TABLE_SLOTS)
        return list(struct.unpack(f"<{mgs4save.OCTOCAMO_TABLE_SLOTS}I", raw))

    def read_octocamo_state(self, code: int) -> int:
        """1 (obtenu) ou OCTOCAMO_LOCKED. Motifs de la partie : presence
        dans la table ; Dore/Precommande : octet du jeu (lie au compte) ;
        tous les autres sont donnes d'office par le menu du jeu."""
        if code in self.OCTOCAMO_EDITABLE:
            present = any((entry & 0xFFFFFF) == code for entry in self._octocamo_table())
            return 1 if present else self.OCTOCAMO_LOCKED
        rva = self.OCTOCAMO_ACCOUNT_FLAG_RVAS.get(code)
        if rva is not None:
            return 1 if self.proc.read_bytes(self.base + rva, 1)[0] else self.OCTOCAMO_LOCKED
        # Motifs ajoutes d'office par le menu : "verrouille" = masque par le
        # hook du trainer (install_octocamo_hide_hook), effet de session.
        return self.OCTOCAMO_LOCKED if code in self.speed.read_octocamo_hidden() else 1

    # Emplacements 0-9 de la table : motifs captures sur une surface puis
    # memorises par le joueur (categorie 1, ex. "Beton" -> 114C3A3E avec
    # ses propres caracteristiques 350/350/350/500/500/500). Les
    # emplacements 10-19 sont les motifs obtenus (categorie 2).
    OCTOCAMO_SAVED_SLOTS = range(10)

    def read_octocamo_slot_code(self, slot: int) -> int:
        return self._octocamo_table()[slot] & 0xFFFFFF

    def read_octocamo_slot_state(self, slot: int) -> int:
        return 1 if self._octocamo_table()[slot] else self.OCTOCAMO_LOCKED

    def write_octocamo_slot_state(self, slot: int, value: int) -> None:
        """Verrouille = oublie le motif memorise (vide l'emplacement et ses
        caracteristiques). Obtenu ne fait rien : un motif capture ne
        s'invente pas."""
        if value != self.OCTOCAMO_LOCKED or slot not in self.OCTOCAMO_SAVED_SLOTS:
            return
        for table_offset in self.OCTOCAMO_STAT_TABLES:
            self.proc.write_bytes(self.linkvarbuf + table_offset + slot * 2, struct.pack("<H", 0))
        self.proc.write_bytes(self.linkvarbuf + mgs4save.OCTOCAMO_TABLE_OFFSET + slot * 4, struct.pack("<I", 0))

    # Visage porte : linkvarbuf+0xB27 = indice interne du jeu (0 = aucun),
    # +0xB26 = autre parametre de la meme fonction, repasse tel quel.
    # Indices releves en equipant chaque visage dans le menu (2026-10-03) :
    # ID d'objet -> indice. 3 n'est utilise par aucun visage du menu ;
    # 16/17 = Dore / FaceCamo Dore (bonus lies au compte, non equipables
    # depuis le trainer).
    FACECAMO_EQUIP_OFFSET = 0xB27
    FACECAMO_EQUIP_INDEX = {
        0x1F: 1,   # FaceCamo
        0x20: 2,   # Jeune Snake
        0x22: 4,   # Laughing Beauty
        0x23: 5,   # Raging Beauty
        0x24: 6,   # Crying Beauty
        0x21: 7,   # Screaming Beauty
        0x25: 8,   # Jeune Snake avec bandana
        0x28: 9,   # Big Boss
        0x27: 10,  # Campbell
        0x26: 11,  # Otacon
        0x29: 12,  # Drebin
        0x2A: 13,  # MGS1
        0x2B: 14,  # Raiden - Visiere fermee
        0x2C: 15,  # Raiden - Visiere ouverte
    }

    def read_equipped_facecamo_id(self) -> int | None:
        index = self.proc.read_bytes(self.linkvarbuf + self.FACECAMO_EQUIP_OFFSET, 1)[0]
        return next((i for i, idx in self.FACECAMO_EQUIP_INDEX.items() if idx == index), None)

    # Gilet porte : linkvarbuf+0xB3C = ID d'objet - 0x2D (Kaki 0 ... Brun 9 ;
    # 0, 1, 2 et 7 confirmes en jeu le 2026-10-03). Le jeu
    # (9004E0, appele a chaque image) repeint le gilet d'apres cet octet :
    # il suffit de l'ecrire, effet immediat. La valeur 10 (remise a 0 par
    # le jeu dans certains cas, tres probablement le gilet Dore lie au
    # compte) n'est pas proposee.
    VEST_EQUIP_OFFSET = 0xB3C
    VEST_FIRST_ID = 0x2D
    VEST_EQUIP_IDS = range(0x2D, 0x37)

    def read_equipped_vest_id(self) -> int | None:
        index = self.proc.read_bytes(self.linkvarbuf + self.VEST_EQUIP_OFFSET, 1)[0]
        item_id = self.VEST_FIRST_ID + index
        return item_id if item_id in self.VEST_EQUIP_IDS else None

    def equip_vest(self, item_id: int) -> bool:
        if not (self.connected and self.sane) or item_id not in self.VEST_EQUIP_IDS:
            return False
        self.proc.write_bytes(self.linkvarbuf + self.VEST_EQUIP_OFFSET, bytes([item_id - self.VEST_FIRST_ID]))
        return True

    # Arme en main (2026-10-03) : linkvarbuf+0xAC4 = ID de l'arme equipee
    # (u16), +0xACC = la precedente. set_weapon (6D2D0, rcx = entree de
    # l'arme dans la table du jeu, mgs4+1D82580 + ID*0x50 - meme table que
    # weapon_state_rva) ecrit les deux et marque l'arme comme changee :
    # Snake la prend en main tout de suite.
    # Seules les armes du sous-menu rapide ont leur modele charge : nombre
    # de places en +0xA9C (5), ID u16 en +0xAA4 (8 places en memoire, mais
    # le menu plante a l'affichage au-dela de 5). Equiper une arme absente
    # du sous-menu a plante le jeu (M4). On fait donc comme le menu pause :
    # jeu en pause, l'arme est placee dans une place libre du sous-menu,
    # sinon dans la DERNIERE place (choix de l'utilisateur : les autres ne
    # sont jamais touchees), preload_weapons (6D490 : compare le sous-menu
    # aux modeles charges, charge/decharge la difference), attente, puis
    # set_weapon et reprise.
    WEAPON_EQUIP_OFFSET = 0xAC4
    WEAPON_QUICK_COUNT_OFFSET = 0xA9C
    WEAPON_QUICK_IDS_OFFSET = 0xAA4
    WEAPON_TABLE_RVA = 0x1D82580
    WEAPON_TABLE_STRIDE = 0x50
    # preload_weapons est synchrone : il demande le chargement (128DB0),
    # boucle sur 129090 jusqu'a la fin puis active le modele (128BD0)
    # avant de rendre la main. Juste quelques images de marge ensuite.
    WEAPON_LOAD_WAIT = 0.1  # secondes de pause apres le chargement
    WEAPON_RELEASE_WAIT = 0.3  # secondes (jeu non fige) pour lacher l'arme en main
    WEAPON_LIVE_FUNCS = {
        "set_weapon": (0x6D2D0, "33c0488bd14885c9"),
        "preload_weapons": (0x6D490, "40554883ec20488d6c2420"),
    }

    def read_quick_weapon_ids(self) -> list[int]:
        """Sous-menu rapide des armes, places vides comprises (0)."""
        count = struct.unpack("<i", self.proc.read_bytes(self.linkvarbuf + self.WEAPON_QUICK_COUNT_OFFSET, 4))[0]
        if not 0 < count <= 8:
            return []
        raw = self.proc.read_bytes(self.linkvarbuf + self.WEAPON_QUICK_IDS_OFFSET, 2 * count)
        return list(struct.unpack(f"<{count}h", raw))

    def read_equipped_weapon_id(self) -> int:
        return struct.unpack("<H", self.proc.read_bytes(self.linkvarbuf + self.WEAPON_EQUIP_OFFSET, 2))[0]

    def read_equippable_weapon_ids(self) -> list[int]:
        """Armes possedees (etat 1 ou 2 du tableau d'etat) : equipables,
        quitte a passer par la derniere place du sous-menu."""
        return [i for i in range(1, mgs4save.WEAPON_STATE_COUNT) if self.read_weapon(i) in (1, 2)]

    def equip_weapon(self, weapon_id: int) -> bool:
        if not (self.connected and self.sane) or weapon_id not in self.read_equippable_weapon_ids():
            return False
        return self._start_equip(self._equip_weapon_live, weapon_id)

    def _equip_weapon_live(self, weapon_id: int) -> bool:
        funcs = self._live_funcs(self.WEAPON_LIVE_FUNCS)
        model_funcs = self._live_funcs(self.MODEL_LIVE_FUNCS)
        quick = self.read_quick_weapon_ids()
        if funcs is None or model_funcs is None or not quick:
            return False
        call = self.speed.game_call
        entry = self.base + self.WEAPON_TABLE_RVA + weapon_id * self.WEAPON_TABLE_STRIDE
        if weapon_id in quick:
            return call(funcs["set_weapon"], entry) is not None
        slot = quick.index(0) if 0 in quick else len(quick) - 1
        # L'arme remplacee est en main : preload_weapons dechargerait le
        # modele tenu et le jeu plante (vu 2 fois le 2026-10-03, y compris
        # en passant d'abord a "aucune arme" jeu en pause : le modele en
        # main ne change qu'a la mise a jour de Snake, figee par la pause).
        # On passe donc d'abord a "aucune arme" jeu NON fige, et on laisse
        # quelques images a Snake pour lacher l'arme.
        if quick[slot] and quick[slot] == self.read_equipped_weapon_id():
            if call(funcs["set_weapon"], self.base + self.WEAPON_TABLE_RVA) is None:
                return False
            time.sleep(self.WEAPON_RELEASE_WAIT)
        state = call(model_funcs["state"])
        if state is None:
            return False
        pause = not (state & 6)
        if pause:
            call(model_funcs["pause_set"], self.MODEL_PAUSE_FLAG)
        try:
            self.proc.write_bytes(self.linkvarbuf + self.WEAPON_QUICK_IDS_OFFSET + 2 * slot,
                                  struct.pack("<h", weapon_id))
            if call(funcs["preload_weapons"], timeout=10.0) is None:
                return False
            time.sleep(self.WEAPON_LOAD_WAIT)
            ok = call(funcs["set_weapon"], entry) is not None
            time.sleep(0.1)
            return ok
        finally:
            if pause:
                call(model_funcs["pause_clear"], self.MODEL_PAUSE_FLAG)

    # Tenue (linkvarbuf+0xB26) et visage (+0xB27) en direct, sans menu
    # (2026-10-03). Les deux passent par la meme fonction du jeu,
    # equip_model (8FCC70, ecx = tenue, edx = visage), appelee par le menu
    # (4F6BF0) : elle n'agit que jeu en pause et lance le rechargement du
    # modele ([gestionnaire+0x108] = 2, decompte par image jusqu'a -1, puis
    # chargement suivi par les bits 0-1 de [gestionnaire+0xC0]). Si Snake
    # est mis a jour pendant ce rechargement, le jeu plante : on met donc
    # le jeu en pause avec sa propre fonction (pause_set(2), comme le menu
    # mais sans l'afficher), on equipe, on attend la fin du rechargement
    # (~0,1-0,2 s) puis pause_clear(2). Si un menu est deja ouvert, on n'y
    # touche pas. Comme le menu, le visage passe a 0 si la tenue ne
    # l'autorise pas (8FCEF0(motif, tenue, visage) == 0, ex. Altair).
    MODEL_MANAGER_PTR_RVA = 0x23EB5F58
    MODEL_LIVE_FUNCS = {
        "state": (0x73FDC0, "8b05????????c3"),
        "pause_set": (0x73FE60, "4883ec288b05????????8bd183e220"),
        "pause_clear": (0x73FDD0, "4883ec28448b0d????????4485c9"),
        "equip": (0x8FCC70, "40535741554883ec204c8b2d"),
        "face_allowed": (0x8FCEF0, "4883ec48488b05"),
    }
    MODEL_PAUSE_FLAG = 2
    OUTFIT_EQUIP_OFFSET = 0xB26
    # ID d'objet -> valeur de B26, verifies en jeu (2026-10-03). 0 =
    # combinaison OctoCamo (sans objet). Le menu ne propose les deguisements
    # de rebelle et de civil que dans leur acte, mais les forcer ailleurs
    # fonctionne (teste hors de leur acte).
    OUTFIT_EQUIP_INDEX = {
        0x1A: 1,  # Deguisement de milicien du Moyen-Orient
        0x1B: 2,  # Deguisement de rebelle d'Amerique du Sud
        0x1C: 3,  # Deguisement civil de l'Europe de l'Est
        0x1E: 4,  # Costume de Snake
        0x1D: 7,  # Costume d'Altair
    }

    def _live_funcs(self, table: dict[str, tuple[int, str]]) -> dict[str, int] | None:
        """Adresses des fonctions du jeu de la table, ou None si l'une
        n'a pas les octets attendus (autre version du jeu)."""
        funcs = {}
        for name, (rva, signature) in table.items():
            expected = signature.replace("??", "..")
            actual = self.proc.read_bytes(self.base + rva, len(signature) // 2).hex()
            if not all(e == "." or e == a for e, a in zip(expected, actual)):
                return None
            funcs[name] = self.base + rva
        return funcs

    def _start_equip(self, action, *args) -> bool:
        """Lance action(*args) dans un fil separe (les appels au jeu se
        font une image a la fois). Un seul equipement en direct a la fois."""
        if not (self.connected and self.sane and self.pid and self.speed.ensure_injected(self.pid)):
            return False
        if not self._equip_lock.acquire(blocking=False):
            return False
        threading.Thread(target=self._equip_worker, args=(action, *args), daemon=True).start()
        return True

    def _equip_worker(self, action, *args) -> None:
        try:
            action(*args)
        except OSError:
            pass
        finally:
            self._equip_lock.release()

    def read_equipped_outfit_id(self) -> int | None:
        index = self.proc.read_bytes(self.linkvarbuf + self.OUTFIT_EQUIP_OFFSET, 1)[0]
        return next((i for i, idx in self.OUTFIT_EQUIP_INDEX.items() if idx == index), None)

    def equip_outfit(self, item_id: int) -> bool:
        if item_id not in self.OUTFIT_EQUIP_INDEX:
            return False
        return self._start_equip(self._equip_model_live, self.OUTFIT_EQUIP_INDEX[item_id], None)

    def equip_facecamo(self, item_id: int | None) -> bool:
        """Lance le changement de visage en direct (None = aucun)."""
        if item_id is not None and item_id not in self.FACECAMO_EQUIP_INDEX:
            return False
        index = 0 if item_id is None else self.FACECAMO_EQUIP_INDEX[item_id]
        return self._start_equip(self._equip_model_live, None, index)

    def _equip_model_live(self, outfit: int | None, face: int | None) -> bool:
        """Tenue et/ou visage (None = garder l'actuel)."""
        funcs = self._live_funcs(self.MODEL_LIVE_FUNCS)
        manager = struct.unpack("<Q", self.proc.read_bytes(self.base + self.MODEL_MANAGER_PTR_RVA, 8))[0]
        if funcs is None or not manager:
            return False
        current_outfit, current_face = self.proc.read_bytes(self.linkvarbuf + self.OUTFIT_EQUIP_OFFSET, 2)
        outfit = current_outfit if outfit is None else outfit
        face = current_face if face is None else face
        if (outfit, face) == (current_outfit, current_face):
            return True
        call = self.speed.game_call
        state = call(funcs["state"])
        if state is None:
            return False
        pause = not (state & 6)
        if pause:
            call(funcs["pause_set"], self.MODEL_PAUSE_FLAG)
        try:
            pattern = struct.unpack("<I", self.proc.read_bytes(self.linkvarbuf + mgs4save.OCTOCAMO_EQUIPPED_OFFSET, 4))[0]
            if face and not (call(funcs["face_allowed"], pattern, outfit, face) or 0) & 0xFFFFFFFF:
                face = 0
            if (call(funcs["equip"], outfit, face) or 0) & 0xFFFFFFFF != 0:
                return False
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                countdown = struct.unpack("<i", self.proc.read_bytes(manager + 0x108, 4))[0]
                loading = self.proc.read_bytes(manager + 0xC0, 1)[0] & 3
                if countdown <= 0 and not loading:
                    break
                time.sleep(0.02)
            time.sleep(0.1)  # quelques images de marge
            return True
        finally:
            if pause:
                call(funcs["pause_clear"], self.MODEL_PAUSE_FLAG)

    # Motif OctoCamo en direct, sans menu (2026-10-03) : on pilote le
    # controleur d'auto-camouflage du joueur (celui qui change la
    # combinaison contre un mur), pointe par OCTOCAMO_CONTROLLER_PTR_RVA.
    # Il tient un "enregistrement" de motif de 0x12D0 octets pour le motif
    # porte (+0xA0) et un pour le motif en attente (+0x1370) : code a +0,
    # 6 teintes en flottants (= les 6 tables de caracteristiques / 1000,
    # 3 couleurs puis 3 autres ; 0 = combinaison noire) a OCTOCAMO_TINT_OFFSETS,
    # drapeaux a +0x10D8 (recopies chaque image dans linkvarbuf+0xB38, B28
    # recevant le code). Drapeau 0x1000 = motif force (Olive, Cadavre,
    # speciaux...) : le controleur ne le remplace plus au contact d'un mur.
    # Etat +0x98 (0 aucun, 1 apparition, 2 stable, 3 disparition, 4
    # transition) et fondu +0x9C (0..1) ; la combinaison n'est redessinee
    # que si le fondu varie dans l'image ou si le bit 1 de +0x39A8 est mis.
    # Sequence (fonctions du jeu appelees dans son fil, via game_call) :
    # demande de chargement de la texture, attente qu'elle soit prete,
    # bascule du double tampon de textures, construction de
    # l'enregistrement en attente, teintes, copie vers le motif porte puis
    # apparition en fondu (motif auto) ou redessin direct (motif force).
    OCTOCAMO_CONTROLLER_PTR_RVA = 0x23EB5F50
    OCTOCAMO_LIVE_FUNCS = {
        # nom : (RVA, premiers octets attendus) - verifies avant tout appel.
        "load": (0xA1060, "405356574883ec40488b1d"),
        "ready": (0xA0240, "488b05????????4885c07506"),
        "flip": (0xA15F0, "48895c24084889742410574883ec20"),
        "build": (0x9FC10, "4055574881ecb80100008bea488bf9"),
        "memcpy": (0xD25800, "ff25"),
        "memset": (0x7513C0, "4c8bc233d2e9"),
    }
    OCTOCAMO_RECORD_SIZE = 0x12D0
    OCTOCAMO_TINT_OFFSETS = (0x1248, 0x124C, 0x1250, 0x1258, 0x125C, 0x1260)
    OCTOCAMO_FLAG_FORCED = 0x1000

    def _octocamo_tints(self, code: int) -> list[int]:
        """Teintes du motif : celles de la table de la partie s'il y est
        (motifs obtenus ou memorises), sinon neutres (1000)."""
        for slot, entry in enumerate(self._octocamo_table()):
            if entry and (entry & 0xFFFFFF) == code:
                return [struct.unpack("<H", self.proc.read_bytes(self.linkvarbuf + table + slot * 2, 2))[0]
                        for table in self.OCTOCAMO_STAT_TABLES]
        return [1000] * 6

    def equip_octocamo(self, code: int) -> bool:
        """Lance le changement de motif en direct (fil separe, ~0,1-0,5 s
        le temps que la texture charge). Faux si refuse d'emblee."""
        if not (self.connected and self.sane):
            return False
        # Dore/Precommande : seulement si le jeu les a debloques (contenu lie
        # au compte - ne pas le contourner).
        rva = self.OCTOCAMO_ACCOUNT_FLAG_RVAS.get(code)
        if rva is not None and not self.proc.read_bytes(self.base + rva, 1)[0]:
            return False
        return self._start_equip(self._equip_octocamo_live, code)

    def _equip_octocamo_live(self, code: int) -> bool:
        # Autre tenue portee : le controleur se remet a zero a chaque image
        # (linkvarbuf+0xB26 != 0) - on remet d'abord la combinaison OctoCamo.
        if self.proc.read_bytes(self.linkvarbuf + self.OUTFIT_EQUIP_OFFSET, 1)[0]:
            if not self._equip_model_live(0, None):
                return False
        funcs = self._live_funcs(self.OCTOCAMO_LIVE_FUNCS)
        ctrl = struct.unpack("<Q", self.proc.read_bytes(self.base + self.OCTOCAMO_CONTROLLER_PTR_RVA, 8))[0]
        if funcs is None or not ctrl:
            return False
        call = self.speed.game_call
        current, pending = ctrl + 0xA0, ctrl + 0x1370
        if code == 0:
            # Infiltration : aucun motif.
            if call(funcs["memset"], current, self.OCTOCAMO_RECORD_SIZE) is None:
                return False
            self._octocamo_show(ctrl, forced=True, fade_value=0.0, state=0)
            return True
        if call(funcs["load"], code) is None:
            return False
        deadline = time.monotonic() + 5.0
        while (call(funcs["ready"], code) or 0) & 0xFFFFFFFF != 1:
            if time.monotonic() > deadline:
                return False
            time.sleep(0.05)
        call(funcs["flip"], code)
        if (call(funcs["build"], pending, code) or 0) & 0xFFFFFFFF != 1:
            return False
        for offset, tint in zip(self.OCTOCAMO_TINT_OFFSETS, self._octocamo_tints(code)):
            self.proc.write_bytes(pending + offset, struct.pack("<f", tint / 1000))
        call(funcs["memcpy"], current, pending, self.OCTOCAMO_RECORD_SIZE)
        call(funcs["memset"], pending, self.OCTOCAMO_RECORD_SIZE)
        flags = struct.unpack("<I", self.proc.read_bytes(current + 0x10D8, 4))[0]
        if flags & self.OCTOCAMO_FLAG_FORCED:
            self._octocamo_show(ctrl, forced=True, fade_value=1.0, state=2)
        else:
            self._octocamo_show(ctrl, forced=False, fade_value=0.0, state=1)
        return True

    def _octocamo_show(self, ctrl: int, forced: bool, fade_value: float, state: int) -> None:
        self.proc.write_bytes(ctrl + 0x9C, struct.pack("<f", fade_value))
        self.proc.write_bytes(ctrl + 0x98, struct.pack("<I", state))
        if forced:
            redraw = self.proc.read_bytes(ctrl + 0x39A8, 1)[0] | 1
            self.proc.write_bytes(ctrl + 0x39A8, bytes([redraw]))

    def equip_octocamo_slot(self, slot: int) -> bool:
        code = self.read_octocamo_slot_code(slot)
        return self.equip_octocamo(code) if code else False

    def write_octocamo_state(self, code: int, value: int) -> None:
        unlocked = value != self.OCTOCAMO_LOCKED
        if code not in self.OCTOCAMO_EDITABLE:
            # Motif ajoute d'office par le menu : masque/demasque via le
            # hook (injecte la DLL au besoin, comme les autres reglages).
            # Jamais pour Dore/Precommande (lignes en lecture seule).
            if code in self.OCTOCAMO_ACCOUNT_FLAG_RVAS or code == 0:
                return
            if not (self.connected and self.sane and self.pid and self.speed.ensure_injected(self.pid)):
                return
            hidden = [c for c in self.speed.read_octocamo_hidden() if c != code]
            if not unlocked:
                hidden.append(code)
            self.speed.write_octocamo_hidden(hidden)
            return
        table = self._octocamo_table()
        slots = [i for i, entry in enumerate(table) if (entry & 0xFFFFFF) == code]
        if unlocked:
            if slots or code not in self.OCTOCAMO_EDITABLE:
                return
            free = [i for i, entry in enumerate(table) if entry == 0]
            if not free:
                return
            usual_slot, flags = self.OCTOCAMO_EDITABLE[code]
            slot = usual_slot if usual_slot in free else free[0]
            entry, stat = (flags << 24) | code, 1000
            targets = [slot]
        else:
            entry, stat = 0, 0
            targets = slots
        for slot in targets:
            for table_offset in self.OCTOCAMO_STAT_TABLES:
                self.proc.write_bytes(self.linkvarbuf + table_offset + slot * 2, struct.pack("<H", stat))
            self.proc.write_bytes(self.linkvarbuf + mgs4save.OCTOCAMO_TABLE_OFFSET + slot * 4,
                                  struct.pack("<I", entry))

    def write_vital_percent(self, name: str, percent: float) -> None:
        maxi = self.read_vital_max(name)
        self.write_vital(name, round(maxi * percent / 100))

    def read_alert_state(self) -> int:
        """Lecture seule - l'ecriture ne tient pas (voir ALERT_STATE_RVA)."""
        return int.from_bytes(self.proc.read_bytes(self.base + ALERT_STATE_RVA, 4), "little")

    # Points Drebin : "actuel" (solde depensable) et "total_ventes" (cumul
    # historique) sont deux champs distincts de STATS, confirmes fiables
    # (2026-09-23) via linkvarbuf. Invariant impose ici a la demande de
    # l'utilisateur (pas necessairement la logique exacte du jeu, mais une
    # garde-fou d'edition sensee) : actuel >= total_ventes toujours, aucun
    # des deux negatif. Modifier total_ventes repercute la meme difference
    # sur actuel (gagner plus de ventes historiques augmente d'autant le
    # solde courant).
    def read_drebin_actuel(self) -> int:
        return self.read_stat("drebin_actuel")

    def read_drebin_total_ventes(self) -> int:
        return self.read_stat("drebin_total_ventes")

    def write_drebin_actuel(self, value: int) -> bool:
        """False sans rien ecrire si value < total_ventes ou < 0."""
        if value < 0 or value < self.read_stat("drebin_total_ventes"):
            return False
        self.write_stat("drebin_actuel", value)
        return True

    def write_drebin_total_ventes(self, value: int) -> bool:
        """False sans rien ecrire si value < 0 ou si la repercussion sur
        actuel le ferait passer sous 0."""
        if value < 0:
            return False
        old_ventes = self.read_stat("drebin_total_ventes")
        new_actuel = self.read_stat("drebin_actuel") + (value - old_ventes)
        if new_actuel < 0:
            return False
        self.write_stat("drebin_total_ventes", value)
        self.write_stat("drebin_actuel", new_actuel)
        return True


# Categories du tableau d'objets partage (0x0526), calquees sur les onglets
# de gui_app.py plutot que sur un unique gros tableau - chaque dict source
# est confirme comme indexant ce meme tableau via les appels a
# _read_item_collection/read_camo/read_objects dans mgs4save.py.
# Onglet "OctoCamo" fusionne (2026-09-25, demande explicite de
# l'utilisateur) : sous-sections FaceCamo/Gilet/Octocamo empilees dans
# UN SEUL onglet (via GroupedItemsTab), meme logique que CAMO_GROUPS
# dans gui_app.py plutot que des onglets separes comme la veille (a
# quand meme permis de retrouver "Big Boss" 0x28 le 2026-09-24-25,
# coince entre Campbell 0x27 et Drebin 0x29). La section "Octocamo" ne
# lit PAS ce tableau : motifs stockes dans une table a part de linkvarbuf
# (2026-10-03, voir MGS4Live.OCTOCAMO_EDITABLE et OctoCamoTab).
_FACECAMO_NAMES_VISIBLE: dict[int, str] = {i: facecamo_name(i) for i in mgs4save.FACECAMO_NAMES}
_FACECAMO_IDS_ORDERED: list[int] = sorted(
    _FACECAMO_NAMES_VISIBLE, key=lambda i: mgs4save.FACECAMO_SORT_ORDER.get(i, 999)
)
_VEST_NAMES_VISIBLE: dict[int, str] = {k: vest_name(k) for k in mgs4save.VEST_NAMES if isinstance(k, int)}

_CLASSIFIED_IDS = (
    set(mgs4save.GENERAL_ITEM_NAMES) | set(_VEST_NAMES_VISIBLE) | set(_FACECAMO_NAMES_VISIBLE)
    | set(mgs4save.OUTFIT_NAMES) | set(mgs4save.FIGURE_NAMES) | set(mgs4save.SONG_NAMES)
)
def item_unclassified_format() -> str:
    """Gabarit de format positionnel brut (ex. "Objet #{:02d}") - pas via
    tr() qui attend des arguments nommes, celui-ci est applique avec
    .format(id) a l'appel (voir TableTab, qui l'utilise aussi pour les
    ID absents de son dict names)."""
    return _STRINGS.get("item.unclassified_format", "Objet #{:02d}")


_NON_CLASSES_NAMES: dict[int, str] = {
    i: item_unclassified_format().format(i)
    for i in range(mgs4save.ITEM_STATE_COUNT) if i not in _CLASSIFIED_IDS
}

# Objets generaux confirmes structurels (jamais un vrai objet, voir
# STRUCTURAL_ITEM_IDS dans mgs4save.py - 0x00 reconfirme le 2026-09-23,
# force a 1 en live sans aucun effet visible en jeu) - masques ici aussi,
# comme deja fait pour l'onglet Objets de l'appli principale, pour ne pas
# polluer les tests "a l'aveugle" avec des cases qui ne font jamais rien.
_GENERAL_ITEMS_VISIBLE = {
    k: item_name(k) for k in mgs4save.GENERAL_ITEM_NAMES if k not in mgs4save.STRUCTURAL_ITEM_IDS
}

# Objets empilables (quantite en stock), pas de sens "Obtenu"=1 fige - voir
# mgs4save.py ligne ~616 ("les 5 premiers IDs ... sont des COMPTEURS").
GENERAL_ITEM_QUANTITY_IDS = {0x01, 0x02, 0x03, 0x04, 0x05}  # Ration/Nouilles/Regain/Pentazemine/Compresse

# (label d'onglet, dict id->nom, IDs verrouilles a 65535/obtenus a 1 comme
# les chansons/statuettes/tenues/camos - PAS le tableau d'armes, qui a sa
# propre convention 0/1/2, voir TrainerWindow)
# FaceCamo/Gilet ne sont plus ici : fusionnes dans l'onglet "OctoCamo"
# dedie (GroupedItemsTab), construit a part dans TrainerWindow.
# (cle stable - jamais traduite, sert aux comparaisons logiques en aval -,
# libelle affiche, dict id->nom) - la cle stable evite de comparer du
# texte traduit dans la logique (fragile, casserait selon la langue).
ITEM_CATEGORIES: list[tuple[str, str, dict[int, str]]] = [
    ("items", tr("tab.items"), _GENERAL_ITEMS_VISIBLE),
    ("outfits", tr("tab.outfits"), {i: outfit_name(i) for i in mgs4save.OUTFIT_NAMES}),
    ("figures", tr("tab.figures"), {i: figure_name(i) for i in mgs4save.FIGURE_NAMES}),
    ("songs", tr("tab.songs"), mgs4save.SONG_NAMES),
    ("unclassified", tr("tab.unclassified"), _NON_CLASSES_NAMES),
]


# ---------------------------------------------------------------------------
# Interface Qt
# ---------------------------------------------------------------------------

REFRESH_MS = 750
# Cycle dedie, plus rapide que REFRESH_MS, pour la reassertion des
# verrous munitions (VitalsTab) : certaines armes tirent assez vite pour
# vider plusieurs coups entre deux cycles a 750ms avant correction,
# visible/genant (demande utilisateur 2026-09-26). Independant du
# rafraichissement general de l'UI (que ralentir ferait inutilement
# tout ralentir) - juste de la lecture/ecriture memoire brute, pas de
# repaint Qt, donc un cycle rapide reste tres peu couteux.
AMMO_LOCK_REFRESH_MS = 50


class TableTab(QWidget):
    """Un onglet (une categorie du tableau objets, ou le tableau armes) :
    tableau ID/Nom/Etat + controles d'ecriture par ligne, un par ID de
    `ids` (pas forcement une plage continue). `reader`/`writer` donnent
    acces a la case memoire correspondante, `quick_states` est la liste des
    etats proposes dans le menu deroulant [(label, valeur), ...] - choisir
    une entree ecrit immediatement, pas besoin de bouton "OK" separe.
    La valeur brute et le controle "definir une valeur arbitraire" sont
    reserves au mode avance (masques par defaut, voir set_advanced) ; les
    munitions restent toujours visibles (simple quantite a editer, pas une
    fonctionnalite "avancee")."""

    def __init__(self, live: MGS4Live, ids: list[int], names: dict[int, str], placeholder: str,
                 reader, writer, quick_states: list[tuple[str, int]],
                 ammo_reader=None, ammo_writer=None, quantity_ids: set[int] | None = None,
                 binary_lock_value: int | None = None, battery_link: tuple[int, int] | None = None,
                 confirmed_ids: set[int] | None = None, show_filter: bool = True, fit_height: bool = False,
                 advanced_only_ids: set[int] | None = None, readonly_ids: set[int] | None = None,
                 equip_action=None, equip_ids: set[int] | None = None, equip_available=None):
        super().__init__()
        self.live = live
        # Colonne "Equiper" (bouton par ligne) pour les ID de equip_ids :
        # equip_action(item_id) demande l'equipement en direct (voir
        # MGS4Live._start_equip). equip_available() (optionnel) renvoie les
        # ID equipables en ce moment : les autres boutons sont grises a
        # chaque rafraichissement (ex. armes absentes de la liste du jeu).
        self.equip_action = equip_action
        self.equip_ids = equip_ids or set()
        self.equip_available = equip_available
        self.equip_buttons: dict[int, QPushButton] = {}
        # ID affiches avec leur vraie valeur mais non modifiables (menu Etat
        # et controle brut grises) - ex. motifs OctoCamo donnes d'office par
        # le jeu, ou lies au compte (voir OctoCamoTab).
        self.readonly_ids = readonly_ids or set()
        self.ids = ids
        self.names = names
        self.placeholder = placeholder
        self.reader = reader
        self.writer = writer
        # ID masques en mode simple, visibles seulement en mode avance -
        # sert a cacher les entrees dangereuses (ex. "Destabil.SOP" 0x44,
        # qui fait planter le jeu si equipe, voir notes.md 2026-09-24) a
        # un utilisateur non averti, tout en gardant l'acces pour la
        # recherche. self._advanced/self._filter_text suivent l'etat
        # courant pour que _apply_filter() puisse recombiner les deux
        # conditions (filtre texte ET verrou avance) a chaque appel.
        self.advanced_only_ids = advanced_only_ids or set()
        self._advanced = False
        self._filter_text = ""
        # Mecanisme generique herite de l'epoque ou seuls certains ID
        # d'armes avaient une adresse d'etat fiable (avant la decouverte
        # de weapon_state_rva(), voir notes.md 2026-09-24) : si defini,
        # les ID hors de cet ensemble ont leur menu Etat/controle "Definir
        # (brut)" desactives et laisses vides plutot que d'afficher une
        # valeur potentiellement trompeuse. Plus utilise pour l'onglet
        # Armes (toujours None desormais), garde au cas ou une future
        # table aurait le meme besoin.
        self.confirmed_ids = confirmed_ids
        # Si defini : TOUTES les lignes de cet onglet utilisent un menu a
        # exactement 2 etats (Verrouille/Deverrouille) au lieu du systeme
        # quick_states+"Autre" - Deverrouille = n'importe quelle valeur
        # differente de binary_lock_value, pas une correspondance exacte
        # figee (utile pour les objets, ou meme les booleens ont une seule
        # valeur "obtenu"=1 alors que les quantites peuvent valoir autre
        # chose). Les armes (3 etats reels : non possedee/verrouillee/
        # utilisable) n'utilisent PAS ce mode, elles gardent quick_states.
        self.binary_lock_value = binary_lock_value
        self.quick_states = quick_states
        self.ammo_reader = ammo_reader
        self.ammo_writer = ammo_writer
        self.has_ammo = ammo_reader is not None
        # IDs "a quantite" (ex. Ration/Nouilles/Regain...) : pas de valeur
        # "Obtenu" fixe qui aurait sens (une ration ne s'"obtient" pas a une
        # valeur precise, elle s'empile) - dropdown reduit a "Verrouille"
        # pour ces lignes, avec une colonne Quantite toujours visible a la
        # place (memes reader/writer que la valeur brute, juste affichee en
        # priorite et sans etre reservee au mode avance).
        self.quantity_ids = quantity_ids or set()
        # Cas particulier Batterie (Solid Eye) : (id_batterie, id_solid_eye).
        # La batterie n'a pas d'etat verrouille/deverrouille a elle - elle
        # suit celui du Solid Eye (pas de Solid Eye = pas de batterie du
        # tout, meme "de base"). Affichage 1-6 (jamais 0 : une batterie de
        # base est toujours installee), stockage brut 0-5 (+1 pour
        # l'affichage, -1 a l'ecriture) - meme convention que
        # read_battery_count()/BATTERY_MAX dans mgs4save.py.
        self.battery_link = battery_link
        if battery_link is not None:
            self.quantity_ids = self.quantity_ids | {battery_link[0]}
        self.has_quantity = bool(self.quantity_ids)
        self.state_combos: dict[int, QComboBox] = {}
        self.value_items: dict[int, QTableWidgetItem] = {}
        self.spin_items: dict[int, QSpinBox] = {}
        # Une seule colonne pour les lignes a quantite/munitions (le
        # spinbox affiche deja la valeur courante - pas besoin d'une
        # colonne d'affichage separee en plus, c'etait redondant).
        self.ammo_controls: dict[int, tuple[QSpinBox, QPushButton]] = {}
        self.quantity_controls: dict[int, tuple[QSpinBox, QPushButton]] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.filter_edit = QLineEdit()
        if show_filter:
            filter_row = QHBoxLayout()
            filter_row.addWidget(QLabel(tr("table.filter_id_name")))
            self.filter_edit.textChanged.connect(self._apply_filter)
            filter_row.addWidget(self.filter_edit)
            layout.addLayout(filter_row)

        headers = [tr("table.id"), tr("table.name"), tr("table.state"), tr("table.raw_value")]
        headers.append(tr("table.set_raw"))
        if self.has_quantity:
            headers.append(tr("table.quantity"))
        if self.has_ammo:
            headers.append(tr("table.ammo"))
        if self.equip_action is not None:
            headers.append(tr("table.equip"))
        self.col_state = 2
        self.col_value = 3
        self.col_control = 4
        col = 5
        self.col_control_quantity = col if self.has_quantity else None
        col += 1 if self.has_quantity else 0
        self.col_control_ammo = col if self.has_ammo else None
        col += 1 if self.has_ammo else 0
        self.col_equip = col if self.equip_action is not None else None
        # Colonnes masquees par defaut (mode simple) - voir set_advanced.
        # Quantite/Munitions restent toujours visibles (edition normale,
        # pas "avancee").
        self.advanced_columns = [self.col_value, self.col_control]

        self.table = QTableWidget(len(ids), len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        # Garde-fou : sans ca, une colonne large peut ecraser "Nom" a
        # quasi 0 (deja vu). "Nom" est en Stretch, donc profite de tout
        # l'espace rendu disponible par ce plancher sur les autres colonnes.
        self.table.horizontalHeader().setMinimumSectionSize(90)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        for row, item_id in enumerate(ids):
            self._build_row(row, item_id)
            if self.col_equip is not None and item_id in self.equip_ids:
                equip_btn = QPushButton(tr("equip.button"))
                equip_btn.clicked.connect(lambda _checked=False, i=item_id: self._on_equip(i))
                self.table.setCellWidget(row, self.col_equip, equip_btn)
                self.equip_buttons[item_id] = equip_btn

        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(2)
        self.table.resizeColumnToContents(3)
        self._cap_column_width(self.col_control, 300)
        if self.has_quantity:
            self._cap_column_width(self.col_control_quantity, 220)
        if self.has_ammo:
            self._cap_column_width(self.col_control_ammo, 220)

        self.set_advanced(False)

        if fit_height:
            # Utilise dans une section empilee (GroupedWeaponsTab) : la
            # table adopte exactement la hauteur de ses lignes, c'est le
            # QScrollArea englobant qui gere le defilement global plutot
            # que chaque petite table individuellement.
            row_h = self.table.rowHeight(0) if len(ids) else 30
            total_h = self.table.horizontalHeader().height() + row_h * len(ids) + 2 * self.table.frameWidth() + 4
            self.table.setFixedHeight(total_h)
            self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def _on_equip(self, item_id: int):
        if not (self.live.connected and self.live.sane):
            return
        try:
            self.equip_action(item_id)
        except OSError:
            pass

    def set_advanced(self, advanced: bool):
        self._advanced = advanced
        for col in self.advanced_columns:
            self.table.setColumnHidden(col, not advanced)
        if self.advanced_only_ids:
            self._apply_filter(self._filter_text)

    def _cap_column_width(self, col: int, max_width: int):
        self.table.resizeColumnToContents(col)
        if self.table.columnWidth(col) > max_width:
            self.table.setColumnWidth(col, max_width)

    def _build_row(self, row: int, item_id: int):
        id_item = QTableWidgetItem(f"{item_id:#04x}")
        id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 0, id_item)

        name = self.names.get(item_id, self.placeholder.format(item_id))
        name_item = QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 1, name_item)

        is_quantity_row = item_id in self.quantity_ids
        is_battery_row = self.battery_link is not None and item_id == self.battery_link[0]
        is_unconfirmed_row = self.confirmed_ids is not None and item_id not in self.confirmed_ids
        combo = QComboBox()
        if self.binary_lock_value is not None:
            # Exactement 2 etats, pas de "Autre" : sentinelle (verrouille/
            # non possede) ou n'IMPORTE quelle autre valeur (deverrouille/
            # utilisable - une ration a 15 ou 42 en stock est tout autant
            # "deverrouille" qu'un objet simplement "obtenu", pas une
            # correspondance exacte figee ; idem pour une arme a 1 ou 2,
            # voir BINARY_CATEGORIES). Libelles et valeur d'ecriture pris
            # dans quick_states (index 0 = sentinelle, index 1 = le reste).
            combo.addItem(self.quick_states[0][0], self.binary_lock_value)
            combo.addItem(self.quick_states[1][0], self.quick_states[1][1])
        else:
            for label, value in self.quick_states:
                combo.addItem(label, value)
            # Pas d'entree "Autre" grisee (inutile, jamais choisissable) -
            # si la valeur ne correspond a aucun etat connu, le menu reste
            # simplement vide (setCurrentIndex(-1) dans refresh()), la
            # vraie valeur restant visible via "Valeur brute".
        combo.currentIndexChanged.connect(
            lambda idx, i=item_id, c=combo: self._on_combo_changed(i, c)
        )
        if is_battery_row:
            # Pas d'etat propre - reflet en lecture seule de celui du
            # Solid Eye, mis a jour dans refresh().
            combo.setEnabled(False)
        if is_unconfirmed_row:
            # confirmed_ids defini et cet ID en dehors - menu laisse vide
            # plutot que trompeur (voir commentaire sur self.confirmed_ids).
            combo.setEnabled(False)
        if item_id in self.readonly_ids:
            combo.setEnabled(False)
        self.table.setCellWidget(row, self.col_state, combo)
        self.state_combos[item_id] = combo

        value_item = QTableWidgetItem("?")
        value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, self.col_value, value_item)
        self.value_items[item_id] = value_item

        control = QWidget()
        control_layout = QHBoxLayout(control)
        control_layout.setContentsMargins(2, 0, 2, 0)
        control_layout.setSpacing(4)
        spin = QSpinBox()
        spin.setRange(0, 0xFFFF)
        spin.setMinimumWidth(65)
        control_layout.addWidget(spin)
        self.spin_items[item_id] = spin
        apply_btn = QPushButton(tr("button.ok"))
        apply_btn.clicked.connect(lambda _checked=False, i=item_id, s=spin: self._write(i, s.value()))
        control_layout.addWidget(apply_btn)
        control.setLayout(control_layout)
        control.adjustSize()
        if is_unconfirmed_row or item_id in self.readonly_ids:
            spin.setEnabled(False)
            apply_btn.setEnabled(False)
        self.table.setCellWidget(row, self.col_control, control)

        if self.has_quantity:
            qty_control = QWidget()
            qty_layout = QHBoxLayout(qty_control)
            qty_layout.setContentsMargins(2, 0, 2, 0)
            qty_layout.setSpacing(4)
            qty_spin = QSpinBox()
            if is_battery_row:
                # Affichage 1-BATTERY_MAX (jamais 0, une batterie de base
                # est toujours installee) - voir read_battery_count() dans
                # mgs4save.py. Ecriture avec le decalage -1 (stockage brut
                # 0-based).
                qty_spin.setRange(1, mgs4save.BATTERY_MAX)
                qty_ok = QPushButton(tr("button.ok"))
                qty_ok.clicked.connect(lambda _checked=False, i=item_id, s=qty_spin: self._write(i, s.value() - 1))
            else:
                qty_spin.setRange(0, 0xFFFF)
                qty_ok = QPushButton(tr("button.ok"))
                qty_ok.clicked.connect(lambda _checked=False, i=item_id, s=qty_spin: self._write(i, s.value()))
            qty_spin.setMinimumWidth(65)
            qty_layout.addWidget(qty_spin)
            qty_layout.addWidget(qty_ok)
            qty_control.setLayout(qty_layout)
            qty_control.adjustSize()
            self.table.setCellWidget(row, self.col_control_quantity, qty_control)
            self.quantity_controls[item_id] = (qty_spin, qty_ok)
            if not is_quantity_row:
                qty_spin.setEnabled(False)
                qty_ok.setEnabled(False)

        if self.has_ammo:
            ammo_control = QWidget()
            ammo_layout = QHBoxLayout(ammo_control)
            ammo_layout.setContentsMargins(2, 0, 2, 0)
            ammo_layout.setSpacing(4)
            ammo_spin = QSpinBox()
            ammo_spin.setRange(0, 0xFFFF)
            ammo_spin.setMinimumWidth(65)
            ammo_layout.addWidget(ammo_spin)
            ammo_ok = QPushButton(tr("button.ok"))
            ammo_ok.clicked.connect(lambda _checked=False, i=item_id, s=ammo_spin: self._write_ammo(i, s.value()))
            ammo_layout.addWidget(ammo_ok)
            ammo_control.setLayout(ammo_layout)
            ammo_control.adjustSize()
            self.table.setCellWidget(row, self.col_control_ammo, ammo_control)
            self.ammo_controls[item_id] = (ammo_spin, ammo_ok)

    def _on_combo_changed(self, item_id: int, combo: QComboBox):
        value = combo.currentData()
        if value is None:  # "Autre" (place-tenant) ou signal declenche par le refresh
            return
        self._write(item_id, value)

    def _write(self, item_id: int, value: int):
        if not (self.live.connected and self.live.sane):
            return
        try:
            self.writer(item_id, value)
        except OSError:
            self.value_items[item_id].setText("erreur ecriture")
        # La correction munitions 65535 -> 10 pour une arme "Utilisable"
        # est geree dans refresh() (rattrape aussi les armes deja
        # debloquees avant ce correctif, pas seulement au moment du clic) -
        # inutile de la dupliquer ici, le prochain tick (750ms) s'en charge.

    def _write_ammo(self, item_id: int, value: int):
        if not (self.live.connected and self.live.sane):
            return
        try:
            self.ammo_writer(item_id, value)
        except OSError:
            pass

    def _refresh_battery_row(self, item_id: int, raw_battery_value: int):
        _, solid_eye_id = self.battery_link
        try:
            solid_eye_value = self.reader(solid_eye_id)
        except OSError:
            return
        solid_eye_locked = solid_eye_value == self.binary_lock_value

        combo = self.state_combos.get(item_id)
        if combo is not None and not combo.view().isVisible():
            idx = 0 if solid_eye_locked else 1
            if combo.currentIndex() != idx:
                combo.blockSignals(True)
                combo.setCurrentIndex(idx)
                combo.blockSignals(False)

        qty_ctrl = self.quantity_controls.get(item_id)
        if qty_ctrl is None:
            return
        qty_spin, qty_btn = qty_ctrl
        qty_spin.setEnabled(not solid_eye_locked)
        qty_btn.setEnabled(not solid_eye_locked)
        if not solid_eye_locked and not qty_spin.hasFocus():
            displayed = 1 if raw_battery_value == 65535 else min(raw_battery_value + 1, mgs4save.BATTERY_MAX)
            qty_spin.blockSignals(True)
            qty_spin.setValue(displayed)
            qty_spin.blockSignals(False)

    def refresh(self):
        if not (self.live.connected and self.live.sane):
            for item in self.value_items.values():
                item.setText("?")
            return
        if self.equip_available is not None and self.equip_buttons:
            try:
                available = set(self.equip_available())
            except OSError:
                available = set()
            for item_id, equip_btn in self.equip_buttons.items():
                equip_btn.setEnabled(item_id in available)
        state_by_id: dict[int, int] = {}
        for item_id, item in self.value_items.items():
            try:
                value = self.reader(item_id)
            except OSError:
                item.setText("?")
                continue
            state_by_id[item_id] = value
            item.setText(str(value))
            spin = self.spin_items.get(item_id)
            # Ne pas ecraser ce que l'utilisateur est en train de taper/
            # ajuster dans la molette (sinon impossible de cliquer sur les
            # fleches +/- sans que le rafraichissement live ne remette la
            # valeur d'origine entre-temps).
            if spin is not None and not spin.hasFocus():
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)

            if self.battery_link is not None and item_id == self.battery_link[0]:
                # Cas special : pas d'etat propre (suit le Solid Eye), pas
                # de correspondance directe raw<->affiche (decalage +1).
                self._refresh_battery_row(item_id, value)
                continue

            if self.confirmed_ids is not None and item_id not in self.confirmed_ids:
                # ID hors de confirmed_ids - "Valeur brute" reste visible
                # pour reference mais le menu Etat reste vide, jamais une
                # correspondance qui donnerait une fausse impression de
                # certitude.
                combo = self.state_combos.get(item_id)
                if combo is not None and combo.currentIndex() != -1:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(-1)
                    combo.blockSignals(False)
                continue

            qty_ctrl = self.quantity_controls.get(item_id)
            if qty_ctrl is not None:
                qty_spin, qty_btn = qty_ctrl
                # Verrouille (sentinelle habituelle 65535) = pas de stock a
                # ajuster tant que ce n'est pas deverrouille via le menu.
                is_quantity_row = item_id in self.quantity_ids and value != 65535
                qty_spin.setEnabled(is_quantity_row)
                qty_btn.setEnabled(is_quantity_row)
                if is_quantity_row and not qty_spin.hasFocus():
                    qty_spin.blockSignals(True)
                    qty_spin.setValue(value)
                    qty_spin.blockSignals(False)

            combo = self.state_combos.get(item_id)
            if combo is not None and not combo.view().isVisible():
                if self.binary_lock_value is not None:
                    # Binaire par construction : verrouille (sentinelle) ou
                    # deverrouille (tout le reste), pas de correspondance
                    # exacte sur une valeur figee - voir _build_row.
                    idx = 0 if value == self.binary_lock_value else 1
                else:
                    # -1 = aucun etat connu ne correspond -> menu vide,
                    # plutot qu'une entree "Autre" grisee inutile.
                    idx = combo.findData(value)
                if combo.currentIndex() != idx:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(idx)
                    combo.blockSignals(False)

        if not self.has_ammo:
            return
        for item_id, (ammo_spin, ammo_btn) in self.ammo_controls.items():
            try:
                ammo_value = self.ammo_reader(item_id)
            except OSError:
                ammo_spin.setEnabled(False)
                ammo_btn.setEnabled(False)
                continue
            if ammo_value is None:
                # Adresse munitions pas encore trouvee pour cette arme -
                # desactivee plutot que trompeuse (voir
                # CONFIRMED_WEAPON_AMMO_RVAS, a completer au fil des tests).
                ammo_spin.setEnabled(False)
                ammo_btn.setEnabled(False)
                continue
            # Arme pas "Utilisable" (Non poss./Verrouillee) : munitions
            # masquees (grisees) plutot que d'afficher la sentinelle 65535
            # habituelle sur un champ jamais initialise en jeu, qui
            # ressemble a tort a un etat "verrouille" (demande utilisateur
            # 2026-09-25). "Utilisable" est toujours la derniere entree de
            # quick_states par construction - voir _build_row.
            weapon_state = state_by_id.get(item_id)
            is_unlocked = weapon_state is None or weapon_state == self.quick_states[-1][1]
            ammo_spin.setEnabled(is_unlocked)
            ammo_btn.setEnabled(is_unlocked)
            if is_unlocked and ammo_value == 65535:
                # Meme correction que dans _write() au moment du
                # deblocage, mais ici pour les armes deja "Utilisable" au
                # moment ou ce controle est apparu (partie deja avancee,
                # deblocage arrive avant l'existence de ce correctif...) -
                # rattrape en continu plutot qu'une seule fois au clic
                # (demande utilisateur 2026-09-25). Idempotent : une fois
                # corrige a 10, ce test ne redeclenche plus rien au tour
                # suivant.
                try:
                    self.ammo_writer(item_id, 10)
                    ammo_value = 10
                except OSError:
                    pass
            if is_unlocked and not ammo_spin.hasFocus():
                ammo_spin.blockSignals(True)
                ammo_spin.setValue(ammo_value)
                ammo_spin.blockSignals(False)

    def _apply_filter(self, text: str):
        text = text.strip().lower()
        self._filter_text = text
        for row in range(self.table.rowCount()):
            if self.ids[row] in self.advanced_only_ids and not self._advanced:
                self.table.setRowHidden(row, True)
                continue
            if not text:
                self.table.setRowHidden(row, False)
                continue
            id_text = self.table.item(row, 0).text().lower()
            name_text = self.table.item(row, 1).text().lower()
            self.table.setRowHidden(row, text not in id_text and text not in name_text)


class GroupedWeaponsTab(QWidget):
    """Un seul onglet "Armes", sections empilees par categorie (meme
    regroupement que WeaponsPanel dans gui_app.py : WEAPON_CATEGORIES/
    WEAPON_GROUP_ORDER) plutot que des onglets separes par categorie -
    demande explicite de l'utilisateur pour coller a l'appli principale.
    Un seul champ de filtre en haut, qui filtre chaque section et masque
    celles qui n'ont plus aucune ligne visible."""

    # Categories dont l'etat 1 ("Verrouillee") n'a aucun effet observable
    # distinct de 2 ("Utilisable") - confirme (2026-09-24) sur le
    # Masterkey puis tous les accessoires (0x4a-0x5b) : seul 0 change
    # vraiment quelque chose en jeu. Menu reduit a 2 choix pour ces
    # categories plutot que 3, sur le meme mecanisme binaire que
    # binary_lock_value (deja utilise pour les objets).
    BINARY_CATEGORIES = {"accessory"}  # slug stable, voir WEAPON_GROUP_SLUGS

    # ID masques en mode simple (visibles seulement en mode avance) car
    # dangereux a manipuler par un utilisateur non averti - voir
    # advanced_only_ids sur TableTab. "Destabil.SOP" (0x44) fait PLANTER
    # le jeu s'il est equipe (confirme 2 fois, 2026-09-24) - objet
    # probablement pas prevu pour etre reellement utilise en solo, voir
    # notes.md.
    DANGEROUS_IDS = {0x44}

    def __init__(self, live: MGS4Live, category_ids: list[tuple[str, str, list[int]]],
                 names: dict[int, str], reader, writer, quick_states: list[tuple[str, int]],
                 ammo_reader, ammo_writer, equip_action=None, equip_available=None):
        super().__init__()
        self.sub_tabs: list[tuple[QLabel, TableTab]] = []

        layout = QVBoxLayout(self)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel(tr("table.filter_id_name")))
        self.filter_edit = QLineEdit()
        self.filter_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.filter_edit)
        layout.addLayout(filter_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        for slug, label, ids in category_ids:
            if not ids:
                continue
            header = QLabel(f"{label} ({len(ids)})")
            header.setStyleSheet("font-weight: bold; font-size: 13px; margin-top: 6px;")
            inner_layout.addWidget(header)
            is_binary = slug in self.BINARY_CATEGORIES
            section_quick_states = (
                [(tr("weapon.state_unowned"), 0), (tr("weapon.state_usable"), 2)] if is_binary else quick_states
            )
            tab = TableTab(
                live, ids, names, tr("weapon.unclassified_format"), reader, writer, section_quick_states,
                ammo_reader=ammo_reader, ammo_writer=ammo_writer,
                binary_lock_value=0 if is_binary else None,
                show_filter=False, fit_height=True,
                advanced_only_ids=self.DANGEROUS_IDS,
                # Bouton "Equiper" (arme en main) sauf accessoires.
                equip_action=None if is_binary else equip_action,
                equip_ids=None if is_binary else set(ids) - self.DANGEROUS_IDS,
                equip_available=None if is_binary else equip_available,
            )
            inner_layout.addWidget(tab)
            self.sub_tabs.append((header, tab))
        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        layout.addWidget(scroll)

    def set_advanced(self, advanced: bool):
        for _header, tab in self.sub_tabs:
            tab.set_advanced(advanced)

    def refresh(self):
        for _header, tab in self.sub_tabs:
            tab.refresh()

    def _apply_filter(self, text: str):
        text = text.strip().lower()
        for header, tab in self.sub_tabs:
            tab._apply_filter(text)
            visible_rows = sum(
                1 for row in range(tab.table.rowCount()) if not tab.table.isRowHidden(row)
            )
            header.setVisible(visible_rows > 0)
            tab.setVisible(visible_rows > 0)


class GroupedItemsTab(QWidget):
    """Version generalisee de GroupedWeaponsTab pour des categories
    d'objets (pas d'armes) qui doivent etre fusionnees en un seul onglet
    avec sous-sections - demande explicite de l'utilisateur (2026-09-25)
    pour que l'onglet "OctoCamo" du trainer suive la meme logique que
    CAMO_GROUPS dans gui_app.py (FaceCamo + Gilet + Octocamo empiles
    plutot que des onglets separes). Contrairement a GroupedWeaponsTab,
    pas de colonne munitions et une seule convention verrouille/obtenu
    (binary_lock_value) commune a toutes les sections - pas besoin des
    mecanismes specifiques aux armes (BINARY_CATEGORIES, DANGEROUS_IDS,
    etat 0/1/2)."""

    def __init__(self, live: MGS4Live, category_ids: list[tuple[str, list[int], dict[int, str]]],
                 reader, writer, quick_states: list[tuple[str, int]], binary_lock_value: int | None = None):
        super().__init__()
        self.sub_tabs: list[tuple[QLabel, TableTab]] = []

        layout = QVBoxLayout(self)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel(tr("table.filter_id_name")))
        self.filter_edit = QLineEdit()
        self.filter_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.filter_edit)
        layout.addLayout(filter_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        # Chaque section : (label, ids, names) ou (label, ids, names,
        # reader, writer[, readonly_ids[, equip_action, equip_ids]]) - lecteur
        # propre quand elle ne lit pas le tableau objets (ex. motifs
        # OctoCamo, voir MGS4Live.read_octocamo_state), bouton "Equiper".
        for label, ids, names, *extra in category_ids:
            if not ids:
                continue
            section_reader, section_writer = extra[:2] if extra else (reader, writer)
            section_readonly = extra[2] if len(extra) > 2 else None
            section_equip = extra[3] if len(extra) > 3 else None
            section_equip_ids = extra[4] if len(extra) > 4 else None
            header = QLabel(f"{label} ({len(ids)})")
            header.setStyleSheet("font-weight: bold; font-size: 13px; margin-top: 6px;")
            inner_layout.addWidget(header)
            tab = TableTab(
                live, ids, names, item_unclassified_format(), section_reader, section_writer, quick_states,
                binary_lock_value=binary_lock_value,
                show_filter=False, fit_height=True, readonly_ids=section_readonly,
                equip_action=section_equip, equip_ids=section_equip_ids,
            )
            inner_layout.addWidget(tab)
            self.sub_tabs.append((header, tab))
        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        layout.addWidget(scroll)

    def set_advanced(self, advanced: bool):
        for _header, tab in self.sub_tabs:
            tab.set_advanced(advanced)

    def refresh(self):
        for _header, tab in self.sub_tabs:
            tab.refresh()

    def _apply_filter(self, text: str):
        text = text.strip().lower()
        for header, tab in self.sub_tabs:
            tab._apply_filter(text)
            visible_rows = sum(
                1 for row in range(tab.table.rowCount()) if not tab.table.isRowHidden(row)
            )
            header.setVisible(visible_rows > 0)
            tab.setVisible(visible_rows > 0)


# Meme convention que gui_app.py (FRAMES_PER_SECOND) : framerate reel
# variable (~55-62 fps selon le champ, voir notes.md), 60 est la meilleure
# approximation disponible - pas de conversion exacte possible.
FRAMES_PER_SECOND = 60


def _frames_to_hms_parts(frames: int) -> tuple[int, int, int]:
    total_seconds = frames // FRAMES_PER_SECOND
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    return h, m, s


# Regroupement thematique + libelle FR des champs de mgs4save.STATS, pour
# l'onglet Stats du trainer (voir StatsTab). Purement cosmetique : aucun
# impact sur la fiabilite/l'ecriture, qui reste au cas par cas (voir note
# affichee en haut de l'onglet). Doit couvrir tous les noms de STATS sauf
# drebin_actuel/drebin_total_ventes (deja exclus en amont, UI dediee).
STATS_TRAINER_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    (tr("stat_group.combat"), [
        ("kills_total", tr("stat.kills_total")),
        ("headshots", tr("stat.headshots")),
        ("knife_kills", tr("stat.knife_kills")),
        ("knife_knockouts", tr("stat.knife_knockouts")),
        ("cqc", tr("stat.cqc")),
        ("combat_high", tr("stat.combat_high")),
    ]),
    (tr("stat_group.infiltration"), [
        ("alertes", tr("stat.alertes")),
        ("continues", tr("stat.continues")),
        ("holdups", tr("stat.holdups")),
        ("body_searches", tr("stat.body_searches")),
        ("praises", tr("stat.praises")),
    ]),
    (tr("stat_group.movement"), [
        ("roulades_avant", tr("stat.roulades_avant")),
        ("roulades_cote", tr("stat.roulades_cote")),
    ]),
    (tr("stat_group.items"), [
        ("soins_utilises", tr("stat.soins_utilises")),
        ("objets_speciaux_bitmask", tr("stat.objets_speciaux_bitmask")),
        ("objets_donnes_milices", tr("stat.objets_donnes_milices")),
        ("weapon_pickups", tr("stat.weapon_pickups")),
        ("item_pickups", tr("stat.item_pickups")),
        ("syringe_uses", tr("stat.syringe_uses")),
        ("scanning_plug_uses", tr("stat.scanning_plug_uses")),
        ("playboy_pages", tr("stat.playboy_pages")),
        ("emotion_magazine_pages", tr("stat.emotion_magazine_pages")),
        ("posters_vus", tr("stat.posters_vus")),
    ]),
    (tr("stat_group.flashbacks"), [
        ("flashbacks_vues", tr("stat.flashbacks_vues")),
    ]),
    (tr("stat_group.time"), [
        ("temps_jeu_frames", tr("stat.temps_jeu_frames")),
        ("temps_accroupi_frames", tr("stat.temps_accroupi_frames")),
        ("temps_allonge_frames", tr("stat.temps_allonge_frames")),
        ("temps_mur_frames", tr("stat.temps_mur_frames")),
        ("temps_boite_carton_frames", tr("stat.temps_boite_carton_frames")),
        ("temps_baril_frames", tr("stat.temps_baril_frames")),
    ]),
]


class OctoCamoTab(GroupedItemsTab):
    """Onglet OctoCamo (2026-10-03) : sections FaceCamo/Gilet/Octocamo
    comme avant, plus une ligne "Equipe : ..." en haut (motif OctoCamo lu
    en direct). La section Octocamo ne liste que les 6 motifs stockes dans
    la partie (MGS4Live.OCTOCAMO_EDITABLE) ; changer de motif equipe reste
    du ressort du menu du jeu (la fonction qui l'applique doit tourner dans
    le fil du jeu, et les motifs speciaux ne sont charges que menu
    ouvert)."""

    def __init__(self, live: MGS4Live, *args, **kwargs):
        super().__init__(live, *args, **kwargs)
        self.live = live
        self._names_by_code = {code: name for name, code in mgs4save.OCTOCAMO_CODES.items()}
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("octocamo.equipped")))
        self.equipped_label = QLabel("?")
        self.equipped_label.setStyleSheet("font-weight: bold;")
        row.addWidget(self.equipped_label)
        row.addStretch(1)
        self.layout().insertLayout(0, row)

        # Boutons "Equiper" par ligne (voir TableTab.equip_action) : effet
        # immediat, sans menu (le visage fige le jeu une fraction de
        # seconde, le temps de recharger la tete).
        hint = QLabel(tr("equip.when_menu"))
        hint.setStyleSheet("color: gray;")
        row.insertWidget(row.count() - 1, hint)

    def _pattern_label(self, code: int) -> str:
        """Nom d'un motif : un des 21 du menu, un motif capture au nom
        connu (mgs4save.OCTOCAMO_CAPTURED_NAMES, avec son code), ou
        "motif capture (code)"."""
        name = self._names_by_code.get(code)
        if name:
            return octocamo_name(name)
        captured = mgs4save.OCTOCAMO_CAPTURED_NAMES.get(code)
        if captured:
            return f"{captured} ({code:06X})"
        return tr("octocamo.captured", code=f"{code:06X}")

    def refresh(self):
        super().refresh()
        if not (self.live.connected and self.live.sane):
            self.equipped_label.setText("?")
            return
        try:
            code = self.live.read_equipped_octocamo_code()
        except OSError:
            self.equipped_label.setText("?")
            return
        self.equipped_label.setText(self._pattern_label(code))
        # Section "Motifs memorises" (derniere) : nom de ligne mis a jour
        # en direct avec le code de l'emplacement et "porte" le cas echeant.
        _header, saved_tab = self.sub_tabs[-1]
        for row, slot in enumerate(MGS4Live.OCTOCAMO_SAVED_SLOTS):
            item = saved_tab.table.item(row, 1)
            if item is None:
                continue
            try:
                slot_code = self.live.read_octocamo_slot_code(slot)
            except OSError:
                continue
            label = tr("octocamo.slot", n=slot + 1)
            if not slot_code:
                text = f"{label} — {tr('octocamo.slot_empty')}"
            else:
                text = f"{label} — {self._pattern_label(slot_code)}"
                if slot_code == code:
                    text += f" ({tr('octocamo.slot_worn')})"
            if item.text() != text:
                item.setText(text)


class StatsTab(QWidget):
    """Onglet Stats : un champ par entree de mgs4save.STATS (cle textuelle,
    pas un ID numerique - kills, CQC, temps divers...), lu/ecrit via
    live.read_stat/write_stat (linkvarbuf). Une mini-table par theme
    (STATS_TRAINER_GROUPS, meme convention que GroupedWeaponsTab/
    GroupedItemsTab : en-tete + table dimensionnee a son contenu, empilees
    dans un QScrollArea commun) - pas de valeur affichee en double a cote
    d'un spinbox qui la montre deja (retour utilisateur 2026-09-25).
    Ecriture immediate (pas de bouton "OK", juge inutile) : au changement
    de selection pour le select "Objets speciaux", et pour les spinbox a
    chaque pas de fleche/molette ou a la validation d'une saisie clavier
    (setKeyboardTracking(False) - evite d'ecrire une valeur intermediaire
    incomplete pendant la frappe)."""

    # Les 4 combinaisons possibles des 2 bits identifies de
    # objets_speciaux_bitmask (voir mgs4save.SPECIAL_ITEM_USE_BITS :
    # Bandana=bit0, Camouflage optique=bit1) - valeur = bitmask a ecrire
    # telle quelle dans le champ u16.
    SPECIAL_ITEMS_STATES = [
        (tr("stats.special_items_none"), 0),
        (item_name(0x0f), 1),
        (item_name(0x10), 2),
        (tr("stats.special_items_both"), 3),
    ]

    def __init__(self, live: MGS4Live, names: list[str]):
        super().__init__()
        self.live = live
        self.names = names
        self.spin_items: dict[str, QSpinBox] = {}
        self.time_items: dict[str, tuple[QSpinBox, QSpinBox, QSpinBox]] = {}
        self.special_items_combo: QComboBox | None = None
        self.sections: list[tuple[QLabel, QTableWidget, list[str]]] = []

        layout = QVBoxLayout(self)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel(tr("table.filter_name")))
        self.filter_edit = QLineEdit()
        self.filter_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.filter_edit)
        layout.addLayout(filter_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)

        remaining = set(names)
        for group_label, fields in STATS_TRAINER_GROUPS:
            fields = [(n, lbl) for n, lbl in fields if n in remaining]
            if not fields:
                continue
            self._add_section(inner_layout, group_label, fields)
            remaining -= {n for n, _ in fields}

        # Filet de securite : tout champ de STATS non couvert par
        # STATS_TRAINER_GROUPS (ne devrait pas arriver, voir commentaire du
        # dict) atterrit quand meme quelque part plutot que de disparaitre.
        if remaining:
            self._add_section(inner_layout, tr("stats.other_group"), [(n, n) for n in names if n in remaining])

        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        layout.addWidget(scroll)

    def _add_section(self, inner_layout: QVBoxLayout, label: str, fields: list[tuple[str, str]]):
        header = QLabel(f"{label} ({len(fields)})")
        header.setStyleSheet("font-weight: bold; font-size: 13px; margin-top: 6px;")
        inner_layout.addWidget(header)

        # Legende H:M:S dans l'en-tete pour les sections 100% "_frames"
        # (3 spinbox cote a cote sans autre indication - demande
        # utilisateur 2026-09-25) plutot qu'un "Valeur" generique ambigu.
        all_time_fields = all(name.endswith("_frames") for name, _ in fields)
        value_header = tr("stats.value_hms") if all_time_fields else tr("stats.value")

        table = QTableWidget(len(fields), 2)
        table.setHorizontalHeaderLabels([tr("table.field"), value_header])
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)

        for row, (name, display) in enumerate(fields):
            self._build_row(table, row, name, display)

        table.resizeColumnToContents(1)
        # Meme technique que fit_height dans TableTab : la table prend
        # exactement la hauteur de ses lignes, le QScrollArea englobant
        # gere le defilement global plutot que chaque petite table.
        row_h = table.rowHeight(0) if fields else 30
        total_h = table.horizontalHeader().height() + row_h * len(fields) + 2 * table.frameWidth() + 4
        table.setFixedHeight(total_h)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner_layout.addWidget(table)
        self.sections.append((header, table, [n for n, _ in fields]))

    def _build_row(self, table: QTableWidget, row: int, name: str, display: str):
        offset, fmt = mgs4save.STATS[name]
        name_item = QTableWidgetItem(display)
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        name_item.setToolTip(f"{name} - offset {offset:#06x} ({'u32' if fmt == '<I' else 'u16'})")
        table.setItem(row, 0, name_item)

        if name == "objets_speciaux_bitmask":
            # Seulement 2 bits identifies (voir SPECIAL_ITEM_USE_BITS) sur
            # ce champ u16 - un select des 4 combinaisons possibles est
            # plus naturel qu'un spinbox brut pour l'edition (demande
            # explicite de l'utilisateur, 2026-09-25).
            combo = QComboBox()
            for label, value in self.SPECIAL_ITEMS_STATES:
                combo.addItem(label, value)
            combo.currentIndexChanged.connect(
                lambda _idx, n=name, c=combo: self._write(n, c.currentData())
            )
            table.setCellWidget(row, 1, combo)
            self.special_items_combo = combo
            return

        if name.endswith("_frames"):
            # Stocke en frames a framerate variable (voir notes.md), mais
            # un compteur "HH:MM:SS" est bien plus lisible/editable qu'un
            # nombre de frames brut (retour utilisateur 2026-09-25) - 3
            # spinbox H/M/S plutot que QTimeEdit, dont le plafond de 23h59
            # ne conviendrait pas a des compteurs de temps de jeu total
            # pouvant largement depasser 24h (champs u32).
            table.setCellWidget(row, 1, self._build_time_widget(name))
            return

        spin = QSpinBox()
        # QSpinBox est limite a un int signe 32 bits (max ~2.1 milliards),
        # ne peut pas couvrir tout un u32 (jusqu'a ~4.3 milliards) - marge
        # large mais pas la plage entiere pour les champs u32.
        spin.setRange(0, 2_000_000_000 if fmt == "<I" else 0xFFFF)
        spin.setMinimumWidth(110)
        spin.setKeyboardTracking(False)
        spin.valueChanged.connect(lambda value, n=name: self._write(n, value))
        table.setCellWidget(row, 1, spin)
        self.spin_items[name] = spin

    def _build_time_widget(self, name: str) -> QWidget:
        container = QWidget()
        row_layout = QHBoxLayout(container)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(2)
        spins = []
        for i, (maximum, tooltip) in enumerate(
            ((99999, tr("stats.hours")), (59, tr("stats.minutes")), (59, tr("stats.seconds")))
        ):
            spin = QSpinBox()
            spin.setRange(0, maximum)
            spin.setButtonSymbols(QSpinBox.NoButtons)  # 3 champs cote a cote, fleches inutiles/encombrantes
            spin.setToolTip(tooltip)
            spin.setAlignment(Qt.AlignCenter)
            spin.setMinimumWidth(50 if i == 0 else 36)
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(lambda _v, n=name: self._write_time(n))
            row_layout.addWidget(spin)
            if i < 2:
                row_layout.addWidget(QLabel(":"))
            spins.append(spin)
        self.time_items[name] = tuple(spins)
        return container

    def _write(self, name: str, value: int):
        if not (self.live.connected and self.live.sane):
            return
        try:
            self.live.write_stat(name, value)
        except OSError:
            pass  # refresh() reaffichera l'etat "deconnecte" au prochain cycle si le process a disparu

    def _write_time(self, name: str):
        if not (self.live.connected and self.live.sane):
            return
        h, m, s = self.time_items[name]
        total_seconds = h.value() * 3600 + m.value() * 60 + s.value()
        frames = total_seconds * FRAMES_PER_SECOND
        _, fmt = mgs4save.STATS[name]
        frames = min(frames, 0xFFFFFFFF if fmt == "<I" else 0xFFFF)
        try:
            self.live.write_stat(name, frames)
        except OSError:
            pass  # refresh() reaffichera l'etat "deconnecte" au prochain cycle si le process a disparu

    def set_advanced(self, advanced: bool):
        pass  # pas de mode simple/avance distinct ici, deja tout en "brut"

    def refresh(self):
        connected = self.live.connected and self.live.sane
        for name in self.names:
            try:
                value = self.live.read_stat(name) if connected else None
            except OSError:
                value = None

            if name == "objets_speciaux_bitmask":
                combo = self.special_items_combo
                combo.setEnabled(connected)
                if value is not None and not combo.hasFocus():
                    combo.blockSignals(True)
                    combo.setCurrentIndex(combo.findData(value))  # -1 si bits inconnus actifs
                    combo.blockSignals(False)
                continue

            if name.endswith("_frames"):
                h, m, s = self.time_items[name]
                for spin in (h, m, s):
                    spin.setEnabled(connected)
                if value is not None and not (h.hasFocus() or m.hasFocus() or s.hasFocus()):
                    for spin, part in zip((h, m, s), _frames_to_hms_parts(value)):
                        spin.blockSignals(True)
                        spin.setValue(part)
                        spin.blockSignals(False)
                continue

            spin = self.spin_items[name]
            spin.setEnabled(connected)
            if value is not None and not spin.hasFocus():
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)

    def _apply_filter(self, text: str):
        text = text.strip().lower()
        for header, table, field_names in self.sections:
            any_visible = False
            for row, name in enumerate(field_names):
                display = table.item(row, 0).text()
                visible = not text or text in display.lower() or text in name.lower()
                table.setRowHidden(row, not visible)
                any_visible = any_visible or visible
            header.setVisible(any_visible)
            table.setVisible(any_visible)


class VitalsTab(QWidget):
    """Onglet "Etat de jeu" : Sante/Stamina/Stress/Batterie Solid
    Eye/Sante Metal Gear REX (live.read_vital_percent/write_vital_percent,
    voir VITALS) via un curseur 0-100% (pas la valeur brute - la vraie
    borne max de chaque champ est lue en live et sert a convertir), avec
    une case "Verrouiller" par ligne (reecrit le pourcentage a chaque
    rafraichissement - "vie infinie" etc.), plus l'etat d'alerte en
    lecture seule (l'ecriture ne tient pas, voir ALERT_STATE_RVA)."""

    # Mapping asymetrique centre sur 0 = vitesse normale (1.0x) : moitie
    # gauche du curseur (-100..0) va de 10% a 100%, moitie droite (0..100)
    # de 100% a 300% - le curseur reste visuellement symetrique (demande
    # explicite de l'utilisateur : "au milieu pour la vitesse normale")
    # meme si la plage de vitesses couverte ne l'est pas.
    SPEED_SLIDER_RANGE = (-100, 100)
    SPEED_SLOWDOWN_FLOOR = 0.1  # multiplicateur au bout gauche (-100)
    SPEED_BOOST_CEILING = 3.0  # multiplicateur au bout droit (+100)

    @classmethod
    def _speed_from_slider(cls, value: int) -> float:
        if value <= 0:
            return 1.0 + (value / 100) * (1.0 - cls.SPEED_SLOWDOWN_FLOOR)
        return 1.0 + (value / 100) * (cls.SPEED_BOOST_CEILING - 1.0)

    def __init__(self, live: MGS4Live):
        super().__init__()
        self.live = live
        self.value_labels: dict[str, QLabel] = {}
        self.sliders: dict[str, QSlider] = {}
        self.lock_checks: dict[str, QCheckBox] = {}
        self.locked_percents: dict[str, float] = {}
        # weapon_id -> vraie reserve au moment ou "Munitions infinies" a
        # ete cochee, reecrite en continu tant qu'elle reste cochee (pas
        # de valeur fixe artificielle - demande explicite de l'utilisateur
        # 2026-09-26, apres l'echec de deux pistes plus "authentiques"
        # mais trop fragiles, voir notes.md : mecanisme du Bandana limite
        # a l'objet reellement possede et en conflit avec un autre objet
        # special equipe ; sentinel 65535 du Patriot specifique a cette
        # arme, casse l'affichage sur les autres). "Pas de rechargement"
        # n'a pas besoin de cet instantane : la capacite max du chargeur
        # (WEAPON_MAGAZINE_MAX_OFFSET) est une constante par arme, relue
        # et reecrite en direct a chaque cycle dans refresh() pour TOUTES
        # les armes plutot que figee au moment du clic - fonctionne donc
        # automatiquement quelle que soit l'arme equipee/changee ensuite.
        self.ammo_snapshot: dict[int, int] = {}

        # Degats en paliers pour "Un coup, un mort" sur les boss (voir
        # _reassert_boss_staged_damage) : contrairement aux ennemis
        # standards (code-patch, vraie mise a mort en un coup), les boss
        # n'ont pas d'instruction de degats exploitable - on quantifie
        # chaque coup REEL en paliers de 25% plutot que de forcer 0
        # directement (deja teste : forcer 0 soi-meme peut desynchroniser
        # l'etat du combat et le bloquer, 2026-09-26). Reinitialise a
        # chaque nouveau pointeur boss_actor2 (nouvelle phase/pool).
        self._boss_damage_addr: int | None = None
        self._boss_damage_max_hp: int | None = None
        self._boss_damage_max_stamina: int | None = None
        self._boss_damage_step_hp: int = -1
        self._boss_damage_step_stamina: int = -1
        # Raging Raven (pas de paliers, voir _reassert_boss_staged_damage) :
        # derniere valeur observee, pour ne forcer 0 que sur une vraie
        # transition/baisse detectee, jamais en continu.
        self._raven_last_hp: int | None = None
        self._raven_last_stamina: int | None = None

        layout = QVBoxLayout(self)

        # Regroupement en QGroupBox par theme (demande utilisateur
        # 2026-10-01 : l'onglet devenait trop charge en controles empiles
        # a plat) - purement visuel, aucun changement de comportement des
        # widgets eux-memes (meme noms, memes connexions).
        speed_group = QGroupBox(tr("vitals.speed_group"))
        speed_layout = QVBoxLayout(speed_group)

        speed_row = QHBoxLayout()
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(*self.SPEED_SLIDER_RANGE)
        self.speed_slider.setValue(0)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        speed_row.addWidget(self.speed_slider, 1)
        self.speed_value_label = QLabel("100 %")
        self.speed_value_label.setMinimumWidth(60)
        speed_row.addWidget(self.speed_value_label)
        self.pause_check = QCheckBox(tr("vitals.pause"))
        self.pause_check.toggled.connect(self._on_pause_toggled)
        speed_row.addWidget(self.pause_check)
        speed_layout.addLayout(speed_row)
        layout.addWidget(speed_group)

        alert_group = QGroupBox(tr("vitals.alert_group"))
        alert_layout = QVBoxLayout(alert_group)

        alert_row = QHBoxLayout()
        alert_row.addWidget(QLabel(tr("vitals.alert_real_state")))
        self.alert_label = QLabel("?")
        self.alert_label.setStyleSheet("font-weight: bold;")
        alert_row.addWidget(self.alert_label)
        alert_row.addStretch(1)
        alert_layout.addLayout(alert_row)

        force_row = QHBoxLayout()
        force_row.addWidget(QLabel(tr("vitals.alert_force")))
        self.alert_force_combo = QComboBox()
        self.alert_force_combo.addItem(tr("vitals.alert_auto"))
        for state_value in sorted(ALERT_STATE_NAMES):
            self.alert_force_combo.addItem(alert_state_name(state_value))
        self.alert_force_combo.setToolTip(tr("vitals.alert_force_tooltip"))
        self.alert_force_combo.activated.connect(self._on_alert_force_changed)
        force_row.addWidget(self.alert_force_combo)
        force_row.addStretch(1)
        alert_layout.addLayout(force_row)

        self.no_alerts_check = QCheckBox(tr("vitals.no_alerts"))
        self.no_alerts_check.setToolTip(tr("vitals.no_alerts_tooltip"))
        self.no_alerts_check.toggled.connect(self._on_no_alerts_toggled)
        alert_layout.addWidget(self.no_alerts_check)
        layout.addWidget(alert_group)

        weapons_group = QGroupBox(tr("vitals.weapons_group"))
        weapons_layout = QVBoxLayout(weapons_group)

        weapons_row = QHBoxLayout()
        self.infinite_ammo_check = QCheckBox(tr("vitals.infinite_ammo"))
        self.infinite_ammo_check.setToolTip(tr("vitals.infinite_ammo_tooltip"))
        self.infinite_ammo_check.toggled.connect(self._on_infinite_ammo_toggled)
        weapons_row.addWidget(self.infinite_ammo_check)
        self.no_reload_check = QCheckBox(tr("vitals.no_reload"))
        self.no_reload_check.setToolTip(tr("vitals.no_reload_tooltip"))
        self.no_reload_check.toggled.connect(self._on_no_reload_toggled)
        weapons_row.addWidget(self.no_reload_check)
        self.instant_kill_check = QCheckBox(tr("vitals.instant_kill"))
        self.instant_kill_check.setToolTip(tr("vitals.instant_kill_tooltip"))
        self.instant_kill_check.toggled.connect(self._apply_instant_kill_mode)
        weapons_row.addWidget(self.instant_kill_check)
        pill, self.lethal_btn, self.non_lethal_btn, self._lethal_group = self._build_pill_toggle(
            tr("vitals.lethal"), tr("vitals.non_lethal")
        )
        self.lethal_btn.setToolTip(tr("vitals.lethal_tooltip"))
        self.non_lethal_btn.setToolTip(tr("vitals.non_lethal_tooltip"))
        self.lethal_btn.toggled.connect(self._apply_instant_kill_mode)
        self.non_lethal_btn.toggled.connect(self._apply_instant_kill_mode)
        weapons_row.addWidget(pill)
        weapons_row.addStretch(1)
        weapons_layout.addLayout(weapons_row)

        self.railgun_charge_check = QCheckBox(tr("vitals.railgun_charge"))
        self.railgun_charge_check.setToolTip(tr("vitals.railgun_charge_tooltip"))
        self.railgun_charge_check.toggled.connect(self._on_railgun_charge_toggled)
        weapons_layout.addWidget(self.railgun_charge_check)
        layout.addWidget(weapons_group)

        names = list(VITALS)
        self.table = QTableWidget(len(names), 3)
        self.table.setHorizontalHeaderLabels([tr("table.field"), tr("table.live_value"), tr("table.lock")])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setMinimumSectionSize(90)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        for row, name in enumerate(names):
            self._build_row(row, name)

        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(2)

        # Minuteur dedie (AMMO_LOCK_REFRESH_MS, plus rapide que le cycle
        # general REFRESH_MS) pour "Munitions infinies"/"Pas de
        # rechargement" - voir _reassert_ammo_locks.
        self.ammo_lock_timer = QTimer(self)
        self.ammo_lock_timer.timeout.connect(self._reassert_ammo_locks)
        self.ammo_lock_timer.start(AMMO_LOCK_REFRESH_MS)

    @staticmethod
    def _build_pill_toggle(left_text: str, right_text: str):
        """2 QPushButton cochables regroupes (exclusif) stylises en une
        seule "pilule" scindee en deux (coins arrondis uniquement sur les
        bords exterieurs, pas de bordure au milieu) - demande utilisateur
        2026-09-26, plus lisible qu'une paire de cases a cocher separees
        pour un choix mutuellement exclusif. Retourne (widget conteneur,
        bouton gauche, bouton droit, le QButtonGroup - a garder en vie
        c'est deja fait via le parent Qt, mais utile si l'appelant veut
        y toucher)."""
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        left_btn = QPushButton(left_text)
        right_btn = QPushButton(right_text)
        base = (
            "QPushButton {{ {radius} border: 1px solid #808080;"
            " background: #808080; color: white; padding: 4px 10px; }}"
            " QPushButton:checked {{ background: #2ea3ff; border-color: #2ea3ff; }}"
        )
        left_btn.setStyleSheet(base.format(
            radius="border-top-left-radius: 13px; border-bottom-left-radius: 13px;"
                   " border-top-right-radius: 0px; border-bottom-right-radius: 0px;"
        ))
        right_btn.setStyleSheet(base.format(
            radius="border-top-right-radius: 13px; border-bottom-right-radius: 13px;"
                   " border-top-left-radius: 0px; border-bottom-left-radius: 0px;"
        ))
        for btn in (left_btn, right_btn):
            btn.setCheckable(True)
            btn.setMinimumHeight(26)
        group = QButtonGroup(container)
        group.setExclusive(True)
        group.addButton(left_btn)
        group.addButton(right_btn)
        left_btn.setChecked(True)
        row.addWidget(left_btn)
        row.addWidget(right_btn)
        return container, left_btn, right_btn, group

    def _build_row(self, row: int, name: str):
        name_item = QTableWidgetItem(vital_display_name(name))
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 0, name_item)

        control = QWidget()
        control_layout = QHBoxLayout(control)
        control_layout.setContentsMargins(4, 0, 4, 0)
        control_layout.setSpacing(6)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.valueChanged.connect(lambda value, n=name: self._on_slider_changed(n, value))
        control_layout.addWidget(slider, 1)
        self.sliders[name] = slider
        value_label = QLabel("? %")
        value_label.setMinimumWidth(90)
        control_layout.addWidget(value_label)
        self.value_labels[name] = value_label
        control.setLayout(control_layout)
        self.table.setCellWidget(row, 1, control)

        lock = QCheckBox()
        lock.toggled.connect(lambda checked, n=name: self._on_lock_toggled(n, checked))
        lock_wrap = QWidget()
        lock_layout = QHBoxLayout(lock_wrap)
        lock_layout.setContentsMargins(0, 0, 0, 0)
        lock_layout.addWidget(lock)
        lock_layout.setAlignment(Qt.AlignCenter)
        self.table.setCellWidget(row, 2, lock_wrap)
        self.lock_checks[name] = lock

    def _on_lock_toggled(self, name: str, checked: bool):
        if checked:
            self.locked_percents[name] = self.sliders[name].value()
        else:
            self.locked_percents.pop(name, None)

    def _on_slider_changed(self, name: str, value: int):
        if not (self.live.connected and self.live.sane):
            return
        try:
            self.live.write_vital_percent(name, value)
        except OSError:
            self.value_labels[name].setText("erreur")
            return
        if name in self.locked_percents:
            self.locked_percents[name] = value

    def _on_speed_changed(self, value: int):
        speed = self._speed_from_slider(value)
        self.speed_value_label.setText(f"{round(speed * 100)} %")
        if not (self.live.connected and self.live.sane):
            return
        self.live.set_game_speed(speed)

    def _on_pause_toggled(self, checked: bool):
        if not (self.live.connected and self.live.sane):
            return
        self.live.set_paused(checked)

    def _apply_instant_kill_mode(self):
        """Appele par la case a cocher maitresse ET par le bouton pilule
        Letal/Non letal (les deux doivent se recalculer ensemble) - un
        seul des deux effets actif a la fois cote DLL, jamais les deux."""
        if not (self.live.connected and self.live.sane):
            return
        active = self.instant_kill_check.isChecked()
        lethal = self.lethal_btn.isChecked()
        self.live.set_one_shot_kill(active and lethal)
        self.live.set_non_lethal(active and not lethal)
        # Repart d'une reference 100% fraiche a chaque (re)activation du
        # mode, voir _reassert_boss_staged_damage.
        self._boss_damage_addr = None
        self._boss_damage_step_hp = -1
        self._boss_damage_step_stamina = -1
        self._raven_last_hp = None
        self._raven_last_stamina = None

    def _on_infinite_ammo_toggled(self, checked: bool):
        self.ammo_snapshot.clear()
        if not checked or not (self.live.connected and self.live.sane):
            return
        for weapon_id in CONFIRMED_WEAPON_AMMO_RVAS:
            try:
                self.ammo_snapshot[weapon_id] = self.live.read_weapon_ammo(weapon_id)
            except OSError:
                pass

    def _on_no_reload_toggled(self, checked: bool):
        if not (self.live.connected and self.live.sane):
            return
        self.live.set_no_reload(checked)

    def _on_no_alerts_toggled(self, checked: bool):
        if not (self.live.connected and self.live.sane):
            return
        self.live.set_no_alerts(checked)

    def _on_railgun_charge_toggled(self, checked: bool):
        if not (self.live.connected and self.live.sane):
            return
        self.live.set_railgun_force_charge(checked)

    def _on_alert_force_changed(self, index: int):
        if not (self.live.connected and self.live.sane):
            return
        if index == 0:
            self.live.set_alert_mode_override(None)
        else:
            self.live.set_alert_mode_override(index - 1)

    def _reassert_ammo_locks(self):
        """Cycle dedie (AMMO_LOCK_REFRESH_MS, independant du
        rafraichissement general de l'UI) : certaines armes tirent assez
        vite pour vider plusieurs coups entre deux cycles a REFRESH_MS
        (750ms) avant correction, visible/genant (demande utilisateur
        2026-09-26)."""
        if not (self.live.connected and self.live.sane):
            return
        if self.infinite_ammo_check.isChecked():
            for weapon_id, value in self.ammo_snapshot.items():
                try:
                    self.live.write_weapon_ammo(weapon_id, value)
                except OSError:
                    pass
        # "Pas de rechargement" : patch de code (install_no_reload_hook),
        # plus besoin de reassertion ici depuis le 2026-09-29 - voir
        # _on_no_reload_toggled.
        if self.instant_kill_check.isChecked():
            try:
                self._reassert_boss_staged_damage()
            except OSError:
                pass

    # Paliers successifs (fraction de la reference 100% capturee a
    # l'activation/au changement de phase) - le dernier palier est un
    # reste volontairement non nul : le coup final reste un vrai coup du
    # jeu plutot qu'une ecriture memoire, pour ne pas court-circuiter
    # l'evenement de victoire/KO du jeu (voir commentaire plus bas). Par
    # paliers de 10% (90% a 10%) plutot que 25% - premier essai a 75%
    # juge trop brutal (demande utilisateur 2026-09-26).
    BOSS_DAMAGE_STEPS = tuple(i / 10 for i in range(9, 0, -1))

    def _reassert_boss_staged_damage(self):
        """Les boss ne passent pas par l'instruction de degats patchee
        (one_shot_kill normal pour les ennemis standards) - pas
        d'equivalent trouve malgre plusieurs pistes (voir notes.md). A la
        place : chaque coup REEL encaisse par le boss (vie en mode Letal,
        stamina en mode Non letal, deux mecanismes distincts selon la
        phase, constate sur le boss 1) fait chuter la jauge au palier
        suivant plutot que de la forcer directement a 0. Deja teste et
        confirme dangereux (2026-09-26) : forcer 0 nous-memes plutot que
        via un vrai coup du jeu peut desynchroniser l'etat du combat et le
        bloquer completement (necessite alors de recharger un
        checkpoint) - le dernier palier laisse donc volontairement un
        reste (5%), le coup qui l'acheve reste un vrai coup traite
        normalement par le jeu. Detection automatique du boss actif (voir
        MGS4Live.active_boss_addr) : deux boss testes a ce jour, deux
        jeux d'offsets differents selon le hook qui se declenche."""
        addr = self.live.active_boss_addr()
        if not addr:
            self._boss_damage_addr = None
            return

        if self.live.active_boss_kind() == "raven":
            # Pas de mecanisme multi-phases connu pour ce boss (demande
            # utilisateur 2026-09-27, a l'inverse du premier boss) - on
            # force directement 0 plutot que de passer par les paliers de
            # precaution ci-dessous, mais SEULEMENT quand une vraie baisse
            # est detectee (un coup reel), jamais en continu a chaque
            # cycle de 50ms - ecrire sans arret a fait planter le jeu
            # (constate 2026-09-27).
            if addr != self._boss_damage_addr:
                self._boss_damage_addr = addr
                self._raven_last_hp = self.live.active_boss_hp()
                self._raven_last_stamina = self.live.active_boss_stamina()
                return

            current_hp = self.live.active_boss_hp()
            hp_hit_detected = (current_hp is not None and self._raven_last_hp is not None
                                and current_hp < self._raven_last_hp)

            if self.lethal_btn.isChecked():
                if hp_hit_detected:
                    self.live.set_active_boss_hp(0)
                    current_hp = 0
                self._raven_last_hp = current_hp
                return

            # Non letal : n'importe quelle arme (letale ou non) fait
            # avancer la stamina - contrairement a Laughing Octopus, pas
            # besoin de restaurer la vie ici (demande utilisateur
            # 2026-09-27) : un tir letal reste applique normalement, il
            # sert juste aussi de signal pour faire chuter la stamina.
            current_stamina = self.live.active_boss_stamina()
            stamina_hit_detected = (current_stamina is not None and self._raven_last_stamina is not None
                                     and current_stamina < self._raven_last_stamina)
            if hp_hit_detected or stamina_hit_detected:
                self.live.set_active_boss_stamina(0)
                current_stamina = 0
            self._raven_last_stamina = current_stamina
            return

        if addr != self._boss_damage_addr:
            # Nouveau boss ou nouvelle phase (pool de vie/stamina
            # different, ex. 7200 en phase 1 vs une autre valeur ensuite) -
            # nouvelle reference 100%. Ne verrouille PAS addr tant que les
            # deux valeurs lues ne sont pas franchement positives : si une
            # session precedente (test manuel, ancien palier) avait laisse
            # la vie ou la stamina a 0 pile a cette adresse, une reference
            # a 0 casse tout le calcul de paliers pour le reste du combat
            # (constate 2026-09-26, stamina restee a 0 apres un test
            # manuel puis changement de scene).
            fresh_hp = self.live.active_boss_hp()
            fresh_stamina = self.live.active_boss_stamina()
            if not fresh_hp or not fresh_stamina:
                return
            self._boss_damage_addr = addr
            self._boss_damage_max_hp = fresh_hp
            self._boss_damage_max_stamina = fresh_stamina
            self._boss_damage_step_hp = -1
            self._boss_damage_step_stamina = -1

        lethal = self.lethal_btn.isChecked()
        max_hp = self._boss_damage_max_hp
        current_hp = self.live.active_boss_hp()
        if current_hp is None or not max_hp:
            return

        if lethal:
            step_idx = self._boss_damage_step_hp
            next_idx = step_idx + 1
            if next_idx >= len(self.BOSS_DAMAGE_STEPS):
                return  # dernier palier deja atteint, on laisse le jeu finir normalement
            current_floor = int(max_hp * self.BOSS_DAMAGE_STEPS[step_idx]) if step_idx >= 0 else max_hp
            if current_hp >= current_floor:
                return  # pas de nouveau coup reel depuis le dernier palier force
            new_floor = int(max_hp * self.BOSS_DAMAGE_STEPS[next_idx])
            self.live.set_active_boss_hp(new_floor)
            self._boss_damage_step_hp = next_idx
            return

        # Non letal : n'importe quelle arme fait avancer la stamina par
        # paliers (comme le code-patch le fait pour les ennemis standards,
        # qui ignore la lethalite reelle de l'arme) - la vie reelle ne
        # doit jamais baisser dans ce mode, sinon le boss pourrait mourir
        # "pour de vrai" malgre le mode choisi. On restaure donc la vie si
        # un tir letal vient de l'entamer, et on detecte le coup via CE
        # signal (vie entamee) OU via une vraie baisse de stamina (arme
        # non letale utilisee directement) - le premier des deux qui se
        # produit fait avancer le palier de stamina.
        hp_hit_detected = current_hp < max_hp
        if hp_hit_detected:
            self.live.set_active_boss_hp(max_hp)

        max_stamina = self._boss_damage_max_stamina
        current_stamina = self.live.active_boss_stamina()
        step_idx = self._boss_damage_step_stamina
        next_idx = step_idx + 1
        if next_idx >= len(self.BOSS_DAMAGE_STEPS):
            return
        if current_stamina is None or not max_stamina:
            return
        current_floor = int(max_stamina * self.BOSS_DAMAGE_STEPS[step_idx]) if step_idx >= 0 else max_stamina
        stamina_hit_detected = current_stamina < current_floor
        if not (hp_hit_detected or stamina_hit_detected):
            return
        new_floor = int(max_stamina * self.BOSS_DAMAGE_STEPS[next_idx])
        self.live.set_active_boss_stamina(new_floor)
        self._boss_damage_step_stamina = next_idx

    def set_advanced(self, advanced: bool):
        pass  # pas de mode simple/avance distinct ici

    def refresh(self):
        if not (self.live.connected and self.live.sane):
            for label in self.value_labels.values():
                label.setText("?")
            self.alert_label.setText("?")
            self.speed_slider.setEnabled(False)
            self.pause_check.setEnabled(False)
            self.infinite_ammo_check.setEnabled(False)
            self.no_reload_check.setEnabled(False)
            self.no_alerts_check.setEnabled(False)
            self.railgun_charge_check.setEnabled(False)
            self.alert_force_combo.setEnabled(False)
            self.instant_kill_check.setEnabled(False)
            self.lethal_btn.setEnabled(False)
            self.non_lethal_btn.setEnabled(False)
            return
        self.speed_slider.setEnabled(True)
        self.pause_check.setEnabled(True)
        self.infinite_ammo_check.setEnabled(True)
        self.no_reload_check.setEnabled(True)
        self.no_alerts_check.setEnabled(True)
        self.railgun_charge_check.setEnabled(True)
        self.alert_force_combo.setEnabled(True)
        self.instant_kill_check.setEnabled(True)
        self.lethal_btn.setEnabled(True)
        self.non_lethal_btn.setEnabled(True)

        for name in VITALS:
            if name in self.locked_percents:
                try:
                    self.live.write_vital_percent(name, self.locked_percents[name])
                except OSError:
                    pass
            label = self.value_labels[name]
            slider = self.sliders[name]
            try:
                raw = self.live.read_vital(name)
                maxi = self.live.read_vital_max(name)
                percent = (raw / maxi * 100) if maxi else 0.0
            except OSError:
                label.setText("?")
                continue
            label.setText(f"{raw} / {maxi} ({percent:.1f}%)")
            if not slider.isSliderDown():
                slider.blockSignals(True)
                slider.setValue(round(percent))
                slider.blockSignals(False)

        try:
            alert = self.live.read_alert_state()
            self.alert_label.setText(alert_state_name(alert) if alert in ALERT_STATE_NAMES else tr("alert.unknown", value=alert))
        except OSError:
            self.alert_label.setText("?")


TRAINER_VERSION = "V2.2"

TRAINER_HELP_TEXT = tr("help.text")

# Chargelog charge depuis locales/<langue>/changelog.json (dict {version:
# {date, description}}) plutot que code en dur - meme structure
# symetrique FR/EN que le reste de l'i18n (demande utilisateur
# 2026-10-01, V2.0). Ordre d'affichage = ordre d'insertion du JSON
# (Python 3.7+ garde l'ordre des dicts), donc le plus recent doit rester
# en premier dans le fichier source.
TRAINER_CHANGELOG = [
    (version_label, entry["date"], entry["description"])
    for version_label, entry in CHANGELOG_STRINGS.items()
]


class HelpDialog(QDialog):
    """Popup d'aide : explication rapide, compatibilite, avertissements,
    changelog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("window.help"))
        self.setMinimumSize(480, 420)
        layout = QVBoxLayout(self)

        version = QLabel(f"MGS4 Trainer — {TRAINER_VERSION}")
        version_font = version.font()
        version_font.setBold(True)
        version_font.setPointSize(version_font.pointSize() + 2)
        version.setFont(version_font)
        layout.addWidget(version)

        help_text = QLabel(TRAINER_HELP_TEXT)
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        changelog_title = QLabel(tr("help.changelog_title"))
        changelog_title_font = changelog_title.font()
        changelog_title_font.setBold(True)
        changelog_title.setFont(changelog_title_font)
        layout.addWidget(changelog_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(10)
        for version_label, date, description in TRAINER_CHANGELOG:
            entry = QFrame()
            entry.setFrameShape(QFrame.StyledPanel)
            entry_layout = QVBoxLayout(entry)
            header = QLabel(f"{version_label} — {date}")
            header_font = header.font()
            header_font.setBold(True)
            header.setFont(header_font)
            entry_layout.addWidget(header)
            desc = QLabel(description)
            desc.setWordWrap(True)
            entry_layout.addWidget(desc)
            content_layout.addWidget(entry)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        close_btn = QPushButton(tr("button.close"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class TeleportTab(QWidget):
    """Points de teleportation pour Snake - experimental (2026-09-27),
    voir notes.md. Repose sur coord_actor (native/speedhack.c,
    install_coord_tracker_hook) : un hook de lecture seule sur une routine
    generique de calcul de distance entre deux acteurs, qui capture le
    pointeur de Snake (confirme stable pendant le deplacement + veritable
    teleportation validee en jeu). Coordonnees absolues (pas relatives a
    l'orientation du joueur) - +0x10 X, +0x14 Y (hauteur, le jeu peut
    rejeter une position invalide sous le sol), +0x18 Z."""

    def __init__(self, live: MGS4Live):
        super().__init__()
        self.live = live
        self.points: list[dict] = self._load_points()

        layout = QVBoxLayout(self)

        warning = QLabel(tr("teleport.warning"))
        warning.setWordWrap(True)
        layout.addWidget(warning)

        pos_row = QHBoxLayout()
        pos_row.addWidget(QLabel(tr("teleport.current_position")))
        self.current_pos_label = QLabel("?")
        pos_row.addWidget(self.current_pos_label)
        pos_row.addStretch(1)
        save_btn = QPushButton(tr("teleport.save_here"))
        save_btn.clicked.connect(self._save_current_position)
        pos_row.addWidget(save_btn)
        layout.addLayout(pos_row)

        # Edition manuelle des 3 axes - ne se resynchronise PAS toute
        # seule pendant que l'utilisateur tape (uniquement via le bouton
        # "Actualiser"), sinon le cycle de rafraichissement general
        # (REFRESH_MS) ecraserait la saisie en cours.
        edit_row = QHBoxLayout()
        self.axis_spins: dict[str, QDoubleSpinBox] = {}
        for axis in ("X", "Y", "Z"):
            edit_row.addWidget(QLabel(f"{axis} :"))
            spin = QDoubleSpinBox()
            spin.setRange(-1_000_000.0, 1_000_000.0)
            spin.setDecimals(2)
            spin.setSingleStep(10.0)
            edit_row.addWidget(spin)
            self.axis_spins[axis] = spin
        refresh_pos_btn = QPushButton(tr("teleport.refresh_from_game"))
        refresh_pos_btn.clicked.connect(self._pull_current_position)
        edit_row.addWidget(refresh_pos_btn)
        apply_pos_btn = QPushButton(tr("teleport.teleport_here"))
        apply_pos_btn.clicked.connect(self._apply_manual_position)
        edit_row.addWidget(apply_pos_btn)
        edit_row.addStretch(1)
        layout.addLayout(edit_row)

        file_row = QHBoxLayout()
        export_btn = QPushButton(tr("teleport.export"))
        export_btn.clicked.connect(self._export_points)
        file_row.addWidget(export_btn)
        import_btn = QPushButton(tr("teleport.import"))
        import_btn.clicked.connect(self._import_points)
        file_row.addWidget(import_btn)
        file_row.addStretch(1)
        layout.addLayout(file_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([tr("table.name"), "X", "Y", "Z"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.doubleClicked.connect(self._teleport_selected)
        layout.addWidget(self.table, 1)

        action_row = QHBoxLayout()
        teleport_btn = QPushButton(tr("teleport.teleport_to_selected"))
        teleport_btn.clicked.connect(self._teleport_selected)
        action_row.addWidget(teleport_btn)
        delete_btn = QPushButton(tr("teleport.delete_selected"))
        delete_btn.clicked.connect(self._delete_selected)
        action_row.addWidget(delete_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self._rebuild_table()

    @staticmethod
    def _load_points() -> list[dict]:
        try:
            with open(TELEPORT_POINTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def _save_points(self):
        try:
            with open(TELEPORT_POINTS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.points, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def _rebuild_table(self):
        self.table.setRowCount(len(self.points))
        for row, point in enumerate(self.points):
            self.table.setItem(row, 0, QTableWidgetItem(point["name"]))
            self.table.setItem(row, 1, QTableWidgetItem(f"{point['x']:.1f}"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{point['y']:.1f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{point['z']:.1f}"))

    def _save_current_position(self):
        pos = self.live.player_position()
        if pos is None:
            warn_dialog(self, tr("teleport.position_not_found_title"),
                                 tr("teleport.position_not_found_body"))
            return
        name, ok = QInputDialog.getText(self, tr("teleport.point_name_title"), tr("teleport.point_name_body"))
        if not ok or not name.strip():
            return
        x, y, z = pos
        self.points.append({"name": name.strip(), "x": x, "y": y, "z": z})
        self._save_points()
        self._rebuild_table()

    def _pull_current_position(self):
        pos = self.live.player_position()
        if pos is None:
            warn_dialog(self, tr("teleport.position_not_found_title"),
                                 tr("teleport.position_not_found_body"))
            return
        x, y, z = pos
        self.axis_spins["X"].setValue(x)
        self.axis_spins["Y"].setValue(y)
        self.axis_spins["Z"].setValue(z)

    def _apply_manual_position(self):
        x = self.axis_spins["X"].value()
        y = self.axis_spins["Y"].value()
        z = self.axis_spins["Z"].value()
        if not self.live.set_player_position(x, y, z):
            warn_dialog(self, tr("teleport.teleport_failed_title"), tr("teleport.snake_pointer_not_found"))

    def _export_points(self):
        path, _ = QFileDialog.getSaveFileName(
            self, tr("teleport.export_dialog_title"), "", "JSON (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.points, f, indent=2, ensure_ascii=False)
        except OSError as exc:
            warn_dialog(self, tr("teleport.export_failed_title"), str(exc))

    def _import_points(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("teleport.import_dialog_title"), "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                imported = json.load(f)
            if not isinstance(imported, list) or not all(
                isinstance(p, dict) and {"name", "x", "y", "z"} <= p.keys() for p in imported
            ):
                raise ValueError(tr("teleport.unexpected_format"))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            warn_dialog(self, tr("teleport.import_failed_title"), str(exc))
            return
        box = QMessageBox(self)
        box.setWindowTitle(tr("teleport.import_title"))
        box.setText(tr("teleport.import_confirm", count=len(imported)))
        yes_btn = box.addButton(tr("button.yes"), QMessageBox.YesRole)
        box.addButton(tr("button.no"), QMessageBox.NoRole)
        box.exec()
        if box.clickedButton() == yes_btn:
            self.points = imported
        else:
            self.points.extend(imported)
        self._save_points()
        self._rebuild_table()

    def _selected_row(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return rows[0].row()

    def _teleport_selected(self):
        row = self._selected_row()
        if row is None:
            return
        point = self.points[row]
        if not self.live.set_player_position(point["x"], point["y"], point["z"]):
            warn_dialog(self, tr("teleport.teleport_failed_title"), tr("teleport.snake_pointer_not_found"))

    def _delete_selected(self):
        row = self._selected_row()
        if row is None:
            return
        del self.points[row]
        self._save_points()
        self._rebuild_table()

    def set_advanced(self, advanced: bool):
        pass  # pas de mode simple/avance distinct ici

    def refresh(self):
        if not (self.live.connected and self.live.sane):
            self.current_pos_label.setText("?")
            self.setEnabled(False)
            return
        self.setEnabled(True)
        pos = self.live.player_position()
        if pos is None:
            self.current_pos_label.setText(tr("teleport.not_captured_yet"))
        else:
            x, y, z = pos
            self.current_pos_label.setText(f"X={x:.1f}  Y={y:.1f}  Z={z:.1f}")


class TrainerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr("window.title", version=TRAINER_VERSION))
        self.resize(1400, 640)
        self.live = MGS4Live()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        top_row = QHBoxLayout()
        self.status_label = QLabel(tr("status.not_connected"))
        self.status_label.setWordWrap(True)
        top_row.addWidget(self.status_label, stretch=1)

        self.advanced_check = QCheckBox(tr("window.advanced_mode"))
        self.advanced_check.toggled.connect(self._on_advanced_toggled)
        top_row.addWidget(self.advanced_check)

        refresh_btn = QPushButton(tr("window.refresh_now"))
        refresh_btn.clicked.connect(self.refresh)
        top_row.addWidget(refresh_btn)
        reconnect_btn = QPushButton(tr("window.reconnect"))
        reconnect_btn.clicked.connect(self.try_attach)
        top_row.addWidget(reconnect_btn)
        help_btn = QPushButton(tr("window.help"))
        help_btn.clicked.connect(lambda: HelpDialog(self).exec())
        top_row.addWidget(help_btn)

        self.language_combo = QComboBox()
        self._language_codes = list(SUPPORTED_LANGUAGES)
        for code in self._language_codes:
            self.language_combo.addItem(SUPPORTED_LANGUAGES[code])
        self.language_combo.setCurrentIndex(self._language_codes.index(_LANG))
        self.language_combo.activated.connect(self._on_language_changed)
        top_row.addWidget(self.language_combo)
        layout.addLayout(top_row)

        # Conteneur dedie (pas juste un layout) pour pouvoir desactiver tout
        # le bloc Drebin d'un coup si le jeu se ferme - voir refresh().
        self.drebin_container = QWidget()
        drebin_row = QHBoxLayout(self.drebin_container)
        drebin_row.setContentsMargins(0, 0, 0, 0)
        drebin_row.addWidget(QLabel(tr("window.drebin_current")))
        self.drebin_actuel_label = QLabel("?")
        self.drebin_actuel_label.setMinimumWidth(80)
        drebin_row.addWidget(self.drebin_actuel_label)
        self.drebin_actuel_spin = QSpinBox()
        self.drebin_actuel_spin.setRange(0, 2_000_000_000)
        self.drebin_actuel_spin.setMinimumWidth(110)
        drebin_row.addWidget(self.drebin_actuel_spin)
        drebin_actuel_ok = QPushButton(tr("button.ok"))
        drebin_actuel_ok.clicked.connect(self._write_drebin_actuel)
        drebin_row.addWidget(drebin_actuel_ok)

        drebin_row.addSpacing(20)
        drebin_row.addWidget(QLabel(tr("window.drebin_sales")))
        self.drebin_ventes_label = QLabel("?")
        self.drebin_ventes_label.setMinimumWidth(80)
        drebin_row.addWidget(self.drebin_ventes_label)
        self.drebin_ventes_spin = QSpinBox()
        self.drebin_ventes_spin.setRange(0, 2_000_000_000)
        self.drebin_ventes_spin.setMinimumWidth(110)
        drebin_row.addWidget(self.drebin_ventes_spin)
        drebin_ventes_ok = QPushButton(tr("button.ok"))
        drebin_ventes_ok.clicked.connect(self._write_drebin_ventes)
        drebin_row.addWidget(drebin_ventes_ok)
        drebin_row.addStretch(1)
        layout.addWidget(self.drebin_container)

        self.tabs = QTabWidget()
        self.item_tabs: list[TableTab | StatsTab | GroupedWeaponsTab] = []

        # Meme ordre d'onglets que MGS4SaveStats (gui_app.py) : Stats,
        # Armes, Objets, OctoCamo, Tenues, Statuettes, Chansons - puis
        # "Non classes" en dernier, propre a ce trainer (n'existe pas dans
        # l'appli principale).
        # drebin_actuel/drebin_total_ventes ont leur propre UI dediee et
        # validee (drebin_row ci-dessus) - exclus d'ici pour ne pas offrir
        # un 2e chemin d'edition qui contournerait la correlation/les
        # garde-fous (deja source de confusion une fois, voir notes.md).
        stats_names = [n for n in mgs4save.STATS if n not in ("drebin_actuel", "drebin_total_ventes")]
        stats_tab = StatsTab(self.live, stats_names)
        self.tabs.addTab(stats_tab, tr("tab.stats_count", count=len(stats_names)))
        self.item_tabs.append(stats_tab)

        vitals_tab = VitalsTab(self.live)
        self.tabs.addTab(vitals_tab, tr("tab.game_state"))
        self.item_tabs.append(vitals_tab)

        # Un seul onglet "Armes", sections empilees par categorie (meme
        # regroupement que WeaponsPanel dans gui_app.py : WEAPON_CATEGORIES/
        # WEAPON_GROUP_ORDER) plutot que des onglets separes par categorie
        # ou un seul gros tableau de 95 lignes. STRUCTURAL_WEAPON_IDS
        # (0x5c/0x5d/0x5e) exclus - confirmes comme jamais de vraies armes,
        # meme raison que STRUCTURAL_ITEM_IDS pour l'onglet Objets. IDs
        # sans nom dans WEAPON_NAMES (jamais identifies) exclus aussi
        # (2026-09-24, demande explicite de l'utilisateur) - la liste ne
        # montre plus que les armes confirmees, plus de lignes "Arme #NN"
        # bruyantes. Meme filtre applique cote MGS4SaveStats
        # (WeaponsPanel dans gui_app.py).
        # Plus de gating "confirmed_ids" depuis la decouverte de la formule
        # lineaire du tableau d'etat (weapon_state_rva, 2026-09-24) : l'etat
        # est desormais fiable pour TOUS les ID, pas seulement les 11
        # scannes individuellement avant. Voir notes.md.
        weapon_ids_by_group: dict[str, list[int]] = {g: [] for g in mgs4save.WEAPON_GROUP_ORDER}
        for weapon_id in range(mgs4save.WEAPON_STATE_COUNT):
            if weapon_id in mgs4save.STRUCTURAL_WEAPON_IDS:
                continue
            if weapon_id not in mgs4save.WEAPON_NAMES:
                continue
            group = mgs4save.WEAPON_CATEGORIES.get(weapon_id, "Non identifiée")
            weapon_ids_by_group[group].append(weapon_id)
        weapon_category_ids = [
            (WEAPON_GROUP_SLUGS.get(g, g), weapon_group_label(g), weapon_ids_by_group[g])
            for g in mgs4save.WEAPON_GROUP_ORDER
        ]
        weapon_names_localized = {i: weapon_name(i) for i in mgs4save.WEAPON_NAMES}

        weapons_tab = GroupedWeaponsTab(
            self.live, weapon_category_ids, weapon_names_localized,
            self.live.read_weapon, self.live.write_weapon,
            [(tr("weapon.state_unowned"), 0), (tr("weapon.state_locked"), 1), (tr("weapon.state_usable"), 2)],
            self.live.read_weapon_ammo, self.live.write_weapon_ammo,
            equip_action=self.live.equip_weapon, equip_available=self.live.read_equippable_weapon_ids,
        )
        total_weapons = sum(len(ids) for _s, _g, ids in weapon_category_ids)
        self.tabs.addTab(weapons_tab, tr("tab.weapons_count", count=total_weapons))
        self.item_tabs.append(weapons_tab)

        for key, label, names in ITEM_CATEGORIES:
            ids = sorted(names)
            tab = TableTab(
                self.live, ids, names, item_unclassified_format(),
                self.live.read_item, self.live.write_item,
                [(tr("item.state_locked"), 65535), (tr("item.state_owned"), 1)],
                quantity_ids=GENERAL_ITEM_QUANTITY_IDS if key == "items" else None,
                binary_lock_value=65535,
                battery_link=(mgs4save.BATTERY_ITEM_ID, 0x06) if key == "items" else None,
                equip_action=self.live.equip_outfit if key == "outfits" else None,
                equip_ids=set(MGS4Live.OUTFIT_EQUIP_INDEX) if key == "outfits" else None,
            )
            self.tabs.addTab(tab, f"{label} ({len(ids)})")
            self.item_tabs.append(tab)
            if key == "items":
                # Onglet "OctoCamo" fusionne juste apres "Objets" (meme
                # position qu'avant), sections FaceCamo/Gilet/Octocamo -
                # voir GroupedItemsTab et le commentaire sur
                # _FACECAMO_NAMES_VISIBLE plus haut.
                # Section Octocamo : les 21 motifs, identifies par leur code
                # (colonne ID), dans l'ordre du menu du jeu. Seuls les 6
                # stockes dans la partie sont modifiables (OCTOCAMO_EDITABLE).
                octocamo_names = {
                    code: octocamo_name(name) for name, code in mgs4save.OCTOCAMO_CODES.items()
                }
                # Lecture seule : Infiltration (= aucun motif) et les bonus
                # lies au compte (Dore/Precommande) ; les motifs donnes
                # d'office sont masquables du menu via le hook du trainer.
                octocamo_readonly = {0, *MGS4Live.OCTOCAMO_ACCOUNT_FLAG_RVAS}
                octocamo_sections = [
                    (tr("group.facecamo"), _FACECAMO_IDS_ORDERED, _FACECAMO_NAMES_VISIBLE,
                     self.live.read_item, self.live.write_item, None,
                     self.live.equip_facecamo, set(MGS4Live.FACECAMO_EQUIP_INDEX)),
                    (tr("group.vest"), sorted(_VEST_NAMES_VISIBLE), _VEST_NAMES_VISIBLE,
                     self.live.read_item, self.live.write_item, None,
                     self.live.equip_vest, set(MGS4Live.VEST_EQUIP_IDS)),
                    (tr("group.octocamo"), list(octocamo_names), octocamo_names,
                     self.live.read_octocamo_state, self.live.write_octocamo_state, octocamo_readonly,
                     self.live.equip_octocamo, set(octocamo_names)),
                    (tr("group.octocamo_saved"), list(MGS4Live.OCTOCAMO_SAVED_SLOTS),
                     {slot: tr("octocamo.slot", n=slot + 1) for slot in MGS4Live.OCTOCAMO_SAVED_SLOTS},
                     self.live.read_octocamo_slot_state, self.live.write_octocamo_slot_state, None,
                     self.live.equip_octocamo_slot, set(MGS4Live.OCTOCAMO_SAVED_SLOTS)),
                ]
                octocamo_tab = OctoCamoTab(
                    self.live, octocamo_sections,
                    self.live.read_item, self.live.write_item,
                    [(tr("item.state_locked"), 65535), (tr("item.state_owned"), 1)],
                    binary_lock_value=65535,
                )
                total_octocamo = sum(len(section[1]) for section in octocamo_sections)
                self.tabs.addTab(octocamo_tab, tr("tab.octocamo_count", count=total_octocamo))
                self.item_tabs.append(octocamo_tab)

        teleport_tab = TeleportTab(self.live)
        self.tabs.addTab(teleport_tab, tr("tab.teleport"))
        self.item_tabs.append(teleport_tab)

        layout.addWidget(self.tabs)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(REFRESH_MS)

        self.try_attach()

    def try_attach(self):
        self.live.attach()
        # Injecte la DLL des l'accrochage (elle demarre a vitesse 1.0, sans
        # effet tant qu'aucun reglage n'est active) : les boutons "Equiper"
        # et les hooks sont prets sans avoir a toucher un reglage avant.
        if self.live.connected and self.live.sane and self.live.pid:
            self.live.speed.ensure_injected(self.live.pid)
        self._apply_connection_state()

    def _apply_connection_state(self):
        """Active/desactive toute l'interface (sauf statut/Rafraichir/
        (Re)connecter) selon que le jeu repond encore ou non - avant ce
        correctif, le statut ne se remettait jamais a jour tout seul apres
        la fermeture du jeu (restait affiche "Connecte" indefiniment).
        Seul le CONTENU des onglets est desactive, pas la barre d'onglets
        (V2.1, demande utilisateur) : on peut parcourir l'interface et lire
        les infobulles sans etre accroche au jeu. Pas de risque : chaque
        ecriture reverifie elle-meme connected/sane avant d'agir."""
        self.status_label.setText(self.live.status)
        ok = self.live.connected and self.live.sane
        self.drebin_container.setEnabled(ok)
        for i in range(self.tabs.count()):
            self.tabs.widget(i).setEnabled(ok)

    def _on_advanced_toggled(self, checked: bool):
        for tab in self.item_tabs:
            tab.set_advanced(checked)

    def _on_language_changed(self, index: int):
        code = self._language_codes[index]
        if code == _LANG:
            return
        # QMessageBox.question() affiche ses boutons Oui/Non standards dans
        # la langue par defaut de Qt (pas la notre) - boutons personnalises
        # via tr() pour eviter ce decalage.
        box = QMessageBox(self)
        box.setWindowTitle(tr("language.restart_title"))
        box.setText(tr("language.restart_body", language=SUPPORTED_LANGUAGES[code]))
        yes_btn = box.addButton(tr("button.yes"), QMessageBox.YesRole)
        box.addButton(tr("button.no"), QMessageBox.NoRole)
        box.exec()
        if box.clickedButton() != yes_btn:
            self.language_combo.setCurrentIndex(self._language_codes.index(_LANG))
            return
        set_language(code)
        restart_trainer()

    def refresh(self):
        if self.live.connected and not self.live.check_alive():
            self._apply_connection_state()
        for tab in self.item_tabs:
            tab.refresh()
        if not (self.live.connected and self.live.sane):
            self.drebin_actuel_label.setText("?")
            self.drebin_ventes_label.setText("?")
            return
        try:
            actuel = self.live.read_drebin_actuel()
            ventes = self.live.read_drebin_total_ventes()
        except OSError:
            self.drebin_actuel_label.setText("?")
            self.drebin_ventes_label.setText("?")
            return
        self.drebin_actuel_label.setText(str(actuel))
        self.drebin_ventes_label.setText(str(ventes))
        if not self.drebin_actuel_spin.hasFocus():
            self.drebin_actuel_spin.blockSignals(True)
            self.drebin_actuel_spin.setValue(actuel)
            self.drebin_actuel_spin.blockSignals(False)
        if not self.drebin_ventes_spin.hasFocus():
            self.drebin_ventes_spin.blockSignals(True)
            self.drebin_ventes_spin.setValue(ventes)
            self.drebin_ventes_spin.blockSignals(False)

    def _write_drebin_actuel(self):
        if not (self.live.connected and self.live.sane):
            return
        try:
            ok = self.live.write_drebin_actuel(self.drebin_actuel_spin.value())
        except OSError:
            self.drebin_actuel_label.setText("erreur ecriture")
            return
        if not ok:
            self.drebin_actuel_label.setText("invalide (< ventes)")

    def _write_drebin_ventes(self):
        if not (self.live.connected and self.live.sane):
            return
        try:
            ok = self.live.write_drebin_total_ventes(self.drebin_ventes_spin.value())
        except OSError:
            self.drebin_ventes_label.setText("erreur ecriture")
            return
        if not ok:
            self.drebin_ventes_label.setText("invalide (actuel < 0)")

    def closeEvent(self, event):
        self.live.detach()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(TRAINER_ICON))
    window = TrainerWindow()
    window.setWindowIcon(QIcon(TRAINER_ICON))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
