"""Injection de la DLL native et memoire partagee avec elle (SpeedController)."""
import ctypes
import os
import threading
import time
from ctypes import wintypes

from mgs4trainer.core.paths import _bundled_path
from mgs4trainer.core.winproc import (
    MEM_COMMIT, PAGE_READWRITE, PROCESS_QUERY_INFORMATION, PROCESS_VM_OPERATION,
    PROCESS_VM_READ, PROCESS_VM_WRITE, find_module_base, kernel32,
)


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

    def set_machine_kill(self, enabled: bool) -> bool:
        """Un coup, un mort sur les Gekko et les tanks (machine_kill, offset
        392), independant de one_shot_kill pour marcher aussi en Non letal.
        Sans effet avec une DLL anterieure deja injectee (elle lit encore
        one_shot_kill, toujours pose en Letal)."""
        return self._write_u8_at(392, 1 if enabled else 0)

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

    # Offsets 32 a 61 : reserves (anciens hooks de suivi des boss et des
    # coordonnees, retires le 2026-10-12, voir native/speedhack.c).

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
