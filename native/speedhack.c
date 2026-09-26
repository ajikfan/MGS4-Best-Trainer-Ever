/* speedhack.c - DLL injectee dans mgs4.exe pour controler la vitesse du
 * jeu (ralenti/accelere) et non juste le pauser (deja possible sans
 * injection via NtSuspendProcess, voir live_trainer.py).
 *
 * Principe : patch l'IAT (Import Address Table) de TOUS les modules
 * charges dans le process (pas seulement l'exe principal - un moteur de
 * jeu/middleware separe a sa propre IAT) pour rediriger les fonctions de
 * mesure du temps vers des versions "hookees" qui renvoient un temps
 * virtuel avancant plus vite/lentement que le temps reel, selon un
 * multiplicateur lu dans une memoire partagee nommee ("Local\
 * MGS4TrainerSpeedHack") que le trainer Python (process externe) met a
 * jour a chaque mouvement du curseur.
 *
 * CONFIRME FONCTIONNEL EN JEU (2026-09-26), ralenti ET accelere (0.3x et
 * 2.0x testes, visibles). Chemin qui a marche : hook simultane de
 * QueryPerformanceCounter (kernel32) et timeGetTime (winmm), poses sur
 * TOUS les modules charges (pas juste l'exe - un test limite a l'exe
 * principal seul n'avait aucun effet, confirmant qu'au moins une des 2
 * API est bien appelee depuis une DLL du jeu separee). GetTickCount/
 * GetTickCount64 (kernel32) sont aussi hookes par precaution mais ne
 * semblent pas utilises par le moteur (present dans le diagnostic mais
 * scenario a l'origine du sans-effet initial explique par les 2
 * premiers). Diagnostic (bitmask + compteurs de sites patches) publie
 * dans la memoire partagee pour le debug futur.
 *
 * Reste charge/hooke en permanence une fois injecte (pas de dechargement
 * propre) - remettre le multiplicateur a 1.0 suffit a redonner une
 * vitesse normale, inutile de decharger la DLL.
 */

#include <windows.h>
#include <tlhelp32.h>
#include <string.h>

/* Memoire partagee : [0] double vitesse (1.0 = normal), [8] uint32
 * bitmask diagnostic des hooks effectivement poses (bit0=QPC,
 * bit1=timeGetTime, bit2=GetTickCount, bit3=GetTickCount64), [12]/[16]
 * uint32 nombre total de sites patches (peut depasser 1 si plusieurs DLL
 * du jeu importent la meme fonction chacune via leur propre IAT). */
#pragma pack(push, 1)
typedef struct {
    double speed;
    UINT32 patched_mask;
    UINT32 qpc_hit_count;
    UINT32 timegettime_hit_count;
} SharedState;
#pragma pack(pop)

#define HOOK_QPC 0x1
#define HOOK_TIMEGETTIME 0x2
#define HOOK_GETTICKCOUNT 0x4
#define HOOK_GETTICKCOUNT64 0x8

static CRITICAL_SECTION g_lock;
static HANDLE g_map = NULL;
static volatile SharedState *g_shared = NULL;

static double read_speed(void) {
    if (g_shared) {
        double s = g_shared->speed;
        /* Garde-fou : une valeur absurde (memoire partagee pas encore
         * initialisee, ou corrompue) retombe sur la vitesse normale
         * plutot que de figer/emballer le jeu. */
        if (s >= 0.01 && s <= 10.0) {
            return s;
        }
    }
    return 1.0;
}

static void mark_patched(UINT32 bit) {
    if (g_shared) {
        g_shared->patched_mask |= bit;
    }
}

/* --- Hook QueryPerformanceCounter (kernel32) --- */
typedef BOOL(WINAPI *QPC_t)(LARGE_INTEGER *);
static QPC_t g_real_qpc = NULL;
static LONGLONG g_qpc_last = 0, g_qpc_virtual = 0;

static BOOL WINAPI HookedQPC(LARGE_INTEGER *out) {
    LARGE_INTEGER real;
    g_real_qpc(&real);
    EnterCriticalSection(&g_lock);
    if (g_qpc_last == 0) {
        g_qpc_virtual = real.QuadPart;
    } else {
        g_qpc_virtual += (LONGLONG)((double)(real.QuadPart - g_qpc_last) * read_speed());
    }
    g_qpc_last = real.QuadPart;
    out->QuadPart = g_qpc_virtual;
    LeaveCriticalSection(&g_lock);
    return TRUE;
}

/* --- Hook timeGetTime (winmm) --- */
typedef DWORD(WINAPI *TimeGetTime_t)(void);
static TimeGetTime_t g_real_timegettime = NULL;
static DWORD g_tgt_last = 0, g_tgt_virtual = 0;

