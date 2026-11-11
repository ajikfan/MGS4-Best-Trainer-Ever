"""Apparition d'un soldat PMC devant Snake (prototype, 2026-10-31).

Le jeu cree ses acteurs par des commandes de script. On rejoue ces commandes
avec nos propres arguments, apres avoir enregistre les ressources du soldat
(modeles, animations...) dans le dictionnaire de ressources. Le nom de zone
est echange le temps de cet enregistrement : le jeu en deduit le dossier des
textures HD (textures/PC_TXN_UP/stageNN/<zone>/...) et les lit lui-meme.

Les ressources sont lues dans les archives du jeu installe (core/vpak.py),
d'apres le data.cnf de la zone d'origine du soldat."""
import ctypes
import math
import os
import struct
import threading
import time
from ctypes import wintypes

from mgs4trainer.core.speedhack import kernel32
from mgs4trainer.core.vpak import StageFiles

MEM_COMMIT_RESERVE = 0x3000
PAGE_READWRITE = 0x04
PAGE_EXECUTE_READWRITE = 0x40


def _mov_rax(value: int) -> bytes:
    return b"\x48\xB8" + struct.pack("<Q", value)


def _mov_rcx(value: int) -> bytes:
    return b"\x48\xB9" + struct.pack("<Q", value)


