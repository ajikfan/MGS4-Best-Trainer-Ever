/* speedhack.c - DLL injectee dans mgs4.exe pour controler la vitesse du
 * jeu (ralenti/accelere) et, depuis le 2026-09-26, activer un mode "one
 * shot kill" (voir plus bas dans ce fichier) - pas juste pauser (deja
 * possible sans injection via NtSuspendProcess, voir live_trainer.py).
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
 * du jeu importent la meme fonction chacune via leur propre IAT), [20]
 * uint8 one_shot_kill (1 = actif), [21] uint8 damage_hook_installed
 * (diagnostic : le patch de code plus bas a-t-il reussi), [22] uint8
 * damage_hook_error (0=succes ou pas encore tente, 1=motif introuvable,
 * 2=echec allocation trampoline, 3=hors de portee d'un jmp relatif),
 * [23] uint8 non_lethal (1 = actif - les degats normaux ne sont plus
 * appliques du tout, voir install_damage_hook), [24] uint64
 * last_damaged_actor (pointeur brut vers le dernier personnage touche,
 * diagnostic uniquement - permet d'inspecter cote Python un personnage
 * sur lequel one_shot_kill n'a pas d'effet, ex. un boss), [32] uint64
 * boss_actor (pointeur brut vers l'acteur boss actif, mis a jour par un
 * second hook de lecture seule distinct de celui des degats - les boss ne
 * passent pas par l'instruction patchee pour one_shot_kill, voir
 * install_boss_tracker_hook), [40] uint8 boss_hook_installed, [41] uint8
 * boss_hook_error (memes codes que damage_hook_error), [42] uint64
 * boss_actor2 (meme idee, troisieme point d'injection distinct - routine
 * generique de recopie HP/parametres vers l'affichage, voir
 * install_boss_tracker_hook2), [50] uint8 boss_hook2_installed, [51]
 * uint8 boss_hook2_error, [52] uint64 coord_actor (pointeur brut capture
 * par une routine generique de calcul de distance entre deux acteurs -
 * position (X/Y/Z, 3 floats) a +0x10/+0x14/+0x18 de ce pointeur, voir
 * install_coord_tracker_hook), [60] uint8 coord_hook_installed, [61]
 * uint8 coord_hook_error. */
