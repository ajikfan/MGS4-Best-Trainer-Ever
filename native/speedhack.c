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
#include <math.h>

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
 * sur lequel one_shot_kill n'a pas d'effet, ex. un boss), [32..61]
 * reserve (anciens hooks de suivi des boss et des coordonnees, repris de
 * la table CE communautaire et retires le 2026-10-12 : la position vient
 * de la table des joueurs du jeu, les boss de patchs de code - octets
 * gardes pour ne pas decaler les offsets lus cote Python), [62] uint8
 * gecko_hook_installed, [63] uint8
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
    UINT8 reserved_32[30]; /* anciens boss/coord trackers, voir plus haut */
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
    /* [392] Un coup, un mort sur ce qui n'a pas d'endurance (Gekko, tanks :
     * install_gecko_one_shot_kill_hook, install_tank_whitelist_hook,
     * install_tank_flags_hook), separe de one_shot_kill (humains) pour
     * rester actif en mode Non letal (2026-10-10). */
    UINT8 machine_kill;
    /* [393] Mode photo (2026-10-23) : la camera libre est pilotee ici, une
     * fois par image dans le fil du jeu (photo_frame, appelee par le
     * crochet de boucle principale) - une boucle Python dans le trainer
     * etait bloquee 1 s toutes les 3-4 s par le reste du trainer. Le
     * trainer pose les patchs (camera libre, manette detournee vers une
     * copie) et remplit ces champs ; photo_version = 1 indique une DLL qui
     * sait le faire. */
    UINT8 photo_active;
    UINT8 photo_version;
    UINT8 photo_reserved[5];
    UINT64 photo_pad;     /* [400] copie de la manette B (format PS3) */
    UINT64 photo_camera;  /* [408] matrice monde de la camera du jeu */
    float photo_step;     /* [416] unites par image, stick a fond */
    float photo_fast;     /* [420] facteur avec carre (X) maintenu */
    float photo_turn;     /* [424] radians par image, stick droit a fond */
    float photo_deadzone; /* [428] */
    UINT32 photo_frames;  /* [432] images traitees (diagnostic) */
    /* [436] HUD masque pendant le mode photo (2026-10-24, valide en jeu) :
     * mot de drapeaux global (mgs4+1D77AA8) teste par chaque element du
     * HUD (bit 4 : radar et indice de camouflage, autres bits : le reste).
     * Le jeu efface certains bits lui-meme : ils sont reimposes a chaque
     * image. 0 = HUD laisse tel quel. */
    UINT32 photo_hud_mask;
    UINT64 photo_hud;     /* [440] adresse du mot de drapeaux */
    /* [448] Appuis sur triangle (Y, touche E) pendant le mode photo : le
     * trainer les lit et fige ou relance le temps (2026-10-24). */
    UINT32 photo_toggles;
    /* [452] Cinematique en cours (le trainer le signale) : le jeu n'y met
     * plus ZQSD ni la souris dans la manette virtuelle (seuls quelques
     * boutons passent) ; la DLL les lit alors elle-meme (2026-10-24). */
    UINT8 photo_direct;
    UINT8 photo_direct_reserved[3];
    float photo_mouse;    /* [456] radians par pixel de souris */
    /* [460] Zoom du mode photo (2026-10-24) : le trainer fige le zoom du jeu
     * (camera+0x380, voir MGS4Live._freeze_zoom) ; la DLL le modifie avec la
     * croix haut/bas (la molette y arrive en partie) et la molette lue par
     * l'accroche souris en cinematique. Facteur par image, 0 = pas de zoom. */
    float photo_zoom_rate;
    UINT64 photo_zoom;    /* [464] adresse du zoom (float) */
    /* [472] Appuis sur croix (A) : le trainer teleporte Snake a la camera. */
    UINT32 photo_teleports;
} SharedState;
#pragma pack(pop)
_Static_assert(offsetof(SharedState, rpc_result) == 384 && offsetof(SharedState, machine_kill) == 392,
               "offsets lus par live_trainer.py");
