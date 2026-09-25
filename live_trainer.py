"""Trainer de recherche : lit/ecrit en direct la memoire du processus
mgs4.exe pour identifier les IDs encore inconnus des tableaux
objets/armes, sans avoir a save/reload a chaque test.

PAS un outil pour l'appli finale (MGS4SaveStats.spec ne l'embarque pas,
gui_app.py ne l'importe pas) - script de dev separe, a lancer a la main
pendant une session de jeu :

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
import os
import struct
import sys
from ctypes import wintypes

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
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
# MGS4.CT (licence perso, fichier fourni par l'utilisateur - pas de
# provenance/licence externe a documenter) via deux fonctions assembleur
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


class MGS4Live:
    def __init__(self):
        self.proc: ProcessHandle | None = None
        self.base: int | None = None
        self.linkvarbuf: int | None = None
        self.varbuf: int | None = None
        self.sane = False
        self.status = "Non connecte"

    def attach(self) -> bool:
        self.detach()
        pid = find_pid(PROCESS_NAME)
        if pid is None:
            self.status = f"{PROCESS_NAME} introuvable - lance le jeu"
            return False
        base = find_module_base(pid, PROCESS_NAME)
        if base is None:
            self.status = "Module mgs4.exe introuvable dans le process"
            return False
        try:
            self.proc = ProcessHandle(pid)
            self.base = base
            self.linkvarbuf = struct.unpack("<Q", self.proc.read_bytes(base + LINKVARBUF_POINTER_RVA, 8))[0]
            self.varbuf = struct.unpack("<Q", self.proc.read_bytes(base + VARBUF_POINTER_RVA, 8))[0]
            if self.varbuf == 0:
                self.status = "Pointeur varbuf nul (pas encore de partie chargee ?)"
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
                    self.status = (
                        f"Verification echouee : item[{item_id:#04x}] = {raw} "
                        "(attendu 0 sur toutes les saves connues) - chaine de "
                        "pointeurs probablement invalide pour cette build, "
                        "ecriture desactivee"
                    )
                    return False
        except OSError as e:
            self.sane = False
            self.status = f"Verification impossible : {e}"
            return False
        self.sane = True
        self.status = f"Connecte (varbuf={self.varbuf:#x}), verification OK"
        return True

    def detach(self):
        if self.proc:
            self.proc.close()
            self.proc = None
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
            self.status = f"{PROCESS_NAME} ferme ou inaccessible - reconnecte-toi"
            return False
        return True

    @property
    def connected(self) -> bool:
        return self.proc is not None and self.varbuf is not None

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
# coince entre Campbell 0x27 et Drebin 0x29). "Octocamo" (camouflages
# de base, motifs) n'a jamais eu d'ID retrouve (voir SPECIAL_CAMO_NAMES
# infirme dans mgs4save.py) - section vide pour l'instant, cf.
# CAMO_GROUPS/group_totals dans gui_app.py qui a le meme trou.
_FACECAMO_NAMES_VISIBLE: dict[int, str] = dict(mgs4save.FACECAMO_NAMES)
_FACECAMO_IDS_ORDERED: list[int] = sorted(
    _FACECAMO_NAMES_VISIBLE, key=lambda i: mgs4save.FACECAMO_SORT_ORDER.get(i, 999)
)
_VEST_NAMES_VISIBLE: dict[int, str] = {k: v for k, v in mgs4save.VEST_NAMES.items() if isinstance(k, int)}
_OCTOCAMO_BASE_NAMES: dict[int, str] = {}  # jamais trouve, voir commentaire ci-dessus

_CLASSIFIED_IDS = (
    set(mgs4save.GENERAL_ITEM_NAMES) | set(_VEST_NAMES_VISIBLE) | set(_FACECAMO_NAMES_VISIBLE)
    | set(mgs4save.OUTFIT_NAMES) | set(mgs4save.FIGURE_NAMES) | set(mgs4save.SONG_NAMES)
)
_NON_CLASSES_NAMES: dict[int, str] = {
    i: f"Objet #{i:02d}" for i in range(mgs4save.ITEM_STATE_COUNT) if i not in _CLASSIFIED_IDS
}

# Objets generaux confirmes structurels (jamais un vrai objet, voir
# STRUCTURAL_ITEM_IDS dans mgs4save.py - 0x00 reconfirme le 2026-09-23,
# force a 1 en live sans aucun effet visible en jeu) - masques ici aussi,
# comme deja fait pour l'onglet Objets de l'appli principale, pour ne pas
# polluer les tests "a l'aveugle" avec des cases qui ne font jamais rien.
_GENERAL_ITEMS_VISIBLE = {
    k: v for k, v in mgs4save.GENERAL_ITEM_NAMES.items() if k not in mgs4save.STRUCTURAL_ITEM_IDS
}

# Objets empilables (quantite en stock), pas de sens "Obtenu"=1 fige - voir
# mgs4save.py ligne ~616 ("les 5 premiers IDs ... sont des COMPTEURS").
GENERAL_ITEM_QUANTITY_IDS = {0x01, 0x02, 0x03, 0x04, 0x05}  # Ration/Nouilles/Regain/Pentazemine/Compresse

# (label d'onglet, dict id->nom, IDs verrouilles a 65535/obtenus a 1 comme
# les chansons/statuettes/tenues/camos - PAS le tableau d'armes, qui a sa
# propre convention 0/1/2, voir TrainerWindow)
# FaceCamo/Gilet ne sont plus ici : fusionnes dans l'onglet "OctoCamo"
# dedie (GroupedItemsTab), construit a part dans TrainerWindow.
ITEM_CATEGORIES: list[tuple[str, dict[int, str]]] = [
    ("Objets", _GENERAL_ITEMS_VISIBLE),
    ("Tenues", mgs4save.OUTFIT_NAMES),
    ("Statuettes", mgs4save.FIGURE_NAMES),
    ("Chansons", mgs4save.SONG_NAMES),
    ("Non classes", _NON_CLASSES_NAMES),
]


# ---------------------------------------------------------------------------
# Interface Qt
# ---------------------------------------------------------------------------

REFRESH_MS = 750


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
                 advanced_only_ids: set[int] | None = None):
        super().__init__()
        self.live = live
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
            filter_row.addWidget(QLabel("Filtre (ID ou nom) :"))
            self.filter_edit.textChanged.connect(self._apply_filter)
            filter_row.addWidget(self.filter_edit)
            layout.addLayout(filter_row)

        headers = ["ID", "Nom", "Etat", "Valeur brute"]
        headers.append("Definir (brut)")
        if self.has_quantity:
            headers.append("Quantite")
        if self.has_ammo:
            headers.append("Munitions")
        self.col_state = 2
        self.col_value = 3
        self.col_control = 4
        col = 5
        self.col_control_quantity = col if self.has_quantity else None
        col += 1 if self.has_quantity else 0
        self.col_control_ammo = col if self.has_ammo else None
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
        apply_btn = QPushButton("OK")
        apply_btn.clicked.connect(lambda _checked=False, i=item_id, s=spin: self._write(i, s.value()))
        control_layout.addWidget(apply_btn)
        control.setLayout(control_layout)
        control.adjustSize()
        if is_unconfirmed_row:
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
                qty_ok = QPushButton("OK")
                qty_ok.clicked.connect(lambda _checked=False, i=item_id, s=qty_spin: self._write(i, s.value() - 1))
            else:
                qty_spin.setRange(0, 0xFFFF)
                qty_ok = QPushButton("OK")
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
            ammo_ok = QPushButton("OK")
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
    BINARY_CATEGORIES = {"Accessoire"}

    # ID masques en mode simple (visibles seulement en mode avance) car
    # dangereux a manipuler par un utilisateur non averti - voir
    # advanced_only_ids sur TableTab. "Destabil.SOP" (0x44) fait PLANTER
    # le jeu s'il est equipe (confirme 2 fois, 2026-09-24) - objet
    # probablement pas prevu pour etre reellement utilise en solo, voir
    # notes.md.
    DANGEROUS_IDS = {0x44}

    def __init__(self, live: MGS4Live, category_ids: list[tuple[str, list[int]]],
                 names: dict[int, str], reader, writer, quick_states: list[tuple[str, int]],
                 ammo_reader, ammo_writer):
        super().__init__()
        self.sub_tabs: list[tuple[QLabel, TableTab]] = []

        layout = QVBoxLayout(self)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filtre (ID ou nom) :"))
        self.filter_edit = QLineEdit()
        self.filter_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.filter_edit)
        layout.addLayout(filter_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        for label, ids in category_ids:
            if not ids:
                continue
            header = QLabel(f"{label} ({len(ids)})")
            header.setStyleSheet("font-weight: bold; font-size: 13px; margin-top: 6px;")
            inner_layout.addWidget(header)
            is_binary = label in self.BINARY_CATEGORIES
            section_quick_states = [("Non poss.", 0), ("Utilisable", 2)] if is_binary else quick_states
            tab = TableTab(
                live, ids, names, "Arme #{:02d}", reader, writer, section_quick_states,
                ammo_reader=ammo_reader, ammo_writer=ammo_writer,
                binary_lock_value=0 if is_binary else None,
                show_filter=False, fit_height=True,
                advanced_only_ids=self.DANGEROUS_IDS,
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
        filter_row.addWidget(QLabel("Filtre (ID ou nom) :"))
        self.filter_edit = QLineEdit()
        self.filter_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.filter_edit)
        layout.addLayout(filter_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        for label, ids, names in category_ids:
            if not ids:
                continue
            header = QLabel(f"{label} ({len(ids)})")
            header.setStyleSheet("font-weight: bold; font-size: 13px; margin-top: 6px;")
            inner_layout.addWidget(header)
            tab = TableTab(
                live, ids, names, "Objet #{:02d}", reader, writer, quick_states,
                binary_lock_value=binary_lock_value,
                show_filter=False, fit_height=True,
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
    ("Combat", [
        ("kills_total", "Kills (total)"),
        ("headshots", "Headshots"),
        ("knife_kills", "Kills au couteau"),
        ("knife_knockouts", "KO au couteau"),
        ("cqc", "CQC"),
        ("combat_high", "Poussees d'adrenaline"),
    ]),
    ("Infiltration", [
        ("alertes", "Alertes"),
        ("continues", "Continues"),
        ("holdups", "Hold-ups"),
        ("body_searches", "Fouilles corporelles"),
        ("praises", "Compliments recus"),
    ]),
    ("Mouvement", [
        ("roulades_avant", "Roulades en avant"),
        ("roulades_cote", "Roulades de cote"),
    ]),
    ("Objets", [
        ("soins_utilises", "Objets de soin utilises"),
        ("objets_speciaux_bitmask", "Objets speciaux utilises (bitmask brut)"),
        ("objets_donnes_milices", "Objets donnes aux milices"),
        ("weapon_pickups", "Armes ramassees"),
        ("item_pickups", "Objets ramasses"),
        ("syringe_uses", "Utilisations seringue"),
        ("scanning_plug_uses", "Utilisations Scanning Plug"),
        ("playboy_pages", "Pages Playboy tournees"),
        ("emotion_magazine_pages", "Pages Emotion tournees"),
        ("posters_vus", "Posters vus (incertain, voir notes.md)"),
    ]),
    ("Flashbacks", [
        ("flashbacks_vues", "Flashbacks declenches (occurrences)"),
    ]),
    ("Temps (HH:MM:SS, approx.)", [
        ("temps_jeu_frames", "Temps de jeu"),
        ("temps_accroupi_frames", "Temps accroupi"),
        ("temps_allonge_frames", "Temps allonge"),
        ("temps_mur_frames", "Temps contre un mur"),
        ("temps_boite_carton_frames", "Temps boite carton"),
        ("temps_baril_frames", "Temps baril"),
    ]),
]


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
        ("Non", 0),
        ("Bandana", 1),
        ("Camouflage optique", 2),
        ("Les deux", 3),
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
        note = QLabel(
            "Champs de stats globales (linkvarbuf) - fiabilite confirmee individuellement "
            "seulement pour drebin_actuel pour l'instant, le reste est a verifier au cas par cas."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filtre (nom) :"))
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
            self._add_section(inner_layout, "Autres", [(n, n) for n in names if n in remaining])

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
        value_header = "Valeur (H : M : S)" if all_time_fields else "Valeur"

        table = QTableWidget(len(fields), 2)
        table.setHorizontalHeaderLabels(["Champ", value_header])
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
        for i, (maximum, tooltip) in enumerate(((99999, "Heures"), (59, "Minutes"), (59, "Secondes"))):
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

    def __init__(self, live: MGS4Live):
        super().__init__()
        self.live = live
        self.value_labels: dict[str, QLabel] = {}
        self.sliders: dict[str, QSlider] = {}
        self.lock_checks: dict[str, QCheckBox] = {}
        self.locked_percents: dict[str, float] = {}

        layout = QVBoxLayout(self)

        alert_row = QHBoxLayout()
        alert_row.addWidget(QLabel("Etat d'alerte (lecture seule) :"))
        self.alert_label = QLabel("?")
        self.alert_label.setStyleSheet("font-weight: bold;")
        alert_row.addWidget(self.alert_label)
        alert_row.addStretch(1)
        layout.addLayout(alert_row)

        names = list(VITALS)
        self.table = QTableWidget(len(names), 3)
        self.table.setHorizontalHeaderLabels(["Champ", "Valeur live", "Verrouiller"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setMinimumSectionSize(90)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        for row, name in enumerate(names):
            self._build_row(row, name)

        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(2)

    def _build_row(self, row: int, name: str):
        name_item = QTableWidgetItem(name)
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

    def set_advanced(self, advanced: bool):
        pass  # pas de mode simple/avance distinct ici

    def refresh(self):
        if not (self.live.connected and self.live.sane):
            for label in self.value_labels.values():
                label.setText("?")
            self.alert_label.setText("?")
            return

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
            self.alert_label.setText(ALERT_STATE_NAMES.get(alert, f"Inconnu ({alert})"))
        except OSError:
            self.alert_label.setText("?")


TRAINER_VERSION = "V1.0"

TRAINER_HELP_TEXT = (
    "Ce trainer lit et ÉCRIT en direct la mémoire du process mgs4.exe "
    "pendant une partie en cours (pas le fichier de sauvegarde) : force "
    "n'importe quel champ déjà identifié (armes, objets, stats, "
    "vie/stamina/stress/batterie Solid Eye...) et sert aussi d'outil de "
    "recherche pour les ID encore inconnus.\n\n"
    "Nécessite que MGS4 (version Steam) soit lancé avec une partie "
    "chargée — \"(Re)connecter\" tente de s'attacher au process en "
    "cours.\n\n"
    "Calibré et testé sur la version Steam 1.4.1 du JEU (à ne pas "
    "confondre avec la version ci-dessus, qui est celle du trainer). "
    "Les adresses mémoire dépendent de la version exacte de l'exe : une mise à jour "
    "du jeu peut toutes les décaler d'un coup (déjà arrivé le "
    "2026-09-24, corrigé depuis). Si une future mise à jour casse la "
    "détection (bloqué sur \"Non connecté\", ou le contrôle de "
    "cohérence échoue en boucle après reconnexion), voir notes.md pour "
    "la méthode de recalibration.\n\n"
    "Usage solo uniquement, à tes risques : ce n'est pas un outil "
    "officiel, il lit/écrit dans la mémoire d'un autre processus, ce "
    "qu'un antivirus peut signaler à tort. Certains champs restent en "
    "confiance basse ou pas encore testés individuellement (voir "
    "notes.md au cas par cas). Le \"Mode avancé\" masque par défaut les "
    "objets dont le comportement en jeu est incertain ou dangereux "
    "(ex. un objet dont l'équipement fait planter le jeu, confirmé à "
    "plusieurs reprises) — à n'activer qu'en connaissance de cause."
)

# Meme convention que APP_CHANGELOG dans gui_app.py (liste de tuples
# version/date/description), mais pour le trainer - premiere publication,
# une seule entree pour l'instant.
TRAINER_CHANGELOG = [
    ("V1.0", "25 septembre 2026",
     "Première publication : lecture/écriture mémoire live (formule "
     "linéaire pour l'état des armes, tables munitions/objets/"
     "accessoires) pour toutes les entrées déjà identifiées côté "
     "MGS4SaveStats. Onglet \"État de jeu\" (vie, stamina, stress, "
     "batterie Solid Eye, santé Metal Gear REX en curseur %, "
     "verrouillage pour vie/endurance infinies, état d'alerte en "
     "lecture seule). Onglet Stats réorganisé en mini-tables par thème, "
     "champs de temps en HH:MM:SS, select dédié pour les objets "
     "spéciaux utilisés. Les munitions d'une arme non \"Utilisable\" "
     "sont masquées plutôt que d'afficher la sentinelle 65535, "
     "corrigée automatiquement à 10 dès que l'arme devient utilisable. "
     "\"Mode avancé\" masquant par défaut les objets internes/de debug "
     "dangereux."),
]


class HelpDialog(QDialog):
    """Popup d'aide : explication rapide, compatibilite, avertissements,
    changelog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aide")
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

        changelog_title = QLabel("CHANGELOG")
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

        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class TrainerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"MGS4 - Trainer de recherche (memoire live) - {TRAINER_VERSION}")
        self.resize(1400, 640)
        self.live = MGS4Live()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        top_row = QHBoxLayout()
        self.status_label = QLabel("Non connecte")
        self.status_label.setWordWrap(True)
        top_row.addWidget(self.status_label, stretch=1)

        self.advanced_check = QCheckBox("Mode avance (valeurs brutes)")
        self.advanced_check.toggled.connect(self._on_advanced_toggled)
        top_row.addWidget(self.advanced_check)

        refresh_btn = QPushButton("Rafraichir maintenant")
        refresh_btn.clicked.connect(self.refresh)
        top_row.addWidget(refresh_btn)
        reconnect_btn = QPushButton("(Re)connecter")
        reconnect_btn.clicked.connect(self.try_attach)
        top_row.addWidget(reconnect_btn)
        help_btn = QPushButton("Aide")
        help_btn.clicked.connect(lambda: HelpDialog(self).exec())
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        # Conteneur dedie (pas juste un layout) pour pouvoir desactiver tout
        # le bloc Drebin d'un coup si le jeu se ferme - voir refresh().
        self.drebin_container = QWidget()
        drebin_row = QHBoxLayout(self.drebin_container)
        drebin_row.setContentsMargins(0, 0, 0, 0)
        drebin_row.addWidget(QLabel("Points Drebin - Actuel :"))
        self.drebin_actuel_label = QLabel("?")
        self.drebin_actuel_label.setMinimumWidth(80)
        drebin_row.addWidget(self.drebin_actuel_label)
        self.drebin_actuel_spin = QSpinBox()
        self.drebin_actuel_spin.setRange(0, 2_000_000_000)
        self.drebin_actuel_spin.setMinimumWidth(110)
        drebin_row.addWidget(self.drebin_actuel_spin)
        drebin_actuel_ok = QPushButton("OK")
        drebin_actuel_ok.clicked.connect(self._write_drebin_actuel)
        drebin_row.addWidget(drebin_actuel_ok)

        drebin_row.addSpacing(20)
        drebin_row.addWidget(QLabel("Ventes (cumul) :"))
        self.drebin_ventes_label = QLabel("?")
        self.drebin_ventes_label.setMinimumWidth(80)
        drebin_row.addWidget(self.drebin_ventes_label)
        self.drebin_ventes_spin = QSpinBox()
        self.drebin_ventes_spin.setRange(0, 2_000_000_000)
        self.drebin_ventes_spin.setMinimumWidth(110)
        drebin_row.addWidget(self.drebin_ventes_spin)
        drebin_ventes_ok = QPushButton("OK")
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
        self.tabs.addTab(stats_tab, f"Stats ({len(stats_names)})")
        self.item_tabs.append(stats_tab)

        vitals_tab = VitalsTab(self.live)
        self.tabs.addTab(vitals_tab, "Etat de jeu")
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
        weapon_category_ids = [(g, weapon_ids_by_group[g]) for g in mgs4save.WEAPON_GROUP_ORDER]

        weapons_tab = GroupedWeaponsTab(
            self.live, weapon_category_ids, mgs4save.WEAPON_NAMES,
            self.live.read_weapon, self.live.write_weapon,
            [("Non poss.", 0), ("Verrouillée", 1), ("Utilisable", 2)],
            self.live.read_weapon_ammo, self.live.write_weapon_ammo,
        )
        total_weapons = sum(len(ids) for _g, ids in weapon_category_ids)
        self.tabs.addTab(weapons_tab, f"Armes ({total_weapons})")
        self.item_tabs.append(weapons_tab)

        for label, names in ITEM_CATEGORIES:
            ids = sorted(names)
            tab = TableTab(
                self.live, ids, names, "Objet #{:02d}",
                self.live.read_item, self.live.write_item,
                [("Verrouillé", 65535), ("Obtenu", 1)],
                quantity_ids=GENERAL_ITEM_QUANTITY_IDS if label == "Objets" else None,
                binary_lock_value=65535,
                battery_link=(mgs4save.BATTERY_ITEM_ID, 0x06) if label == "Objets" else None,
            )
            self.tabs.addTab(tab, f"{label} ({len(ids)})")
            self.item_tabs.append(tab)
            if label == "Objets":
                # Onglet "OctoCamo" fusionne juste apres "Objets" (meme
                # position qu'avant), sections FaceCamo/Gilet/Octocamo -
                # voir GroupedItemsTab et le commentaire sur
                # _FACECAMO_NAMES_VISIBLE plus haut.
                octocamo_sections = [
                    ("FaceCamo", _FACECAMO_IDS_ORDERED, _FACECAMO_NAMES_VISIBLE),
                    ("Gilet", sorted(_VEST_NAMES_VISIBLE), _VEST_NAMES_VISIBLE),
                    ("Octocamo", sorted(_OCTOCAMO_BASE_NAMES), _OCTOCAMO_BASE_NAMES),
                ]
                octocamo_tab = GroupedItemsTab(
                    self.live, octocamo_sections,
                    self.live.read_item, self.live.write_item,
                    [("Verrouillé", 65535), ("Obtenu", 1)],
                    binary_lock_value=65535,
                )
                total_octocamo = sum(len(ids) for _l, ids, _n in octocamo_sections)
                self.tabs.addTab(octocamo_tab, f"OctoCamo ({total_octocamo})")
                self.item_tabs.append(octocamo_tab)

        layout.addWidget(self.tabs)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(REFRESH_MS)

        self.try_attach()

    def try_attach(self):
        self.live.attach()
        self._apply_connection_state()

    def _apply_connection_state(self):
        """Active/desactive toute l'interface (sauf statut/Rafraichir/
        (Re)connecter) selon que le jeu repond encore ou non - avant ce
        correctif, le statut ne se remettait jamais a jour tout seul apres
        la fermeture du jeu (restait affiche "Connecte" indefiniment)."""
        self.status_label.setText(self.live.status)
        ok = self.live.connected and self.live.sane
        self.drebin_container.setEnabled(ok)
        self.tabs.setEnabled(ok)

    def _on_advanced_toggled(self, checked: bool):
        for tab in self.item_tabs:
            tab.set_advanced(checked)

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