#pragma pack(push, 1)
typedef struct {
    double speed;
    UINT32 patched_mask;
    UINT32 qpc_hit_count;
    UINT32 timegettime_hit_count;
    UINT8 one_shot_kill;
    UINT8 damage_hook_installed;
    UINT8 damage_hook_error;
    UINT8 non_lethal;
    UINT64 last_damaged_actor;
    UINT64 boss_actor;
    UINT8 boss_hook_installed;
    UINT8 boss_hook_error;
    UINT64 boss_actor2;
    UINT8 boss_hook2_installed;
    UINT8 boss_hook2_error;
    UINT64 coord_actor;
    UINT8 coord_hook_installed;
    UINT8 coord_hook_error;
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

/* ---------------------------------------------------------------------
 * One Shot Kill (2026-09-26) - PATCH DE CODE, pas un hook IAT comme
 * tout ce qui precede : redirige une instruction du jeu lui-meme plutot
 * qu'une entree de table d'imports. Technique differente, risque de
 * crash plus eleve si mal fait (on modifie des instructions executees
 * en permanence, pas juste un pointeur de fonction).
 *
 * Origine : script Cheat Engine communautaire (MGS4.CT, section "aob
 * Damage", auteur RMLSNK 2026-07-02) qui localise et documente deja
 * cette instruction et sa logique - reimplemente ici (pas copie telle
 * quelle, notre propre trampoline en C plutot que du langage Auto
 * Assembler de CE). Protection alliés du script original non reprise
 * (deja geree autrement : le check d'equipe ci-dessous exclut le
 * joueur, seul cas demande).
 *
 * Principe : l'instruction `mov [rdi+0x314], ecx` (rdi = personnage
 * touche, ecx = sa vie apres application des degats) est localisee par
 * recherche de motif d'octets (l'adresse exacte bouge d'une version du
 * jeu a l'autre, contrairement aux tables d'armes/objets qui ont une
 * RVA fixe) puis redirigee vers un trampoline avec 2 effets possibles,
 * jamais appliques au joueur (`[rdi+0x7C]` = 0 -> equipe joueur,
 * exclu) :
 * - one_shot_kill : force ecx (vie apres degats) a 0 avant l'ecriture -
 *   mort instantanee au moindre coup touche.
 * - non_lethal : n'applique PAS l'ecriture de vie du tout (les degats
 *   n'ont aucun effet sur la vie) et efface un champ voisin a
 *   [rdi+0x324] - meme logique que le script CE original ("bRemoveLethal"),
 *   sens exact de ce champ voisin non confirme individuellement, a
 *   tester en jeu.
 * ------------------------------------------------------------------ */

#define DAMAGE_TARGET_TEAM_OFFSET 0x7C
#define DAMAGE_HP_WRITE_OFFSET 0x314

/* Recherche d'un motif d'octets avec jokers ('?' dans mask = n'importe
 * quel octet, 'x' = doit correspondre exactement) - meme principe que
 * "AOB scan" de Cheat Engine. */
static BYTE *find_pattern(BYTE *start, SIZE_T size, const BYTE *pattern, const char *mask, SIZE_T patLen) {
    if (size < patLen) {
        return NULL;
    }
    for (SIZE_T i = 0; i + patLen <= size; i++) {
        BOOL ok = TRUE;
        for (SIZE_T j = 0; j < patLen; j++) {
            if (mask[j] == 'x' && start[i + j] != pattern[j]) {
                ok = FALSE;
                break;
            }
        }
        if (ok) {
            return start + i;
        }
    }
    return NULL;
}

/* VirtualAlloc(NULL, ...) peut renvoyer une adresse n'importe ou dans
 * l'espace d'adressage du process - sur un jeu avec un gros working set
 * (plusieurs Go), tres probablement a plus de 2 Go de `target`, hors de
 * portee d'un jmp relatif 32 bits (cause du premier echec silencieux,
 * 2026-09-26 : le motif etait bien trouve mais le trampoline atterrissait
 * trop loin). Essaie des adresses croissantes a partir de `target`,
 * alignees sur la granularite d'allocation, jusqu'a trouver une page
 * libre - meme principe que les bibliotheques de hooking usuelles
 * (MinHook etc.) pour rester dans la portee d'un jmp/call relatif. */
static BYTE *alloc_near(BYTE *target, SIZE_T size) {
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    UINT64 granularity = si.dwAllocationGranularity;
    UINT64 startAddr = ((UINT64)target / granularity) * granularity;
    UINT64 limit = (UINT64)target + 0x70000000; /* marge sous 2 Go, pas pile la limite */
    for (UINT64 addr = startAddr; addr < limit; addr += granularity) {
        BYTE *p = (BYTE *)VirtualAlloc((LPVOID)addr, size, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        if (p) {
            return p;
        }
    }
    return NULL;
}

/* Construit et pose le trampoline. Retourne FALSE (sans rien modifier
 * du code du jeu) si le motif est introuvable ou si une des deux
 * redirections (jmp initial ou retour) tombe hors de portee d'un jmp
 * relatif 32 bits (+/-2 Go) - garde-fou plutot qu'un crash silencieux.
 *
 * Disposition du trampoline (98 octets, offsets fixes commentes a
 * chaque etape - le calcul des rel8/rel32 en depend directement) :
 *   0   push rax / mov rax,&last_damaged_actor / mov [rax],rdi / pop rax
 *       (diagnostic : garde une trace du dernier personnage touche,
 *       quelle que soit l'equipe, pour inspection cote Python)
 *   15  cmp dword [rdi+0x7C],0        (equipe joueur ?)
 *   19  je PASS                       (oui -> saute tout, juste l'ecriture normale)
 *   25  push rax / mov rax,&one_shot_kill / movzx eax,[rax] / cmp al,1 / pop rax
 *   42  jne CHECK_NONLETHAL           (one_shot_kill pas actif)
 *   44  xor ecx,ecx                   (one_shot_kill actif : vie -> 0)
 *   46  jmp PASS
 *   48  CHECK_NONLETHAL: push rax / mov rax,&non_lethal / movzx eax,[rax] / cmp al,1 / pop rax
 *   65  jne PASS                      (non_lethal pas actif)
 *   67  push rax / lea rax,[rdi+disp] / mov word[rax+0x10],0 / pop rax
 *   82  jmp BACK                      (non_lethal actif : ecriture de vie SAUTEE entierement)
 *   87  PASS: <6 octets originaux : mov [rdi+0x314],ecx>
 *   93  jmp BACK
 *   98  (fin) */
static BOOL install_one_shot_kill_hook(void) {
    HMODULE base = GetModuleHandle(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    SIZE_T imageSize = nt->OptionalHeader.SizeOfImage;

    /* mov [rdi+0000xxxx],ecx ; jmp xxxxxxxx ; mov eax,[rbx+xxxxxxxx] -
     * les 4 octets de deplacement du mov et les 4 octets du jmp sont
     * des jokers (peuvent varier), le reste (opcodes + les 2 premiers
     * octets de l'instruction suivante, utilises comme "signature" pour
     * eviter un faux positif) doit correspondre exactement. */
    static const BYTE pattern[] = {0x89, 0x8F, 0, 0, 0, 0, 0xE9, 0, 0, 0, 0, 0x8B, 0x83};
    static const char mask[] = "xx????x????xx";

    BYTE *objDamage = find_pattern((BYTE *)base, imageSize, pattern, mask, sizeof(pattern));
    if (!objDamage) {
        g_shared->damage_hook_error = 1;
        return FALSE;
    }

    BYTE *trampoline = alloc_near(objDamage, 4096);
    if (!trampoline) {
        g_shared->damage_hook_error = 2;
        return FALSE;
    }

    UINT64 oneShotAddr = (UINT64)&g_shared->one_shot_kill;
    UINT64 nonLethalAddr = (UINT64)&g_shared->non_lethal;
    UINT64 lastActorAddr = (UINT64)&g_shared->last_damaged_actor;
    BYTE code[98];
    SIZE_T p = 0;

    /* push rax ; mov rax,&last_damaged_actor ; mov [rax],rdi ; pop rax -
     * diagnostic : trace le dernier personnage touche (avant le filtre
     * d'equipe) pour pouvoir inspecter sa structure cote Python. */
    code[p++] = 0x50;
    code[p++] = 0x48;
    code[p++] = 0xB8;
    memcpy(&code[p], &lastActorAddr, 8);
    p += 8;
    code[p++] = 0x48;
    code[p++] = 0x89;
    code[p++] = 0x38; /* mov [rax],rdi (ModRM: mod=00,reg=rdi(111),rm=rax(000)) */
    code[p++] = 0x58;

    /* cmp dword ptr [rdi+0x7C], 0 */
    code[p++] = 0x83;
    code[p++] = 0x7F;
    code[p++] = (BYTE)DAMAGE_TARGET_TEAM_OFFSET;
    code[p++] = 0x00;
    /* je PASS (offset87) - equipe joueur, n'applique jamais les effets */
    code[p++] = 0x0F;
    code[p++] = 0x84;
    { INT32 rel = 87 - 25; memcpy(&code[p], &rel, 4); p += 4; }
    /* push rax ; mov rax,&one_shot_kill ; movzx eax,[rax] ; cmp al,1 ; pop rax */
    code[p++] = 0x50;
    code[p++] = 0x48;
    code[p++] = 0xB8;
    memcpy(&code[p], &oneShotAddr, 8);
    p += 8;
    code[p++] = 0x0F;
    code[p++] = 0xB6;
    code[p++] = 0x00;
    code[p++] = 0x3C;
    code[p++] = 0x01;
    code[p++] = 0x58;
    /* jne CHECK_NONLETHAL (offset48) */
    code[p++] = 0x75;
    code[p++] = (BYTE)(48 - 44);
    /* xor ecx,ecx (vie apres degats forcee a 0) */
    code[p++] = 0x31;
    code[p++] = 0xC9;
    /* jmp PASS (offset87) */
    code[p++] = 0xEB;
    code[p++] = (BYTE)(87 - 48);
    /* CHECK_NONLETHAL (offset48) : push rax ; mov rax,&non_lethal ; movzx eax,[rax] ; cmp al,1 ; pop rax */
    code[p++] = 0x50;
    code[p++] = 0x48;
    code[p++] = 0xB8;
    memcpy(&code[p], &nonLethalAddr, 8);
    p += 8;
    code[p++] = 0x0F;
    code[p++] = 0xB6;
    code[p++] = 0x00;
    code[p++] = 0x3C;
    code[p++] = 0x01;
    code[p++] = 0x58;
    /* jne PASS (offset87) */
    code[p++] = 0x75;
    code[p++] = (BYTE)(87 - 67);
    /* non_lethal actif : push rax ; lea rax,[rdi+disp32(copie de objDamage+2)] ;
     * mov word ptr [rax+0x10],0 ; pop rax - meme mecanisme que "bRemoveLethal"
     * du script CE original (efface un champ voisin de la vie, sens exact
     * non confirme individuellement). */
    code[p++] = 0x50;
    code[p++] = 0x48;
    code[p++] = 0x8D;
    code[p++] = 0x87;
    memcpy(&code[p], objDamage + 2, 4); /* meme deplacement que l'ecriture de vie originale */
    p += 4;
    code[p++] = 0x66;
    code[p++] = 0xC7;
    code[p++] = 0x40;
    code[p++] = 0x10;
    code[p++] = 0x00;
    code[p++] = 0x00;
    code[p++] = 0x58;
    /* jmp BACK (offset82, len5 - BACK est externe, calcule plus bas) -
     * ecriture de vie entierement sautee (non_lethal actif). */
    code[p++] = 0xE9;
    {
        BYTE *nextInstrAddr = trampoline + p + 4;
        INT64 rel64 = (INT64)(objDamage + 6) - (INT64)nextInstrAddr;
        if (rel64 > 0x7FFFFFFFLL || rel64 < -0x80000000LL) {
            g_shared->damage_hook_error = 3;
            return FALSE;
        }
        INT32 rel = (INT32)rel64;
        memcpy(&code[p], &rel, 4);
        p += 4;
    }
    /* PASS (offset87) : instruction originale (6 octets copies tels quels
     * depuis le motif trouve, plutot que recodes a la main). */
    memcpy(&code[p], objDamage, 6);
    p += 6;
    /* jmp BACK (vers objDamage+6, suite du code original jamais modifiee) */
    code[p++] = 0xE9;
    {
        BYTE *nextInstrAddr = trampoline + p + 4;
        INT64 rel64 = (INT64)(objDamage + 6) - (INT64)nextInstrAddr;
        if (rel64 > 0x7FFFFFFFLL || rel64 < -0x80000000LL) {
            g_shared->damage_hook_error = 3;
            return FALSE;
        }
        INT32 rel = (INT32)rel64;
        memcpy(&code[p], &rel, 4);
        p += 4;
    }

    memcpy(trampoline, code, p);

    INT64 relToTrampoline = (INT64)trampoline - (INT64)(objDamage + 5);
    if (relToTrampoline > 0x7FFFFFFFLL || relToTrampoline < -0x80000000LL) {
        g_shared->damage_hook_error = 3;
        return FALSE;
    }

    DWORD oldProt;
    VirtualProtect(objDamage, 6, PAGE_EXECUTE_READWRITE, &oldProt);
    objDamage[0] = 0xE9;
    INT32 relJmp = (INT32)relToTrampoline;
    memcpy(objDamage + 1, &relJmp, 4);
    objDamage[5] = 0x90; /* nop de bourrage : l'instruction remplacee fait 6 octets, jmp rel32 en fait 5 */
    VirtualProtect(objDamage, 6, oldProt, &oldProt);

    return TRUE;
}

/* Hook de tracking pur (lecture seule, ne modifie aucun comportement du
 * jeu) sur la routine generique de mise a jour des parties/points faibles
 * des boss (motif repris du script CE communautaire "Bosses 2" - generique
 * a tous les boss, pas specifique a un seul). Les boss ne passent pas par
 * l'instruction patchee par install_one_shot_kill_hook, d'ou ce second
 * point d'injection distinct pour au moins obtenir leur pointeur d'acteur.
 *
 * Trampoline (26 octets) :
 *   0   push rax / mov rax,&boss_actor / mov [rax],rdi / pop rax
 *   15  PASS: <6 octets originaux : mov esi,[rdi+0xE8]>
 *   21  jmp BACK
 *   26  (fin) */
static BOOL install_boss_tracker_hook(void) {
    HMODULE base = GetModuleHandle(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    SIZE_T imageSize = nt->OptionalHeader.SizeOfImage;

    /* mov esi,[rdi+0xE8] ; mov r14d,[rdi+0xF0] - aucun joker, motif exact
     * (13 octets, seuls les 6 premiers sont remplaces par le jmp). */
    static const BYTE pattern[] = {0x8B, 0xB7, 0xE8, 0x00, 0x00, 0x00,
                                    0x44, 0x8B, 0xB7, 0xF0, 0x00, 0x00, 0x00};
    static const char mask[] = "xxxxxxxxxxxxx";

    BYTE *objBoss = find_pattern((BYTE *)base, imageSize, pattern, mask, sizeof(pattern));
    if (!objBoss) {
        g_shared->boss_hook_error = 1;
        return FALSE;
    }

    BYTE *trampoline = alloc_near(objBoss, 4096);
    if (!trampoline) {
        g_shared->boss_hook_error = 2;
        return FALSE;
    }

    UINT64 bossActorAddr = (UINT64)&g_shared->boss_actor;
    BYTE code[26];
    SIZE_T p = 0;

    /* push rax ; mov rax,&boss_actor ; mov [rax],rdi ; pop rax */
    code[p++] = 0x50;
    code[p++] = 0x48;
    code[p++] = 0xB8;
    memcpy(&code[p], &bossActorAddr, 8);
    p += 8;
    code[p++] = 0x48;
    code[p++] = 0x89;
    code[p++] = 0x38; /* mov [rax],rdi (ModRM: mod=00,reg=rdi(111),rm=rax(000)) */
    code[p++] = 0x58;

    /* PASS : instruction originale (6 octets copies tels quels) */
    memcpy(&code[p], objBoss, 6);
    p += 6;

    /* jmp BACK (vers objBoss+6, suite du code original jamais modifiee) */
    code[p++] = 0xE9;
    {
        BYTE *nextInstrAddr = trampoline + p + 4;
        INT64 rel64 = (INT64)(objBoss + 6) - (INT64)nextInstrAddr;
        if (rel64 > 0x7FFFFFFFLL || rel64 < -0x80000000LL) {
            g_shared->boss_hook_error = 3;
            return FALSE;
        }
        INT32 rel = (INT32)rel64;
        memcpy(&code[p], &rel, 4);
        p += 4;
    }

    memcpy(trampoline, code, p);

    INT64 relToTrampoline = (INT64)trampoline - (INT64)(objBoss + 5);
    if (relToTrampoline > 0x7FFFFFFFLL || relToTrampoline < -0x80000000LL) {
        g_shared->boss_hook_error = 3;
        return FALSE;
    }

    DWORD oldProt;
    VirtualProtect(objBoss, 6, PAGE_EXECUTE_READWRITE, &oldProt);
    objBoss[0] = 0xE9;
    INT32 relJmp = (INT32)relToTrampoline;
    memcpy(objBoss + 1, &relJmp, 4);
    objBoss[5] = 0x90;
    VirtualProtect(objBoss, 6, oldProt, &oldProt);

    return TRUE;
}

/* Second hook de tracking (lecture seule), motif repris du script CE
 * communautaire "Bosses Laughing Octopus" - malgre son nom, le motif ne
 * contient aucun octet specifique a ce boss : c'est la routine generique
 * qui recopie HP/parametres de l'acteur (rcx) vers un buffer d'affichage,
 * en lisant [rcx+0x314] (meme offset HP que partout ailleurs). Point
 * d'injection distinct de install_boss_tracker_hook (rdi) et de
 * install_one_shot_kill_hook.
 *
 * Trampoline (26 octets) :
 *   0   push rax / mov rax,&boss_actor2 / mov [rax],rcx / pop rax
 *   15  PASS: <6 octets originaux : mov eax,[rcx+0x314]>
 *   21  jmp BACK
 *   26  (fin) */
static BOOL install_boss_tracker_hook2(void) {
    HMODULE base = GetModuleHandle(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    SIZE_T imageSize = nt->OptionalHeader.SizeOfImage;

    /* jmp xxxxxxxx ; mov rcx,[rbx+xxxxxxxx] ; mov eax,[rcx+0x314] -
     * les 4+4 octets de deplacement sont des jokers, le reste (opcodes,
     * plus les 2 premiers octets utilises comme signature) doit
     * correspondre exactement. Redirection au point objBoss2 = match+0xC
     * (debut de "mov eax,[rcx+0x314]"), pas au debut du motif. */
    static const BYTE pattern[] = {0xE9, 0, 0, 0, 0, 0x48, 0x8B, 0x8B, 0, 0, 0, 0, 0x8B, 0x81, 0x14, 0x03};
    static const char mask[] = "x????xxx????xxxx";

    BYTE *raw = find_pattern((BYTE *)base, imageSize, pattern, mask, sizeof(pattern));
    if (!raw) {
        g_shared->boss_hook2_error = 1;
        return FALSE;
    }
    BYTE *objBoss2 = raw + 0xC;

    BYTE *trampoline = alloc_near(objBoss2, 4096);
    if (!trampoline) {
        g_shared->boss_hook2_error = 2;
        return FALSE;
    }

    UINT64 bossActor2Addr = (UINT64)&g_shared->boss_actor2;
    BYTE code[26];
    SIZE_T p = 0;

    /* push rax ; mov rax,&boss_actor2 ; mov [rax],rcx ; pop rax */
    code[p++] = 0x50;
    code[p++] = 0x48;
    code[p++] = 0xB8;
    memcpy(&code[p], &bossActor2Addr, 8);
    p += 8;
    code[p++] = 0x48;
    code[p++] = 0x89;
    code[p++] = 0x08; /* mov [rax],rcx (ModRM: mod=00,reg=rcx(001),rm=rax(000)) */
    code[p++] = 0x58;

    /* PASS : instruction originale (6 octets copies tels quels) */
    memcpy(&code[p], objBoss2, 6);
    p += 6;

    /* jmp BACK (vers objBoss2+6, suite du code original jamais modifiee) */
    code[p++] = 0xE9;
    {
        BYTE *nextInstrAddr = trampoline + p + 4;
        INT64 rel64 = (INT64)(objBoss2 + 6) - (INT64)nextInstrAddr;
        if (rel64 > 0x7FFFFFFFLL || rel64 < -0x80000000LL) {
            g_shared->boss_hook2_error = 3;
            return FALSE;
        }
        INT32 rel = (INT32)rel64;
        memcpy(&code[p], &rel, 4);
        p += 4;
    }

    memcpy(trampoline, code, p);

    INT64 relToTrampoline = (INT64)trampoline - (INT64)(objBoss2 + 5);
    if (relToTrampoline > 0x7FFFFFFFLL || relToTrampoline < -0x80000000LL) {
        g_shared->boss_hook2_error = 3;
        return FALSE;
    }

    DWORD oldProt;
    VirtualProtect(objBoss2, 6, PAGE_EXECUTE_READWRITE, &oldProt);
    objBoss2[0] = 0xE9;
    INT32 relJmp = (INT32)relToTrampoline;
    memcpy(objBoss2 + 1, &relJmp, 4);
    objBoss2[5] = 0x90;
    VirtualProtect(objBoss2, 6, oldProt, &oldProt);

    return TRUE;
}

/* Troisieme hook de tracking (lecture seule), motif repris du script CE
 * communautaire "aob Coordinates" - routine generique de calcul de
 * distance entre deux acteurs (alerte/rayon de detection...), capture
 * rbx (l'acteur "cible" du calcul, pas forcement toujours le joueur mais
 * un bon point de depart pour tester la position X/Y/Z a +0x10/+0x14/
 * +0x18 de ce pointeur, memes offsets que documente par le CE table).
 *
 * Trampoline (25 octets) :
 *   0   push rax / mov rax,&coord_actor / mov [rax],rbx / pop rax
 *   15  PASS: <5 octets originaux : movss xmm1,[rbx+0x14]>
 *   20  jmp BACK
 *   25  (fin) */
static BOOL install_coord_tracker_hook(void) {
    HMODULE base = GetModuleHandle(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    SIZE_T imageSize = nt->OptionalHeader.SizeOfImage;

    /* 02 74 ? F3 0F 10 ? ? F3 0F 10 ? ? F3 - le point d'injection reel est
     * a +3 (debut de "F3 0F 10 4B 14"), pas au debut du motif. */
    static const BYTE pattern[] = {0x02, 0x74, 0, 0xF3, 0x0F, 0x10, 0, 0,
                                    0xF3, 0x0F, 0x10, 0, 0, 0xF3};
    static const char mask[] = "xx?xxx??xxx??x";

    BYTE *raw = find_pattern((BYTE *)base, imageSize, pattern, mask, sizeof(pattern));
    if (!raw) {
        g_shared->coord_hook_error = 1;
        return FALSE;
    }
    BYTE *objCoord = raw + 3;

    BYTE *trampoline = alloc_near(objCoord, 4096);
    if (!trampoline) {
        g_shared->coord_hook_error = 2;
        return FALSE;
    }

    UINT64 coordActorAddr = (UINT64)&g_shared->coord_actor;
    BYTE code[25];
    SIZE_T p = 0;

    /* push rax ; mov rax,&coord_actor ; mov [rax],rbx ; pop rax */
    code[p++] = 0x50;
    code[p++] = 0x48;
    code[p++] = 0xB8;
    memcpy(&code[p], &coordActorAddr, 8);
    p += 8;
    code[p++] = 0x48;
    code[p++] = 0x89;
    code[p++] = 0x18; /* mov [rax],rbx (ModRM: mod=00,reg=rbx(011),rm=rax(000)) */
    code[p++] = 0x58;

    /* PASS : instruction originale (5 octets copies tels quels) */
    memcpy(&code[p], objCoord, 5);
    p += 5;

    /* jmp BACK (vers objCoord+5, suite du code original jamais modifiee) */
    code[p++] = 0xE9;
    {
        BYTE *nextInstrAddr = trampoline + p + 4;
        INT64 rel64 = (INT64)(objCoord + 5) - (INT64)nextInstrAddr;
        if (rel64 > 0x7FFFFFFFLL || rel64 < -0x80000000LL) {
            g_shared->coord_hook_error = 3;
            return FALSE;
        }
        INT32 rel = (INT32)rel64;
        memcpy(&code[p], &rel, 4);
        p += 4;
    }

    memcpy(trampoline, code, p);

    INT64 relToTrampoline = (INT64)trampoline - (INT64)(objCoord + 5);
    if (relToTrampoline > 0x7FFFFFFFLL || relToTrampoline < -0x80000000LL) {
        g_shared->coord_hook_error = 3;
        return FALSE;
    }

    DWORD oldProt;
    VirtualProtect(objCoord, 5, PAGE_EXECUTE_READWRITE, &oldProt);
    objCoord[0] = 0xE9;
    INT32 relJmp = (INT32)relToTrampoline;
    memcpy(objCoord + 1, &relJmp, 4);
    VirtualProtect(objCoord, 5, oldProt, &oldProt);

    return TRUE;
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
            g_shared->one_shot_kill = 0;
            g_shared->damage_hook_installed = 0;
            g_shared->damage_hook_error = 0;
            g_shared->non_lethal = 0;
            g_shared->last_damaged_actor = 0;
            g_shared->boss_actor = 0;
            g_shared->boss_hook_installed = 0;
            g_shared->boss_hook_error = 0;
            g_shared->boss_actor2 = 0;
            g_shared->boss_hook2_installed = 0;
            g_shared->boss_hook2_error = 0;
            g_shared->coord_actor = 0;
            g_shared->coord_hook_installed = 0;
            g_shared->coord_hook_error = 0;
        }
    }

    /* Necessite g_shared deja mappe (le trampoline embarque l'adresse de
     * g_shared->one_shot_kill en dur) - doit rester apres le bloc
     * ci-dessus. Echec silencieux (juste le diagnostic a 0) si le motif
     * n'est pas trouve ou hors de portee - one_shot_kill restera sans
     * effet, mais ne doit jamais planter le jeu. */
    if (g_shared && install_one_shot_kill_hook()) {
        g_shared->damage_hook_installed = 1;
    }

    /* Hook de tracking pur, voir install_boss_tracker_hook - independant
     * du precedent, echec silencieux egalement possible. */
    if (g_shared && install_boss_tracker_hook()) {
        g_shared->boss_hook_installed = 1;
    }

    if (g_shared && install_boss_tracker_hook2()) {
        g_shared->boss_hook2_installed = 1;
    }

    if (g_shared && install_coord_tracker_hook()) {
        g_shared->coord_hook_installed = 1;
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
