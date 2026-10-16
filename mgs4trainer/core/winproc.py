"""Acces au processus Windows (ctypes) : recherche, lecture/ecriture memoire."""
import ctypes
import struct
from ctypes import wintypes


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
MEM_RESERVE = 0x2000
MEM_FREE = 0x10000
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

    def alloc_near(self, target: int, size: int = 0x1000) -> int:
        """Memoire executable a moins de ~2 Go de `target` (pour un saut
        rel32 depuis le code du jeu) ; 0 si aucune place libre."""
        kernel32.VirtualAllocEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t,
                                            wintypes.DWORD, wintypes.DWORD]
        kernel32.VirtualAllocEx.restype = wintypes.LPVOID
        granularity = 0x10000
        reach = 0x7F000000
        mbi = MEMORY_BASIC_INFORMATION()
        # D'abord au-dessus de `target` (juste apres le module), puis en
        # dessous : la place la plus proche, loin de la limite du saut.
        for start, stop in ((target, target + reach), (max(target - reach, granularity), target)):
            address = start & ~(granularity - 1)
            while address < stop - size:
                if not kernel32.VirtualQueryEx(self.handle, ctypes.c_void_p(address), ctypes.byref(mbi),
                                               ctypes.sizeof(mbi)):
                    break
                region = mbi.BaseAddress or 0
                end = region + (mbi.RegionSize or granularity)
                if mbi.State == MEM_FREE:
                    candidate = (max(region, address) + granularity - 1) & ~(granularity - 1)
                    if candidate + size <= min(end, stop):
                        result = kernel32.VirtualAllocEx(self.handle, candidate, size, MEM_COMMIT | MEM_RESERVE,
                                                         PAGE_EXECUTE_READWRITE)
                        if result:
                            return result
                address = end
        return 0

    def allocation_blocks(self, address: int):
        """Contenu (adresse, octets) des plages commises et accessibles en
        ecriture de l'allocation qui contient `address` (un tas du jeu) -
        bien plus rapide que _writable_regions sur toute la memoire."""
        mbi = MEMORY_BASIC_INFORMATION()
        size = ctypes.sizeof(mbi)
        if not kernel32.VirtualQueryEx(self.handle, ctypes.c_void_p(address), ctypes.byref(mbi), size):
            return
        allocation = mbi.AllocationBase
        address = allocation
        while kernel32.VirtualQueryEx(self.handle, ctypes.c_void_p(address), ctypes.byref(mbi), size):
            if mbi.AllocationBase != allocation:
                break
            base = mbi.BaseAddress or 0
            region_size = mbi.RegionSize or 0x1000
            if (mbi.State == MEM_COMMIT
                    and (mbi.Protect & WRITABLE_PROTECT) and not (mbi.Protect & PAGE_GUARD)):
                try:
                    yield base, self.read_bytes(base, region_size)
                except OSError:
                    pass
            address = base + region_size

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