class SpawnMixin:
    SPAWN_FUNCS = {
        "register": (0x74C9B0, "4883ec48"),
        "chara": (0x5C4D0, "40564883ec20"),
        "chara_named": (0x5C440, "48895c241857"),
        "args_end_push": (0x3EEF20, "488b05"),
        "args_set": (0x3EEF10, "48890d"),
        "args_end_pop": (0x3EEFC0, "48832d"),
        "warp": (0xB39C90, "48895c2408"),
        "start": (0xB4BBC0, "4057"),
        "alloc": (0xD20488, "e9b7ffffff"),
    }
    SPAWN_LINKVARBUF_RVA = 0x1C28B28
    SPAWN_ZONE_OFFSETS = (0x34, 0x44)  # nom de zone (voir 5C900)
    SPAWN_RESOURCES_RVA = 0x23D2F6D0  # 16 arbres : +0 gauche, +8 droite, +0x10 cle
    SPAWN_ARGS_RVA = 0x23FFAC20  # pointeur d'arguments de l'interpreteur de script
    SPAWN_CURRENT_UNIT_RVA = 0x23F0B5B8
    SPAWN_OFFSET_BASE_RVA = 0x22864B0  # base des decalages sur 32 bits (136980)
    SPAWN_OFFSET_REACH = 0x100000000
    SPAWN_ARENA_SIZE = 0x2000000
    SPAWN_MANAGER_RVA = 0x23F0B5B0  # ENE_MANAGER : +0x20 nombre de groupes
    SPAWN_TASK_LIST_RVA = 0x23D044D0
    SPAWN_UNIT_VTABLE_RVA = 0x18BA610
    SPAWN_START_VTABLE_OFFSET = 0x1C8
    SPAWN_START_FLAGS = 0x45B0
    SPAWN_START_BIT = 0x200000
    # Fiches de route (3 de 5 entiers) et groupes de routes, repris d'un acteur
    # de la zone : une route absente de la zone plante le jeu (B66A10).
    SPAWN_ROUTE_RECORD = 0x4640
    SPAWN_ROUTE_RECORD_SIZE = 0x3C
    SPAWN_ROUTE_GROUPS = 0x46EC
    SPAWN_ROUTE_GROUPS_SIZE = 8
    SPAWN_GROUND_OFFSET = -100.0

    # QG (ENE_HQC) -> valeur de camp, option 0x9737C9 de leur creation. Les
    # scripts des zones a deux camps jouent ensuite 0x664E35 (PMC, rebelles).
    # A la mort d'un allie, EB13F0 (vie a 0) et EB6470 sautent vers E98D00, qui
    # passe son SCTargetControl (+0xE8E8) au niveau 0 : la camera reste sur lui
    # et bloque Snake. Sans histoire ici, on remplace ces sauts par un retour.
    SPAWN_DEATH_CAMERA_SITES = ((0xEB1421, bytes.fromhex("e9da78feff")), (0xEB6486, bytes.fromhex("e97528feff")))
    SPAWN_GROUPS_MAX = 4
    SPAWN_GROUP_PMC = 0x971E5A
    SPAWN_GROUP_REBEL = 0x37BA8B
    # Cote du QG (option 0x9737C968). Le combat de l'acte 1 met -1 (0xC0) aux
    # deux ; essaye pour les rebelles le 2026-11-07 : aucun changement.
    SPAWN_GROUP_SIDES = {SPAWN_GROUP_PMC: 0xC0, SPAWN_GROUP_REBEL: 0xC1}
    SPAWN_GROUP_ARGS = "0690ca3006{name}5568c93797{side}00"
    SPAWN_GROUP_RELATION_ARGS = "06354e66065a1e97068bba3700"
    SPAWN_GROUP_RELATION_POSITIONAL = 12
    # Relation d'hostilite PMC / rebelles (commande 0x664E35) a la creation du
    # groupe rebelle : coupee (2026-11-07). Dans une zone sans rebelles
    # (s01a57l), elle mettait les escouades PMC en posture de bataille,
    # visant d'ou viendraient les rebelles, meme apres leur mort ; un rebelle
    # ajoute ne combattait de toute facon pas les PMC.
    SPAWN_DECLARE_WAR = False

    # Types d'ennemis. zone : leur zone d'origine, dont le data.cnf liste les
    # ressources et dont le nom sert a trouver leurs textures. Arguments de
    # script : parametres de procedure deja remplaces par leur valeur, nom de
    # l'acteur en +5 sur 4 octets. Retirees : les options qui lancent une
    # procedure du script d'origine (0x89F065 sur l'escouade, 0x39D643 sur
    # l'acteur : plantage a la mort) et le nom de l'escouade (0x84E412).
    # setup : commande de reglage jouee apres la creation (Gekko : 0x1C0B11).
    SPAWN_TYPES = {
        "pmc": {
            "zone": "s01a57l",
            "vtable": 0x18C31B8,
            "group": SPAWN_GROUP_PMC,
            "distance": 2000.0,
            "unit": bytes.fromhex(
                "0679690709000000005873e5303b065a1e975d0d62efca9e065e2cea09901e22"
                "00597465f23b0904000000000000"),
            "actor": bytes.fromhex(
                "063e2d3e0900000000586585a301190002c0586892a035190002c45868a3a54a"
                "190002c8586ec5ca38190002cc5c6c25b1371900030c19000310587317a16719"
                "0003145d18690d5d3608540102640855010264085601026408570102645976cc"
                "309909000000005977424f820930910000556596618ac45565b5362fe1556d91"
                "2c3ec15565498b83915d0e72ec625909e2cfcc0009000000005d0e63d7cb8b09"
                "2ecdec0009000000005d0e67aa12ac09567d48000970170000586813ee2d1200"
                "02bd586edf26ed1200033a0000"),
            "setup": None,
        },
        "rebel": {
            "zone": "s01a00l",
            "vtable": 0x18C26A8,
            "group": SPAWN_GROUP_REBEL,
            "own_route": True,
            "distance": 2000.0,
            "unit": bytes.fromhex(
                "0679690709000000005873e5303b068bba375d0d62efca9e065e2cea09901e22"
                "00597465f23b0904000000000000"),
            "actor": bytes.fromhex(
                "0655d81a0900000000586585a301190002d0586892a035190002d45c6c25b137"
                "1900030019000304587317a167190003085d18690d5d36084001026408410102"
                "64084201026408430102645d18681e4769084401026408450102640846010264"
                "08470102645968264a4c08480102645968dd0a2408490102645768acfb60084a"
                "015976cc309909000000005977424f820930910000556596618ac4556d912c3e"
                "c1586813ee2d12000338586edf26ed1200033d5d0e72ec625909e2cfcc000900"
                "0000005d0e63d7cb8b092ecdec0009000000005d0e67aa12ac09567d48000970"
                "17000000"),
            "setup": None,
        },
        "pmc_sa": {
            "zone": "s02a10l",
            "vtable": 0x18CAD80,
            "group": SPAWN_GROUP_PMC,
            "distance": 2000.0,
            "unit": bytes.fromhex(
                "0679690709000000005873e5303b065a1e975d0d62efca9e065e2cea09901e22"
                "00597465f23b0904000000000000"),
            "actor": bytes.fromhex(
                "06be4ba60900000000586585a301190002c0586892a035190002c45868a3a54a"
                "190002c8586ec5ca38190002cc586585a301190002d0586892a035190002d45c"
                "6c25b1371900030c19000310587317a167190003145d18690d5d3608ac010264"
                "08ad01026408ae01026408af0102645976cc309909000000005977424f820930"
                "910000556596618ac45565b5362fe1556d912c3ec15d0e72ec625909e2cfcc00"
                "09000000005d0e63d7cb8b092ecdec000900000000586813ee2d1200033f586e"
                "df26ed120003445d0e67aa12ac09567d4800097017000000"),
            "setup": None,
        },
        "pmc_ee": {
            "zone": "s03a10l",
            "vtable": 0x18BE1C8,
            "group": SPAWN_GROUP_PMC,
            "distance": 2000.0,
            "unit": bytes.fromhex(
                "0679690709000000005873e5303b065a1e975d0d62efca9e065e2cea09901e22"
                "00597465f23b0904000000000000"),
            "actor": bytes.fromhex(
                "063e838309000000005d0e67aa12ac09567d480009701700005d0e72ec625909"
                "e2cfcc0009000000005d0e63d7cb8b092ecdec0009000000005565498b83c458"
                "6585a301190002d0586892a035190002d4576eeb3f6101401f586e5e2d291900"
                "02d45c6c25b1371900030c19000310586813ee2d1200034a586edf26ed120003"
                "4c5d18690d5d3608460102640847010264084801026408490102645977424f82"
                "0930910000556596618ac4556d912c3ec158656fcc2bc1c1c1c100"),
            "setup": None,
        },
        # Rebelle d'Amerique du Sud (ENEMY_SOUTHAMERICA_MIL, id 0xABDA77, 2026-11-06) :
        # creation tiree du script de s02a10l, comme le PMC de la meme zone.
        "rebel_sa": {
            "zone": "s02a10l",
            "vtable": 0x18CA7F8,
            "group": SPAWN_GROUP_REBEL,
            "own_route": True,
            "distance": 2000.0,
            "unit": bytes.fromhex(
                "0679690709000000005873e5303b068bba375d0d62efca9e065e2cea09901e22"
                "00597465f23b0904000000000000"),
            "actor": bytes.fromhex(
                "0677daab0900000000586585a301190002c0586892a035190002c45868a3a54a"
                "190002c8586ec5ca38190002cc586585a301190002d0586892a035190002d45c"
                "6c25b13719000300190003045976cc309909000000005977424f820930910000"
                "556596618ac45565b5362fe1556d912c3ec15d0e72ec625909e2cfcc00090000"
                "0000586813ee2d12000342586edf26ed120003475d0e67aa12ac09567d480009"
                "7017000000"),
            "setup": None,
        },
        "rebel_ee": {
            "zone": "s03a10l",
            "vtable": 0x18F8588,
            "group": SPAWN_GROUP_REBEL,
            "own_route": True,
            "distance": 2000.0,
            "unit": bytes.fromhex(
                "0679690709000000005873e5303b068bba375d0d62efca9e065e2cea09901e22"
                "00597465f23b0904000000000000"),
            "actor": bytes.fromhex(
                "0640415209000000005d0e67aa12ac09567d48000970170000586585a3011900"
                "02f0586892a035190002f4586eeb3f61190002d0586e5e2d29190002d45c6c25"
                "b1371900030019000304586813ee2d1200034b586edf26ed1200034d5d18690d"
                "5d3608420102640843010264084401026408450102645977424f820930910000"
                "556596618ac4556d912c3ec100"),
            "setup": None,
        },
        # Meryl : pas d'escouade dans le script, mais son IA de soldat lit +0x4580
        # (nul sans escouade en cours) : on la range avec les rebelles.
        "meryl": {
            "zone": "s01a40l",
            "vtable": 0x18E65C8,
            "no_death_camera": True,
            "group": SPAWN_GROUP_REBEL,
            "own_route": True,
            # a cote de Snake : a 2000 unites, les ennemis la voyaient surgir
            # et restaient a viser ce point (s01a57l, 2026-11-07)
            "distance": 150.0,
            # IA relancee apres le demarrage (sinon elle ne demarre pas seule)
            "kick": True,
            "unit": bytes.fromhex(
                "0679690709000000005873e5303b068bba375d0d62efca9e065e2cea09901e22"
                "00597465f23b0904000000000000"),
            "actor": bytes.fromhex(
                "06e33e6609000000005765b5362f0100015c6c25b137190011c4190011c85873"
                "17a167190011cc576585a301013075576892a035013075586813ee2d190011d0"
                "586edf26ed190011d057641a66d201d0075766af246d01100e55682adf56c200"),
            "setup": None,
        },
        "gekko": {
            "zone": "s02a90l",
            "vtable": 0x18EC5B8,
            "group": SPAWN_GROUP_PMC,
            "distance": 4000.0,
            "unit": bytes.fromhex(
                "067969070d0318dc015873e5303b065a1e975870b0ce01061963315c62efca9e"
                "065e2cea06901e225972ec62590610d480c159636115280610d480c10000"),
            "actor": bytes.fromhex(
                "0641c0240d2abcb501586585a3011900035c584cd8a548190003605855eaa648"
                "19000364586580a72e19000368584c26acbc1900036c58554aaebc1900037058"
                "6581a72e19000374584c27acbc1900037858554baebc1900037c586892a03519"
                "0003505c6c25b13719000354190003585b67aa12ac064578f80188130000"),
            # 06 id 0x1C0B11, puis option 0x389205 = nom de l'acteur
            "setup": (bytes.fromhex("06110b1c596e0592380d2abcb501556103d61ac10000"), 4, 10),
        },
        # Laughing Octopus, forme bete (ESSAI 2026-11-07) : commande de
        # creation relevee a l'entree du combat (s02a50l, chara nomme 4EC50
        # en 1.4.2), sans parametre de procedure ; nom d'origine 06 04A663
        # remplace par 09 + nom. Pas d'escouade ni de demarrage de soldat
        # (vtable+0x1C8 nulle) : boss cree seul, a la position de l'option
        # 0x70FA4ECF (09 X, 01 Y, 09 Z, entiers), reecrite pres de Snake.
        # vtable OCTOPUS en 1.4.2 (pas d'image 1.4.1 de cette zone : sur une
        # autre version, l'acteur cree n'est pas retrouve et rien ne suit).
        "laughing": {
            "zone": "s02a50l",
            "vtable": 0x1331950,
            "game": "1.4.2",  # adresses de parade et vtable relevees en 1.4.2 seulement
            "boss": True,
            "effect_guard": True,  # effet visuel sans ressource
            "arena": True,  # zone d'arene geante avec un point
            "no_relocate": True,  # ni cachette ni teleportation
            "loop_action": 15,  # tir sur Snake, relance des qu'elle se fige
            "position_option": bytes.fromhex("70fa4ecf"),
            "distance": 4000.0,
            "actor": bytes.fromhex(
                "06e922250900000000557794113d915c73006072190018bc190018c05d1270fa"
                "4ecf0957c0fdff01182e09c7cff8ffc15d0d6585a30101e02e01002001002057"
                "6592a00101102758692bb201191001405864131248191001445a727511ce0800"
                "020801025a674d7f940802020803025a63f1ef2908040208050257737199a008"
                "0602596e696a4e08070202645a64511791080902080a0200"),
        },
    }
    # Gestionnaires absents de certaines zones (salle blanche des Beauty), dans
    # l'ordre des scripts de zone. Sans RAGDOLL_MNG : deja la, et un doublon
    # plante dans BBA1D0. Dernier : le groupe 0x971E5A cite par l'escouade.
    SPAWN_MANAGERS = tuple(bytes.fromhex(args) for args in (
        "0618ba2d0618ba2d556dddc8f8e1556d8c4ab1c357731cdbfc0100105565a4a194c800",  # ENE_MANAGER
        "0660361d0660361d5561b33de3e100",  # CORP_MANAGER
        "0697782806e439ed5565ba5a81cb00",  # ENE_GPAUTO_MNG
        "0652fb470682f85558740fe6bd06e6dc28556175ad03c300",
        "0690ca30065a1e975568c93797c000",
    ))
    SPAWN_MANAGER_POSITIONAL = 8
    # Suivi de route : une quinzaine de sites appellent B680C0 (animation du
    # point de route) puis B83F50 sans tenir compte de l'echec, et appliquent
    # une structure locale non remplie : sans route, valeurs de la pile et
    # plantage dans 8AA00. B680C0 note en entrant la structure et son id
    # (+0x44), sans rien y ecrire : un appelant passe un tampon plus petit,
    # et y ecrire mettait a 0 la moitie haute d'un rbp sauve (plantage au
    # rechargement apres Continuer, 2026-11-06). B83F50 : meme structure et
    # meme id = rien n'a ete ecrit = echec ; il garde alors l'animation en
    # cours, et sans aucune animation en pose une (8A9D0 planterait sur +0x80 nul).
    SPAWN_ROUTE_LOOKUP = 0xB680C0
    SPAWN_ROUTE_LOOKUP_ORIG = bytes.fromhex("48895c2408")
    SPAWN_ROUTE_APPLY = 0xB83F50
    SPAWN_ROUTE_APPLY_ORIG = bytes.fromhex("440fbf42308b5244")
    SPAWN_ROUTE_PLAY = 0xB83ED0
    SPAWN_ROUTE_FIND = 0x40D420
    SPAWN_ROUTE_MOTION = 0x41052B
    # Avance de l'animation (8A9D0, 20 appelants) : sans animation posee, ni
    # la fonction ni ses appelants ne tiennent (+0x50 nul). On en pose une.
    SPAWN_STEP_SITE = 0x8A9D0
    SPAWN_STEP_ORIG = bytes.fromhex("66ff4130488b4150")
    SPAWN_STEP_SET = 0x8A910
    # Liste affichee, dans l'ordre. Sans entree dans SPAWN_TYPES : grise (pas de recette).
    # SPAWN_BROKEN : recette connue mais plantage constate (rebelle d'Europe
    # de l'Est : a sa creation), grise aussi.
    # Laughing Octopus (2026-11-07) : creee, mais son effet visuel attend des
    # ressources graphiques non injectees (pointeur actif nul, plantage A3B40 ;
    # parade : vider le lien +8 de sa structure -> objet par defaut 0x33A2B8),
    # puis son IA cherche la zone d'arene de sa cible (F0C6C0, table vide hors
    # de s02a50l) et plante en F0A727. Mise en pause.
    # Laughing Octopus validee en jeu le 2026-11-11 (experimental) : hors de
    # son arene, elle tire sur Snake en boucle et s'evapore une fois vaincue
    # (_spawn_boss : effet visuel, arene fabriquee, plus de teleportation ni
    # de procedures de script, action 15 relancee, action 30 a la defaite).
    SPAWN_BROKEN = frozenset({"rebel_ee"})
    SPAWN_ROSTER = (
        "pmc", "pmc_sa", "pmc_ee", "rebel", "rebel_sa", "rebel_ee",
        "gekko", "gekko_dwarf", "frog", "zombie", "laughing", "raging",
        "crying", "screaming", "vamp", "liquid", "raiden", "meryl",
        "akiba", "jonathan", "citizen", "animal", "stryker", "humvee",
        "bmp3", "canard", "d9",
    )
    SPAWN_POSITIONAL_SIZE = 9  # fin des arguments positionnels, debut des options
    SPAWN_NAME_OFFSET = 5
    SPAWN_RESOURCE_FLAGS = 1  # comme le chargeur pour les fichiers de data.cnf
    SPAWN_FIRST_NAME = 0x7A7A0000

    def _spawn_game_root(self) -> str | None:
        """Dossier de mgs4.exe, d'apres le processus."""
        size = wintypes.DWORD(1024)
        name = ctypes.create_unicode_buffer(size.value)
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        if not kernel32.QueryFullProcessImageNameW(self.proc.handle, 0, name, ctypes.byref(size)):
            return None
        return os.path.dirname(name.value)

    def _spawn_resources(self, zone: str) -> list[tuple[int, bytes]]:
        """(cle, contenu) des ressources de la zone, lues une fois."""
        if not hasattr(self, "_spawn_resource_cache"):
            self._spawn_resource_cache = {}
            self._spawn_files = None
        if zone not in self._spawn_resource_cache:
            if self._spawn_files is None:
                root = self._spawn_game_root()
                if not root:
                    raise OSError("dossier du jeu introuvable")
                self._spawn_files = StageFiles(root)
            files = self._spawn_files
            self._spawn_resource_cache[zone] = [(key, files.read(path)) for key, path in files.zone_resources(zone)]
        return self._spawn_resource_cache[zone]

    def spawn_available(self, kind: str) -> bool:
        """Recette connue, sans plantage constate, et faite pour la version
        du jeu detectee (cle "game" d'une recette propre a une version)."""
        from mgs4trainer.core import versions
        recipe = self.SPAWN_TYPES.get(kind)
        if recipe is None or kind in self.SPAWN_BROKEN:
            return False
        return recipe.get("game") in (None, versions.name())

    def spawn_enemy(self, kind: str) -> bool:
        """Lance l'apparition dans un fil separe (les appels au jeu se font
        une image a la fois). Une seule a la fois."""
        if getattr(self, "_spawn_busy", False) or not self.spawn_available(kind):
            return False
        if not (self.connected and self.sane and self.pid and self.speed.ensure_injected(self.pid)):
            return False
        if not self.speed.main_loop_hook_installed():
            return False
        self._spawn_busy = True
        threading.Thread(target=self._spawn_run, args=(self.SPAWN_TYPES[kind],), daemon=True).start()
        return True

    # Changer la route d'un allie : commande de script 0x48CC82 (C74720),
    # comme s01a40l pour le Rat Patrol : 1er argument = nom de l'acteur
    # (acteur+0x18), option 0x5962EC = (route, point). Ecrit la 1re fiche de
    # route (+0x4640..+0x4650) par la recherche du jeu ; le jeu y ramene le
    # suivi de route de l'acteur a chaque image.
    ALLY_ROUTE_ARGS = "0682cc480d{name}5a72ec62590d{route}{point:02x}00"  # option de 10 octets
    ALLY_ROUTE_POSITIONAL = 9  # 06 id (4) + 0d nom (5)

    # Mode compagnon (« Meryl me suit », voir ally_follow_tick). Routes chargees : table
    # ALLY_ROUTE_TABLE_RVA (nombre, puis entrees de 0x10 : nom, ?, nombre de
    # points, decalage depuis SPAWN_OFFSET_BASE_RVA ; points de 0x30 octets,
    # position en +0). Seules les routes d'un groupe de la famille 0xEA2C5E
    # (liste ALLY_ROUTE_GROUPS_RVA : +8 tete, +0x10 suivant, +0x18 famille,
    # +0x20 nombre, +0x28 groupes ; groupe : +0xF04 nombre, +0xF28 routes
    # de 0x10, nom en +8) sont resolues par la commande.
    ALLY_ROUTE_GROUPS_RVA = 0x23F0B5C0
    ALLY_ROUTE_TABLE_RVA = 0x234F488
    ALLY_ROUTE_KIND = 0xEA2C5E
    ALLY_FOLLOW_PERIOD = 0.5
    ALLY_FOLLOW_RESEND = 3.0
    # Position d'un acteur : objet du corps (vtable+0x130 = acteur+0x2C0),
    # X/Y/Z en +0x10 -> acteur+0x2D0 (2026-11-07, s04a10l).
    ALLY_POSITION = 0x2D0
    # Route empruntee : une route de la zone qu'aucun soldat ne suit ; ses
    # points deviennent la trace de Snake (voir ALLY_TRAIL_STEP) et sont
    # remis a l'origine quand le mode est coupe (ally_follow_release).
    # Trace de Snake (2026-11-07) : l'IA rejoint un point de route en ligne
    # droite, sans chercher de chemin (Meryl coincee contre un mur a 90 m en
    # s01a57l). Les points de la route empruntee deviennent les derniers pas
    # de Snake (un tous les ALLY_TRAIL_STEP), du plus ancien a Snake : chaque
    # etape a ete parcourue, donc degagee. Elle est envoyee au pas le plus
    # proche d'elle et remonte la trace jusqu'a lui.
    ALLY_TRAIL_STEP = 200.0
    ALLY_TRAIL_KEEP = 256  # pas gardes (trace + distance d'arret)
    ALLY_STOP_BEHIND = 1000.0  # arret a cette distance derriere Snake, le long de sa trace
    ALLY_STOP_FLAGS = 0x2  # +0xC des postes de garde du jeu (octets 02 00 00 00)
    ALLY_STOP_ACTION = 3  # action des postes de garde (attente sur place, debout)
    ALLY_STOP_ACTION_CROUCH = 4  # meme poste, accroupie (releve en jeu le 2026-11-07)
    # pres du point d'arret (rayon d'arrivee ~500) : poste ; au-dela elle repart
    # (1500 la faisait attendre que Snake ait deja bien avance, 2026-11-07)
    ALLY_STOP_NEAR = 700.0
    # Allure d'un point (+0x1E), releve en jeu le 2026-11-07 : 0 marche lente,
    # 1 course, 2 marche/course, 3 marche, 4 course, 5 accroupi, 6 marche en
    # visant ; 12 (points de l'acte 1) marche. -1 = automatique : accroupie si
    # Snake l'est, course s'il court ou si elle est loin, marche sinon ; une
    # autre valeur est imposee (reglage de mise au point, pas d'interface).
    ally_point_move = -1
    # 1 ne va qu'a ~1600 unites/s (marche de Snake) ; 5 (accroupie) ~3000
    # (releve 2026-11-07) ; 4 « court » d'apres l'utilisateur
    ALLY_MOVE_RUN, ALLY_MOVE_WALK, ALLY_MOVE_CROUCH = 4, 3, 5
    # Etats de la machine principale de Snake (+0x60) accroupi : immobile
    # 9DF1E0, en mouvement 9DDF60 (1.4.2 : 6FE0F0, 6FCE70 ; releves en jeu
    # le 2026-11-07). Vitesse de Snake : marche 600-1900, course 3200-3700
    # unites/s.
    SNAKE_CROUCH_STATES = (0x9DF1E0, 0x9DDF60)
    ALLY_RUN_SPEED = 2400.0
    ALLY_RUN_LAG = 4000.0  # plus loin de Snake : elle court pour le rattraper
    # Suivi de route de l'acteur (objet pointe par acteur+0x42D8, celui de
    # 860590) : +0x30 point vise (copie du point par 75E80), +0x58 action,
    # +0x5A allure, +0x5C attente, +0x5E orientation, +0x60 point en cours,
    # +0x80 entree de la route suivie. L'allure n'y est recopiee qu'a
    # l'arrivee a un point : ecrite ici en direct (2026-11-07).
    ALLY_FOLLOWER = 0x42D8
    ALLY_FOLLOWER_ENTRY = 0x80
    ALLY_FOLLOWER_ACTION = 0x58
    ALLY_FOLLOWER_MOVE = 0x5A
    ALLY_FOLLOWER_WAIT = 0x5C
    ALLY_FOLLOWER_TARGET = 0x30  # position visee (copie du point)
    ALLY_FOLLOWER_INDEX = 0x60  # point en cours (mot)
    # Action du poste (+0x1C) imposee si >= 0 (mise au point) ; -1 =
    # automatique (3 debout, 4 accroupie).
    ally_point_action = -1
    ALLY_POINT_PLAIN = 1  # action d'un point de passage simple (+0x1C)
    ALLY_ROUTE_POINT = 0x4650  # point en cours de la 1re fiche de route (avance avec elle)
    ALLY_STOP_WAIT = 0xFFFF  # attente infinie (postes de garde du jeu)

    def _ally_command_page(self) -> int:
        """Une page par processus pour les commandes repetees (la commande ne
        garde rien de ses arguments apres l'appel)."""
        if getattr(self, "_ally_page_pid", None) != self.pid:
            self._ally_page = self._spawn_alloc(0x1000, PAGE_EXECUTE_READWRITE)
            self._ally_page_pid = self.pid
        return self._ally_page

    def _ally_alive(self) -> list[int]:
        out = []
        for ally in self._spawn_tasks(self.SPAWN_TYPES["meryl"]["vtable"]):
            life_object = self._spawn_q(ally + 0x42B0)
            if life_object and struct.unpack("<i", self.proc.read_bytes(life_object + 0x314, 4))[0] > 0:
                out.append(ally)
        return out

    def _ally_send(self, orders: list[tuple[int, int, int]]) -> bool:
        """(allie, route, point) : commande 0x48CC82 pour chacun, dans un
        fil separe comme les apparitions."""
        if self._ally_busy_now() or not orders:
            return False
        if not (self.connected and self.sane and self.pid and self.speed.ensure_injected(self.pid)):
            return False
        if not self.speed.main_loop_hook_installed():
            return False
        self._ally_busy = True

        def run():
            self._game_lock().acquire()
            try:
                funcs = self._live_funcs(self.SPAWN_FUNCS)
                if funcs is None:
                    return
                for ally, route, point in orders:
                    args = bytes.fromhex(self.ALLY_ROUTE_ARGS.format(
                        name=self.proc.read_bytes(ally + 0x18, 4).hex(),
                        route=struct.pack("<I", route).hex(), point=0xC1 + point))
                    self._spawn_command(args, funcs["chara"], positional=self.ALLY_ROUTE_POSITIONAL,
                                        memory=self._ally_command_page())
            except (OSError, struct.error, ValueError, KeyError):
                pass
            finally:
                self._ally_busy = False
                self._game_lock().release()

        threading.Thread(target=run, daemon=True).start()
        return True

    def _ally_is_spawned(self, ally: int) -> bool:
        return struct.unpack("<I", self.proc.read_bytes(ally + 0x18, 4))[0] >> 16 == self.SPAWN_FIRST_NAME >> 16

    def ally_kick(self, allies: list[int], route: int) -> bool:
        """Replace chaque allie a sa propre position (fonction de placement :
        elle relance aussi son etat) puis l'envoie sur `route`. L'IA d'une
        Meryl ajoutee ne demarre pas seule ; la placer la debloque (s04a10l,
        2026-11-07), sans la deplacer ici."""
        if self._ally_busy_now() or not allies:
            return False
        if not (self.connected and self.sane and self.pid and self.speed.ensure_injected(self.pid)):
            return False
        if not self.speed.main_loop_hook_installed():
            return False
        self._ally_busy = True

        def run():
            self._game_lock().acquire()
            try:
                funcs = self._live_funcs(self.SPAWN_FUNCS)
                if funcs is None:
                    return
                page = self._ally_command_page()
                for ally in allies:
                    x, y, z = struct.unpack("<3f", self.proc.read_bytes(ally + self.ALLY_POSITION, 12))
                    self.proc.write_bytes(page + 0xF00, struct.pack("<4f", x, y, z, 1.0))
                    self.speed.game_call(funcs["warp"], ally, page + 0xF00, 0, timeout=10.0)
                    if route:
                        args = bytes.fromhex(self.ALLY_ROUTE_ARGS.format(
                            name=self.proc.read_bytes(ally + 0x18, 4).hex(),
                            route=struct.pack("<I", route).hex(), point=0xC1))
                        self._spawn_command(args, funcs["chara"], positional=self.ALLY_ROUTE_POSITIONAL, memory=page)
                    self._ally_kicked.add(ally)
            except (OSError, struct.error, ValueError, KeyError):
                pass
            finally:
                self._ally_busy = False
                self._game_lock().release()

        threading.Thread(target=run, daemon=True).start()
        return True

    def _ally_route_entry(self, name: int) -> int:
        """Adresse de l'entree de table de la route (nom +0, nombre +8)."""
        b, q = self.base, self._spawn_q
        count = struct.unpack("<i", self.proc.read_bytes(b + self.ALLY_ROUTE_TABLE_RVA, 4))[0]
        table = q(b + self.ALLY_ROUTE_TABLE_RVA + 8)
        entries = self.proc.read_bytes(table, 0x10 * min(max(count, 0), 0x2000)) if table else b""
        for index in range(len(entries) // 0x10):
            if struct.unpack_from("<I", entries, 0x10 * index)[0] == name:
                return table + 0x10 * index
        return 0

    def _ally_route_entries(self) -> dict[int, tuple[int, int]]:
        """Nom de route -> (adresse des points, nombre) des routes chargees."""
        b, q = self.base, self._spawn_q
        count = struct.unpack("<i", self.proc.read_bytes(b + self.ALLY_ROUTE_TABLE_RVA, 4))[0]
        table = q(b + self.ALLY_ROUTE_TABLE_RVA + 8)
        offset_base = q(b + self.SPAWN_OFFSET_BASE_RVA)
        entries = self.proc.read_bytes(table, 0x10 * min(max(count, 0), 0x2000)) if table else b""
        out = {}
        for index in range(len(entries) // 0x10):
            name, _unused, total, offset = struct.unpack_from("<IIII", entries, 0x10 * index)
            if offset and 0 < total < 0x3F:
                out[name] = (offset_base + offset, total)
        return out

    def _ally_pick_route(self, exclude=()) -> dict | None:
        """Route resolvable par la commande et suivie par aucun soldat de la
        zone (1re fiche : groupe +0x4648, index +0x464C) : ses points seront
        deplaces pres de Snake. None s'il n'y en a pas."""
        q = self._spawn_q
        grouped = {}
        node = q(q(self.base + self.ALLY_ROUTE_GROUPS_RVA) + 8)
        seen = set()
        while node and node not in seen and len(seen) < 64:
            seen.add(node)
            kind, _unused, groups = struct.unpack("<iii", self.proc.read_bytes(node + 0x18, 12))
            if kind == self.ALLY_ROUTE_KIND:
                group_table = q(node + 0x28)
                for index in range(min(max(groups, 0), 64)):
                    group = q(group_table + 8 * index)
                    gid, routes = struct.unpack("<i", self.proc.read_bytes(group + 8, 4))[0], \
                        struct.unpack("<i", self.proc.read_bytes(group + 0xF04, 4))[0]
                    entries = self.proc.read_bytes(q(group + 0xF28), 0x10 * min(max(routes, 0), 0x400))
                    for r in range(len(entries) // 0x10):
                        grouped[struct.unpack_from("<I", entries, 0x10 * r + 8)[0]] = (gid, r)
            node = q(node + 0x10)
        used = set()
        manager = self._alert_manager()
        allies = set(self._ally_alive())
        followed = set()  # routes suivies en ce moment (suivi de route), meme hors fiche
        for soldier in self._alert_soldiers(manager) if manager else []:
            if soldier not in allies:
                used.add(struct.unpack("<ii", self.proc.read_bytes(soldier + 0x4648, 8)))
                follower = self._spawn_q(soldier + self.ALLY_FOLLOWER)
                if follower:
                    followed.add(self._spawn_q(follower + self.ALLY_FOLLOWER_ENTRY))
        loaded = self._ally_route_entries()
        # au moins 2 points : une route d'un seul point (sortie des renforts ?) ne
        # fait pas bouger l'allie (s01a57l, 2026-11-07)
        free = [(loaded[name][1], name) for name, pair in grouped.items()
                if pair not in used and name in loaded and name not in (exclude if isinstance(exclude, (set, tuple, list)) else {exclude})
                and self._ally_route_entry(name) not in followed
                and loaded[name][1] >= 2]
        if not free:
            return None
        total, name = max(free)  # la plus longue : trace de Snake plus longue
        address = loaded[name][0]
        original = self.proc.read_bytes(address, 0x30 * total)
        # Champs apres la position (+0xC..+0x30) d'un point de passage simple,
        # construits (drapeau 0, regard, action 1, allure 1, attente 0, reste a
        # 0 comme dans les routes du jeu) : en recopier un d'origine echouait
        # quand la route choisie n'en avait pas (2026-11-07). Le dernier point
        # d'origine (action 0x19) renvoie l'acteur en reserve.
        plain = struct.pack("<I3fHHHH", 0, 0.0, 0.0, 0.0, self.ALLY_POINT_PLAIN, 1, 0, 0) + bytes(12)
        return {"name": name, "address": address, "count": total, "original": original,
                "plain": plain, "pid": self.pid, "entry": self._ally_route_entry(name)}

    # Une route a nous (entree et points hors des groupes) ne tient pas : le
    # jeu ramene le suivi de route a celle de la fiche de l'acteur en moins de
    # 20 ms (2026-11-07). D'ou l'emprunt, avec rendu en cas de conflit.

    def _ally_route_taken(self, route: dict, allies: list[int]) -> bool:
        """Un soldat autre que les allies suit-il la route empruntee ?"""
        manager = self._alert_manager()
        others = [s for s in (self._alert_soldiers(manager) if manager else []) if s not in allies]
        for soldier in others:
            follower = self._spawn_q(soldier + self.ALLY_FOLLOWER)
            if follower and self._spawn_q(follower + self.ALLY_FOLLOWER_ENTRY) == route["entry"]:
                return True
        return False

    def ally_follow_release(self) -> None:
        """Remet les points d'origine des routes empruntees."""
        for attribute in ("_ally_follow_route",):
            route = getattr(self, attribute, None)
            setattr(self, attribute, None)
            if route and route["pid"] == self.pid and route.get("original"):
                try:
                    if self._ally_route_entries().get(route["name"], (None,))[0] == route["address"]:
                        self.proc.write_bytes(route["address"], route["original"])
                        if route.get("entry"):
                            self.proc.write_bytes(route["entry"] + 8, struct.pack("<H", route["count"]))
                except OSError:
                    pass

    def _ally_live_style(self, allies: list[int], route: dict, style: tuple[int, int]) -> None:
        """Allure (et action d'essai au poste) ecrites dans le suivi de route
        de chaque allie qui suit la route empruntee : effet immediat."""
        posted = (getattr(self, "_ally_layout", None) or ("",))[0] == "post"
        for ally in allies:
            follower = self._spawn_q(ally + self.ALLY_FOLLOWER)
            if not follower or self._spawn_q(follower + self.ALLY_FOLLOWER_ENTRY) != route["entry"]:
                continue
            action, move = struct.unpack("<HH", self.proc.read_bytes(follower + self.ALLY_FOLLOWER_ACTION, 4))
            wanted_action = style[1] if posted else action
            if (action, move) != (wanted_action, style[0]):
                self.proc.write_bytes(follower + self.ALLY_FOLLOWER_ACTION, struct.pack("<HH", wanted_action, style[0]))

    def _ally_auto_move(self, position, allies: list[int], now: float) -> int:
        """Allure des pas (+0x1E) : imposee si ally_point_move >= 0, sinon
        d'apres Snake (accroupi -> accroupie ; course ou retard -> course)."""
        last = getattr(self, "_ally_speed_sample", None)
        speed = getattr(self, "_ally_snake_speed", 0.0)
        if last and now > last[1]:
            sample = math.dist((position[0], position[2]), (last[0][0], last[0][2])) / (now - last[1])
            speed = 0.5 * speed + 0.5 * sample
        self._ally_speed_sample, self._ally_snake_speed = (position, now), speed
        machines = self._snake_machines()
        state = self._spawn_q(machines[0] + 0x60) - self.base if machines else 0
        self._ally_snake_crouched = state in self.SNAKE_CROUCH_STATES
        if self.ally_point_move >= 0:
            return self.ally_point_move
        if self._ally_snake_crouched:
            return self.ALLY_MOVE_CROUCH
        lag = max((math.dist(struct.unpack("<3f", self.proc.read_bytes(a + self.ALLY_POSITION, 12)), position)
                   for a in allies), default=0.0)
        # hysteresis : garde la course tant que Snake n'est pas nettement revenu a la marche
        running = getattr(self, "_ally_running", False)
        running = speed > (self.ALLY_RUN_SPEED * (0.75 if running else 1.0)) or lag > self.ALLY_RUN_LAG
        self._ally_running = running
        return self.ALLY_MOVE_RUN if running else self.ALLY_MOVE_WALK

    def _ally_point(self, position, look, action: int, move: int, wait: int = 0, angle: int = 0,
                    flags: int = 0) -> bytes:
        """Point de route de 0x30 octets (voir _ally_pick_route)."""
        return struct.pack("<3fI3fHHHH", *position, flags, *look, action, move, wait, angle) + bytes(12)

    def _ally_steer(self, ally: int, route: dict, index: int, target) -> None:
        """Ecrit dans le suivi de route de l'allie le point en cours et la
        position visee : effet immediat, sans ordre de route."""
        follower = self._spawn_q(ally + self.ALLY_FOLLOWER)
        if follower and self._spawn_q(follower + self.ALLY_FOLLOWER_ENTRY) == route["entry"]:
            self.proc.write_bytes(follower + self.ALLY_FOLLOWER_TARGET, struct.pack("<3f", *target))
            self.proc.write_bytes(follower + self.ALLY_FOLLOWER_INDEX, struct.pack("<h", index))

    # Hostilite entre groupes (2026-11-07) : table du gestionnaire des
    # soldats (ENE_MANAGER), jusqu'a 4 groupes de 8 octets a +0x15C : nom,
    # puis masque de ses groupes ennemis (+0x160, bit = rang du groupe). La
    # commande 0x664E35 (C78340 -> B5FA40) ne fait qu'y ajouter un bit dans
    # chaque sens. Mode compagnon : PMC et rebelles ennemis pendant une alerte
    # (Meryl, du groupe rebelle, combat alors), et seulement les bits ajoutes
    # par le trainer retires au retour au calme.
    ALLY_GROUP_TABLE = 0x15C
    ALLY_GROUP_SLOTS = 4

    def _ally_group_slots(self) -> dict[int, int]:
        manager = self._spawn_q(self.base + self.SPAWN_MANAGER_RVA)
        if not manager:
            return {}
        data = self.proc.read_bytes(manager + self.ALLY_GROUP_TABLE, 8 * self.ALLY_GROUP_SLOTS)
        return {struct.unpack_from("<I", data, 8 * i)[0]: i for i in range(self.ALLY_GROUP_SLOTS)
                if struct.unpack_from("<I", data, 8 * i)[0]}

    def _ally_war(self, wanted: bool) -> None:
        """Ajoute (wanted) ou retire les bits d'hostilite PMC / rebelles que
        le trainer a lui-meme poses."""
        manager = self._spawn_q(self.base + self.SPAWN_MANAGER_RVA)
        slots = self._ally_group_slots()
        pmc, rebel = slots.get(self.SPAWN_GROUP_PMC), slots.get(self.SPAWN_GROUP_REBEL)
        if not manager or pmc is None or rebel is None:
            return
        added = getattr(self, "_ally_war_added", {})
        if getattr(self, "_ally_war_pid", None) != self.pid:
            added, self._ally_war_pid = {}, self.pid
        for slot, enemy in ((pmc, rebel), (rebel, pmc)):
            address = manager + self.ALLY_GROUP_TABLE + 8 * slot + 4
            mask = struct.unpack("<I", self.proc.read_bytes(address, 4))[0]
            bit = 1 << enemy
            if wanted and not mask & bit:
                self.proc.write_bytes(address, struct.pack("<I", mask | bit))
                added[address] = bit
            elif not wanted and address in added and mask & added[address]:
                self.proc.write_bytes(address, struct.pack("<I", mask & ~added.pop(address)))
        self._ally_war_added = added

    # Meryl dans le camp de Snake (2026-11-07) : l'hostilite reste posee tant
    # qu'un soldat vivant la vise, meme alerte retombee (Snake invisible), puis
    # ALLY_WAR_HOLD s encore. Cible d'un soldat : module de terrain
    # (ENE_PLG_FIELD, acteur+0x42B8), pointeur +0x4E930 vers une entree de sa
    # table dont +0x60 est l'acteur vise. Sans hostilite, les PMC sont au
    # statut 1 (connus) dans la table de Meryl et elle ne tire pas ; avec,
    # statut 3 (ennemis).
    ALLY_FIELD = 0x42B8
    ALLY_FIELD_TARGET = 0x4E930
    ALLY_FIELD_ENTRY_ACTOR = 0x60
    ALLY_LIFE_OBJECT, ALLY_LIFE = 0x42B0, 0x314
    ALLY_WAR_HOLD = 5.0

    def _ally_engaged(self, allies: list[int]) -> bool:
        """Un soldat vivant de la zone vise-t-il un allie ?"""
        manager = self._alert_manager()
        for soldier in self._alert_soldiers(manager) if manager else []:
            if soldier in allies:
                continue
            try:
                life_object = self._spawn_q(soldier + self.ALLY_LIFE_OBJECT)
                field = self._spawn_q(soldier + self.ALLY_FIELD)
                if not life_object or not field:
                    continue
                if struct.unpack("<i", self.proc.read_bytes(life_object + self.ALLY_LIFE, 4))[0] <= 0:
                    continue
                entry = self._spawn_q(field + self.ALLY_FIELD_TARGET)
                if entry and self._spawn_q(entry + self.ALLY_FIELD_ENTRY_ACTOR) in allies:
                    return True
            except OSError:
                continue
        return False

    def _ally_hold(self, allies: list[int]) -> None:
        """Combat : poste de garde d'un point a la position du premier allie
        qui suit la route empruntee, ecrit une fois par combat."""
        route = getattr(self, "_ally_follow_route", None)
        if not route or route["pid"] != self.pid or not route.get("entry"):
            return
        bound = [a for a in allies
                 if self._spawn_q(self._spawn_q(a + self.ALLY_FOLLOWER) + self.ALLY_FOLLOWER_ENTRY) == route["entry"]]
        if not bound:
            return
        here = struct.unpack("<3f", self.proc.read_bytes(bound[0] + self.ALLY_POSITION, 12))
        layout = getattr(self, "_ally_layout", None) or ("",)
        if layout[0] == "hold" and math.dist(layout[1], here) < self.ALLY_STOP_NEAR:
            return
        # poste absent ou laisse loin derriere (un poste d'un combat
        # precedent la faisait courir vers lui a travers un mur, 2026-11-07)
        self.proc.write_bytes(route["address"], self._ally_point(
            here, here, self.ALLY_STOP_ACTION, self.ALLY_MOVE_RUN, self.ALLY_STOP_WAIT, 0, self.ALLY_STOP_FLAGS))
        self.proc.write_bytes(route["entry"] + 8, struct.pack("<H", 1))
        for ally in bound:
            self._ally_steer(ally, route, 0, struct.unpack("<3f", self.proc.read_bytes(ally + self.ALLY_POSITION, 12)))
        self._ally_layout = ("hold", here)

    def ally_follow_tick(self, enabled: bool) -> None:
        """Mode compagnon (2026-11-07). Une route de la zone que personne ne
        suit est empruntee et attachee une fois a l'allie (commande 0x48CC82) ;
        ensuite tout passe par ses donnees et par le suivi de route de l'allie
        (acteur+0x42D8) :
          - en marche : la route ne garde que les pas de Snake devant elle,
            du plus proche d'elle jusqu'au dernier, ALLY_STOP_BEHIND derriere
            lui (nombre de points reduit d'autant, dans la table du jeu) ; pas
            de point derriere elle ou retourner ;
          - a l'arrivee : route d'un point, poste de garde (attente infinie,
            action 3 debout / 4 accroupie), elle ne bouge plus ;
          - allure et action ecrites en direct dans son suivi.
        Un point atteint passe au suivant dans la meme image : jamais une
        route dont tous les points sont identiques sans attente (gel)."""
        now = time.monotonic()
        if not enabled:
            if getattr(self, "_ally_follow_route", None):
                self.ally_follow_release()
            if getattr(self, "_ally_war_added", None):
                self._ally_war(False)
            return
        if now - getattr(self, "_ally_follow_last", 0.0) < self.ALLY_FOLLOW_PERIOD:
            return
        self._ally_follow_last = now
        position = self.player_position()
        allies = self._ally_alive()
        alert = self.read_alert_state() != 0
        if allies and (alert or self._ally_engaged(allies)):
            self._ally_war_until = now + self.ALLY_WAR_HOLD
        fighting = bool(allies) and now < getattr(self, "_ally_war_until", 0.0)
        self._ally_war(fighting)
        if position is None or not allies:
            return
        route = getattr(self, "_ally_follow_route", None)
        if route and (route["pid"] != self.pid or not route.get("entry")
                      or self._ally_route_entry(route["name"]) != route["entry"]):
            self._ally_follow_route = route = None  # zone rechargee : la route d'origine est revenue
        if route and self._ally_route_taken(route, allies):
            # un soldat a recu la route empruntee (un PMC suivait Snake comme
            # Meryl, 2026-11-07) : rendue telle quelle, une autre est empruntee
            self.ally_follow_release()
            self._ally_banned = getattr(self, "_ally_banned", set()) | {route["name"]}
            route = None
        if route is None:
            route = self._ally_pick_route(exclude=getattr(self, "_ally_banned", set()))
            self._ally_follow_route, self._ally_layout = route, None
            if route is None:
                return

        # attache : une fois par allie (et apres relance de son IA), avant
        # tout le reste, combat compris : une Meryl apparue pendant une
        # alerte suivait sinon la route de sa recette (patrouille de la zone,
        # 19 points) en ligne droite, a travers un mur (2026-11-07)
        if getattr(self, "_ally_kicked_pid", None) != self.pid:
            self._ally_kicked, self._ally_kicked_pid = set(), self.pid
        new = [a for a in allies if a not in self._ally_kicked and self._ally_is_spawned(a)]
        if new:
            self.ally_kick(new, 0)  # relance de son IA, sans ordre de route
            return
        # attache par la commande de route : le jeu ramene le suivi a la route
        # de la fiche de l'acteur a chaque image (une route a nous, hors des
        # groupes, etait quittee en moins de 20 ms, 2026-11-07)
        unbound = [a for a in allies if self._spawn_q(self._spawn_q(a + self.ALLY_FOLLOWER) + self.ALLY_FOLLOWER_ENTRY)
                   != route["entry"]]
        if unbound:
            # la route empruntee ramenee d'abord a sa position (poste d'un
            # point) : elle ne part ni vers le debut d'origine de la route ni
            # vers un ancien pas de la trace
            here = struct.unpack("<3f", self.proc.read_bytes(unbound[0] + self.ALLY_POSITION, 12))
            self.proc.write_bytes(route["address"], self._ally_point(
                here, here, self.ALLY_STOP_ACTION, self.ALLY_MOVE_RUN, self.ALLY_STOP_WAIT, 0,
                self.ALLY_STOP_FLAGS))
            self.proc.write_bytes(route["entry"] + 8, struct.pack("<H", 1))
            self._ally_layout = ("hold", here)
            self._ally_send([(a, route["name"], 0) for a in unbound])
            return

        if fighting:
            # en alerte, son IA de combat agit seule : piloter son suivi de
            # route la ramenait sans cesse a la trace, elle ne ripostait pas
            # et courait contre un mur (2026-11-07). Le poste est ramene une
            # fois a sa position : laisse tel quel, elle repartait en ligne
            # droite vers l'ancien poste, a travers un mur. En deplacement
            # (acteur+0x45E0 bit 0x800), son module de cible ne vise que sa
            # destination et elle ne tire pas.
            self._ally_hold(allies)
            return

        move = self._ally_auto_move(position, allies, now)
        post_action = self.ally_point_action if self.ally_point_action >= 0 else (
            self.ALLY_STOP_ACTION_CROUCH if getattr(self, "_ally_snake_crouched", False) else self.ALLY_STOP_ACTION)
        style = (move, post_action)
        self._ally_live_style(allies, route, style)

        # trace de Snake ; arret ALLY_STOP_BEHIND derriere lui le long de la trace
        trail = getattr(self, "_ally_trail", [])
        if not trail or math.dist(trail[-1], position) >= self.ALLY_TRAIL_STEP:
            trail = (trail + [tuple(position)])[-self.ALLY_TRAIL_KEEP:]
            self._ally_trail = trail
        behind, cut = 0.0, len(trail) - 1
        while cut > 0 and behind < self.ALLY_STOP_BEHIND:
            behind += math.dist(trail[cut], trail[cut - 1])
            cut -= 1
        if behind < self.ALLY_STOP_BEHIND or cut < 1:
            # trace trop courte : poste sur place (ramene a elle si elle s'en
            # est eloignee)
            self._ally_hold(allies)
            return
        path = trail[:cut + 1]
        stop = path[-1]
        heres = {ally: struct.unpack("<3f", self.proc.read_bytes(ally + self.ALLY_POSITION, 12)) for ally in allies}

        layout = getattr(self, "_ally_layout", None)
        facing = int(math.atan2(position[0] - stop[0], position[2] - stop[2]) / (2 * math.pi) * 0x10000) & 0xFFFF
        if all(math.dist(heres[a], stop) < self.ALLY_STOP_NEAR for a in allies):
            # poste : 1 point (attente infinie), elle ne bouge plus
            wanted = ("post", stop, style)
            if layout != wanted:
                self.proc.write_bytes(route["address"], self._ally_point(
                    stop, stop, post_action, move, self.ALLY_STOP_WAIT, facing, self.ALLY_STOP_FLAGS))
                self.proc.write_bytes(route["entry"] + 8, struct.pack("<H", 1))
                for ally in allies:
                    self._ally_steer(ally, route, 0, stop)
                self._ally_layout = wanted
            return

        # en marche : les pas devant le plus en retard des allies
        nearest = {a: min(range(len(path)), key=lambda i: (math.dist(path[i], heres[a]), -i)) for a in allies}
        first = min(nearest.values())
        ahead = path[first:]
        if len(ahead) < 2:
            ahead = path[-2:]
            first = len(path) - 2
        if len(ahead) > route["count"]:
            # plus de pas que la route n'en contient : un sur k, du plus proche
            # d'elle jusqu'au dernier (sinon elle restait derriere le debut de
            # la trace sur un long trajet, 2026-11-07)
            span = len(ahead) - 1
            picks = sorted({round(i * span / (route["count"] - 1)) for i in range(route["count"])})
            ahead = [ahead[i] for i in picks]
        wanted = ("trail", tuple(ahead), style)
        if layout != wanted:
            data = b"".join(self._ally_point(point, ahead[min(i + 1, len(ahead) - 1)], self.ALLY_POINT_PLAIN, move)
                            for i, point in enumerate(ahead[:-1]))
            # dernier pas : poste de garde (attente infinie) ; jamais atteint
            # sans passer au poste ci-dessus
            data += self._ally_point(ahead[-1], ahead[-1], post_action, move, self.ALLY_STOP_WAIT, facing,
                                     self.ALLY_STOP_FLAGS)
            self.proc.write_bytes(route["address"], data)
            self.proc.write_bytes(route["entry"] + 8, struct.pack("<H", len(ahead)))
            for ally in allies:
                # le pas de la route juste apres le plus proche d'elle
                here_index = min(range(len(ahead)), key=lambda i: (math.dist(ahead[i], heres[ally]), -i))
                index = min(here_index + 1, len(ahead) - 1)
                self._ally_steer(ally, route, index, ahead[index])
            self._ally_layout = wanted

    def _game_lock(self) -> threading.Lock:
        """Une commande de jeu a la fois (apparition, ordres aux allies)."""
        if not hasattr(self, "_game_lock_obj"):
            self._game_lock_obj = threading.Lock()
        return self._game_lock_obj

    def _ally_busy_now(self) -> bool:
        """Les ordres aux allies s'effacent devant une apparition en attente
        ou un ordre deja en cours (ils reviennent toutes les 2 s)."""
        return getattr(self, "_spawn_busy", False) or getattr(self, "_ally_busy", False)

    def _spawn_run(self, kind: dict) -> None:
        # attend la fin d'un ordre en cours (mode compagnon) au lieu d'etre
        # refusee : apparitions qui echouaient au hasard (2026-11-07)
        locked = self._game_lock().acquire(timeout=15.0)
        try:
            if locked:
                self._spawn_enemy(kind)
        except (OSError, struct.error, ValueError, KeyError, StopIteration):
            pass
        finally:
            if locked:
                self._game_lock().release()
            self._spawn_busy = False

    def _spawn_q(self, address: int) -> int:
        return struct.unpack("<Q", self.proc.read_bytes(address, 8))[0]

    def _spawn_enemy(self, kind: dict) -> bool:
        funcs = self._live_funcs(self.SPAWN_FUNCS)
        position = self.player_position()
        if funcs is None or position is None:
            return False
        if self._spawn_q(self.base + self.SPAWN_CURRENT_UNIT_RVA):
            return False  # un script de creation est en cours
        if kind.get("boss"):
            return self._spawn_boss(kind, funcs, position)
        if not self._spawn_patch_route() or not self._spawn_managers(funcs):
            return False
        if not self._spawn_group(funcs, kind["group"]):
            return False
        if kind.get("no_death_camera") and not self._spawn_patch_death_camera():
            return False
        if not self._spawn_register(funcs, kind["zone"]):
            return False
        unit_template = self._spawn_unit_for_zone(kind["unit"])
        if unit_template is None:
            return False
        self._spawn_names = getattr(self, "_spawn_names", self.SPAWN_FIRST_NAME) + 2
        units = self._spawn_tasks(self.SPAWN_UNIT_VTABLE_RVA)
        unit_args = self._spawn_named(unit_template, self._spawn_names)
        if self._spawn_command(unit_args, funcs["chara_named"]) is None:
            return False
        created = self._spawn_tasks(self.SPAWN_UNIT_VTABLE_RVA) - units
        if len(created) != 1:
            return False
        unit = created.pop()
        actors = self._spawn_tasks(kind["vtable"])
        actor_name = self._spawn_names + 1
        if self._spawn_command(self._spawn_named(kind["actor"], actor_name), funcs["chara"], unit) is None:
            return False
        created = self._spawn_tasks(kind["vtable"]) - actors
        if len(created) != 1:
            return False
        soldier = created.pop()
        if kind["setup"]:
            args, positional, name_offset = kind["setup"]
            args = args[:name_offset] + struct.pack("<I", actor_name) + args[name_offset + 4:]
            if self._spawn_command(args, funcs["chara"], positional=positional) is None:
                return False
        # Tout de suite : ne au point (0, 0, 0), il tomberait sous la carte.
        target = self._spawn_alloc(0x100, PAGE_READWRITE)
        x, y, z = position
        self.proc.write_bytes(target, struct.pack(
            "<4f", x + kind["distance"], y + self.SPAWN_GROUND_OFFSET, z, 1.0))
        if self.speed.game_call(funcs["warp"], soldier, target, 0, timeout=10.0) is None:
            return False
        vtable = self._spawn_q(soldier)
        if self._spawn_q(vtable + self.SPAWN_START_VTABLE_OFFSET) != funcs["start"]:
            return False
        self._spawn_copy_route(soldier, kind)
        flags = struct.unpack("<I", self.proc.read_bytes(soldier + self.SPAWN_START_FLAGS, 4))[0]
        self.proc.write_bytes(soldier + self.SPAWN_START_FLAGS, struct.pack("<I", flags | self.SPAWN_START_BIT))
        if self.speed.game_call(funcs["start"], soldier, timeout=10.0) is None:
            return False
        if kind.get("kick"):
            # la placer de nouveau relance son etat : son IA demarre (voir ally_kick)
            self.speed.game_call(funcs["warp"], soldier, target, 0, timeout=10.0)
        return True

    def _spawn_boss(self, kind: dict, funcs: dict[str, int], position) -> bool:
        """Boss cree seul (ESSAI) : ressources de sa zone, puis sa commande de
        creation (chara nomme), position de depart ecrite dans l'option
        position_option : 09 X (int32), 01 Y (int16), 09 Z (int32)."""
        if not self._spawn_register(funcs, kind["zone"]):
            return False
        self._spawn_names = getattr(self, "_spawn_names", self.SPAWN_FIRST_NAME) + 2
        args = self._spawn_named(kind["actor"], self._spawn_names + 1)
        at = args.index(kind["position_option"]) + len(kind["position_option"])
        x, y, z = position
        y = max(-0x8000, min(0x7FFF, int(y)))
        place = (b"\x09" + struct.pack("<i", int(x + kind["distance"])) + b"\x01" + struct.pack("<h", y)
                 + b"\x09" + struct.pack("<i", int(z)))
        if args[at] != 0x09 or args[at + 5] != 0x01 or args[at + 8] != 0x09:
            return False  # option de position inattendue
        args = args[:at] + place + args[at + len(place):]
        if kind.get("effect_guard") and not self._spawn_boss_effect_guard():
            return False
        if kind.get("no_relocate") and not (self._spawn_boss_no_relocate() and self._spawn_boss_fallback()):
            return False
        before = self._spawn_tasks(kind["vtable"])
        if self._spawn_command(args, funcs["chara_named"], positional=self.SPAWN_POSITIONAL_SIZE) is None:
            return False
        created = self._spawn_tasks(kind["vtable"]) - before
        if len(created) != 1:
            return False
        boss = created.pop()
        if kind.get("arena"):
            self._spawn_boss_arena(boss, (x + kind["distance"], position[1], z))
        if kind.get("loop_action"):
            threading.Thread(target=self._spawn_boss_loop, args=(boss, kind["loop_action"]), daemon=True).start()
        return True

    # Relance d'action (ESSAI 2026-11-11) : sans arene, Octopus ne decide plus
    # rien apres une action (la suite attend un point de l'arene) et reste
    # figee. Machines d'etats de l'acteur : nombre +0x34, tableau [+0x38] de
    # 0x130 (id +0x128, etat +0xA4) ; machine 1 = action, machine 2 = sous-
    # etape. Action 15 (essai en jeu) : elle tire sur Snake (sous-etapes
    # 0x59-0x5D, fin d'animation en 0x5C) puis s'arrete. Si la sous-etape ne
    # change plus pendant BOSS_LOOP_IDLE s, l'action est relancee par F21E60
    # (changement d'action du jeu), dans le fil du jeu.
    BOSS_SET_ACTION = 0xF21E60
    BOSS_LOOP_IDLE = 3.0
    # Machine 0 : 2 = combat ; 6 = mise hors de combat (endurance 0, vu en
    # jeu). Action 30 : fin de combat, elle tombe et s'evapore (essai en jeu).
    BOSS_DOWN_MODE = 6
    BOSS_DEFEAT_ACTION = 30

    def _spawn_boss_machines(self, boss: int) -> dict[int, int]:
        count = struct.unpack("<i", self.proc.read_bytes(boss + 0x34, 4))[0]
        table = self._spawn_q(boss + 0x38)
        out = {}
        for k in range(min(max(count, 0), 8)):
            machine, state = struct.unpack("<ii", self.proc.read_bytes(table + k * 0x130 + 0x128, 4)
                                           + self.proc.read_bytes(table + k * 0x130 + 0xA4, 4))
            out[machine] = state
        return out

    def _spawn_boss_loop(self, boss: int, action: int) -> None:
        last, since = None, time.monotonic()
        while True:
            time.sleep(0.25)
            try:
                if boss not in self._spawn_tasks(self.SPAWN_TYPES["laughing"]["vtable"]):
                    return
                life_object = self._spawn_q(boss + 0x42B0)
                life, _, stamina = struct.unpack("<iii", self.proc.read_bytes(life_object + 0x314, 12)) \
                    if life_object else (1, 0, 1)
                machines = self._spawn_boss_machines(boss)
            except OSError:
                return
            if life <= 0 or stamina <= 0 or machines.get(0) == self.BOSS_DOWN_MODE:
                # vaincue (vie ou endurance a 0 ; mode 6 vu en jeu) : action
                # de fin de combat (elle tombe et s'evapore), plus de relance
                with self._game_lock():
                    self.speed.game_call(self.base + self.BOSS_SET_ACTION, boss, self.BOSS_DEFEAT_ACTION, timeout=5.0)
                return
            state = (machines.get(1), machines.get(2))
            now = time.monotonic()
            if state != last:
                last, since = state, now
                continue
            if now - since < self.BOSS_LOOP_IDLE:
                continue
            with self._game_lock():
                self.speed.game_call(self.base + self.BOSS_SET_ACTION, boss, action, timeout=5.0)
            last, since = None, time.monotonic()

    # Parades pour un boss hors de son arene (ESSAI 2026-11-11, adresses 1.4.2
    # seulement, comme la recette de Laughing Octopus).
    # Effet visuel : A2B50 (tache d'effet d'Octopus, F06380) recopie la
    # ressource d'une structure (+0xD8 / +0xE8) dans le pointeur actif
    # 0x17341D0 ; ressource absente hors de sa zone -> pointeur nul ->
    # plantage A3B40 a l'image suivante. Detour de l'ecriture (A2C6F,
    # « mov [rip+..], rax ») : nul -> objet par defaut du jeu (global 0x1734170,
    # objet 0x33A2B8), le repli que le jeu prevoit lui-meme.
    BOSS_EFFECT_SITE = 0xA2C6F
    BOSS_EFFECT_ORIGINAL = bytes.fromhex("4889055a156901")
    BOSS_EFFECT_RETURN = 0xA2C76
    BOSS_EFFECT_ACTIVE = 0x17341D0
    BOSS_EFFECT_DEFAULT = 0x1734170
    # Arene : F0C6C0 cherche la zone d'arene contenant un point dans la table
    # d'Octopus (entrees de 0xA50 a +0x5970, nombre +0x127B0 ; boite min
    # +0x960 / max +0x970 ; points : nombre +0xA30, pointeurs +0x988,
    # positions +0x9C0 de 0x20) ; table vide hors de s02a50l -> nul, que
    # plusieurs appelants lisent sans test (plantage F0A727, et division par
    # +0xA30). Une zone geante avec un point pres de Snake.
    BOSS_ARENA_TABLE, BOSS_ARENA_COUNT, BOSS_ARENA_STRIDE = 0x5970, 0x127B0, 0xA50
    BOSS_AREA_BOX_MIN, BOSS_AREA_BOX_MAX = 0x960, 0x970
    BOSS_AREA_POINTS, BOSS_AREA_POINT_PTRS, BOSS_AREA_POINT_POS = 0xA30, 0x988, 0x9C0

    def _spawn_boss_effect_guard(self) -> bool:
        """Pose une fois par processus le detour de l'effet visuel."""
        from mgs4trainer.core import versions
        if versions.name() != "1.4.2":
            return False
        site = self.base + self.BOSS_EFFECT_SITE
        current = self.proc.read_bytes(site, len(self.BOSS_EFFECT_ORIGINAL))
        if current[0] == 0xE9:
            return True  # deja pose
        if current != self.BOSS_EFFECT_ORIGINAL:
            return False
        cave = self.proc.alloc_near(site, 0x1000)
        if not cave:
            return False
        code = (
            b"\x48\x85\xC0"                                                   # test rax, rax
            + b"\x75\x0D"                                                     # jnz +13
            + b"\x48\xB8" + struct.pack("<Q", self.base + self.BOSS_EFFECT_DEFAULT)  # mov rax, defaut
            + b"\x48\x8B\x00"                                                 # mov rax, [rax]
            + b"\x51"                                                         # push rcx
            + b"\x48\xB9" + struct.pack("<Q", self.base + self.BOSS_EFFECT_ACTIVE)   # mov rcx, actif
            + b"\x48\x89\x01"                                                 # mov [rcx], rax
            + b"\x59"                                                         # pop rcx
            + b"\xFF\x25\x00\x00\x00\x00" + struct.pack("<Q", self.base + self.BOSS_EFFECT_RETURN)
        )
        self.proc.write_bytes(cave, code)
        self.proc.write_bytes(site, b"\xE9" + struct.pack("<i", cave - (site + 5)) + b"\x90\x90")
        return True

    # Deplacements d'Octopus : F0A6D0(boss, 0, type) choisit une destination
    # dans une zone d'arene (types 1, 2, 8, 0x10, 0x20, 0x40, 0x80, 0x800) et
    # renvoie > 0 si trouvee ; ses appelants (F1CD20, F1CE00, F1CE90, F1CF70,
    # decision F3AD80) passent a autre chose sinon. Debut remplace par
    # « xor eax,eax ; ret » : plus de cachette ni de teleportation, le reste
    # du combat continue. Touche aussi son vrai combat : pose seulement a
    # l'apparition hors arene, pour la session de jeu (ESSAI 2026-11-11).
    # Procedures de script d'Octopus : ses reactions (contact avec Snake,
    # phases, defaite...) lancent par 2DA1A0 des procedures dont les numeros
    # viennent de sa recette (+0x4468, +0x4C74..+0x4C98) ; hors de s02a50l
    # ils designent d'autres procedures (un contact a lance une liste de 355
    # « slot_save » de s01a57l : pile debordee en 2DA9E5, 2026-11-11). Les
    # 8 appels sont coupes (call -> « xor eax,eax », jmp -> « xor eax,eax ;
    # ret ») ; meme reserve que ci-dessus (son vrai combat en est prive).
    BOSS_PATCHES = (
        (0xF0A6D0, "448944241848", "31c0c3"),       # destination d'arene : aucune
        (0xF183B1, "e8ea1d3cff", "31c0909090"),
        (0xF1C7F5, "e8a6d93bff", "31c0909090"),
        (0xF1F75B, "e840aa3bff", "31c0909090"),
        (0xF1FF1B, "e880a23bff", "31c0909090"),
        (0xF3B643, "e858eb39ff", "31c0909090"),
        (0xF3D709, "e892ca39ff", "31c0909090"),
        (0xF3DA1C, "e97fc739ff", "31c0c39090"),
        (0xF3DED2, "e9c9c239ff", "31c0c39090"),
    )

    def _spawn_boss_no_relocate(self) -> bool:
        from mgs4trainer.core import versions
        if versions.name() != "1.4.2":
            return False
        todo = []
        for rva, original, patch in self.BOSS_PATCHES:
            original, patch = bytes.fromhex(original), bytes.fromhex(patch)
            current = self.proc.read_bytes(self.base + rva, len(original))
            if current.startswith(patch):
                continue
            if current != original:
                return False  # code inattendu : rien n'est pose
            todo.append((self.base + rva, patch))
        for site, patch in todo:
            self.proc.write_bytes(site, patch)
        return True

    def _spawn_boss_arena(self, boss: int, point) -> None:
        """Une zone d'arene geante (tout le monde dedans) avec un point."""
        spot = self._spawn_alloc(0x1000, PAGE_READWRITE)
        area = boss + self.BOSS_ARENA_TABLE
        self.proc.write_bytes(area + self.BOSS_AREA_BOX_MIN, struct.pack("<4f", -1e9, -1e9, -1e9, 1.0))
        self.proc.write_bytes(area + self.BOSS_AREA_BOX_MAX, struct.pack("<4f", 1e9, 1e9, 1e9, 1.0))
        self.proc.write_bytes(area + self.BOSS_AREA_POINT_PTRS, struct.pack("<Q", spot))
        self.proc.write_bytes(area + self.BOSS_AREA_POINT_POS, struct.pack("<4f", *point, 1.0))
        self.proc.write_bytes(area + self.BOSS_AREA_POINTS, struct.pack("<i", 1))
        self.proc.write_bytes(boss + self.BOSS_ARENA_COUNT, struct.pack("<i", 1))
        # Seconde liste de points (F0C5F0, plus proche point libre -> +0x26628,
        # lu sans test en F39A27) : entrees de 0x60 a +0x12FD0, nombre
        # +0x13BD0, mot +0x8 = 0 (libre), position +0x10.
        # Un point utilise est marque occupe (+0x8) : un seul ne suffit pas
        # (plus de point libre apres la premiere teleportation, plantage
        # F394C1). BOSS_POINT_RING points en cercle autour de l'apparition.
        x, y, z = point
        for k in range(self.BOSS_POINT_RING):
            angle = 2 * math.pi * k / self.BOSS_POINT_RING
            entry = boss + self.BOSS_POINT_LIST + k * self.BOSS_POINT_STRIDE
            self.proc.write_bytes(entry + 0x8, struct.pack("<H", 0))
            self.proc.write_bytes(entry + 0x10, struct.pack(
                "<4f", x + self.BOSS_POINT_RADIUS * math.cos(angle), y,
                z + self.BOSS_POINT_RADIUS * math.sin(angle), 1.0))
        self.proc.write_bytes(boss + self.BOSS_POINT_COUNT, struct.pack("<i", self.BOSS_POINT_RING))

    # Action de repli d'Octopus : sa decision (F3AD80, entree de l'etat 2 de
    # sa machine 0) ne trouve plus rien sans arene et ne lance aucune action
    # (elle reste en boule). Detour de F3AE1E (11 octets, dernier essai
    # F0A6D0) : lance l'action BOSS_FALLBACK_ACTION (F21E60 via F3AE35).
    # Action 12 (choisie par le jeu sans arene, sur un drapeau) : boule,
    # chute au sol, se releve (vu en jeu le 2026-11-11).
    BOSS_POINT_LIST, BOSS_POINT_COUNT, BOSS_POINT_STRIDE = 0x12FD0, 0x13BD0, 0x60  # 32 au plus
    BOSS_POINT_RING, BOSS_POINT_RADIUS = 8, 2500.0
    BOSS_FALLBACK_SITE = 0xF3AE1E
    BOSS_FALLBACK_ORIGINAL = bytes.fromhex("33d2448d4201")  # puis call F0A6D0 (e8 + 4)
    BOSS_FALLBACK_SET_ACTION, BOSS_FALLBACK_SKIP = 0xF3AE35, 0xF3AE3A
    BOSS_FALLBACK_ACTION = 15  # tir sur Snake (essai en jeu : 12 = boule, chute, releve)

    def _spawn_boss_fallback(self) -> bool:
        from mgs4trainer.core import versions
        if versions.name() != "1.4.2":
            return False
        site = self.base + self.BOSS_FALLBACK_SITE
        current = self.proc.read_bytes(site, 11)
        if current[0] == 0xE9:
            return True  # deja pose
        if current[:6] != self.BOSS_FALLBACK_ORIGINAL or current[6] != 0xE8:
            return False
        cave = self.proc.alloc_near(site, 0x1000)
        if not cave:
            return False
        code = (
            b"\xBA" + struct.pack("<I", self.BOSS_FALLBACK_ACTION)           # mov edx, action
            + b"\x48\x8B\xCB"                                                 # mov rcx, rbx
            + b"\xFF\x25\x00\x00\x00\x00" + struct.pack("<Q", self.base + self.BOSS_FALLBACK_SET_ACTION)
        )
        self.proc.write_bytes(cave, code)
        self.proc.write_bytes(site, b"\xE9" + struct.pack("<i", cave - (site + 5)) + b"\x90" * 6)
        return True

    def _spawn_managers(self, funcs: dict[str, int]) -> bool:
        """Cree les gestionnaires s'il n'y en a pas. Sans groupe, l'inscription
        de l'escouade (B54070) lit un pointeur nul : on s'arrete."""
        if not self._spawn_q(self.base + self.SPAWN_MANAGER_RVA):
            for args in self.SPAWN_MANAGERS:
                if self._spawn_command(args, funcs["chara_named"], positional=self.SPAWN_MANAGER_POSITIONAL) is None:
                    return False
        manager = self._spawn_q(self.base + self.SPAWN_MANAGER_RVA)
        return bool(manager) and struct.unpack("<i", self.proc.read_bytes(manager + 0x20, 4))[0] > 0

    def _spawn_groups_present(self) -> set[int]:
        manager = self._spawn_q(self.base + self.SPAWN_MANAGER_RVA)
        count = struct.unpack("<i", self.proc.read_bytes(manager + 0x20, 4))[0]
        groups = self._spawn_q(manager + 0x28)
        return {
            struct.unpack("<I", self.proc.read_bytes(self._spawn_q(groups + i * 8) + 0x18, 4))[0]
            for i in range(count)
        }

    def _spawn_grow_groups(self, funcs: dict[str, int], manager: int, limit: int) -> bool:
        """Agrandit le tableau des groupes (zones a un seul QG). Alloue par le
        jeu, qui le liberera en quittant la zone ; l'ancien reste perdu. Les
        tables du gestionnaire ont 4 places."""
        if limit >= self.SPAWN_GROUPS_MAX:
            return False
        groups = self._spawn_q(manager + 0x28)
        array = self.speed.game_call(funcs["alloc"], (limit + 1) * 8, timeout=10.0)
        if not array:
            return False
        self.proc.write_bytes(array, self.proc.read_bytes(groups, limit * 8) + bytes(8))
        self.proc.write_bytes(manager + 0x28, struct.pack("<Q", array))
        self.proc.write_bytes(manager + 0x1C, struct.pack("<i", limit + 1))
        return True

    def _spawn_group(self, funcs: dict[str, int], group: int) -> bool:
        """Cree le QG de l'escouade s'il manque : sans lui, B54070 lit un
        pointeur nul. Puis la relation entre camps, s'il y en a deux."""
        present = self._spawn_groups_present()
        if group in present:
            return True
        manager = self._spawn_q(self.base + self.SPAWN_MANAGER_RVA)
        limit = struct.unpack("<i", self.proc.read_bytes(manager + 0x1C, 4))[0]
        if len(present) >= limit and not self._spawn_grow_groups(funcs, manager, limit):
            return False
        args = self.SPAWN_GROUP_ARGS.format(
            name=group.to_bytes(3, "little").hex(), side=f"{self.SPAWN_GROUP_SIDES[group]:02x}")
        if self._spawn_command(bytes.fromhex(args), funcs["chara_named"], positional=self.SPAWN_MANAGER_POSITIONAL) is None:
            return False
        present = self._spawn_groups_present()
        if group not in present:
            return False
        if self.SPAWN_DECLARE_WAR and set(self.SPAWN_GROUP_SIDES) <= present:
            args = bytes.fromhex(self.SPAWN_GROUP_RELATION_ARGS)
            return self._spawn_command(args, funcs["chara"], positional=self.SPAWN_GROUP_RELATION_POSITIONAL) is not None
        return True

    def _spawn_patch_death_camera(self) -> bool:
        for rva, orig in self.SPAWN_DEATH_CAMERA_SITES:
            if not rva:
                continue  # chemin absent de cette version du jeu (versions/*.json)
            current = self.proc.read_bytes(self.base + rva, len(orig))
            if current == orig:
                self.proc.write_bytes(self.base + rva, bytes((0xC3,)) + bytes((0x90,)) * (len(orig) - 1))
            elif current[0] != 0xC3:
                return False
        return True

    def _spawn_patch_route(self) -> bool:
        """Pose les deux detours du suivi de route, une fois par partie."""
        lookup = self.base + self.SPAWN_ROUTE_LOOKUP
        apply = self.base + self.SPAWN_ROUTE_APPLY
        current = self.proc.read_bytes(apply, len(self.SPAWN_ROUTE_APPLY_ORIG))
        if current != self.SPAWN_ROUTE_APPLY_ORIG:
            return current[0] == 0xE9
        if self.proc.read_bytes(lookup, len(self.SPAWN_ROUTE_LOOKUP_ORIG)) != self.SPAWN_ROUTE_LOOKUP_ORIG:
            return False
        cave = self.proc.alloc_near(lookup)
        if not cave:
            return False
        noted = cave + 0x1F0  # structure (+0), son id a l'entree (+8)

        def rip(end: int, target: int) -> bytes:
            return struct.pack("<i", target - end)
        lookup_code = bytearray()
        lookup_code += bytes.fromhex("488915") + rip(cave + len(lookup_code) + 7, noted)       # mov [note], rdx
        lookup_code += bytes.fromhex("4885d27409")                                              # test rdx, rdx ; jz suite
        lookup_code += bytes.fromhex("8b4244")                                                  # mov eax, [rdx + 0x44] (lecture seule)
        lookup_code += bytes.fromhex("8905") + rip(cave + len(lookup_code) + 6, noted + 8)      # mov [note + 8], eax
        lookup_code += self.SPAWN_ROUTE_LOOKUP_ORIG                                             # suite :
        lookup_code += b"\xFF\x25\x00\x00\x00\x00" + struct.pack("<Q", lookup + len(self.SPAWN_ROUTE_LOOKUP_ORIG))
        lookup_code = bytes(lookup_code)
        motion = struct.pack("<I", self.SPAWN_ROUTE_MOTION)
        fallback = (
            b"\x51\x48\x83\xEC\x20"                    # push rcx ; sub rsp, 0x20
            + b"\xB9" + motion + b"\x31\xD2"             # mov ecx, animation ; xor edx, edx
            + _mov_rax(self.base + self.SPAWN_ROUTE_FIND) + b"\xFF\xD0"  # call rax
            + b"\x48\x83\xC4\x20\x59"                  # add rsp, 0x20 ; pop rcx
            + b"\x48\x85\xC0\x75\x01\xC3"              # test rax, rax ; jnz +1 ; ret
            + b"\xBA" + motion + b"\x45\x33\xC0"         # mov edx, animation ; xor r8d, r8d
        )
        keep = (
            b"\x41\xB8\xFF\xFF\xFF\xFF"                # mov r8d, -1 (image en cours)
            + b"\x83\xB9\x90\x00\x00\x00\x00"          # cmp dword ptr [rcx + 0x90], 0
            + b"\x75" + bytes((len(fallback),))           # jne jeu
        )
        apply_cave = cave + 0x40
        # Structure notee par B680C0 et id inchange : la recherche a echoue.
        check = bytearray(self.SPAWN_ROUTE_APPLY_ORIG[:5])                                      # movsx r8d, word [rdx + 0x30]
        check += bytes.fromhex("483b15") + rip(apply_cave + len(check) + 7, noted)              # cmp rdx, [note]
        check += bytes.fromhex("750f")                                                          # jne lire
        check += bytes.fromhex("8b4244")                                                        # mov eax, [rdx + 0x44]
        check += bytes.fromhex("3b05") + rip(apply_cave + len(check) + 6, noted + 8)            # cmp eax, [note + 8]
        check += bytes.fromhex("7504")                                                          # jne lire
        check += bytes.fromhex("31d2")                                                          # xor edx, edx (echec)
        check += bytes.fromhex("eb03")                                                          # jmp tester
        check += self.SPAWN_ROUTE_APPLY_ORIG[5:]                                                # lire : mov edx, [rdx + 0x44]
        apply_code = (
            bytes(check)
            + b"\x85\xD2\x75" + bytes((len(keep) + len(fallback),))  # tester : test edx, edx ; jnz jeu
            + keep + fallback
            + b"\xFF\x25\x00\x00\x00\x00" + struct.pack("<Q", self.base + self.SPAWN_ROUTE_PLAY)  # jeu: jmp [rip]
        )
        step_cave = cave + 0x100
        step = self.base + self.SPAWN_STEP_SITE
        if self.proc.read_bytes(step, len(self.SPAWN_STEP_ORIG)) != self.SPAWN_STEP_ORIG:
            return False
        step_set = (
            bytes.fromhex("488b4c2420")                # mov rcx, [rsp + 0x20]
            + bytes.fromhex("ba") + motion             # mov edx, animation
            + bytes.fromhex("4533c0")                  # xor r8d, r8d
            + _mov_rax(self.base + self.SPAWN_STEP_SET) + bytes.fromhex("ffd0")  # call rax
        )
        step_fix = (
            bytes.fromhex("514883ec20")                # push rcx ; sub rsp, 0x20
            + bytes.fromhex("b9") + motion + bytes.fromhex("31d2")  # mov ecx, animation ; xor edx, edx
            + _mov_rax(self.base + self.SPAWN_ROUTE_FIND) + bytes.fromhex("ffd0")  # call rax
            + bytes.fromhex("4885c074") + bytes((len(step_set),))  # test rax, rax ; jz fin
            + step_set
            + bytes.fromhex("4883c42059")              # fin: add rsp, 0x20 ; pop rcx
        )
        step_code = (
            bytes.fromhex("4883795000")                # cmp qword ptr [rcx + 0x50], 0
            + bytes.fromhex("75") + bytes((len(step_fix),))  # jne jeu
            + step_fix
            + self.SPAWN_STEP_ORIG                     # jeu:
            + bytes.fromhex("ff2500000000") + struct.pack("<Q", step + len(self.SPAWN_STEP_ORIG))
        )
        self.proc.write_bytes(cave, lookup_code)
        self.proc.write_bytes(apply_cave, apply_code)
        self.proc.write_bytes(step_cave, step_code)
        self.proc.write_bytes(lookup, b"\xE9" + struct.pack("<i", cave - (lookup + 5)))
        self.proc.write_bytes(apply, b"\xE9" + struct.pack("<i", apply_cave - (apply + 5)))
        self.proc.write_bytes(step, bytes.fromhex("e9") + struct.pack("<i", step_cave - (step + 5)) + bytes.fromhex("909090"))
        return True

    def _spawn_copy_route(self, soldier: int, kind: dict) -> None:
        """Reprend la route d'un acteur de la zone, s'il y en a un : sans
        acteur a copier, le soldat garde ses fiches vides. own_route : de
        preference celle d'un acteur du meme type ; a defaut, celle d'un autre
        (sans route, l'IA vise un point par defaut et court contre un mur :
        Meryl en s01a57l, 2026-11-06)."""
        actors = self._zone_soldiers()
        same = [a for a, _life, _gauges in actors if self._spawn_q(a) == self._spawn_q(soldier)]
        others = [a for a, _life, _gauges in actors if a not in same] if kind.get("own_route") else []
        for actor in (same + others) if kind.get("own_route") else [a for a, _l, _g in actors]:
            record = self.proc.read_bytes(actor + self.SPAWN_ROUTE_RECORD, self.SPAWN_ROUTE_RECORD_SIZE)
            if actor != soldier and struct.unpack_from("<i", record, 8)[0] > 0:
                groups = self.proc.read_bytes(actor + self.SPAWN_ROUTE_GROUPS, self.SPAWN_ROUTE_GROUPS_SIZE)
                self.proc.write_bytes(soldier + self.SPAWN_ROUTE_RECORD, record)
                self.proc.write_bytes(soldier + self.SPAWN_ROUTE_GROUPS, groups)
                return

    # Groupe de routes de l'unite (option 0x9ECAEF62 = famille 0xEA2C5E,
    # groupe) : les recettes portent 0x221E90 (s01a57l). Dans une zone sans
    # ce groupe, le jeu le cherche sans tester l'echec (A29510, depuis le
    # code des formations 847E8A) et plante : en s01a40l, 2026-11-07. On le
    # remplace par un groupe de la zone ; le Gekko (route de ce groupe dans
    # sa recette) n'apparait que si le groupe existe.
    SPAWN_UNIT_GROUP = 0x221E90

    def _spawn_zone_groups(self) -> list[int]:
        """Groupes de routes (famille ALLY_ROUTE_KIND) de la zone."""
        q = self._spawn_q
        node = q(q(self.base + self.ALLY_ROUTE_GROUPS_RVA) + 8)
        out, seen = [], set()
        while node and node not in seen and len(seen) < 64:
            seen.add(node)
            kind, _unused, groups = struct.unpack("<iii", self.proc.read_bytes(node + 0x18, 12))
            if kind == self.ALLY_ROUTE_KIND:
                table = q(node + 0x28)
                out += [struct.unpack("<i", self.proc.read_bytes(q(table + 8 * i) + 8, 4))[0]
                        for i in range(min(max(groups, 0), 64))]
            node = q(node + 0x10)
        return out

    def _spawn_unit_for_zone(self, unit: bytes) -> bytes | None:
        groups = self._spawn_zone_groups()
        if self.SPAWN_UNIT_GROUP in groups:
            return unit
        long_form = b"\x09" + struct.pack("<I", self.SPAWN_UNIT_GROUP)
        if long_form not in unit or not groups:
            return None
        return unit.replace(long_form, b"\x09" + struct.pack("<I", groups[0] & 0xFFFFFFFF))

    def _spawn_named(self, args: bytes, name: int) -> bytes:
        end = self.SPAWN_NAME_OFFSET + 4
        return args[:self.SPAWN_NAME_OFFSET] + struct.pack("<I", name) + args[end:]

    def _spawn_alloc(self, size: int, protection: int) -> int:
        address = kernel32.VirtualAllocEx(self.proc.handle, None, size, MEM_COMMIT_RESERVE, protection)
        if not address:
            raise OSError("allocation impossible")
        return address

    def _spawn_tasks(self, vtable_rva: int) -> set[int]:
        vtable = self.base + vtable_rva
        head = self.base + self.SPAWN_TASK_LIST_RVA
        node = self._spawn_q(head + 0x20)
        seen = set()
        found = set()
        while node and node != head and node not in seen:
            seen.add(node)
            for actor in (self._spawn_q(node + 0x90), node + 0xC0):
                try:
                    if actor and self._spawn_q(actor) == vtable:
                        found.add(actor)
                except OSError:
                    pass
            node = self._spawn_q(node + 0x20)
        return found

    def _spawn_present_keys(self) -> set[int]:
        keys = set()
        tree = self.base + self.SPAWN_RESOURCES_RVA
        stack = [self._spawn_q(tree + i * 8) for i in range(16)]
        while stack:
            node = stack.pop()
            if node:
                keys.add(struct.unpack("<I", self.proc.read_bytes(node + 0x10, 4))[0])
                stack += [self._spawn_q(node), self._spawn_q(node + 8)]
        return keys

    def _spawn_register(self, funcs: dict[str, int], zone: str) -> bool:
        """Enregistre les ressources absentes. Le dictionnaire est vide a
        chaque changement de zone ; les tampons du trainer sont reutilises,
        et recopies car le jeu peut les modifier."""
        present = self._spawn_present_keys()
        missing = [resource for resource in self._spawn_resources(zone) if resource[0] not in present]
        if not missing:
            return True
        if getattr(self, "_spawn_blob_pid", None) != self.pid:
            self._spawn_blob_pid, self._spawn_blobs = self.pid, {}
            self._spawn_arena, self._spawn_arena_left = 0, 0
        entries = b""
        for key, data in missing:
            if key not in self._spawn_blobs:
                self._spawn_blobs[key] = self._spawn_blob(len(data))
                if not self._spawn_blobs[key]:
                    del self._spawn_blobs[key]
                    return False
            self.proc.write_bytes(self._spawn_blobs[key], data)
            entries += struct.pack("<QIII", self._spawn_blobs[key], key, self.SPAWN_RESOURCE_FLAGS, len(data)) + bytes(4)
        table = self._spawn_alloc(0x1000 + len(entries), PAGE_EXECUTE_READWRITE)
        self.proc.write_bytes(table + 0x1000, entries)
        stub = self._spawn_register_stub(table, table + 0x1000, len(missing), funcs["register"], zone)
        self.proc.write_bytes(table + 0x100, stub)
        return self.speed.game_call(table + 0x100, timeout=30.0) is not None

    def _spawn_blob(self, size: int) -> int:
        """Place pour une ressource, 0 si aucune. Dans un bloc au-dessus de la
        base des decalages 32 bits du jeu (voir SPAWN_OFFSET_BASE_RVA) : plus
        loin, l'animation pointerait a cote (plantage dans DCB8B0)."""
        size = (size + 0x10F) & ~0xF
        if size > self._spawn_arena_left:
            base = self._spawn_q(self.base + self.SPAWN_OFFSET_BASE_RVA)
            arena = self.proc.alloc_near(base, self.SPAWN_ARENA_SIZE, self.SPAWN_OFFSET_REACH) if size <= self.SPAWN_ARENA_SIZE else 0
            if not base < arena < base + self.SPAWN_OFFSET_REACH - self.SPAWN_ARENA_SIZE:
                return 0
            self._spawn_arena, self._spawn_arena_left = arena, self.SPAWN_ARENA_SIZE
        address = self._spawn_arena
        self._spawn_arena += size
        self._spawn_arena_left -= size
        return address

    def _spawn_register_stub(self, saved: int, entries: int, count: int, register: int, zone_name: str) -> bytes:
        """Echange le nom de zone, appelle register sur chaque entree
        {tampon, cle, indicateur, taille}, restaure le nom. saved : 16 octets."""
        lvb = self.base + self.SPAWN_LINKVARBUF_RVA
        first, second = self.SPAWN_ZONE_OFFSETS
        zone = struct.unpack("<Q", zone_name.encode() + bytes(1))[0]
        head = (
            b"\x53\x56\x57\x48\x83\xEC\x20"            # push rbx/rsi/rdi ; sub rsp, 0x20
            + b"\x48\xBB" + struct.pack("<Q", saved)   # mov rbx, saved
            + _mov_rax(lvb) + b"\x48\x8B\x00"          # mov rax, [rax]
            + bytes((0x48, 0x8B, 0x48, first))         # mov rcx, [rax + first]
            + b"\x48\x89\x0B"                          # mov [rbx], rcx
            + bytes((0x48, 0x8B, 0x48, second))        # mov rcx, [rax + second]
            + b"\x48\x89\x4B\x08"                      # mov [rbx + 8], rcx
            + _mov_rcx(zone)
            + bytes((0x48, 0x89, 0x48, first))         # mov [rax + first], rcx
            + bytes((0x48, 0x89, 0x48, second))        # mov [rax + second], rcx
            + b"\x48\xBE" + struct.pack("<Q", entries)  # mov rsi, entries
            + b"\xBF" + struct.pack("<I", count)       # mov edi, count
        )
        body = (
            b"\x48\x8B\x0E"                            # mov rcx, [rsi]
            + b"\x8B\x56\x08"                          # mov edx, [rsi + 8]
            + b"\x44\x8B\x46\x0C"                      # mov r8d, [rsi + 0xC]
            + b"\x44\x8B\x4E\x10"                      # mov r9d, [rsi + 0x10]
            + _mov_rax(register) + b"\xFF\xD0"         # call rax
            + b"\x48\x83\xC6\x18"                      # add rsi, 0x18
            + b"\xFF\xCF"                              # dec edi
        )
        # nxt: test edi, edi ; jz fin ; body ; jmp nxt
        loop = b"\x85\xFF\x74" + bytes((len(body) + 2,)) + body
        loop += b"\xEB" + struct.pack("<b", -(len(loop) + 2))
        tail = (
            _mov_rax(lvb) + b"\x48\x8B\x00"
            + b"\x48\x8B\x0B"                          # mov rcx, [rbx]
            + bytes((0x48, 0x89, 0x48, first))
            + b"\x48\x8B\x4B\x08"                      # mov rcx, [rbx + 8]
            + bytes((0x48, 0x89, 0x48, second))
            + b"\x48\x83\xC4\x20\x5F\x5E\x5B\xC3"      # add rsp, 0x20 ; pop ; ret
        )
        return head + loop + tail

    def _spawn_command(self, args: bytes, command: int, unit: int = 0, positional: int = 0,
                       memory: int = 0) -> int | None:
        """Execute une commande de creation comme l'interpreteur de script :
        fin des arguments empilee, pointeur d'arguments, appel, depilage.
        memory : page reutilisee (commandes repetees), sinon une neuve."""
        funcs = self._live_funcs(self.SPAWN_FUNCS)
        if funcs is None:
            return None
        memory = memory or self._spawn_alloc(0x1000, PAGE_EXECUTE_READWRITE)
        buffer, code = memory + 0x100, memory + 0x600
        self.proc.write_bytes(buffer, args)
        stub = self._spawn_command_stub(buffer, command, unit, funcs, positional or self.SPAWN_POSITIONAL_SIZE)
        self.proc.write_bytes(code, stub)
        return self.speed.game_call(code, timeout=10.0)

    def _spawn_command_stub(self, buffer: int, command: int, unit: int, funcs: dict[str, int], positional: int) -> bytes:
        args_pointer = self.base + self.SPAWN_ARGS_RVA
        current_unit = self.base + self.SPAWN_CURRENT_UNIT_RVA
        code = (
            b"\x53\x56\x48\x83\xEC\x28"                # push rbx/rsi ; sub rsp, 0x28
            + _mov_rax(current_unit) + b"\x48\x8B\x30"  # mov rsi, [rax]
            + _mov_rax(args_pointer) + b"\x48\x8B\x18"  # mov rbx, [rax]
        )
        if unit:
            code += _mov_rax(current_unit) + _mov_rcx(unit) + b"\x48\x89\x08"  # mov [rax], rcx
        code += (
            _mov_rcx(buffer + positional)
            + _mov_rax(funcs["args_end_push"]) + b"\xFF\xD0"
            + _mov_rcx(buffer)
            + _mov_rax(funcs["args_set"]) + b"\xFF\xD0"
            + _mov_rax(command) + b"\xFF\xD0"
            + _mov_rax(funcs["args_end_pop"]) + b"\xFF\xD0"
            + _mov_rax(args_pointer) + b"\x48\x89\x18"  # mov [rax], rbx
            + _mov_rax(current_unit) + b"\x48\x89\x30"  # mov [rax], rsi
            + b"\x48\x83\xC4\x28\x5E\x5B\xC3"          # add rsp, 0x28 ; pop ; ret
        )
        return code
