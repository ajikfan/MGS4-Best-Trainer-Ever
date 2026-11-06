"""Apparition d'un soldat PMC devant Snake (prototype, 2026-10-31).

Le jeu cree ses acteurs par des commandes de script. On rejoue ces commandes
avec nos propres arguments, apres avoir enregistre les ressources du soldat
(modeles, animations...) dans le dictionnaire de ressources. Le nom de zone
est echange le temps de cet enregistrement : le jeu en deduit le dossier des
textures HD (textures/PC_TXN_UP/stageNN/<zone>/...) et les lit lui-meme.

Les ressources sont lues dans les archives du jeu installe (core/vpak.py),
d'apres le data.cnf de la zone d'origine du soldat."""
import ctypes
import os
import struct
import threading
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
    SPAWN_GROUP_SIDES = {SPAWN_GROUP_PMC: 0xC0, SPAWN_GROUP_REBEL: 0xC1}
    SPAWN_GROUP_ARGS = "0690ca3006{name}5568c93797{side}00"
    SPAWN_GROUP_RELATION_ARGS = "06354e66065a1e97068bba3700"
    SPAWN_GROUP_RELATION_POSITIONAL = 12

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
            "distance": 2000.0,
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

    def spawn_enemy(self, kind: str) -> bool:
        """Lance l'apparition dans un fil separe (les appels au jeu se font
        une image a la fois). Une seule a la fois."""
        if getattr(self, "_spawn_busy", False) or kind in self.SPAWN_BROKEN:
            return False
        if not (self.connected and self.sane and self.pid and self.speed.ensure_injected(self.pid)):
            return False
        if not self.speed.main_loop_hook_installed():
            return False
        self._spawn_busy = True
        threading.Thread(target=self._spawn_run, args=(self.SPAWN_TYPES[kind],), daemon=True).start()
        return True

    def _spawn_run(self, kind: dict) -> None:
        try:
            self._spawn_enemy(kind)
        except (OSError, struct.error, ValueError, KeyError, StopIteration):
            pass
        finally:
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
        if not self._spawn_patch_route() or not self._spawn_managers(funcs):
            return False
        if not self._spawn_group(funcs, kind["group"]):
            return False
        if kind.get("no_death_camera") and not self._spawn_patch_death_camera():
            return False
        if not self._spawn_register(funcs, kind["zone"]):
            return False
        self._spawn_names = getattr(self, "_spawn_names", self.SPAWN_FIRST_NAME) + 2
        units = self._spawn_tasks(self.SPAWN_UNIT_VTABLE_RVA)
        unit_args = self._spawn_named(kind["unit"], self._spawn_names)
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
        return self.speed.game_call(funcs["start"], soldier, timeout=10.0) is not None

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
        if set(self.SPAWN_GROUP_SIDES) <= present:
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
        acteur a copier, le soldat garde ses fiches vides. own_route : pas
        celle d'un autre camp."""
        for actor, _life, _gauges in self._zone_soldiers():
            if kind.get("own_route") and self._spawn_q(actor) != self._spawn_q(soldier):
                continue
            record = self.proc.read_bytes(actor + self.SPAWN_ROUTE_RECORD, self.SPAWN_ROUTE_RECORD_SIZE)
            if actor != soldier and struct.unpack_from("<i", record, 8)[0] > 0:
                groups = self.proc.read_bytes(actor + self.SPAWN_ROUTE_GROUPS, self.SPAWN_ROUTE_GROUPS_SIZE)
                self.proc.write_bytes(soldier + self.SPAWN_ROUTE_RECORD, record)
                self.proc.write_bytes(soldier + self.SPAWN_ROUTE_GROUPS, groups)
                return

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

    def _spawn_command(self, args: bytes, command: int, unit: int = 0, positional: int = 0) -> int | None:
        """Execute une commande de creation comme l'interpreteur de script :
        fin des arguments empilee, pointeur d'arguments, appel, depilage."""
        funcs = self._live_funcs(self.SPAWN_FUNCS)
        if funcs is None:
            return None
        memory = self._spawn_alloc(0x1000, PAGE_EXECUTE_READWRITE)
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