static DWORD WINAPI HookedTimeGetTime(void) {
    DWORD real = g_real_timegettime();
    EnterCriticalSection(&g_lock);
    if (g_tgt_last == 0) {
        g_tgt_virtual = real;
    } else {
        g_tgt_virtual += (DWORD)((double)(real - g_tgt_last) * read_speed());
    }
    g_tgt_last = real;
    DWORD result = g_tgt_virtual;
    LeaveCriticalSection(&g_lock);
    return result;
}

/* --- Hook GetTickCount (kernel32) --- */
typedef DWORD(WINAPI *GetTickCount_t)(void);
static GetTickCount_t g_real_gettickcount = NULL;
static DWORD g_gtc_last = 0, g_gtc_virtual = 0;

static DWORD WINAPI HookedGetTickCount(void) {
    DWORD real = g_real_gettickcount();
    EnterCriticalSection(&g_lock);
    if (g_gtc_last == 0) {
        g_gtc_virtual = real;
    } else {
        g_gtc_virtual += (DWORD)((double)(real - g_gtc_last) * read_speed());
    }
    g_gtc_last = real;
    DWORD result = g_gtc_virtual;
    LeaveCriticalSection(&g_lock);
    return result;
}

/* --- Hook GetTickCount64 (kernel32) --- */
typedef ULONGLONG(WINAPI *GetTickCount64_t)(void);
static GetTickCount64_t g_real_gettickcount64 = NULL;
static ULONGLONG g_gtc64_last = 0, g_gtc64_virtual = 0;

static ULONGLONG WINAPI HookedGetTickCount64(void) {
    ULONGLONG real = g_real_gettickcount64();
    EnterCriticalSection(&g_lock);
    if (g_gtc64_last == 0) {
        g_gtc64_virtual = real;
    } else {
        g_gtc64_virtual += (ULONGLONG)((double)(real - g_gtc64_last) * read_speed());
    }
    g_gtc64_last = real;
    ULONGLONG result = g_gtc64_virtual;
    LeaveCriticalSection(&g_lock);
    return result;
}

/* Parcourt la table d'imports d'UN module (identifie par son adresse de
 * base) a la recherche d'une entree IAT dllName!funcName, et la redirige
 * vers hookFunc. *outOriginal recoit l'adresse d'origine (pour que le
 * hook puisse appeler la vraie fonction) - ecrase a chaque nouveau site
 * trouve, mais l'adresse reelle de kernel32!QueryPerformanceCounter (ou
 * winmm!timeGetTime) est la meme quel que soit le module qui l'importe,
 * donc peu importe lequel des sites fournit *outOriginal. */
static BOOL patch_import_in_module(HMODULE base, const char *dllName, const char *funcName, void *hookFunc,
                                    void **outOriginal) {
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    if (dos->e_magic != IMAGE_DOS_SIGNATURE) {
        return FALSE;
    }
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) {
        return FALSE;
    }
    IMAGE_DATA_DIRECTORY importDir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (importDir.VirtualAddress == 0) {
        return FALSE;
    }
    BOOL found = FALSE;
    PIMAGE_IMPORT_DESCRIPTOR desc = (PIMAGE_IMPORT_DESCRIPTOR)((BYTE *)base + importDir.VirtualAddress);
    for (; desc->Name != 0; desc++) {
        char *thisDllName = (char *)base + desc->Name;
        if (_stricmp(thisDllName, dllName) != 0) {
            continue;
        }
        PIMAGE_THUNK_DATA origThunk = (PIMAGE_THUNK_DATA)((BYTE *)base + desc->OriginalFirstThunk);
        PIMAGE_THUNK_DATA thunk = (PIMAGE_THUNK_DATA)((BYTE *)base + desc->FirstThunk);
        for (; origThunk->u1.AddressOfData != 0; origThunk++, thunk++) {
            if (origThunk->u1.Ordinal & IMAGE_ORDINAL_FLAG) {
                continue; /* import par ordinal, pas par nom - pas notre cible */
            }
            PIMAGE_IMPORT_BY_NAME importByName =
                (PIMAGE_IMPORT_BY_NAME)((BYTE *)base + origThunk->u1.AddressOfData);
            if (strcmp((char *)importByName->Name, funcName) == 0) {
                *outOriginal = (void *)thunk->u1.Function;
                DWORD oldProt;
                VirtualProtect(&thunk->u1.Function, sizeof(void *), PAGE_READWRITE, &oldProt);
                thunk->u1.Function = (ULONG_PTR)hookFunc;
                VirtualProtect(&thunk->u1.Function, sizeof(void *), oldProt, &oldProt);
                found = TRUE;
            }
        }
    }
    return found;
}