_Static_assert(offsetof(SharedState, photo_active) == 393 && offsetof(SharedState, photo_pad) == 400 &&
                   offsetof(SharedState, photo_step) == 416 && offsetof(SharedState, photo_frames) == 432,
               "offsets lus par mgs4trainer/core/speedhack.py (mode photo)");
_Static_assert(offsetof(SharedState, photo_hud_mask) == 436 && offsetof(SharedState, photo_hud) == 440,
               "offsets lus par mgs4trainer/core/speedhack.py (HUD du mode photo)");
_Static_assert(offsetof(SharedState, photo_toggles) == 448 && offsetof(SharedState, photo_direct) == 452 &&
                   offsetof(SharedState, photo_mouse) == 456 && offsetof(SharedState, photo_zoom_rate) == 460 &&
                   offsetof(SharedState, photo_zoom) == 464 && offsetof(SharedState, photo_teleports) == 472,
               "offsets lus par mgs4trainer/core/speedhack.py (temps du mode photo)");

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
 * Patchs de code : outils communs (recherche de motif, allocation
 * proche). Les hooks repris de la table Cheat Engine communautaire
 * MGS4.CT (degats des soldats "aob Damage", Gekko/tanks "aob Damage
 * Gecko", "No Reload", "aob No Alerts", "Alert -- Ignore") ont ete
 * retires le 2026-10-13 : le trainer les remplace par ses propres patchs
 * de code (mgs4trainer/live/code_patches.py). Leurs champs de SharedState
 * restent reserves pour ne pas decaler les offsets.
 * ------------------------------------------------------------------ */

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

    UINT64 oneShotAddr = (UINT64)&g_shared->machine_kill; /* Gekko/tanks, voir machine_kill */
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
/* Mode photo : une image de camera libre. Manette au format PS3 (boutons
 * du 2e octet : L1 04, R1 08, croix 40 ; sticks +4/+5 droit, +6/+7 gauche,
 * 0x80 au centre). Camera : 4 lignes de 4 flottants (droite, bas, regard,
 * position). Meme calcul que MGS4Live.move_photo_camera. */
static float photo_axis(BYTE raw, float deadzone) {
    float v = ((float)raw - 128.0f) / 127.0f;
    if (v > 1.0f) v = 1.0f;
    if (v < -1.0f) v = -1.0f;
    return (v < deadzone && v > -deadzone) ? 0.0f : v;
}

static void photo_normalize(float *v) {
    float n = sqrtf(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
    if (n > 0.0f) { v[0] /= n; v[1] /= n; v[2] /= n; }
}

static void photo_cross(const float *a, const float *b, float *out) {
    out[0] = a[1] * b[2] - a[2] * b[1];
    out[1] = a[2] * b[0] - a[0] * b[2];
    out[2] = a[0] * b[1] - a[1] * b[0];
}

static void photo_rotate(float *v, const float *axis, float angle) {
    float c = cosf(angle), sn = sinf(angle);
    float dot = v[0] * axis[0] + v[1] * axis[1] + v[2] * axis[2];
    float cr[3];
    photo_cross(axis, v, cr);
    for (int i = 0; i < 3; i++) v[i] = v[i] * c + cr[i] * sn + axis[i] * dot * (1.0f - c);
}

/* Souris en cinematique (2026-10-24) : lire la position du curseur ne
 * marchait pas (le jeu le recentre lui-meme : mouvements vus par a-coups).
 * Une accroche souris de bas niveau recoit chaque mouvement physique ; dans
 * le rappel, le curseur n'a pas encore bouge, d'ou l'ecart. Installee par un
 * fil dedie seulement pendant le mode photo en cinematique. */
static HINSTANCE g_hinst = NULL;
static volatile LONG g_mouse_dx = 0, g_mouse_dy = 0, g_mouse_wheel = 0;

static LRESULT CALLBACK photo_mouse_hook(int code, WPARAM wp, LPARAM lp) {
    if (code == HC_ACTION && wp == WM_MOUSEMOVE) {
        const MSLLHOOKSTRUCT *m = (const MSLLHOOKSTRUCT *)lp;
        POINT cur;
        if (!(m->flags & LLMHF_INJECTED) && GetCursorPos(&cur)) {
            InterlockedExchangeAdd(&g_mouse_dx, m->pt.x - cur.x);
            InterlockedExchangeAdd(&g_mouse_dy, m->pt.y - cur.y);
        }
    } else if (code == HC_ACTION && wp == WM_MOUSEWHEEL) {
        const MSLLHOOKSTRUCT *m = (const MSLLHOOKSTRUCT *)lp;
        if (!(m->flags & LLMHF_INJECTED)) InterlockedExchangeAdd(&g_mouse_wheel, (SHORT)HIWORD(m->mouseData));
    }
    return CallNextHookEx(NULL, code, wp, lp);
}

static DWORD WINAPI photo_mouse_thread(LPVOID param) {
    (void)param;
    HHOOK hook = NULL;
    MSG msg;
    for (;;) {
        BOOL want = g_shared && g_shared->photo_active && g_shared->photo_direct;
        if (want && !hook) {
            InterlockedExchange(&g_mouse_dx, 0);
            InterlockedExchange(&g_mouse_dy, 0);
            InterlockedExchange(&g_mouse_wheel, 0);
            hook = SetWindowsHookExW(WH_MOUSE_LL, photo_mouse_hook, g_hinst, 0);
        } else if (!want && hook) {
            UnhookWindowsHookEx(hook);
            hook = NULL;
        }
        MsgWaitForMultipleObjects(0, NULL, FALSE, 100, QS_ALLINPUT);
        while (PeekMessageW(&msg, NULL, 0, 0, PM_REMOVE)) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    }
    return 0;
}

static void photo_frame(void) {
    volatile SharedState *sh = g_shared;
    if (!sh || !sh->photo_active || !sh->photo_pad || !sh->photo_camera) return;
    const BYTE *pad = (const BYTE *)(UINT64)sh->photo_pad;
    float *cam = (float *)(UINT64)sh->photo_camera;
    sh->photo_frames++;
    if (sh->photo_hud && sh->photo_hud_mask) *(volatile UINT32 *)(UINT64)sh->photo_hud |= sh->photo_hud_mask;
    float dz = sh->photo_deadzone;
    float lx = photo_axis(pad[6], dz), ly = photo_axis(pad[7], dz);
    float rx = photo_axis(pad[4], dz), ry = photo_axis(pad[5], dz);
    /* La souris arrive dans le stick droit par petites valeurs : racine
     * carree pour les amplifier (stick a fond inchange). */
    rx = rx < 0.0f ? -sqrtf(-rx) : sqrtf(rx);
    ry = ry < 0.0f ? -sqrtf(-ry) : sqrtf(ry);
    /* Monter : R1/R2 (RB/RT, clic gauche) ; descendre : L1/L2 (LB/LT, clic
     * droit) ; rapide : carre (X, touche A). Espace (croix) est lu par le
     * jeu en dehors de la manette virtuelle : le trainer le reserve. */
    BYTE buttons = pad[1];
    /* Triangle (Y, touche E) : figer ou relancer le temps, fait par le
     * trainer (case Pause) ; ici on compte seulement les appuis. */
    static BYTE prev_buttons = 0;
    if ((buttons & 0x10) && !(prev_buttons & 0x10)) sh->photo_toggles++;
    if ((buttons & 0x40) && !(prev_buttons & 0x40)) sh->photo_teleports++; /* croix (A) */
    prev_buttons = buttons;
    /* Clavier lu directement (Maj toujours, le reste en cinematique),
     * seulement quand la fenetre du jeu est au premier plan. */
    DWORD fg_pid = 0;
    HWND fg = GetForegroundWindow();
    if (fg) GetWindowThreadProcessId(fg, &fg_pid);
    BOOL focused = fg && fg_pid == GetCurrentProcessId();
    BOOL shift = focused && (GetAsyncKeyState(VK_SHIFT) & 0x8000);
    float mouse_x = 0.0f, mouse_y = 0.0f;
    static BOOL direct_before = FALSE;
    BOOL direct = focused && sh->photo_direct;
    if (direct) {
        /* Touches par position (scancodes), quelle que soit la disposition :
         * Z/W 0x11, Q/A 0x1E, S 0x1F, D 0x20, A/Q 0x10 (rapide). */
#define PHOTO_KEY(sc) ((GetAsyncKeyState(MapVirtualKeyW((sc), MAPVK_VSC_TO_VK)) & 0x8000) ? 1.0f : 0.0f)
        float kx = PHOTO_KEY(0x20) - PHOTO_KEY(0x1E), ky = PHOTO_KEY(0x1F) - PHOTO_KEY(0x11);
        if (GetAsyncKeyState(VK_CONTROL) & 0x8000) { kx *= 0.5f; ky *= 0.5f; }
        if (lx == 0.0f && ly == 0.0f) { lx = kx; ly = ky; }
        if (PHOTO_KEY(0x10)) buttons |= 0x80;
#undef PHOTO_KEY
        if (GetAsyncKeyState(VK_LBUTTON) & 0x8000) buttons |= 0x02;
        if (GetAsyncKeyState(VK_RBUTTON) & 0x8000) buttons |= 0x01;
        /* Souris : mouvements recus par photo_mouse_hook depuis l'image
         * precedente ; curseur garde au centre pour ne pas buter au bord
         * (SetCursorPos ne passe pas par l'accroche). */
        LONG dx = InterlockedExchange(&g_mouse_dx, 0), dy = InterlockedExchange(&g_mouse_dy, 0);
        if (direct_before) {
            mouse_x = (float)dx * sh->photo_mouse;
            mouse_y = (float)dy * sh->photo_mouse;
        }
        RECT rc;
        POINT center;
        if (GetClientRect(fg, &rc)) {
            center.x = (rc.left + rc.right) / 2;
            center.y = (rc.top + rc.bottom) / 2;
            ClientToScreen(fg, &center);
            SetCursorPos(center.x, center.y);
        }
    }
    direct_before = direct;
    /* Zoom : croix haut (avant) / bas (arriere), maintenue = progressif ;
     * molette en cinematique : 8 images de zoom par cran. Une molette
     * recente fait ignorer la croix (la molette peut aussi y arriver). */
    static int wheel_frames = 0, wheel_idle = 1000;
    LONG wheel = InterlockedExchange(&g_mouse_wheel, 0);
    if (direct && wheel) {
        wheel_frames += (wheel / WHEEL_DELTA) * 8;
        if (wheel_frames == 0) wheel_frames = wheel > 0 ? 8 : -8;
        wheel_idle = 0;
    } else if (wheel_idle < 1000) {
        wheel_idle++;
    }
    float zoom_dir = 0.0f;
    if (wheel_frames > 0) { zoom_dir = 1.0f; wheel_frames--; }
    else if (wheel_frames < 0) { zoom_dir = -1.0f; wheel_frames++; }
    else if (wheel_idle > 30) zoom_dir = ((pad[0] & 0x10) ? 1.0f : 0.0f) - ((pad[0] & 0x40) ? 1.0f : 0.0f);
    if (zoom_dir != 0.0f && sh->photo_zoom && sh->photo_zoom_rate > 0.0f) {
        volatile float *zoom = (volatile float *)(UINT64)sh->photo_zoom;
        float z = *zoom * (zoom_dir > 0.0f ? 1.0f + sh->photo_zoom_rate : 1.0f / (1.0f + sh->photo_zoom_rate));
        if (z < 0.5f) z = 0.5f;
        if (z > 20.0f) z = 20.0f;
        *zoom = z;
    }
    float vertical = ((buttons & 0x0A) ? 1.0f : 0.0f) - ((buttons & 0x05) ? 1.0f : 0.0f);
    if (lx == 0.0f && ly == 0.0f && rx == 0.0f && ry == 0.0f && vertical == 0.0f && mouse_x == 0.0f &&
        mouse_y == 0.0f)
        return;
    float step = sh->photo_step * (((buttons & 0x80) || shift) ? sh->photo_fast : 1.0f);

    float r[3] = {cam[0], cam[1], cam[2]}, down[3] = {cam[4], cam[5], cam[6]};
    float look[3] = {cam[8], cam[9], cam[10]}, pos[3] = {cam[12], cam[13], cam[14]};
    float yaw = -rx * sh->photo_turn - mouse_x, pitch = -ry * sh->photo_turn - mouse_y;
    if (yaw != 0.0f) {
        const float up[3] = {0.0f, 1.0f, 0.0f};
        photo_rotate(r, up, yaw); photo_rotate(down, up, yaw); photo_rotate(look, up, yaw);
    }
    if (pitch != 0.0f) {
        /* Inclinaison bloquee avant la verticale : au-dela, les axes se
         * retournaient (commandes inversees). */
        float axis[3] = {r[0], r[1], r[2]};
        photo_normalize(axis);
        float nd2[3] = {down[0], down[1], down[2]}, nl2[3] = {look[0], look[1], look[2]};
        photo_rotate(nd2, axis, pitch); photo_rotate(nl2, axis, pitch);
        photo_normalize(nl2);
        if (fabsf(nl2[1]) < 0.97f || fabsf(nl2[1]) < fabsf(look[1])) {
            for (int i = 0; i < 3; i++) { down[i] = nd2[i]; look[i] = nl2[i]; }
        }
    }
    photo_normalize(look);
    float updir[3] = {-down[0], -down[1], -down[2]}, nr[3], nd[3];
    photo_cross(look, updir, nr); photo_normalize(nr);
    photo_cross(look, nr, nd); photo_normalize(nd);
    /* garder le sens d'origine des axes */
    if (nd[0] * cam[4] + nd[1] * cam[5] + nd[2] * cam[6] < 0.0f) { nd[0] = -nd[0]; nd[1] = -nd[1]; nd[2] = -nd[2]; }
    if (nr[0] * cam[0] + nr[1] * cam[1] + nr[2] * cam[2] < 0.0f) { nr[0] = -nr[0]; nr[1] = -nr[1]; nr[2] = -nr[2]; }
    float right = lx * step, upm = vertical * step, forward = -ly * step;
    for (int i = 0; i < 3; i++) {
        pos[i] += nr[i] * right - nd[i] * upm + look[i] * forward;
        cam[i] = nr[i]; cam[4 + i] = nd[i]; cam[8 + i] = look[i]; cam[12 + i] = pos[i];
    }
    cam[3] = cam[7] = cam[11] = 0.0f; cam[15] = 1.0f;
}

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
        /* Mode photo : call photo_frame (rsp aligne sur 16, 20h d'espace
         * reserve deja dans les 38h). Registres volatils ecrases, comme
         * l'appel generique ci-dessous. */
        UINT64 photoFn = (UINT64)&photo_frame;
        code[p++] = 0x48; code[p++] = 0xB8; memcpy(&code[p], &photoFn, 8); p += 8; /* mov rax,photo_frame */
        code[p++] = 0xFF; code[p++] = 0xD0; /* call rax */
    }
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

    UINT64 oneShotAddr = (UINT64)&g_shared->machine_kill; /* Gekko/tanks, voir machine_kill */
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
            g_shared->photo_version = 9; /* 2 : HUD ; 3 : commandes ; 4 : Shift ; 5 : triangle ; 6-7 : clavier/souris en cinematique ; 8 : zoom ; 9 : teleportation */
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
            memset((void *)g_shared->reserved_32, 0, sizeof(g_shared->reserved_32));
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
    if (g_shared) {
        CreateThread(NULL, 0, photo_mouse_thread, NULL, 0, NULL);
    }

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
        g_hinst = hinst;
        /* Pas de travail lourd directement dans DllMain (loader lock) -
         * delegue a un thread dedie, comme recommande par Microsoft. */
        CreateThread(NULL, 0, InitThread, NULL, 0, NULL);
    }
    return TRUE;
}
