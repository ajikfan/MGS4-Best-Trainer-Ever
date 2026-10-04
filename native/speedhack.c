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
 * uint8 coord_hook_error, [62] uint8 gecko_hook_installed, [63] uint8
 * gecko_hook_error - meme principe que damage_hook_installed/error mais
 * pour install_gecko_one_shot_kill_hook (instruction de degats separee,
 * commune aux Gecko et aux tanks, partage le flag one_shot_kill mais pas non_lethal -
 * "non letal" n'a pas de sens pour un robot). [64] uint8 no_reload (1 =
 * actif), [65] uint8 no_reload_hook_installed, [66] uint8
 * no_reload_hook_error - patch de code (pas de reassertion en boucle
 * cote Python) qui supprime l'ecriture du nouveau chargeur apres tir,
 * motif "No Reload" du CE table (voir install_no_reload_hook). [67]
 * uint8 no_alerts (1 = actif - la fonction qui evalue si Snake doit etre
 * repere/alerte est court-circuitee, motif "aob No Alerts" du CE table,
 * voir install_no_alerts_hook), [68] uint8 no_alerts_hook_installed,
 * [69] uint8 no_alerts_hook_error (memes codes que damage_hook_error),
 * [70] uint32 alert_mode_override (0xFFFF = desactive, sinon force la
 * valeur ecrite dans la variable d'etat d'alerte du jeu juste avant
 * qu'elle serve a la comparaison qui decide des transitions - motif
 * "Alert -- Ignore" du CE table, voir install_alert_override_hook -
 * complementaire de no_alerts : celui-ci empeche la detection en amont,
 * alert_mode_override force la valeur APRES calcul), [74] uint8
 * alert_override_hook_installed, [75] uint8 alert_override_hook_error.
 * [76] uint64 combat_array_ptr (diagnostic uniquement, lecture seule -
 * pointeur vers le conteneur du tableau des "capteurs" de detection par
 * ennemi proche, lu par B5F120/install_no_alerts_hook pour agreger
 * l'etat d'alerte reel - voir install_combat_array_hook), [84] uint8
 * combat_array_hook_installed, [85] uint8 combat_array_hook_error. [86]
 * uint8 dispatch_hook_installed, [87] uint8 dispatch_hook_error -
 * install_alert_dispatch_hook, hook sur l'entree de la VRAIE fonction de
 * diffusion d'etat d'alerte (edx = nouvel etat, propage a l'IA/l'audio/
 * l'affichage - trouvee par point d'arret materiel x64dbg, 2026-10-01,
 * demande utilisateur). Reutilise alert_mode_override (meme champ,
 * meme convention 0xFFFF=desactive) - contrairement a
 * install_alert_override_hook (desactive, agissait trop en aval sur une
 * simple valeur de cache), celui-ci intercepte le PARAMETRE edx a
 * l'entree de la fonction qui propage reellement le changement partout,
 * bien plus susceptible d'avoir un effet visible. [88] uint64
 * reg_dump[14] (rbx,rcx,rdx,rsi,rbp,rsp,r8,r9,r10,r11,r12,r13,r14,r15 -
 * dans cet ordre - captures brutes de TOUS les registres generaux au
 * meme point d'accroche que last_damaged_actor, diagnostic uniquement,
 * ajoute 2026-10-02 pour chercher un pointeur vers l'arme/projectile a
 * l'origine d'un coup, rdi deja couvert par last_damaged_actor), [192]
 * uint32 reg_dump_seq (incremente a chaque coup, pour detecter cote
 * Python qu'une nouvelle capture est disponible sans comparer les 14
 * valeurs une a une). uint64 damage_hook_addr (adresse absolue du site
 * patche - diagnostic, pose un breakpoint x64dbg directement dessus
 * sans avoir a rechercher le motif, ce qui ne marche plus une fois le
 * hook installe puisque les octets originaux sont alors deja ecrases).
 * uint8 railgun_instant_kill (1 = actif - force un coup fatal sur
 * chaque tir de Rail Gun, quelle que soit sa charge reelle. Meme
 * mecanisme que one_shot_kill mais conditionne sur l'arme active
 * (r15d==0x2d a l'entree du hook de degats) plutot qu'un reglage
 * global, jamais applique au joueur). uint8 railgun_force_charge (1 =
 * actif - la vraie solution trouvee le 2026-10-02 : le niveau de
 * charge du Rail Gun est encode dans 3 bits (0b001/0b010/0b100,
 * paliers 1/2/3) aux bits 24-26 du dword [victime+0x10C], le MEME
 * champ dont les 9 bits bas donnent deja l'ID d'arme - voir
 * install_railgun_force_charge_hook, qui intercepte ce champ bien PLUS
 * TOT que le hook de degats (chez l'appelant, avant que les degats
 * ne soient calcules a partir de la charge - patcher au hook de
 * degats existant est trop tard, la valeur a deja ete consommee).
 * uint8 force_charge_hook_installed, uint8 force_charge_hook_error
 * (memes codes que damage_hook_error). uint64 probe_rsi/probe_rdi/
 * probe_rbx/probe_r12, uint32 probe_seq, uint8 probe_hook_installed/
 * probe_hook_error - diagnostic temporaire (2026-10-02) : dump brut de
 * ces 4 registres juste avant `mov ecx,r12d` / `call 633F70` (l'appel
 * qui calcule les degats reels), pour verifier ce que contient r12 a
 * cet instant precis - le hook sur [rsi+10C] force bien la memoire
 * mais n'a aucun effet visible en jeu, donc r12 ne semble pas (ou pas
 * seulement) derive de cette lecture.
 *
 * Tentative (retiree le 2026-10-02, a cause un crash) : capturer un
 * last_gecko_actor au hook Gecko (install_gecko_one_shot_kill_hook,
 * ecrit [r9+0x314]) pour voir si les tanks y passent - resultat
 * inconclusif (gecko_actor jamais mis a jour par un tir sur un tank)
 * et le jeu a plante peu apres, cause probable mais non confirmee -
 * retire plutot que risque.
 *
 * uint8 tank_whitelist_hook_installed/error, uint8
 * tank_flags_hook_installed/error (2026-10-03) - diagnostics des deux
 * hooks qui etendent one_shot_kill aux tanks touches par n'importe
 * quelle arme, voir install_tank_whitelist_hook et
 * install_tank_flags_hook. Au-dela des 256 premiers octets mappes par
 * live_trainer.py : lisibles seulement en elargissant la vue cote Python. */
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
    UINT8 gecko_hook_installed;
    UINT8 gecko_hook_error;
    UINT8 no_reload;
    UINT8 no_reload_hook_installed;
    UINT8 no_reload_hook_error;
    UINT8 no_alerts;
    UINT8 no_alerts_hook_installed;
    UINT8 no_alerts_hook_error;
    UINT32 alert_mode_override;
    UINT8 alert_override_hook_installed;
    UINT8 alert_override_hook_error;
    UINT64 combat_array_ptr;
    UINT8 combat_array_hook_installed;
    UINT8 combat_array_hook_error;
    UINT8 dispatch_hook_installed;
    UINT8 dispatch_hook_error;
    UINT64 reg_dump[14];
    UINT32 reg_dump_seq;
    UINT64 damage_hook_addr;
    UINT8 railgun_instant_kill;
    UINT8 railgun_force_charge;
    UINT8 force_charge_hook_installed;
    UINT8 force_charge_hook_error;
    UINT64 probe_rsi;
    UINT64 probe_rdi;
    UINT64 probe_rbx;
    UINT64 probe_r12;
    UINT32 probe_seq;
    UINT8 probe_hook_installed;
    UINT8 probe_hook_error;
    UINT8 tank_whitelist_hook_installed;
    UINT8 tank_whitelist_hook_error;
    UINT8 tank_flags_hook_installed;
    UINT8 tank_flags_hook_error;
    UINT8 charge_level_hook_installed;
    UINT8 charge_level_hook_error;
    UINT32 octocamo_hidden[16];
    UINT8 octocamo_hide_hook_installed;
    UINT8 octocamo_hide_hook_error;
    /* Reserve (anciennes demandes visage/motif, remplacees par l'appel
     * generique ci-dessous) - garde pour ne pas decaler les champs. */
    UINT8 equip_req_reserved[14];
    UINT8 main_loop_hook_installed;
    UINT8 main_loop_hook_error;
    /* Appel dans le fil du jeu : rpc_fn = adresse absolue, 4 arguments
     * entiers (rcx, rdx, r8, r9), execute au debut de l'image suivante
     * (boucle principale), resultat (rax) dans rpc_result puis rpc_done=1.
     * Sert au changement de motif OctoCamo en direct (voir
     * MGS4Live.equip_octocamo dans live_trainer.py). */
    UINT8 rpc_pending;
    UINT8 rpc_done;
    UINT64 rpc_fn;
    UINT64 rpc_args[4];
    UINT64 rpc_result;
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
    g_shared->damage_hook_addr = (UINT64)objDamage;

    BYTE *trampoline = alloc_near(objDamage, 4096);
    if (!trampoline) {
        g_shared->damage_hook_error = 2;
        return FALSE;
    }

    UINT64 oneShotAddr = (UINT64)&g_shared->one_shot_kill;
    UINT64 nonLethalAddr = (UINT64)&g_shared->non_lethal;
    UINT64 lastActorAddr = (UINT64)&g_shared->last_damaged_actor;
    UINT64 regDumpAddr = (UINT64)&g_shared->reg_dump[0];
    UINT64 regSeqAddr = (UINT64)&g_shared->reg_dump_seq;
    BYTE code[320];
    SIZE_T p = 0;

    /* push rax ; mov rax,&reg_dump ; mov [rax+N],<reg> pour rbx,rcx,rdx,
     * rsi,rbp,rsp,r8..r15 (14 registres, dans cet ordre) ; mov
     * rax,&reg_dump_seq ; inc dword ptr [rax] ; pop rax - lecture pure
     * (aucun registre source n'est modifie par un mov vers la memoire),
     * ne touche ni les flags utilises plus loin (tous recalcules par
     * leurs propres cmp) ni rdi/ecx dont la suite du trampoline depend.
     * Objectif : chercher un pointeur vers l'arme/projectile a l'origine
     * d'un coup parmi des registres encore non inspectes (rdi seul est
     * deja couvert par last_damaged_actor ci-dessous). */
    code[p++] = 0x50;
    code[p++] = 0x48;
    code[p++] = 0xB8;
    memcpy(&code[p], &regDumpAddr, 8);
    p += 8;
    {
        static const BYTE regMovs[14][4] = {
            {0x48, 0x89, 0x58, 0x00}, /* rbx  -> +0  */
            {0x48, 0x89, 0x48, 0x08}, /* rcx  -> +8  */
            {0x48, 0x89, 0x50, 0x10}, /* rdx  -> +16 */
            {0x48, 0x89, 0x70, 0x18}, /* rsi  -> +24 */
            {0x48, 0x89, 0x68, 0x20}, /* rbp  -> +32 */
            {0x48, 0x89, 0x60, 0x28}, /* rsp  -> +40 */
            {0x4C, 0x89, 0x40, 0x30}, /* r8   -> +48 */
            {0x4C, 0x89, 0x48, 0x38}, /* r9   -> +56 */
            {0x4C, 0x89, 0x50, 0x40}, /* r10  -> +64 */
            {0x4C, 0x89, 0x58, 0x48}, /* r11  -> +72 */
            {0x4C, 0x89, 0x60, 0x50}, /* r12  -> +80 */
            {0x4C, 0x89, 0x68, 0x58}, /* r13  -> +88 */
            {0x4C, 0x89, 0x70, 0x60}, /* r14  -> +96 */
            {0x4C, 0x89, 0x78, 0x68}, /* r15  -> +104 */
        };
        for (int i = 0; i < 14; i++) {
            memcpy(&code[p], regMovs[i], 4);
            p += 4;
        }
    }
    code[p++] = 0x48;
    code[p++] = 0xB8;
    memcpy(&code[p], &regSeqAddr, 8);
    p += 8;
    code[p++] = 0xFF; /* inc dword ptr [rax] */
    code[p++] = 0x00;
    code[p++] = 0x58; /* pop rax */

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

    /* Rail Gun instant kill (ajoute 2026-10-02, demande utilisateur - a
     * defaut d'avoir trouve la valeur de charge live malgre une longue
     * investigation ce soir, voir notes.md) : bloc independant insere
     * AVANT tout le reste (propre copie du filtre d'equipe, jamais
     * applique au joueur) - saute vers SKIP_RG (= le debut du code
     * original ci-dessous, inchange) si equipe joueur, si l'arme active
     * (r15d, voir reg_dump plus haut) n'est pas le Rail Gun (0x2d) ou si
     * le flag railgun_instant_kill est desactive. Reutilise le meme
     * mecanisme que one_shot_kill (xor ecx,ecx avant l'ecriture
     * originale) mais conditionne sur l'arme plutot qu'un reglage
     * global. Tous les sauts ci-dessous sont patches dynamiquement (pas
     * de constantes codees en dur) puisqu'ils retombent au milieu d'un
     * bloc existant dont les distances hardcodees ne doivent pas etre
     * perturbees par une insertion. */
    UINT64 railgunKillAddr = (UINT64)&g_shared->railgun_instant_kill;
    SIZE_T rgSkipPatch[3];
    int rgSkipCount = 0;
    SIZE_T rgPassJmpPatch;

    code[p++] = 0x83; /* cmp dword ptr [rdi+0x7C],0 */
    code[p++] = 0x7F;
    code[p++] = (BYTE)DAMAGE_TARGET_TEAM_OFFSET;
    code[p++] = 0x00;
    code[p++] = 0x74; /* je SKIP_RG (rel8, patche plus bas) */
    rgSkipPatch[rgSkipCount++] = p;
    code[p++] = 0;

    code[p++] = 0x41; code[p++] = 0x81; code[p++] = 0xFF; /* cmp r15d,0x2d */
    { INT32 imm = 0x2d; memcpy(&code[p], &imm, 4); p += 4; }
    code[p++] = 0x75; /* jne SKIP_RG */
    rgSkipPatch[rgSkipCount++] = p;
    code[p++] = 0;

    code[p++] = 0x50; /* push rax */
    code[p++] = 0x48; code[p++] = 0xB8;
    memcpy(&code[p], &railgunKillAddr, 8);
    p += 8;
    code[p++] = 0x0F; code[p++] = 0xB6; code[p++] = 0x00; /* movzx eax,byte[rax] */
    code[p++] = 0x58; /* pop rax */
    code[p++] = 0x3C; code[p++] = 0x01; /* cmp al,1 */
    code[p++] = 0x75; /* jne SKIP_RG */
    rgSkipPatch[rgSkipCount++] = p;
    code[p++] = 0;

    code[p++] = 0x31; code[p++] = 0xC9; /* xor ecx,ecx */
    code[p++] = 0xE9; /* jmp PASS (rel32, patche plus bas une fois PASS connu) */
    rgPassJmpPatch = p;
    p += 4;

    /* SKIP_RG : */
    {
        SIZE_T skipTarget = p;
        for (int i = 0; i < rgSkipCount; i++) {
            code[rgSkipPatch[i]] = (BYTE)(skipTarget - (rgSkipPatch[i] + 1));
        }
    }

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
    {
        INT32 rel = (INT32)(p - (rgPassJmpPatch + 4));
        memcpy(&code[rgPassJmpPatch], &rel, 4);
    }
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

/* Hook sur mov ebp,dword ptr[rsi+0x10C] chez l'appelant de la fonction de
 * degats - PAS le meme point d'accroche que install_one_shot_kill_hook
 * (trop tard : a ce moment-la les degats bases sur la charge ont deja ete
 * calcules et passes en parametre). Trouve le 2026-10-02 par remontee
 * manuelle du code dans x64dbg : [rsi+0x10C] est le MEME champ que celui
 * lu plus tard par le hook de degats (9 bits bas = ID d'arme, deja connu),
 * mais ses bits 24-26 encodent le niveau de charge en bitmask
 * (0b001/0b010/0b100 = palier 1/2/3, confirme par 3 tirs controles). Si
 * railgun_force_charge est actif et que l'arme est le Rail Gun (meme
 * masque &0x1FF que pour l'ID d'arme), force ces 3 bits a 0b100 (palier
 * max) juste apres que le jeu l'ait lu dans r12d - laisse le reste du
 * calcul (table de degats par arme, clamp) se faire normalement avec
 * cette valeur forcee, plutot que d'ecraser le resultat final.
 *
 * CORRECTION 2026-10-02 (2e tentative) : la 1ere version accrochait sur
 * `mov ebp,[rsi+10C]` (une relecture plus tardive du meme champ, utilisee
 * pour un test sans rapport) - sans effet en jeu car r12d, le VRAI
 * vecteur vers le calcul des degats (voir mov ecx,r12d juste avant
 * call 633F70), est deja charge PLUS TOT via `mov r12d,[rsi+10C]`,
 * retrouve en remontant le code a la main dans x64dbg.286 octets avant
 * la "fausse" lecture. Accroche maintenant directement sur cette
 * lecture-la.
 *
 * Etendu au Solar Gun (ID 0x0D) le 2026-10-03 : meme codage de la
 * charge, verifie par bp log x64dbg a ce point de lecture (tirs non
 * charges 0x1181020D, tir charge a fond 0x1481020D). Le flag garde son
 * nom railgun_force_charge.
 *
 * Disposition du trampoline :
 *   0   <7 octets originaux copies tels quels : mov r12d,[rsi+10C]>
 *   7   push rax ; mov rax,&railgun_force_charge ; movzx eax,[rax] ;
 *       cmp al,1 ; pop rax ; jne SKIP
 *       mov eax,r12d ; and eax,1FF ; cmp eax,2D ; je FORCE ;
 *       cmp eax,0D ; jne SKIP
 *  FORCE:
 *       and r12d,F8FFFFFF ; or r12d,04000000
 *       mov dword ptr[rsi+10C],r12d (coherence, voir plus bas)
 *  SKIP:
 *       jmp BACK (vers le motif trouve + 7) */
static BOOL install_railgun_force_charge_hook(void) {
    HMODULE base = GetModuleHandle(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    SIZE_T imageSize = nt->OptionalHeader.SizeOfImage;

    /* mov r12d,dword ptr[rsi+10C] ; mov ebp,r12d - les 3 octets de la 2e
     * instruction servent juste de signature supplementaire, non modifies. */
    static const BYTE pattern[] = {0x44, 0x8B, 0xA6, 0x0C, 0x01, 0x00, 0x00, 0x41, 0x8B, 0xEC};
    static const char mask[] = "xxxxxxxxxx";

    BYTE *objChargeRead = find_pattern((BYTE *)base, imageSize, pattern, mask, sizeof(pattern));
    if (!objChargeRead) {
        g_shared->force_charge_hook_error = 1;
        return FALSE;
    }

    BYTE *trampoline = alloc_near(objChargeRead, 4096);
    if (!trampoline) {
        g_shared->force_charge_hook_error = 2;
        return FALSE;
    }

    UINT64 forceChargeAddr = (UINT64)&g_shared->railgun_force_charge;
    BYTE code[128];
    SIZE_T p = 0;

    /* instruction originale (7 octets) : mov r12d,dword ptr [rsi+10C] */
    memcpy(&code[p], objChargeRead, 7);
    p += 7;

    code[p++] = 0x50; /* push rax */
    code[p++] = 0x48;
    code[p++] = 0xB8;
    memcpy(&code[p], &forceChargeAddr, 8);
    p += 8;
    code[p++] = 0x0F; code[p++] = 0xB6; code[p++] = 0x00; /* movzx eax,byte[rax] */
    code[p++] = 0x3C; code[p++] = 0x01; /* cmp al,1 */
    code[p++] = 0x58; /* pop rax */
    code[p++] = 0x75; /* jne SKIP */
    SIZE_T skip1 = p;
    code[p++] = 0;

    code[p++] = 0x44; code[p++] = 0x89; code[p++] = 0xE0; /* mov eax,r12d */
    code[p++] = 0x25; /* and eax,1FF */
    { UINT32 imm = 0x1FF; memcpy(&code[p], &imm, 4); p += 4; }
    code[p++] = 0x3D; /* cmp eax,2D (Rail Gun) */
    { UINT32 imm = 0x2D; memcpy(&code[p], &imm, 4); p += 4; }
    code[p++] = 0x74; code[p++] = 0x05; /* je FORCE (saute cmp + jne ci-dessous) */
    code[p++] = 0x83; code[p++] = 0xF8; code[p++] = 0x0D; /* cmp eax,0D (Solar Gun) */
    code[p++] = 0x75; /* jne SKIP */
    SIZE_T skip2 = p;
    code[p++] = 0;
    /* FORCE: */

    code[p++] = 0x41; code[p++] = 0x81; code[p++] = 0xE4; /* and r12d,F8FFFFFF */
    { UINT32 imm = 0xF8FFFFFF; memcpy(&code[p], &imm, 4); p += 4; }
    code[p++] = 0x41; code[p++] = 0x81; code[p++] = 0xCC; /* or r12d,04000000 */
    { UINT32 imm = 0x04000000; memcpy(&code[p], &imm, 4); p += 4; }
    /* reecrit aussi en memoire : la 2e lecture plus tardive (mov ebp,
     * [rsi+10C], notre ancien point d'accroche) la relit depuis la
     * memoire, pas depuis r12d - sans cette ecriture elle verrait encore
     * l'ancienne valeur. mov dword ptr[rsi+10C],r12d */
    code[p++] = 0x44; code[p++] = 0x89; code[p++] = 0xA6;
    { UINT32 imm = 0x10C; memcpy(&code[p], &imm, 4); p += 4; }

    /* SKIP: */
    {
        SIZE_T skipTarget = p;
        code[skip1] = (BYTE)(skipTarget - (skip1 + 1));
        code[skip2] = (BYTE)(skipTarget - (skip2 + 1));
    }

    /* jmp BACK (vers objChargeRead+7) */
    code[p++] = 0xE9;
    {
        BYTE *nextInstrAddr = trampoline + p + 4;
        INT64 rel64 = (INT64)(objChargeRead + 7) - (INT64)nextInstrAddr;
        if (rel64 > 0x7FFFFFFFLL || rel64 < -0x80000000LL) {
            g_shared->force_charge_hook_error = 3;
            return FALSE;
        }
        INT32 rel = (INT32)rel64;
        memcpy(&code[p], &rel, 4);
        p += 4;
    }

    memcpy(trampoline, code, p);

    INT64 relToTrampoline = (INT64)trampoline - (INT64)(objChargeRead + 5);
    if (relToTrampoline > 0x7FFFFFFFLL || relToTrampoline < -0x80000000LL) {
        g_shared->force_charge_hook_error = 3;
        return FALSE;
    }

    DWORD oldProt;
    VirtualProtect(objChargeRead, 7, PAGE_EXECUTE_READWRITE, &oldProt);
    objChargeRead[0] = 0xE9;
    INT32 relJmp = (INT32)relToTrampoline;
    memcpy(objChargeRead + 1, &relJmp, 4);
    /* instruction remplacee = 7 octets, jmp rel32 = 5, 2 octets de bourrage */
    objChargeRead[5] = 0x90;
    objChargeRead[6] = 0x90;
    VirtualProtect(objChargeRead, 7, oldProt, &oldProt);

    return TRUE;
}

/* Hook de diagnostic temporaire (2026-10-02) sur `mov edx,ebx ; mov
 * ecx,r12d` juste avant `call 633F70` (la fonction qui calcule reellement
 * les degats) - dump brut de rsi/rdi/rbx/r12 a cet instant precis pour
 * verifier d'ou vient r12 (le hook sur [rsi+10C] force bien la memoire
 * mais n'a aucun effet visible, donc r12 ne semble pas en deriver
 * directement a cet endroit). Lecture seule, ne modifie rien.
 *
 * Disposition du trampoline :
 *   0   <5 octets originaux : mov edx,ebx ; mov ecx,r12d>
 *   5   push rax ; mov rax,&probe_rsi ; mov [rax],rsi ; mov [rax+8],rdi ;
 *       mov [rax+10],rbx ; mov [rax+18],r12 ; mov rax,&probe_seq ;
 *       inc dword[rax] ; pop rax
 *       jmp BACK (vers le motif trouve + 5) */
static BOOL install_r12_probe_hook(void) {
    HMODULE base = GetModuleHandle(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    SIZE_T imageSize = nt->OptionalHeader.SizeOfImage;

    static const BYTE pattern[] = {0x8B, 0xD3, 0x41, 0x8B, 0xCC, 0xE8};
    static const char mask[] = "xxxxxx";

    BYTE *objProbe = find_pattern((BYTE *)base, imageSize, pattern, mask, sizeof(pattern));
    if (!objProbe) {
        g_shared->probe_hook_error = 1;
        return FALSE;
    }

    BYTE *trampoline = alloc_near(objProbe, 4096);
    if (!trampoline) {
        g_shared->probe_hook_error = 2;
        return FALSE;
    }

    UINT64 rsiAddr = (UINT64)&g_shared->probe_rsi;
    UINT64 seqAddr = (UINT64)&g_shared->probe_seq;
    BYTE code[96];
    SIZE_T p = 0;

    /* instruction originale (5 octets) : mov edx,ebx ; mov ecx,r12d */
    memcpy(&code[p], objProbe, 5);
    p += 5;

    code[p++] = 0x50; /* push rax */
    code[p++] = 0x48;
    code[p++] = 0xB8;
    memcpy(&code[p], &rsiAddr, 8);
    p += 8;
    code[p++] = 0x48; code[p++] = 0x89; code[p++] = 0x30;        /* mov [rax],rsi */
    code[p++] = 0x48; code[p++] = 0x89; code[p++] = 0x78; code[p++] = 0x08;  /* mov [rax+8],rdi */
    code[p++] = 0x48; code[p++] = 0x89; code[p++] = 0x58; code[p++] = 0x10; /* mov [rax+10],rbx */
    code[p++] = 0x4C; code[p++] = 0x89; code[p++] = 0x60; code[p++] = 0x18; /* mov [rax+18],r12 */
    code[p++] = 0x48;
    code[p++] = 0xB8;
    memcpy(&code[p], &seqAddr, 8);
    p += 8;
    code[p++] = 0xFF; code[p++] = 0x00; /* inc dword ptr [rax] */
    code[p++] = 0x58; /* pop rax */

    /* jmp BACK (vers objProbe+5) */
    code[p++] = 0xE9;
    {
        BYTE *nextInstrAddr = trampoline + p + 4;
        INT64 rel64 = (INT64)(objProbe + 5) - (INT64)nextInstrAddr;
        if (rel64 > 0x7FFFFFFFLL || rel64 < -0x80000000LL) {
            g_shared->probe_hook_error = 3;
            return FALSE;
        }
        INT32 rel = (INT32)rel64;
        memcpy(&code[p], &rel, 4);
        p += 4;
    }

    memcpy(trampoline, code, p);

    INT64 relToTrampoline = (INT64)trampoline - (INT64)(objProbe + 5);
    if (relToTrampoline > 0x7FFFFFFFLL || relToTrampoline < -0x80000000LL) {
        g_shared->probe_hook_error = 3;
        return FALSE;
    }

    DWORD oldProt;
    VirtualProtect(objProbe, 5, PAGE_EXECUTE_READWRITE, &oldProt);
    objProbe[0] = 0xE9;
    INT32 relJmp = (INT32)relToTrampoline;
    memcpy(objProbe + 1, &relJmp, 4);
    VirtualProtect(objProbe, 5, oldProt, &oldProt);

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

/* One-shot-kill pour les Gecko (robots bipedes) ET les tanks - instruction
 * de degats SEPARATE de celle des ennemis humains (install_one_shot_kill_hook),
 * motif repris du script CE communautaire "aob Damage Gecko".
 * Precision 2026-10-03 : ce motif ne correspond qu'a un seul endroit
 * (mgs4.exe+B22082 cette version), la fonction de degats commune
 * (B21FF0 : r9/rcx = objet de vie, edx = degats, [r9+318] = vie max)
 * utilisee aussi bien par les Gecko que par les tanks - confirme en jeu
 * sur les deux. Pour les tanks, voir aussi install_tank_whitelist_hook
 * et install_tank_flags_hook, sans lesquels seules 4 armes atteignent
 * cette fonction. Meme
 * mecanisme (ecrase ecx par 0 juste avant l'ecriture de vie), mais :
 *  - acteur cible dans r9 (pas rdi), instruction 7 octets (pas 6, prefixe
 *    REX.B necessaire pour adresser r9) ;
 *  - aucune verification d'equipe : les Gecko ne sont jamais controles
 *    par le joueur, le script CE original n'en fait pas non plus ;
 *  - pas de variante non-letale (n'a pas de sens pour un robot) - partage
 *    juste le flag one_shot_kill avec les ennemis humains, ignore
 *    non_lethal.
 *
 * Trampoline (33 octets) :
 *   0   push rax / mov rax,&one_shot_kill / movzx eax,[rax] / cmp al,1 / pop rax
 *   17  jne PASS (offset21)              (one_shot_kill pas actif)
 *   19  xor ecx,ecx                      (one_shot_kill actif : vie -> 0)
 *   21  PASS: <7 octets originaux : mov [r9+0x314],ecx>
 *   28  jmp BACK
 *   33  (fin) */
static BOOL install_gecko_one_shot_kill_hook(void) {
    HMODULE base = GetModuleHandle(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    SIZE_T imageSize = nt->OptionalHeader.SizeOfImage;

    /* EB 07 41 ????????? C2 48 ???? 48 ?? 48 ??? 48 ????????????
     * 48 ?????????????? 41 89 89 - motif long a nombreux jokers (issu
     * tel quel du CE table), signature suffisante pour eviter les faux
     * positifs sur un module de cette taille. Point d'injection reel a
     * +0x34 (les 3 derniers octets exacts du motif, "41 89 89", en sont
     * le tout debut). */
    static const BYTE pattern[] = {
        0xEB, 0x07, 0x41, 0, 0, 0, 0, 0, 0, 0, 0, 0xC2, 0x48, 0, 0, 0, 0,
        0x48, 0, 0, 0x48, 0, 0, 0, 0x48, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0x48, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x41, 0x89, 0x89,
    };
    static const char mask[] =
        "xxx????????xx????x??x???x????????????x??????????????xxx";

    BYTE *raw = find_pattern((BYTE *)base, imageSize, pattern, mask, sizeof(pattern));
    if (!raw) {
        g_shared->gecko_hook_error = 1;
        return FALSE;
    }
    BYTE *objDamageGecko = raw + 0x34;

    BYTE *trampoline = alloc_near(objDamageGecko, 4096);
    if (!trampoline) {
        g_shared->gecko_hook_error = 2;
        return FALSE;
    }

    UINT64 oneShotAddr = (UINT64)&g_shared->one_shot_kill;
    BYTE code[33];
    SIZE_T p = 0;

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
    /* jne PASS (offset21) */
    code[p++] = 0x75;
    code[p++] = (BYTE)(21 - 19);
    /* xor ecx,ecx (vie apres degats forcee a 0) */
    code[p++] = 0x31;
    code[p++] = 0xC9;

    /* PASS (offset21) : instruction originale (7 octets copies tels quels) */
    memcpy(&code[p], objDamageGecko, 7);
    p += 7;

    /* jmp BACK (vers objDamageGecko+7, suite du code original jamais modifiee) */
    code[p++] = 0xE9;
    {
        BYTE *nextInstrAddr = trampoline + p + 4;
        INT64 rel64 = (INT64)(objDamageGecko + 7) - (INT64)nextInstrAddr;
        if (rel64 > 0x7FFFFFFFLL || rel64 < -0x80000000LL) {
            g_shared->gecko_hook_error = 3;
            return FALSE;
        }
        INT32 rel = (INT32)rel64;
        memcpy(&code[p], &rel, 4);
        p += 4;
    }

    memcpy(trampoline, code, p);

    INT64 relToTrampoline = (INT64)trampoline - (INT64)(objDamageGecko + 5);
    if (relToTrampoline > 0x7FFFFFFFLL || relToTrampoline < -0x80000000LL) {
        g_shared->gecko_hook_error = 3;
        return FALSE;
    }

    DWORD oldProt;
    VirtualProtect(objDamageGecko, 7, PAGE_EXECUTE_READWRITE, &oldProt);
    objDamageGecko[0] = 0xE9;
    INT32 relJmp = (INT32)relToTrampoline;
    memcpy(objDamageGecko + 1, &relJmp, 4);
    objDamageGecko[5] = 0x90; /* nop de bourrage : 7 octets remplaces par jmp rel32 (5) */
    objDamageGecko[6] = 0x90;
    VirtualProtect(objDamageGecko, 7, oldProt, &oldProt);

    return TRUE;
}

/* Ecrit un rel32 de code[at] (fin d'instruction = trampoline+at+4) vers
 * target - FALSE si hors de portee. Utilise par les hooks tanks. */
static BOOL put_rel32(BYTE *code, SIZE_T at, BYTE *trampoline, BYTE *target) {
    INT64 rel64 = (INT64)target - (INT64)(trampoline + at + 4);
    if (rel64 > 0x7FFFFFFFLL || rel64 < -0x80000000LL) {
        return FALSE;
    }
    INT32 rel = (INT32)rel64;
    memcpy(&code[at], &rel, 4);
    return TRUE;
}

/* Remplace `len` octets a `at` par jmp rel32 vers trampoline (+ nops). */
static BOOL patch_jmp(BYTE *at, SIZE_T len, BYTE *trampoline) {
    INT64 rel64 = (INT64)trampoline - (INT64)(at + 5);
    if (rel64 > 0x7FFFFFFFLL || rel64 < -0x80000000LL) {
        return FALSE;
    }
    DWORD oldProt;
    VirtualProtect(at, len, PAGE_EXECUTE_READWRITE, &oldProt);
    at[0] = 0xE9;
    INT32 rel = (INT32)rel64;
    memcpy(at + 1, &rel, 4);
    for (SIZE_T i = 5; i < len; i++) {
        at[i] = 0x90;
    }
    VirtualProtect(at, len, oldProt, &oldProt);
    return TRUE;
}

/* Tanks, partie 1/2 (2026-10-03) : liste blanche d'armes du callback de
 * collision des tanks (mgs4.exe+102F0C0 cette version, le callback que
 * pointent les 11 colliders du tank). Ce callback n'ajoute un coup dans
 * la liste de coups du tank ([acteur+0x438]) que si l'ID d'arme vaut
 * 0x28, 0x2D, 0x68 ou 0x99 (`sub ebx,28 ; je ACCEPT ; sub ebx,5 ; je ...`)
 * - toute autre arme (balles, etc.) est ignoree avant meme d'etre
 * enregistree, d'ou l'absence totale d'effet de one_shot_kill.
 * Si one_shot_kill est actif ET que l'attaquant (rsi) est le joueur
 * (meme test que le jeu juste au-dessus : `call 8DA180 ; cmp rsi,[rax]`),
 * saute directement a ACCEPT (verification de trajectoire puis ajout du
 * coup), sinon execute la liste blanche normalement.
 *
 * Sert aussi a railgun_force_charge pour les tanks (2026-10-03) : le
 * hook de charge principal (install_railgun_force_charge_hook) est dans
 * le code des SOLDATS et ne voit jamais les coups sur un tank (un vrai
 * tir charge a fond fait 3000 a un tank, un tir force n'en faisait que
 * 1000). Ici rbp = bloc "attaque" du coup (renvoye par 10314A0, a
 * l'interieur du coup lui-meme), [rbp+10] = drapeaux (ID d'arme + bits
 * de charge 24-26), recopies tels quels par l'ajout dans la liste du
 * tank (D41940) avant tout calcul de degats. Si railgun_force_charge est
 * actif et l'arme est le Rail Gun (0x2D) ou le Solar Gun (0x0D), force
 * le palier max dans [rbp+10] avant de continuer.
 *
 * Trampoline :
 *   push rax ; push rcx
 *   mov rax,&railgun_force_charge ; cmp byte[rax],1 ; jne OSOK
 *   cmp ebx,2D ; je CHARGE ; cmp ebx,0D ; jne OSOK
 *  CHARGE:
 *   and dword[rbp+10],F8FFFFFF ; or dword[rbp+10],04000000
 *  OSOK:
 *   mov rax,&one_shot_kill ; movzx eax,[rax] ; cmp al,1 ; jne ORIG
 *   mov rax,<fonction joueur> ; call rax ; cmp rsi,[rax] ; jne ORIG
 *   pop rcx ; pop rax ; jmp ACCEPT
 *  ORIG:
 *   pop rcx ; pop rax ; sub ebx,28 ; je ACCEPT ; jmp BACK (motif+5) */
static BOOL install_tank_whitelist_hook(void) {
    HMODULE base = GetModuleHandle(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    SIZE_T imageSize = nt->OptionalHeader.SizeOfImage;

    /* sub ebx,28 ; je +0F ; sub ebx,5 ; je +0A ; sub ebx,3B ; je +05 ;
     * cmp ebx,31 ; jne +5E - unique dans le module. */
    static const BYTE pattern[] = {0x83, 0xEB, 0x28, 0x74, 0x0F, 0x83, 0xEB, 0x05, 0x74, 0x0A,
                                   0x83, 0xEB, 0x3B, 0x74, 0x05, 0x83, 0xFB, 0x31, 0x75};
    static const char mask[] = "xxxxxxxxxxxxxxxxxxx";

    BYTE *objWl = find_pattern((BYTE *)base, imageSize, pattern, mask, sizeof(pattern));
    if (!objWl) {
        g_shared->tank_whitelist_hook_error = 1;
        return FALSE;
    }
    BYTE *accept = objWl + 5 + 0x0F;

    /* Fonction qui renvoie le pointeur vers le joueur : cible du
     * `call 8DA180` situe 0x28 octets avant le motif (verifie). */
    BYTE *callSite = objWl - 0x28;
    if (callSite[0] != 0xE8) {
        g_shared->tank_whitelist_hook_error = 4;
        return FALSE;
    }
    INT32 callRel;
    memcpy(&callRel, callSite + 1, 4);
    UINT64 playerFn = (UINT64)(callSite + 5 + callRel);

    BYTE *trampoline = alloc_near(objWl, 4096);
    if (!trampoline) {
        g_shared->tank_whitelist_hook_error = 2;
        return FALSE;
    }

    UINT64 oneShotAddr = (UINT64)&g_shared->one_shot_kill;
    UINT64 forceChargeAddr = (UINT64)&g_shared->railgun_force_charge;
    BYTE code[128];
    SIZE_T p = 0;
    BOOL ok = TRUE;

    code[p++] = 0x50; /* push rax */
    code[p++] = 0x51; /* push rcx */

    code[p++] = 0x48; code[p++] = 0xB8; /* mov rax,&railgun_force_charge */
    memcpy(&code[p], &forceChargeAddr, 8);
    p += 8;
    code[p++] = 0x80; code[p++] = 0x38; code[p++] = 0x01; /* cmp byte[rax],1 */
    code[p++] = 0x75; /* jne OSOK */
    SIZE_T toOsok1 = p++;
    code[p++] = 0x83; code[p++] = 0xFB; code[p++] = 0x2D; /* cmp ebx,2D (Rail Gun) */
    code[p++] = 0x74; code[p++] = 0x05; /* je CHARGE */
    code[p++] = 0x83; code[p++] = 0xFB; code[p++] = 0x0D; /* cmp ebx,0D (Solar Gun) */
    code[p++] = 0x75; /* jne OSOK */
    SIZE_T toOsok2 = p++;
    /* CHARGE: and dword[rbp+10],F8FFFFFF ; or dword[rbp+10],04000000 */
    code[p++] = 0x81; code[p++] = 0x65; code[p++] = 0x10;
    { UINT32 imm = 0xF8FFFFFF; memcpy(&code[p], &imm, 4); p += 4; }
    code[p++] = 0x81; code[p++] = 0x4D; code[p++] = 0x10;
    { UINT32 imm = 0x04000000; memcpy(&code[p], &imm, 4); p += 4; }
    /* OSOK: */
    code[toOsok1] = (BYTE)(p - (toOsok1 + 1));
    code[toOsok2] = (BYTE)(p - (toOsok2 + 1));

    code[p++] = 0x48; code[p++] = 0xB8; /* mov rax,&one_shot_kill */
    memcpy(&code[p], &oneShotAddr, 8);
    p += 8;
    code[p++] = 0x0F; code[p++] = 0xB6; code[p++] = 0x00; /* movzx eax,byte[rax] */
    code[p++] = 0x3C; code[p++] = 0x01; /* cmp al,1 */
    code[p++] = 0x75; /* jne ORIG */
    SIZE_T toOrig1 = p++;
    code[p++] = 0x48; code[p++] = 0xB8; /* mov rax,<fonction joueur> */
    memcpy(&code[p], &playerFn, 8);
    p += 8;
    code[p++] = 0xFF; code[p++] = 0xD0; /* call rax (feuille : ne touche que rax/rcx) */
    code[p++] = 0x48; code[p++] = 0x3B; code[p++] = 0x30; /* cmp rsi,[rax] */
    code[p++] = 0x75; /* jne ORIG */
    SIZE_T toOrig2 = p++;
    code[p++] = 0x59; /* pop rcx */
    code[p++] = 0x58; /* pop rax */
    code[p++] = 0xE9; /* jmp ACCEPT */
    ok &= put_rel32(code, p, trampoline, accept);
    p += 4;

    /* ORIG: */
    code[toOrig1] = (BYTE)(p - (toOrig1 + 1));
    code[toOrig2] = (BYTE)(p - (toOrig2 + 1));
    code[p++] = 0x59; /* pop rcx */
    code[p++] = 0x58; /* pop rax */
    code[p++] = 0x83; code[p++] = 0xEB; code[p++] = 0x28; /* sub ebx,28 (original) */
    code[p++] = 0x0F; code[p++] = 0x84; /* je ACCEPT (original, en rel32) */
    ok &= put_rel32(code, p, trampoline, accept);
    p += 4;
    code[p++] = 0xE9; /* jmp BACK */
    ok &= put_rel32(code, p, trampoline, objWl + 5);
    p += 4;

    if (!ok) {
        g_shared->tank_whitelist_hook_error = 3;
        return FALSE;
    }
    memcpy(trampoline, code, p);

    /* 5 octets remplaces : sub ebx,28 (3) + je rel8 (2) */
    if (!patch_jmp(objWl, 5, trampoline)) {
        g_shared->tank_whitelist_hook_error = 3;
        return FALSE;
    }
    return TRUE;
}

/* Charge cote ARME (2026-10-03) : fonction qui convertit le compteur de
 * charge en palier (mgs4.exe+97F020 cette version). Pour le Rail Gun
 * (0x2D) et le Solar Gun (0x0D) uniquement (ID lu dans [[obj+58]+10]),
 * elle compare le compteur [obj+0x398] (frames de charge maintenue) a des
 * seuils globaux et renvoie 0/1/2 (paliers 1/2/3) - pour le Solar Gun,
 * plafonne en plus par l'energie solaire (appel virtuel +0x100). -1 si
 * pas de charge en cours. 4 appelants, dont la fabrication des drapeaux
 * du projectile (mgs4+9A5D90 : `or edi,1800000/2800000/4800000`) -
 * retrouvee en remontant de la creation du projectile (6470D0) au champ
 * [tireur+0x324] par point d'arret materiel.
 * Si railgun_force_charge est actif, que l'arme est l'une des deux et que
 * la charge a commence (compteur > 0), renvoie directement 2 : tous les
 * appelants voient une charge pleine (effets compris), quel que soit le
 * temps de charge ou l'energie solaire restante. Complete les hooks de
 * drapeaux (install_railgun_force_charge_hook, partie charge de
 * install_tank_whitelist_hook), qui restent en place.
 *
 * Trampoline (remplace mov [rsp+10],rbx, 5 octets) :
 *   mov rax,&railgun_force_charge ; cmp byte[rax],1 ; jne ORIG
 *   mov rax,[rcx+58] ; test rax,rax ; je ORIG
 *   mov eax,[rax+10] ; and eax,1FF ; cmp eax,2D ; je CHK ; cmp eax,0D ; jne ORIG
 *  CHK: cmp dword[rcx+398],0 ; jle ORIG
 *   mov eax,2 ; ret
 *  ORIG: mov [rsp+10],rbx ; jmp BACK (motif+5)
 * rax est libre a l'entree (valeur de retour), rcx/rdx ne sont pas
 * modifies. */
static BOOL install_charge_level_hook(void) {
    HMODULE base = GetModuleHandle(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    SIZE_T imageSize = nt->OptionalHeader.SizeOfImage;

    /* mov [rsp+10],rbx ; push rdi ; sub rsp,20 ; mov rax,[rcx+58] ;
     * mov rdx,rcx - unique avec ces 17 octets. */
    static const BYTE pattern[] = {0x48, 0x89, 0x5C, 0x24, 0x10, 0x57, 0x48, 0x83, 0xEC,
                                   0x20, 0x48, 0x8B, 0x41, 0x58, 0x48, 0x8B, 0xD1};
    static const char mask[] = "xxxxxxxxxxxxxxxxx";

    BYTE *objLvl = find_pattern((BYTE *)base, imageSize, pattern, mask, sizeof(pattern));
    if (!objLvl) {
        g_shared->charge_level_hook_error = 1;
        return FALSE;
    }

    BYTE *trampoline = alloc_near(objLvl, 4096);
    if (!trampoline) {
        g_shared->charge_level_hook_error = 2;
        return FALSE;
    }

    UINT64 forceChargeAddr = (UINT64)&g_shared->railgun_force_charge;
    BYTE code[96];
    SIZE_T p = 0;

    code[p++] = 0x48; code[p++] = 0xB8; /* mov rax,&railgun_force_charge */
    memcpy(&code[p], &forceChargeAddr, 8);
    p += 8;
    code[p++] = 0x80; code[p++] = 0x38; code[p++] = 0x01; /* cmp byte[rax],1 */
    code[p++] = 0x75; /* jne ORIG */
    SIZE_T toOrig1 = p++;
    code[p++] = 0x48; code[p++] = 0x8B; code[p++] = 0x41; code[p++] = 0x58; /* mov rax,[rcx+58] */
    code[p++] = 0x48; code[p++] = 0x85; code[p++] = 0xC0; /* test rax,rax */
    code[p++] = 0x74; /* je ORIG */
    SIZE_T toOrig2 = p++;
    code[p++] = 0x8B; code[p++] = 0x40; code[p++] = 0x10; /* mov eax,[rax+10] */
    code[p++] = 0x25; /* and eax,1FF */
    { UINT32 imm = 0x1FF; memcpy(&code[p], &imm, 4); p += 4; }
    code[p++] = 0x83; code[p++] = 0xF8; code[p++] = 0x2D; /* cmp eax,2D */
    code[p++] = 0x74; code[p++] = 0x05; /* je CHK */
    code[p++] = 0x83; code[p++] = 0xF8; code[p++] = 0x0D; /* cmp eax,0D */
    code[p++] = 0x75; /* jne ORIG */
    SIZE_T toOrig3 = p++;
    /* CHK: cmp dword[rcx+398],0 */
    code[p++] = 0x83; code[p++] = 0xB9;
    { UINT32 disp = 0x398; memcpy(&code[p], &disp, 4); p += 4; }
    code[p++] = 0x00;
    code[p++] = 0x7E; /* jle ORIG */
    SIZE_T toOrig4 = p++;
    code[p++] = 0xB8; /* mov eax,2 */
    { UINT32 imm = 2; memcpy(&code[p], &imm, 4); p += 4; }
    code[p++] = 0xC3; /* ret */

    /* ORIG: */
    code[toOrig1] = (BYTE)(p - (toOrig1 + 1));
    code[toOrig2] = (BYTE)(p - (toOrig2 + 1));
    code[toOrig3] = (BYTE)(p - (toOrig3 + 1));
    code[toOrig4] = (BYTE)(p - (toOrig4 + 1));
    memcpy(&code[p], objLvl, 5); /* mov [rsp+10],rbx (original) */
    p += 5;
    code[p++] = 0xE9; /* jmp BACK */
    if (!put_rel32(code, p, trampoline, objLvl + 5)) {
        g_shared->charge_level_hook_error = 3;
        return FALSE;
    }
    p += 4;
    memcpy(trampoline, code, p);

    if (!patch_jmp(objLvl, 5, trampoline)) {
        g_shared->charge_level_hook_error = 3;
        return FALSE;
    }
    return TRUE;
}

/* OctoCamo : masquer des motifs du menu (2026-10-03). Le menu OctoCamo
 * (rempli a l'ouverture du menu pause, mgs4.exe+4F3789 cette version)
 * parcourt la liste des motifs du jeu (code = appel 642320(i)) et ajoute
 * d'office tous les motifs "speciaux" (boss, numeriques, Mouche, Gear...)
 * a sa table [objet menu]+0x14B0 - ces motifs ne sont stockes nulle part
 * dans la partie. Juste apres la lecture du code (`cmp eax,1CAE01`, test
 * du motif Dore), si le code figure dans octocamo_hidden[] (16 codes 24
 * bits, 0 = libre, rempli par le trainer), saute directement a la suite
 * de la boucle (`inc edi`, meme chemin que Dore/Precommande refuses) : le
 * motif n'apparait pas dans le menu. Effet limite a la session (rien
 * n'est ecrit dans la sauvegarde).
 *
 * Trampoline (remplace cmp eax,1CAE01, 5 octets) :
 *   push rcx ; push rdx ; mov rcx,&octocamo_hidden ; mov edx,16
 *  L: cmp [rcx],eax ; je SKIP ; add rcx,4 ; dec edx ; jnz L
 *   pop rdx ; pop rcx ; cmp eax,1CAE01 ; jmp BACK (motif+5, le jne)
 *  SKIP: pop rdx ; pop rcx ; jmp SUITE (inc edi, motif+0xA4) */
static BOOL install_octocamo_hide_hook(void) {
    HMODULE base = GetModuleHandle(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    SIZE_T imageSize = nt->OptionalHeader.SizeOfImage;

    /* mov ecx,edi ; call ???????? ; cmp eax,1CAE01 ; jne +14 - unique. */
    static const BYTE pattern[] = {0x8B, 0xCF, 0xE8, 0, 0, 0, 0, 0x3D, 0x01, 0xAE, 0x1C, 0x00, 0x75, 0x14};
    static const char mask[] = "xxx????xxxxxxx";

    BYTE *raw = find_pattern((BYTE *)base, imageSize, pattern, mask, sizeof(pattern));
    if (!raw) {
        g_shared->octocamo_hide_hook_error = 1;
        return FALSE;
    }
    BYTE *objCmp = raw + 7;
    BYTE *suite = objCmp + 0xA4;
    if (suite[0] != 0xFF || suite[1] != 0xC7) { /* inc edi attendu */
        g_shared->octocamo_hide_hook_error = 4;
        return FALSE;
    }

    BYTE *trampoline = alloc_near(objCmp, 4096);
    if (!trampoline) {
        g_shared->octocamo_hide_hook_error = 2;
        return FALSE;
    }

    UINT64 hiddenAddr = (UINT64)&g_shared->octocamo_hidden[0];
    BYTE code[96];
    SIZE_T p = 0;
    BOOL ok = TRUE;

    code[p++] = 0x51; /* push rcx */
    code[p++] = 0x52; /* push rdx */
    code[p++] = 0x48; code[p++] = 0xB9; /* mov rcx,&octocamo_hidden */
    memcpy(&code[p], &hiddenAddr, 8);
    p += 8;
    code[p++] = 0xBA; /* mov edx,16 */
    { UINT32 imm = 16; memcpy(&code[p], &imm, 4); p += 4; }
    SIZE_T loop = p;
    code[p++] = 0x39; code[p++] = 0x01; /* L: cmp [rcx],eax */
    code[p++] = 0x74; /* je SKIP */
    SIZE_T toSkip = p++;
    code[p++] = 0x48; code[p++] = 0x83; code[p++] = 0xC1; code[p++] = 0x04; /* add rcx,4 */
    code[p++] = 0xFF; code[p++] = 0xCA; /* dec edx */
    code[p++] = 0x75; /* jnz L */
    code[p] = (BYTE)(loop - (p + 1));
    p++;
    code[p++] = 0x5A; /* pop rdx */
    code[p++] = 0x59; /* pop rcx */
    memcpy(&code[p], objCmp, 5); /* cmp eax,1CAE01 (original) */
    p += 5;
    code[p++] = 0xE9; /* jmp BACK */
    ok &= put_rel32(code, p, trampoline, objCmp + 5);
    p += 4;
    /* SKIP: */
    code[toSkip] = (BYTE)(p - (toSkip + 1));
    code[p++] = 0x5A; /* pop rdx */
    code[p++] = 0x59; /* pop rcx */
    code[p++] = 0xE9; /* jmp SUITE */
    ok &= put_rel32(code, p, trampoline, suite);
    p += 4;

    if (!ok) {
        g_shared->octocamo_hide_hook_error = 3;
        return FALSE;
    }
    memcpy(trampoline, code, p);

    if (!patch_jmp(objCmp, 5, trampoline)) {
        g_shared->octocamo_hide_hook_error = 3;
        return FALSE;
    }
    return TRUE;
}

/* Appel de fonctions du jeu dans son propre fil (2026-10-03). La boucle
 * principale (mgs4.exe+3CE55 cette version) appelle a chaque image le
 * gestionnaire de taches (740280) SANS parametre ; l'appel est redirige
 * vers un trampoline qui execute d'abord l'appel demande par le trainer
 * (rpc_fn avec 4 arguments entiers, resultat dans rpc_result, puis
 * rpc_done = 1) puis saute au gestionnaire (son ret revient normalement
 * dans la boucle). La demande est effacee AVANT l'appel (pas de boucle si
 * l'appel plante). Le trainer s'en sert pour equiper en direct, sans menu
 * (voir MGS4Live._equip_octocamo_live / _equip_facecamo_live dans
 * live_trainer.py) : il enchaine plusieurs appels, un par image.
 * Remplace les demandes visage/motif d'origine : le visage appelait
 * equip_facecamo (n'agit que menu ouvert ; en jeu, plantage pendant le
 * rechargement du modele de tete - le trainer met maintenant le jeu en
 * pause avec la fonction du jeu le temps du rechargement) et le motif
 * equip_camo (4F6D00, corrompait le menu camouflage).
 *
 * Trampoline (atteint par call, rsp = 8 mod 16) :
 *   sub rsp,38h
 *   mov rax,&rpc_pending ; cmp byte[rax],0 ; je DONE
 *   mov byte[rax],0 ; charge rcx/rdx/r8/r9 ; call [rpc_fn]
 *   rpc_result = rax ; rpc_done = 1
 *  DONE:
 *   add rsp,38h ; jmp <gestionnaire de taches> */
static BOOL install_main_loop_hook(void) {
    HMODULE base = GetModuleHandle(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    SIZE_T imageSize = nt->OptionalHeader.SizeOfImage;

    static const BYTE loopPattern[] = {0x84, 0xC0, 0x0F, 0x84, 0, 0, 0, 0, 0x0F, 0x1F, 0x80, 0x00, 0x00,
                                       0x00, 0x00, 0xE8, 0, 0, 0, 0, 0xE8};
    static const char loopMask[] = "xxxx????xxxxxxxx????x";

    BYTE *raw = find_pattern((BYTE *)base, imageSize, loopPattern, loopMask, sizeof(loopPattern));
    if (!raw) {
        g_shared->main_loop_hook_error = 1;
        return FALSE;
    }

    BYTE *callSite = raw + 0x14; /* call <gestionnaire de taches> */
    INT32 callRel;
    memcpy(&callRel, callSite + 1, 4);
    BYTE *taskRunner = callSite + 5 + callRel;

    BYTE *trampoline = alloc_near(callSite, 4096);
    if (!trampoline) {
        g_shared->main_loop_hook_error = 2;
        return FALSE;
    }

    BYTE code[256];
    SIZE_T p = 0;

    code[p++] = 0x48; code[p++] = 0x83; code[p++] = 0xEC; code[p++] = 0x38; /* sub rsp,38h */
    {
        UINT64 rpcAddr = (UINT64)&g_shared->rpc_pending;
        UINT64 rpcResultAddr = (UINT64)&g_shared->rpc_result;
        code[p++] = 0x48; code[p++] = 0xB8; memcpy(&code[p], &rpcAddr, 8); p += 8; /* mov rax,&rpc_pending */
        code[p++] = 0x80; code[p++] = 0x38; code[p++] = 0x00; /* cmp byte[rax],0 */
        code[p++] = 0x74; /* je DONE */
        SIZE_T toDone = p++;
        code[p++] = 0xC6; code[p++] = 0x00; code[p++] = 0x00; /* mov byte[rax],0 */
        code[p++] = 0x48; code[p++] = 0x8B; code[p++] = 0x48; code[p++] = 0x0A; /* mov rcx,[rax+0A] */
        code[p++] = 0x48; code[p++] = 0x8B; code[p++] = 0x50; code[p++] = 0x12; /* mov rdx,[rax+12] */
        code[p++] = 0x4C; code[p++] = 0x8B; code[p++] = 0x40; code[p++] = 0x1A; /* mov r8,[rax+1A] */
        code[p++] = 0x4C; code[p++] = 0x8B; code[p++] = 0x48; code[p++] = 0x22; /* mov r9,[rax+22] */
        /* Convention x64 : l'argument n passe dans rN OU xmmN selon son
         * type - on remplit les deux, pour pouvoir passer des flottants
         * (bits du float dans l'argument entier correspondant). */
        code[p++] = 0x66; code[p++] = 0x48; code[p++] = 0x0F; code[p++] = 0x6E; code[p++] = 0xC1; /* movq xmm0,rcx */
        code[p++] = 0x66; code[p++] = 0x48; code[p++] = 0x0F; code[p++] = 0x6E; code[p++] = 0xCA; /* movq xmm1,rdx */
        code[p++] = 0x66; code[p++] = 0x49; code[p++] = 0x0F; code[p++] = 0x6E; code[p++] = 0xD0; /* movq xmm2,r8 */
        code[p++] = 0x66; code[p++] = 0x49; code[p++] = 0x0F; code[p++] = 0x6E; code[p++] = 0xD9; /* movq xmm3,r9 */
        /* 5e et 6e arguments (pile) a zero. */
        code[p++] = 0x48; code[p++] = 0xC7; code[p++] = 0x44; code[p++] = 0x24; code[p++] = 0x20; /* mov qword[rsp+20h],0 */
        code[p++] = 0x00; code[p++] = 0x00; code[p++] = 0x00; code[p++] = 0x00;
        code[p++] = 0x48; code[p++] = 0xC7; code[p++] = 0x44; code[p++] = 0x24; code[p++] = 0x28; /* mov qword[rsp+28h],0 */
        code[p++] = 0x00; code[p++] = 0x00; code[p++] = 0x00; code[p++] = 0x00;
        code[p++] = 0x48; code[p++] = 0x8B; code[p++] = 0x40; code[p++] = 0x02; /* mov rax,[rax+2] (rpc_fn) */
        code[p++] = 0xFF; code[p++] = 0xD0; /* call rax */
        code[p++] = 0x49; code[p++] = 0xBA; memcpy(&code[p], &rpcResultAddr, 8); p += 8; /* mov r10,&rpc_result */
        code[p++] = 0x49; code[p++] = 0x89; code[p++] = 0x02; /* mov [r10],rax */
        code[p++] = 0x49; code[p++] = 0xBA; memcpy(&code[p], &rpcAddr, 8); p += 8; /* mov r10,&rpc_pending */
        code[p++] = 0x41; code[p++] = 0xC6; code[p++] = 0x42; code[p++] = 0x01; code[p++] = 0x01; /* mov byte[r10+1],1 (rpc_done) */
        code[toDone] = (BYTE)(p - (toDone + 1));
    }
    /* DONE: */
    code[p++] = 0x48; code[p++] = 0x83; code[p++] = 0xC4; code[p++] = 0x38; /* add rsp,38h */
    code[p++] = 0xE9; /* jmp gestionnaire de taches */
    if (!put_rel32(code, p, trampoline, taskRunner)) {
        g_shared->main_loop_hook_error = 3;
        return FALSE;
    }
    p += 4;
    memcpy(trampoline, code, p);

    /* Remplace la cible du call (meme longueur, 5 octets) : call trampoline. */
    INT64 rel64 = (INT64)trampoline - (INT64)(callSite + 5);
    if (rel64 > 0x7FFFFFFFLL || rel64 < -0x80000000LL) {
        g_shared->main_loop_hook_error = 3;
        return FALSE;
    }
    DWORD oldProt;
    VirtualProtect(callSite, 5, PAGE_EXECUTE_READWRITE, &oldProt);
    INT32 rel = (INT32)rel64;
    memcpy(callSite + 1, &rel, 4);
    VirtualProtect(callSite, 5, oldProt, &oldProt);
    return TRUE;
}

/* Tanks, partie 2/2 (2026-10-03) : gestionnaire de coups du tank
 * (mgs4.exe+FF9290 cette version). Une fois le coup enregistre (partie
 * 1), il ne cause des degats que si ses drapeaux ([composant+0x10C],
 * meme champ que pour le Rail Gun : 9 bits bas = ID d'arme) ont le bit
 * 12 ou le bit 9 - sinon rien. Si one_shot_kill est actif, force le bit 9
 * dans edx (registre seulement, la memoire n'est pas modifiee) juste
 * apres sa lecture : le coup prend alors le chemin "degats" (call
 * B21FF0), ou install_gecko_one_shot_kill_hook - qui est en realite le
 * hook de la fonction de degats des TANKS, son motif AOB ne correspond
 * qu'a mgs4.exe+B22082 - met la vie a 0. Le bit 15 (coup ignore) reste
 * respecte : il est teste avant les deux autres.
 *
 * Trampoline :
 *   mov edx,[rdi+10C] (original)
 *   push rax ; mov rax,&one_shot_kill ; movzx eax,[rax] ; cmp al,1 ; pop rax
 *   jne +6 ; or edx,200
 *   jmp BACK (motif+6) */
static BOOL install_tank_flags_hook(void) {
    HMODULE base = GetModuleHandle(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    SIZE_T imageSize = nt->OptionalHeader.SizeOfImage;

    /* mov edx,[rdi+10C] ; neg eax ; mov [rsp+50],rbp - unique. */
    static const BYTE pattern[] = {0x8B, 0x97, 0x0C, 0x01, 0x00, 0x00, 0xF7, 0xD8,
                                   0x48, 0x89, 0x6C, 0x24, 0x50};
    static const char mask[] = "xxxxxxxxxxxxx";

    BYTE *objFl = find_pattern((BYTE *)base, imageSize, pattern, mask, sizeof(pattern));
    if (!objFl) {
        g_shared->tank_flags_hook_error = 1;
        return FALSE;
    }

    BYTE *trampoline = alloc_near(objFl, 4096);
    if (!trampoline) {
        g_shared->tank_flags_hook_error = 2;
        return FALSE;
    }

    UINT64 oneShotAddr = (UINT64)&g_shared->one_shot_kill;
    BYTE code[64];
    SIZE_T p = 0;

    memcpy(&code[p], objFl, 6); /* mov edx,[rdi+10C] */
    p += 6;
    code[p++] = 0x50; /* push rax */
    code[p++] = 0x48; code[p++] = 0xB8; /* mov rax,&one_shot_kill */
    memcpy(&code[p], &oneShotAddr, 8);
    p += 8;
    code[p++] = 0x0F; code[p++] = 0xB6; code[p++] = 0x00; /* movzx eax,byte[rax] */
    code[p++] = 0x3C; code[p++] = 0x01; /* cmp al,1 */
    code[p++] = 0x58; /* pop rax (ne touche pas aux flags) */
    code[p++] = 0x75; code[p++] = 0x06; /* jne +6 */
    code[p++] = 0x81; code[p++] = 0xCA; /* or edx,200 */
    { UINT32 imm = 0x200; memcpy(&code[p], &imm, 4); p += 4; }
    code[p++] = 0xE9; /* jmp BACK */
    if (!put_rel32(code, p, trampoline, objFl + 6)) {
        g_shared->tank_flags_hook_error = 3;
        return FALSE;
    }
    p += 4;
    memcpy(trampoline, code, p);

    if (!patch_jmp(objFl, 6, trampoline)) {
        g_shared->tank_flags_hook_error = 3;
        return FALSE;
    }
    return TRUE;
}

/* "Pas de rechargement" par patch de code plutot que reassertion en
 * boucle cote Python (demande utilisateur 2026-09-29) - motif repris du
 * script CE communautaire "No Reload". Contrairement au CE original (qui
 * NOP la seule instruction en dur), ce trampoline garde un flag
 * activable/desactivable : l'instruction qui ecrit le nouveau nombre de
 * munitions du chargeur apres tir est sautee quand no_reload=1, executee
 * normalement sinon - une seule mise en place au chargement, pas de
 * reecriture periodique de la valeur elle-meme.
 *
 * Trampoline (31 octets) :
 *   0   push rax / mov rax,&no_reload / movzx eax,[rax] / cmp al,1 / pop rax
 *   17  je SKIP (offset23)            (no_reload actif : saute l'ecriture)
 *   19  DO_WRITE: <4 octets originaux : mov [rbx+xx],cx>
 *   23  SKIP: <3 octets originaux : test r10d,r10d>
 *   26  jmp BACK
 *   31  (fin) */
static BOOL install_no_reload_hook(void) {
    HMODULE base = GetModuleHandle(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    SIZE_T imageSize = nt->OptionalHeader.SizeOfImage;

    /* 66 03 ? 66 89 ? ? 45 85 D2 - point d'injection reel a +3 (debut de
     * "mov [rbx+xx],cx", 4 octets, suivi de "test r10d,r10d", 3 octets -
     * 7 octets au total a rediriger). */
    static const BYTE pattern[] = {0x66, 0x03, 0, 0x66, 0x89, 0, 0, 0x45, 0x85, 0xD2};
    static const char mask[] = "xx?xx??xxx";

    BYTE *raw = find_pattern((BYTE *)base, imageSize, pattern, mask, sizeof(pattern));
    if (!raw) {
        g_shared->no_reload_hook_error = 1;
        return FALSE;
    }
    BYTE *objNoReload = raw + 3;

    BYTE *trampoline = alloc_near(objNoReload, 4096);
    if (!trampoline) {
        g_shared->no_reload_hook_error = 2;
        return FALSE;
    }

    UINT64 noReloadAddr = (UINT64)&g_shared->no_reload;
    BYTE code[31];
    SIZE_T p = 0;

    /* push rax ; mov rax,&no_reload ; movzx eax,[rax] ; cmp al,1 ; pop rax */
    code[p++] = 0x50;
    code[p++] = 0x48;
    code[p++] = 0xB8;
    memcpy(&code[p], &noReloadAddr, 8);
    p += 8;
    code[p++] = 0x0F;
    code[p++] = 0xB6;
    code[p++] = 0x00;
    code[p++] = 0x3C;
    code[p++] = 0x01;
    code[p++] = 0x58;
    /* je SKIP (offset23) */
    code[p++] = 0x74;
    code[p++] = (BYTE)(23 - 19);

    /* DO_WRITE (offset19) : instruction originale (4 octets copies tels quels) */
    memcpy(&code[p], objNoReload, 4);
    p += 4;

    /* SKIP (offset23) : instruction originale (3 octets copies tels quels) */
    memcpy(&code[p], objNoReload + 4, 3);
    p += 3;

    /* jmp BACK (vers objNoReload+7, suite du code original jamais modifiee) */
    code[p++] = 0xE9;
    {
        BYTE *nextInstrAddr = trampoline + p + 4;
        INT64 rel64 = (INT64)(objNoReload + 7) - (INT64)nextInstrAddr;
        if (rel64 > 0x7FFFFFFFLL || rel64 < -0x80000000LL) {
            g_shared->no_reload_hook_error = 3;
            return FALSE;
        }
        INT32 rel = (INT32)rel64;
        memcpy(&code[p], &rel, 4);
        p += 4;
    }

    memcpy(trampoline, code, p);

    INT64 relToTrampoline = (INT64)trampoline - (INT64)(objNoReload + 5);
    if (relToTrampoline > 0x7FFFFFFFLL || relToTrampoline < -0x80000000LL) {
        g_shared->no_reload_hook_error = 3;
        return FALSE;
    }

    DWORD oldProt;
    VirtualProtect(objNoReload, 7, PAGE_EXECUTE_READWRITE, &oldProt);
    objNoReload[0] = 0xE9;
    INT32 relJmp = (INT32)relToTrampoline;
    memcpy(objNoReload + 1, &relJmp, 4);
    objNoReload[5] = 0x90; /* nop de bourrage : 7 octets remplaces par jmp rel32 (5) */
    objNoReload[6] = 0x90;
    VirtualProtect(objNoReload, 7, oldProt, &oldProt);

    return TRUE;
}

/* "No Alerts" + forcage d'etat - court-circuite entierement la fonction
 * qui evalue l'etat d'alerte de Snake (motif CE "aob No Alerts", auteur
 * RMLSNK ; meme fonction que celle lue/ecrite par "Alert -- Ignore" plus
 * bas, mgs4.exe+B5F120). Point d'injection = tout debut de la fonction
 * (son prologue, "mov [rsp+08],rcx").
 *
 * Deux usages independants du meme court-circuit, par ordre de priorite :
 *  1. no_alerts=1 : ret immediat avec eax=0 - la fonction ne calcule
 *     jamais rien, Snake n'est jamais considere repere (les ennemis
 *     continuent de reagir localement, mais l'etat global ne bascule
 *     jamais).
 *  2. alert_mode_override != 0xFFFF : ret immediat avec eax=la valeur
 *     voulue - la fonction renvoie directement l'etat force comme si
 *     elle l'avait reellement calcule, pour TOUS ses appelants (y
 *     compris les deux appels de install_alert_override_hook plus bas,
 *     qui deviennent redondants une fois ce court-circuit actif, voir
 *     commentaire de cette fonction). Corrige le defaut de
 *     install_alert_override_hook seul (qui ne devenait visible qu'au
 *     prochain evenement de detection reel, demande utilisateur
 *     2026-10-01 : "changer l'etat manuellement doit etre efficace
 *     directement") - en forcant directement ce que la fonction
 *     source renvoie, plus besoin d'attendre un appel declenche par une
 *     vraie detection.
 * Sinon (les deux a leur valeur par defaut) : prologue original execute,
 * fonction tourne normalement.
 *
 * Trampoline (57 octets) :
 *   0   push rax / mov rax,&no_alerts / movzx eax,[rax] / cmp al,1 / pop rax
 *   17  jne CHECK_OVERRIDE (offset22)
 *   19  xor eax,eax
 *   21  ret
 *   22  CHECK_OVERRIDE: push r11 / mov r11,&alert_mode_override
 *   34  mov eax,dword[r11]
 *   37  cmp eax,0xFFFF
 *   42  pop r11
 *   44  je PASS (offset47)              (pas de forcage : on continue normalement)
 *   46  ret                             (forcage actif : eax deja charge avec la valeur voulue)
 *   47  PASS: <5 octets originaux : mov [rsp+08],rcx>
 *   52  jmp BACK
 *   57  (fin) */
static BOOL install_no_alerts_hook(void) {
    HMODULE base = GetModuleHandle(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    SIZE_T imageSize = nt->OptionalHeader.SizeOfImage;

    /* mov [rsp+08],rcx ; push rbx ; sub rsp,xxxxxxxx ; mov rbx,rcx ;
     * call xxxxxxxx ; test eax,eax - signature complete de 23 octets
     * (reprise telle quelle du motif CE) pour eviter tout faux positif,
     * mais seuls les 5 premiers octets (le prologue) sont rediriges. */
    static const BYTE pattern[] = {0x48, 0x89, 0, 0, 0x08, 0, 0x48, 0x81, 0, 0, 0x00, 0, 0,
                                    0x48, 0x8B, 0, 0xE8, 0, 0, 0, 0, 0x85, 0xC0};
    static const char mask[] = "xx??x?xx??x??xx?x????xx";

    BYTE *objNoAlert = find_pattern((BYTE *)base, imageSize, pattern, mask, sizeof(pattern));
    if (!objNoAlert) {
        g_shared->no_alerts_hook_error = 1;
        return FALSE;
    }

    BYTE *trampoline = alloc_near(objNoAlert, 4096);
    if (!trampoline) {
        g_shared->no_alerts_hook_error = 2;
        return FALSE;
    }

    UINT64 noAlertsAddr = (UINT64)&g_shared->no_alerts;
    UINT64 overrideAddr = (UINT64)&g_shared->alert_mode_override;
    BYTE code[57];
    SIZE_T p = 0;

    /* push rax ; mov rax,&no_alerts ; movzx eax,[rax] ; cmp al,1 ; pop rax */
    code[p++] = 0x50;
    code[p++] = 0x48;
    code[p++] = 0xB8;
    memcpy(&code[p], &noAlertsAddr, 8);
    p += 8;
    code[p++] = 0x0F;
    code[p++] = 0xB6;
    code[p++] = 0x00;
    code[p++] = 0x3C;
    code[p++] = 0x01;
    code[p++] = 0x58;
    /* jne CHECK_OVERRIDE (offset22) */
    code[p++] = 0x75;
    code[p++] = (BYTE)(22 - 19);

    /* xor eax,eax ; ret (n'execute que si no_alerts==1) */
    code[p++] = 0x31;
    code[p++] = 0xC0;
    code[p++] = 0xC3;

    /* CHECK_OVERRIDE (offset22) : push r11 ; mov r11,&alert_mode_override */
    code[p++] = 0x41;
    code[p++] = 0x53;
    code[p++] = 0x49;
    code[p++] = 0xBB;
    memcpy(&code[p], &overrideAddr, 8);
    p += 8;
    /* mov eax,dword[r11] */
    code[p++] = 0x41;
    code[p++] = 0x8B;
    code[p++] = 0x03;
    /* cmp eax,0xFFFF (forme courte, pas de ModRM) */
    code[p++] = 0x3D;
    code[p++] = 0xFF;
    code[p++] = 0xFF;
    code[p++] = 0x00;
    code[p++] = 0x00;
    /* pop r11 */
    code[p++] = 0x41;
    code[p++] = 0x5B;
    /* je PASS (offset47) */
    code[p++] = 0x74;
    code[p++] = (BYTE)(47 - 46);
    /* ret (forcage actif : eax deja charge avec la valeur voulue) */
    code[p++] = 0xC3;

    /* PASS (offset47) : instruction originale (5 octets copies tels quels) */
    memcpy(&code[p], objNoAlert, 5);
    p += 5;

    /* jmp BACK (vers objNoAlert+5, suite du code original jamais modifiee) */
    code[p++] = 0xE9;
    {
        BYTE *nextInstrAddr = trampoline + p + 4;
        INT64 rel64 = (INT64)(objNoAlert + 5) - (INT64)nextInstrAddr;
        if (rel64 > 0x7FFFFFFFLL || rel64 < -0x80000000LL) {
            g_shared->no_alerts_hook_error = 3;
            return FALSE;
        }
        INT32 rel = (INT32)rel64;
        memcpy(&code[p], &rel, 4);
        p += 4;
    }

    memcpy(trampoline, code, p);

    INT64 relToTrampoline = (INT64)trampoline - (INT64)(objNoAlert + 5);
    if (relToTrampoline > 0x7FFFFFFFLL || relToTrampoline < -0x80000000LL) {
        g_shared->no_alerts_hook_error = 3;
        return FALSE;
    }

    DWORD oldProt;
    VirtualProtect(objNoAlert, 5, PAGE_EXECUTE_READWRITE, &oldProt);
    objNoAlert[0] = 0xE9;
    INT32 relJmp = (INT32)relToTrampoline;
    memcpy(objNoAlert + 1, &relJmp, 4);
    /* pas de bourrage : 5 octets rediriges, jmp rel32 fait exactement 5 octets */
    VirtualProtect(objNoAlert, 5, oldProt, &oldProt);

    return TRUE;
}

/* "Alert -- Ignore" - force la valeur de la variable d'etat d'alerte du
 * jeu juste avant qu'elle soit ecrite puis comparee pour decider des
 * transitions (motif CE "Alert -- Ignore", auteur RMLSNK - l'adresse
 * statique qu'il ecrit, mgs4.exe+1D77AB8, est deja exposee en lecture
 * seule cote Python sous le nom ALERT_STATE_RVA, confirmee fiable en
 * lecture mais PAS en ecriture directe car le jeu la recalcule en
 * continu - d'ou la necessite de ce patch de code, qui intercepte la
 * valeur juste avant qu'elle reparte en lecture/comparaison, plutot que
 * d'essayer de reecrire par-dessus un resultat deja perime).
 * alert_mode_override = 0xFFFF (desactive, comportement normal) ou une
 * des valeurs ALERT_STATE_NAMES cote Python (0=Normal, 1=Alerte,
 * 2=Evasion, 3=Prudence) pour forcer cet etat.
 *
 * Trampoline (37 octets) :
 *   0   push r11
 *   2   mov r11,&alert_mode_override
 *   12  cmp dword[r11],0xFFFF
 *   19  je PASS (offset24)              (pas de forcage : eax garde sa valeur calculee)
 *   21  mov eax,dword[r11]              (forcage : eax <- valeur voulue)
 *   24  PASS: pop r11
 *   26  <6 octets originaux : mov [mgs4.exe+xxxxxxxx],eax>
 *   32  jmp BACK
 *   37  (fin) */
static BOOL install_alert_override_hook(void) {
    HMODULE base = GetModuleHandle(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    SIZE_T imageSize = nt->OptionalHeader.SizeOfImage;

    /* mov edi,edx ; call xxxxxxxx ; mov rcx,rbp ; mov [xxxxxxxx],eax -
     * motif CE repris tel quel (12 octets de signature), point reel
     * d'injection a +0xA (le "mov [xxxxxxxx],eax" de 6 octets). */
    static const BYTE pattern[] = {0x8B, 0, 0xE8, 0, 0, 0, 0, 0x48, 0x8B, 0, 0x89, 0x05};
    static const char mask[] = "x?x????xx?xx";

    BYTE *raw = find_pattern((BYTE *)base, imageSize, pattern, mask, sizeof(pattern));
    if (!raw) {
        g_shared->alert_override_hook_error = 1;
        return FALSE;
    }
    BYTE *objAlert = raw + 0xA;

    BYTE *trampoline = alloc_near(objAlert, 4096);
    if (!trampoline) {
        g_shared->alert_override_hook_error = 2;
        return FALSE;
    }

    UINT64 overrideAddr = (UINT64)&g_shared->alert_mode_override;
    BYTE code[37];
    SIZE_T p = 0;

    /* push r11 */
    code[p++] = 0x41;
    code[p++] = 0x53;
    /* mov r11,&alert_mode_override */
    code[p++] = 0x49;
    code[p++] = 0xBB;
    memcpy(&code[p], &overrideAddr, 8);
    p += 8;
    /* cmp dword[r11],0xFFFF */
    code[p++] = 0x41;
    code[p++] = 0x81;
    code[p++] = 0x3B;
    code[p++] = 0xFF;
    code[p++] = 0xFF;
    code[p++] = 0x00;
    code[p++] = 0x00;
    /* je PASS (offset24) */
    code[p++] = 0x74;
    code[p++] = (BYTE)(24 - 21);
    /* mov eax,dword[r11] */
    code[p++] = 0x41;
    code[p++] = 0x8B;
    code[p++] = 0x03;

    /* PASS (offset24) : pop r11 */
    code[p++] = 0x41;
    code[p++] = 0x5B;

    /* instruction originale (6 octets : 89 05 + disp32) - "mov [rip+disp32],eax"
     * (ModRM=05 => mod=00,reg=000,rm=101, cas special RIP-relatif en
     * mode 64 bits, PAS une adresse absolue). Copier ces 6 octets tels
     * quels dans le trampoline (a une tout autre adresse memoire) ferait
     * pointer l'ecriture n'importe ou - bug reel corrige ici (2026-10-01,
     * voir notes.md) : le disp32 est recalcule pour continuer a viser la
     * MEME adresse absolue (mgs4.exe+1D77AB8) depuis sa nouvelle position. */
    {
        INT32 origDisp32;
        memcpy(&origDisp32, objAlert + 2, 4);
        UINT64 targetAbs = (UINT64)(objAlert + 6) + (INT64)origDisp32;

        SIZE_T instrOffset = p;
        memcpy(&code[p], objAlert, 6);
        p += 6;

        INT64 newDisp64 = (INT64)targetAbs - (INT64)(trampoline + instrOffset + 6);
        if (newDisp64 > 0x7FFFFFFFLL || newDisp64 < -0x80000000LL) {
            g_shared->alert_override_hook_error = 3;
            return FALSE;
        }
        INT32 newDisp32 = (INT32)newDisp64;
        memcpy(&code[instrOffset + 2], &newDisp32, 4);
    }

    /* jmp BACK (vers objAlert+6, suite du code original jamais modifiee) */
    code[p++] = 0xE9;
    {
        BYTE *nextInstrAddr = trampoline + p + 4;
        INT64 rel64 = (INT64)(objAlert + 6) - (INT64)nextInstrAddr;
        if (rel64 > 0x7FFFFFFFLL || rel64 < -0x80000000LL) {
            g_shared->alert_override_hook_error = 3;
            return FALSE;
        }
        INT32 rel = (INT32)rel64;
        memcpy(&code[p], &rel, 4);
        p += 4;
    }

    memcpy(trampoline, code, p);

    INT64 relToTrampoline = (INT64)trampoline - (INT64)(objAlert + 5);
    if (relToTrampoline > 0x7FFFFFFFLL || relToTrampoline < -0x80000000LL) {
        g_shared->alert_override_hook_error = 3;
        return FALSE;
    }

    DWORD oldProt;
    VirtualProtect(objAlert, 6, PAGE_EXECUTE_READWRITE, &oldProt);
    objAlert[0] = 0xE9;
    INT32 relJmp = (INT32)relToTrampoline;
    memcpy(objAlert + 1, &relJmp, 4);
    objAlert[5] = 0x90; /* nop de bourrage : 6 octets remplaces par jmp rel32 (5) */
    VirtualProtect(objAlert, 6, oldProt, &oldProt);

    return TRUE;
}

/* Hook diagnostique (lecture seule, aucun changement de comportement) -
 * capture le pointeur retourne par l'appel qui recupere le conteneur du
 * tableau de "capteurs" de detection par ennemi (chaque entree = 224
 * octets, agregees en MAX/somme par B5F120 pour calculer l'etat
 * d'alerte reel, voir install_no_alerts_hook) - demande utilisateur
 * 2026-10-01 : trouver ce tableau pour pouvoir forcer une seule entree
 * reelle plutot que les valeurs agregees (qui ne sont que des resultats
 * d'affichage, jamais lues par le reste du jeu, voir notes.md). Point
 * d'injection juste apres le "call" qui renvoie ce pointeur dans rax,
 * avant qu'il soit copie dans r15 par le code original.
 *
 * Trampoline (27 octets) :
 *   0   push r11 / mov r11,&combat_array_ptr
 *   12  mov [r11],rax
 *   15  pop r11
 *   17  <5 octets originaux : mov [rsp+30],rax>
 *   22  jmp BACK
 *   27  (fin) */
static BOOL install_combat_array_hook(void) {
    HMODULE base = GetModuleHandle(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    SIZE_T imageSize = nt->OptionalHeader.SizeOfImage;

    /* call xxxxxxxx ; mov [rsp+30],rax ; mov r15,rax ; test rax,rax -
     * signature de 16 octets, point reel d'injection a +5 (juste apres
     * le call, debut de "mov [rsp+30],rax"). */
    static const BYTE pattern[] = {0xE8, 0, 0, 0, 0, 0x48, 0x89, 0x44, 0x24, 0x30,
                                    0x4C, 0x8B, 0xF8, 0x48, 0x85, 0xC0};
    static const char mask[] = "x????xxxxxxxxxxx";

    BYTE *raw = find_pattern((BYTE *)base, imageSize, pattern, mask, sizeof(pattern));
    if (!raw) {
        g_shared->combat_array_hook_error = 1;
        return FALSE;
    }
    BYTE *objCombatArray = raw + 5;

    BYTE *trampoline = alloc_near(objCombatArray, 4096);
    if (!trampoline) {
        g_shared->combat_array_hook_error = 2;
        return FALSE;
    }

    UINT64 combatArrayAddr = (UINT64)&g_shared->combat_array_ptr;
    BYTE code[27];
    SIZE_T p = 0;

    /* push r11 ; mov r11,&combat_array_ptr */
    code[p++] = 0x41;
    code[p++] = 0x53;
    code[p++] = 0x49;
    code[p++] = 0xBB;
    memcpy(&code[p], &combatArrayAddr, 8);
    p += 8;
    /* mov [r11],rax */
    code[p++] = 0x49;
    code[p++] = 0x89;
    code[p++] = 0x03;
    /* pop r11 */
    code[p++] = 0x41;
    code[p++] = 0x5B;

    /* instruction originale (5 octets copies tels quels) */
    memcpy(&code[p], objCombatArray, 5);
    p += 5;

    /* jmp BACK (vers objCombatArray+5, suite du code original jamais modifiee) */
    code[p++] = 0xE9;
    {
        BYTE *nextInstrAddr = trampoline + p + 4;
        INT64 rel64 = (INT64)(objCombatArray + 5) - (INT64)nextInstrAddr;
        if (rel64 > 0x7FFFFFFFLL || rel64 < -0x80000000LL) {
            g_shared->combat_array_hook_error = 3;
            return FALSE;
        }
        INT32 rel = (INT32)rel64;
        memcpy(&code[p], &rel, 4);
        p += 4;
    }

    memcpy(trampoline, code, p);

    INT64 relToTrampoline = (INT64)trampoline - (INT64)(objCombatArray + 5);
    if (relToTrampoline > 0x7FFFFFFFLL || relToTrampoline < -0x80000000LL) {
        g_shared->combat_array_hook_error = 3;
        return FALSE;
    }

    DWORD oldProt;
    VirtualProtect(objCombatArray, 5, PAGE_EXECUTE_READWRITE, &oldProt);
    objCombatArray[0] = 0xE9;
    INT32 relJmp = (INT32)relToTrampoline;
    memcpy(objCombatArray + 1, &relJmp, 4);
    /* pas de bourrage : 5 octets rediriges, jmp rel32 fait exactement 5 octets */
    VirtualProtect(objCombatArray, 5, oldProt, &oldProt);

    return TRUE;
}

/* Force le PARAMETRE edx (nouvel etat d'alerte) a l'entree de la
 * fonction qui diffuse reellement le changement d'etat a tout le jeu
 * (reinitialise une serie de champs sur l'objet gestionnaire puis
 * appelle plusieurs sous-fonctions avec ce meme edx - IA, audio,
 * affichage - voir notes.md pour le detail de la pile d'appels trouvee
 * via point d'arret materiel x64dbg, 2026-10-01). Contrairement a
 * install_alert_override_hook (desactive, n'agissait qu'en aval sur une
 * simple valeur de cache jamais relue par le reste du jeu), celui-ci
 * agit a la toute premiere etape utile, avant que la valeur ne soit
 * propagee partout - bien plus susceptible d'avoir un effet reel.
 * Reutilise alert_mode_override (meme flag que install_alert_override_hook,
 * 0xFFFF = desactive).
 *
 * Trampoline (36 octets) :
 *   0   push r11 / mov r11,&alert_mode_override
 *   12  mov eax,dword[r11]
 *   15  cmp eax,0xFFFF
 *   20  je PASS (offset24)              (pas de forcage : edx garde sa valeur)
 *   22  mov edx,eax                     (forcage : edx <- valeur voulue)
 *   24  PASS: pop r11
 *   26  <5 octets originaux : mov [rsp+8],rbx>
 *   31  jmp BACK
 *   36  (fin) */
static BOOL install_alert_dispatch_hook(void) {
    HMODULE base = GetModuleHandle(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)base + dos->e_lfanew);
    SIZE_T imageSize = nt->OptionalHeader.SizeOfImage;

    /* Prologue complet de la fonction (37 octets, tous fixes - aucun
     * joker necessaire, deja tres specifique grace aux constantes
     * immediates 0xE0/0x14C). */
    static const BYTE pattern[] = {
        0x48, 0x89, 0x5C, 0x24, 0x08, 0x48, 0x89, 0x6C, 0x24, 0x10, 0x48, 0x89, 0x74, 0x24, 0x18,
        0x57, 0x41, 0x54, 0x41, 0x55, 0x41, 0x56, 0x41, 0x57, 0x48, 0x81, 0xEC, 0xE0, 0x00, 0x00,
        0x00, 0x8B, 0x81, 0x4C, 0x01, 0x00, 0x00};
    static const char mask[] = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";

    BYTE *objDispatch = find_pattern((BYTE *)base, imageSize, pattern, mask, sizeof(pattern));
    if (!objDispatch) {
        g_shared->dispatch_hook_error = 1;
        return FALSE;
    }

    BYTE *trampoline = alloc_near(objDispatch, 4096);
    if (!trampoline) {
        g_shared->dispatch_hook_error = 2;
        return FALSE;
    }

    UINT64 overrideAddr = (UINT64)&g_shared->alert_mode_override;
    BYTE code[36];
    SIZE_T p = 0;

    /* push r11 ; mov r11,&alert_mode_override */
    code[p++] = 0x41;
    code[p++] = 0x53;
    code[p++] = 0x49;
    code[p++] = 0xBB;
    memcpy(&code[p], &overrideAddr, 8);
    p += 8;
    /* mov eax,dword[r11] */
    code[p++] = 0x41;
    code[p++] = 0x8B;
    code[p++] = 0x03;
    /* cmp eax,0xFFFF */
    code[p++] = 0x3D;
    code[p++] = 0xFF;
    code[p++] = 0xFF;
    code[p++] = 0x00;
    code[p++] = 0x00;
    /* je PASS (offset24) */
    code[p++] = 0x74;
    code[p++] = (BYTE)(24 - 22);
    /* mov edx,eax */
    code[p++] = 0x89;
    code[p++] = 0xC2;

    /* PASS (offset24) : pop r11 */
    code[p++] = 0x41;
    code[p++] = 0x5B;

    /* instruction originale (5 octets copies tels quels) */
    memcpy(&code[p], objDispatch, 5);
    p += 5;

    /* jmp BACK (vers objDispatch+5, suite du code original jamais modifiee) */
    code[p++] = 0xE9;
    {
        BYTE *nextInstrAddr = trampoline + p + 4;
        INT64 rel64 = (INT64)(objDispatch + 5) - (INT64)nextInstrAddr;
        if (rel64 > 0x7FFFFFFFLL || rel64 < -0x80000000LL) {
            g_shared->dispatch_hook_error = 3;
            return FALSE;
        }
        INT32 rel = (INT32)rel64;
        memcpy(&code[p], &rel, 4);
        p += 4;
    }

    memcpy(trampoline, code, p);

    INT64 relToTrampoline = (INT64)trampoline - (INT64)(objDispatch + 5);
    if (relToTrampoline > 0x7FFFFFFFLL || relToTrampoline < -0x80000000LL) {
        g_shared->dispatch_hook_error = 3;
        return FALSE;
    }

    DWORD oldProt;
    VirtualProtect(objDispatch, 5, PAGE_EXECUTE_READWRITE, &oldProt);
    objDispatch[0] = 0xE9;
    INT32 relJmp = (INT32)relToTrampoline;
    memcpy(objDispatch + 1, &relJmp, 4);
    /* pas de bourrage : 5 octets rediriges, jmp rel32 fait exactement 5 octets */
    VirtualProtect(objDispatch, 5, oldProt, &oldProt);

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
            memset((void *)g_shared->reg_dump, 0, sizeof(g_shared->reg_dump));
            g_shared->reg_dump_seq = 0;
            g_shared->damage_hook_addr = 0;
            g_shared->railgun_instant_kill = 0;
            g_shared->railgun_force_charge = 0;
            g_shared->force_charge_hook_installed = 0;
            g_shared->force_charge_hook_error = 0;
            g_shared->probe_rsi = 0;
            g_shared->probe_rdi = 0;
            g_shared->probe_rbx = 0;
            g_shared->probe_r12 = 0;
            g_shared->probe_seq = 0;
            g_shared->probe_hook_installed = 0;
            g_shared->probe_hook_error = 0;
            g_shared->boss_actor = 0;
            g_shared->boss_hook_installed = 0;
            g_shared->boss_hook_error = 0;
            g_shared->boss_actor2 = 0;
            g_shared->boss_hook2_installed = 0;
            g_shared->boss_hook2_error = 0;
            g_shared->coord_actor = 0;
            g_shared->coord_hook_installed = 0;
            g_shared->coord_hook_error = 0;
            g_shared->gecko_hook_installed = 0;
            g_shared->gecko_hook_error = 0;
            g_shared->no_reload = 0;
            g_shared->no_reload_hook_installed = 0;
            g_shared->no_reload_hook_error = 0;
            g_shared->no_alerts = 0;
            g_shared->no_alerts_hook_installed = 0;
            g_shared->no_alerts_hook_error = 0;
            g_shared->alert_mode_override = 0xFFFF;
            g_shared->alert_override_hook_installed = 0;
            g_shared->alert_override_hook_error = 0;
            g_shared->combat_array_ptr = 0;
            g_shared->combat_array_hook_installed = 0;
            g_shared->combat_array_hook_error = 0;
            g_shared->dispatch_hook_installed = 0;
            g_shared->dispatch_hook_error = 0;
            g_shared->tank_whitelist_hook_installed = 0;
            g_shared->tank_whitelist_hook_error = 0;
            g_shared->tank_flags_hook_installed = 0;
            g_shared->tank_flags_hook_error = 0;
            g_shared->charge_level_hook_installed = 0;
            g_shared->charge_level_hook_error = 0;
            for (int i = 0; i < 16; i++) {
                g_shared->octocamo_hidden[i] = 0;
            }
            g_shared->octocamo_hide_hook_installed = 0;
            g_shared->octocamo_hide_hook_error = 0;
            g_shared->main_loop_hook_installed = 0;
            g_shared->main_loop_hook_error = 0;
            g_shared->rpc_pending = 0;
            g_shared->rpc_done = 0;
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

    /* Hook independant, voir install_railgun_force_charge_hook - trouve
     * le 2026-10-02, point d'accroche different (chez l'appelant) de
     * celui du hook de degats ci-dessus. */
    if (g_shared && install_railgun_force_charge_hook()) {
        g_shared->force_charge_hook_installed = 1;
    }

    /* Hook de diagnostic temporaire, voir install_r12_probe_hook. */
    if (g_shared && install_r12_probe_hook()) {
        g_shared->probe_hook_installed = 1;
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

    if (g_shared && install_gecko_one_shot_kill_hook()) {
        g_shared->gecko_hook_installed = 1;
    }

    if (g_shared && install_tank_whitelist_hook()) {
        g_shared->tank_whitelist_hook_installed = 1;
    }

    if (g_shared && install_tank_flags_hook()) {
        g_shared->tank_flags_hook_installed = 1;
    }

    if (g_shared && install_charge_level_hook()) {
        g_shared->charge_level_hook_installed = 1;
    }

    if (g_shared && install_octocamo_hide_hook()) {
        g_shared->octocamo_hide_hook_installed = 1;
    }

    if (g_shared && install_main_loop_hook()) {
        g_shared->main_loop_hook_installed = 1;
    }

    if (g_shared && install_no_reload_hook()) {
        g_shared->no_reload_hook_installed = 1;
    }

    if (g_shared && install_no_alerts_hook()) {
        g_shared->no_alerts_hook_installed = 1;
    }

    /* Devenu redondant depuis que install_no_alerts_hook court-circuite
     * directement mgs4.exe+B5F120 (la fonction source) pour le forcage
     * d'etat - celui-ci n'agissait qu'en aval, sur UNE seule des deux
     * valeurs ecrites a partir du resultat de cette fonction, et son
     * effet ne devenait visible qu'au prochain appel reellement
     * declenche par une detection (2026-10-01, demande utilisateur :
     * "changer l'etat manuellement doit etre efficace directement").
     * Garde pour reference/diagnostic (alert_override_hook_installed
     * reste donc a 0, fonction toujours definie plus haut) mais plus
     * installee par defaut. */
    (void)install_alert_override_hook;

    if (g_shared && install_combat_array_hook()) {
        g_shared->combat_array_hook_installed = 1;
    }

    if (g_shared && install_alert_dispatch_hook()) {
        g_shared->dispatch_hook_installed = 1;
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