/* Meme chose que patch_import_in_module, mais applique a TOUTES les DLL
 * actuellement chargees dans le process (pas seulement l'exe principal) -
 * un moteur de jeu/middleware separe de l'exe a sa propre IAT, invisible
 * pour un patch limite au module principal. Retourne le nombre de sites
 * effectivement patches (0 = fonction non trouvee nulle part).
 *
 * CreateToolhelp32Snapshot avec SNAPMODULE/SNAPMODULE32 peut echouer
 * transitoirement avec ERROR_BAD_LENGTH si la liste des modules change
 * pendant l'appel - nouvelle tentative documentee par Microsoft. Un
 * diagnostic premature (lu depuis Python avant la fin du patching, cote
 * course de vitesse - voir ensure_injected dans live_trainer.py) avait
 * un temps donne l'impression que cette methode echouait completement ;
 * en realite elle fonctionne (confirme en jeu le 2026-09-26, voir
 * commentaire en tete de fichier), le probleme etait uniquement une
 * lecture du diagnostic trop tot, pas un echec reel de cette fonction. */
static UINT32 patch_import_everywhere(const char *dllName, const char *funcName, void *hookFunc,
                                       void **outOriginal) {
    UINT32 count = 0;
    HANDLE snap = INVALID_HANDLE_VALUE;
    for (int attempt = 0; attempt < 10; attempt++) {
        snap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, GetCurrentProcessId());
        if (snap != INVALID_HANDLE_VALUE || GetLastError() != ERROR_BAD_LENGTH) {
            break;
        }
        Sleep(10);
    }
    if (snap == INVALID_HANDLE_VALUE) {
        return 0;
    }
    MODULEENTRY32 entry;
    entry.dwSize = sizeof(entry);
    if (Module32First(snap, &entry)) {
        do {
            if (patch_import_in_module((HMODULE)entry.modBaseAddr, dllName, funcName, hookFunc, outOriginal)) {
                count++;
            }
        } while (Module32Next(snap, &entry));
    }
    CloseHandle(snap);
    return count;
}

static DWORD WINAPI InitThread(LPVOID param) {
    (void)param;
    InitializeCriticalSection(&g_lock);
    g_map = CreateFileMappingW(INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE, 0, sizeof(SharedState),
                                L"Local\\MGS4TrainerSpeedHack");
    if (g_map) {
        g_shared = (SharedState *)MapViewOfFile(g_map, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(SharedState));
        if (g_shared) {
            g_shared->speed = 1.0;
            g_shared->patched_mask = 0;
            g_shared->qpc_hit_count = 0;
            g_shared->timegettime_hit_count = 0;
        }
    }

    /* patch_import_everywhere (pas juste le module principal) : le 1er
     * essai limite a l'exe principal n'a eu aucun effet malgre un patch
     * confirme, hypothese que le vrai appel de timing vient d'une DLL du
     * jeu separee (2026-09-26, voir commentaire en tete de fichier). */
    UINT32 qpc_hits = patch_import_everywhere("kernel32.dll", "QueryPerformanceCounter", (void *)HookedQPC,
                                               (void **)&g_real_qpc);
    if (qpc_hits > 0) {
        mark_patched(HOOK_QPC);
    }
    UINT32 tgt_hits = patch_import_everywhere("winmm.dll", "timeGetTime", (void *)HookedTimeGetTime,
                                               (void **)&g_real_timegettime);
    if (tgt_hits > 0) {
        mark_patched(HOOK_TIMEGETTIME);
    }
    if (patch_import_everywhere("kernel32.dll", "GetTickCount", (void *)HookedGetTickCount,
                                 (void **)&g_real_gettickcount) > 0) {
        mark_patched(HOOK_GETTICKCOUNT);
    }
    if (patch_import_everywhere("kernel32.dll", "GetTickCount64", (void *)HookedGetTickCount64,
                                 (void **)&g_real_gettickcount64) > 0) {
        mark_patched(HOOK_GETTICKCOUNT64);
    }
    if (g_shared) {
        g_shared->qpc_hit_count = qpc_hits;
        g_shared->timegettime_hit_count = tgt_hits;
    }
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hinst);
        /* Pas de travail lourd directement dans DllMain (loader lock) -
         * delegue a un thread dedie, comme recommande par Microsoft. */
        CreateThread(NULL, 0, InitThread, NULL, 0, NULL);
    }
    return TRUE;
}
