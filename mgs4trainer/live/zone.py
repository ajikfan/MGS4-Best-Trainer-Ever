"""MGS4Live : actions sur tous les soldats de la zone (mort, K.O., sommeil, emotions)."""
import struct
import threading

from mgs4trainer.core.winproc import MEM_COMMIT, PAGE_EXECUTE_READWRITE, kernel32


class ZoneMixin:
    """Actions sur tous les soldats de la zone, par les fonctions du jeu
    elles-memes (appelees dans son fil via la DLL, comme l'equipement en
    direct)."""

    # Soldats (2026-10-13, valide en jeu) : liste du gestionnaire d'alerte
    # (_alert_soldiers), objet de vie a soldat+0x42B0 (type 18BC1B0 :
    # +0x314 vie, +0x31C endurance, +0x324 sommeil). B80300 retire du
    # sommeil ; 0x7FFFFFFF = "tout vider", et l'IA du soldat surveille sa
    # jauge de sommeil en continu : il s'endort aussitot. La vie (B21FF0) ou
    # l'endurance (B800B0) a 0 seule ne tue ni n'assomme : comme apres un
    # coup, le soldat doit entrer dans l'etat "touche" de sa machine a
    # etats (soldat+0xE7D0, etat courant +0x8, etats +0x20, soldat +0x50) :
    # F61670(machine, 6) -> entree C7EF70, qui evalue vie/endurance/sommeil
    # (C7D1F0) et enchaine seule mort, K.O. ou retour (valide : mort).
    # Emotions (les quatre des Beauty) : comme les coups "psychiques" de
    # C52190 (bits 17 a 20 des drapeaux du coup), bit 31 de +0x43D0 efface,
    # demande 0x400 posee a +0x4590, puis B65930(soldat+0x4538, soldat,
    # type) choisit l'emotion et sa fonction remplit sa jauge (+0x4538 +
    # 4*(type-1), 0x7FFFFFFF = maximum) et la declenche. Sans les deux
    # premieres etapes, l'emotion ne dure que 2-3 secondes ; avec, une
    # trentaine (fou rire termine par un K.O. d'epuisement, comme en jeu).
    ZONE_LIFE_OBJECT_VTABLE_RVA = 0x18BC1B0
    ZONE_FULL = 0x7FFFFFFF
    # Camp (2026-10-13, valide en s02a30) : octet de poids fort des drapeaux
    # du soldat (+0x43D0) : 1 = ennemis (PMC), 2 = rebelles (milice).
    ZONE_REBEL_CAMP = 2
    ZONE_TARGETS = ("enemies", "rebels", "all")
    # Attitude d'un camp envers Snake (2026-10-13, valide en s02a30) : unite
    # du soldat (soldat+0x4578, type 18BB860) +0x918. Rebelles amicaux : 190,
    # PMC : -500 ; ecrire -500 rend les rebelles hostiles, 190 les calme. Sans
    # effet sur les PMC (restes hostiles a 190).
    ZONE_UNIT_VTABLE_RVA = 0x18BB860
    ZONE_REBEL_AFFINITY = {"neutral": 190, "hostile": -500}
    # Le gestionnaire d'alerte ne liste pas que des soldats (2026-10-14,
    # s02a90) : Gekko (acteur 18EC5B8, objet de vie 3000/3000, pas de machine
    # a etats a +0xE7D0), et civils et rats (18F1F58, vie max 1, meme machine
    # que les soldats). Les non-combattants (vie max <= 1) sont toujours
    # ignores ; les emotions et le sommeil ne visent que les soldats ; les
    # Gekko comptent toujours comme ennemis.
    ZONE_GEKKO_VTABLE_RVA = 0x18EC5B8
    # Gekko (2026-10-14, valide : 5 detruits d'un coup) : machine a etats a
    # acteur+0xE910 ; leur etat "touche" est le 6 (entree 10637D0, mise a
    # jour 10635C0 qui evalue vie/endurance/sommeil et lance la destruction).
    # L'etat 16 (C7EF70, celui des soldats) ne les fait pas exploser.
    # Leur endurance a 0 ne les fait pas tomber ; Endormir = sommeil (+0x324)
    # vide par B80300 puis etat 6 ; Assommer = leurs deux jauges de
    # tranquillisant (mots +0x33C et +0x340 de l'objet de vie) a 0 puis etat
    # 6 : ils tombent au sol, comme avec Un coup, un mort en Non letal (valide).
    ZONE_GEKKO_TRANQ_OFFSETS = (0x33C, 0x340)
    # L'etat 6 choisit chute ou simple sursaut d'apres la copie du dernier
    # coup dans l'objet de vie : +0x174 type, +0x180 drapeaux, +0x198 zone
    # touchee. On y ecrit une flechette du Mk.2 dans la jambe (valeurs
    # relevees sur un vrai coup) : tous tombent, recrees compris (valide).
    ZONE_GEKKO_KNOCKOUT_HIT = ((0x174, 0x10008202), (0x180, 0x4802), (0x198, 0x100650))
    # Le sommeil passe avant le reste (un Gekko endormi ne tombe pas meme
    # jauges de tranquillisant a 0) : chaque action remet d'abord au maximum
    # la jauge de l'etat concurrent (objet de vie : +0x318 vie max, +0x320
    # endurance max, +0x328 sommeil max ; tranquillisant : mot courant puis
    # mot max).
    ZONE_GEKKO_MACHINE_OFFSET = 0xE910
    ZONE_GEKKO_HIT_STATE = 6
    ZONE_GEKKO_HIT_STATE_ENTER_RVA = 0x10637D0
    ZONE_HIT_STATE = 6
    ZONE_HIT_STATE_ENTER_RVA = 0xC7EF70
    # Mini Gekko (2026-10-14, valide en s04a10 : 35 detruits, 36 paralyses) :
    # hors du gestionnaire d'alerte. Leur gestionnaire : [mgs4+23F82DA0]
    # (remis a 0 par le jeu a sa destruction, 11EFD45 ; parcouru par
    # 11EF2E0) : +0x400 nombre de groupes, +0x00 tableau des groupes ; groupe
    # +0x510 premier mini Gekko (a la suite, pas de 0x1360), +0x518 nombre.
    # Mini Gekko : table de methodes 1902C58 (verifiee pour chacun) ; vie
    # +0x12DC, drapeaux +0x1308 (bits 0x2000087 : mort,
    # paralyse...). Leur mise a jour (11FCB30) lit leurs coups dans une liste
    # (+0xB80) ; appeler les degats (11FBE10) ou la reaction sans message dans
    # cette liste plante le jeu (1216CDC). Deux chemins sans message :
    #  - Tuer : bit 21 des drapeaux, "mort immediate" de la mise a jour elle-
    #    meme (vie a 0, 11DB320, comportement 11 ; la reaction ne lit alors
    #    aucun message) : une seule ecriture d'octet (+0x130A, bit 5) ;
    #  - Assommer : dernier coup (+0xC00) = 0x37 (flechette), puis
    #    comportement 11 = reaction a un coup (11EC150 sur le controleur
    #    +0x1000, qui remet d'abord le comportement en cours a zero) :
    #    paralysie (reaction 0x15), courte comme en jeu, sans lire la liste.
    #    Une seule fois par clic : relancee a chaque image, la paralysie
    #    plantait le jeu (2026-10-11, voir code_patches).
    # Pas de sommeil chez eux (reactions : sursaut, paralysie, mort).
    ZONE_MINI_GEKKO_MANAGER_RVA = 0x23F82DA0
    ZONE_MINI_GEKKO_STRIDE = 0x1360
    ZONE_MINI_GEKKO_VTABLE_RVA = 0x1902C58
    ZONE_MINI_GEKKO_LIFE = 0x12DC
    ZONE_MINI_GEKKO_FLAGS = 0x1308
    ZONE_MINI_GEKKO_DOWN_MASK = 0x2000087
    ZONE_MINI_GEKKO_KILL_BYTE = (0x130A, 0x20)
    ZONE_MINI_GEKKO_LAST_HIT = 0xC00
    ZONE_MINI_GEKKO_DART = 0x37
    ZONE_MINI_GEKKO_BEHAVIOUR = (0x1000, 0xB)
    ZONE_MINI_GEKKO_FUNCS = {
        "mg_behave": (0x11EC150, "48895c2408574883ec2081b92401"),
    }
    # Vehicules (2026-10-14, valide sur le Humvee de s01a57) : gestionnaire
    # [mgs4+23F810F0] (cree par FF7A60, mis a jour par FF1A80) : +0 tete de
    # liste, +8 nombre ; noeud : +0 vehicule, +8 suivant. Objet de vie
    # integre a vehicule+0x400 (comme les tanks) ; +0xA60 bit 4 = detruit.
    # FF7BA0 (traitement des coups du vehicule) : si un coup est en cours
    # (objet de vie +0x68 & 0x1E32FB7), FF9290 (degats) puis FF8830 decide
    # la destruction, lancee par B0FAC0 (0x66). FF8830 detruit un vehicule a
    # vie <= 0 si le coup en cours porte le bit 12 ("mise a mort", +0x10C ->
    # drapeaux B81C60 & 0x1800), quel que soit son type (le Humvee, type
    # 0x14, accepte aussi les coups 0x7F/0x3D). Le jeu efface le coup en
    # cours a chaque image : vie videe (B21FF0), coup en cours ecrit et FF7BA0
    # appelee dans un meme appel, par un petit code place dans le jeu.
    ZONE_VEHICLE_MANAGER_RVA = 0x23F810F0
    ZONE_VEHICLE_LIFE_OFFSET = 0x400
    ZONE_VEHICLE_DESTROYED = (0xA60, 0x10)
    ZONE_VEHICLE_KILL_HIT = 0x1000
    ZONE_VEHICLE_FUNCS = {
        "vehicle_hits": (0xFF7BA0, "40574883ec30488bf98b896c0a00008b"),
    }
    # Helicopteres (2026-10-14, valide sur un des deux de s01a57) : chacun est
    # une tache du jeu (creee par 13429E0) : +0x08 sa mise a jour (133FD00),
    # +0x20 tache suivante, dans la liste des taches en cours (tete fixe
    # mgs4+23D044D0, ~100 taches). Vie +0x1068 (max +0x106C). A chaque image,
    # 1352770 marque mort (+0x430 bit 2) un helicoptere a vie <= 0 et lance
    # sa chute : une seule ecriture (vie a 0).
    ZONE_TASK_LIST_RVA = 0x23D044D0
    ZONE_TASK_NEXT = 0x20
    ZONE_TASK_UPDATE = 0x08
    ZONE_HELICOPTER_UPDATE_RVA = 0x133FD00
    ZONE_HELICOPTER_LIFE = 0x1068
    ZONE_HELICOPTER_DEAD = (0x430, 0x4)
    ZONE_FUNCS = {
        "kill": (0xB21FF0, "4c63811803000033c048898168010000"),
        "knockout": (0xB800B0, "33c04c63ca48898168010000"),
        "sleep": (0xB80300, "33c04c63ca48898168010000"),
        "state_goto": (0xF61670, "48895c240848897c24104156"),
        "emotion_set": (0xB65930, "44894110e927feff"),
    }
    # Emotion -> (type, fonction qui remplit sa jauge et la declenche).
    ZONE_EMOTIONS = {
        "laugh": (1, 0xB64ED0),
        "cry": (2, 0xB64B80),
        "rage": (3, 0xB65180),
        "scream": (4, 0xB65260),
    }
    ZONE_EMOTION_SIG = "8b82d04300004c8bd9b90000"

    def _zone_kind(self, actor: int) -> str:
        """"gekko" ou "soldier" selon le type de l'acteur."""
        vtable = struct.unpack("<Q", self.proc.read_bytes(actor, 8))[0] - self.base
        return "gekko" if vtable == self.ZONE_GEKKO_VTABLE_RVA else "soldier"

    def _zone_soldiers(self) -> list[tuple[int, int, tuple[int, int, int]]]:
        """(acteur, objet de vie, (vie, endurance, sommeil)) des acteurs du
        gestionnaire d'alerte (soldats et machines) dont l'objet de vie est
        valide."""
        manager = self._alert_manager()
        out = []
        for soldier in self._alert_soldiers(manager) if manager else []:
            life_object = struct.unpack("<Q", self.proc.read_bytes(soldier + 0x42B0, 8))[0]
            if not life_object:
                continue
            vtable = struct.unpack("<Q", self.proc.read_bytes(life_object, 8))[0]
            if vtable - self.base != self.ZONE_LIFE_OBJECT_VTABLE_RVA:
                continue
            life, life_max, stamina, _, sleep = struct.unpack("<5i", self.proc.read_bytes(life_object + 0x314, 0x14))
            if life_max <= 1:
                continue  # civils, rats
            out.append((soldier, life_object, (life, stamina, sleep)))
        return out

    def _zone_mini_gekkos(self) -> list[int]:
        """Mini Gekko debout (vivants, ni paralyses ni deja a terre) de la
        zone, lus dans leur gestionnaire."""
        manager = struct.unpack("<Q", self.proc.read_bytes(self.base + self.ZONE_MINI_GEKKO_MANAGER_RVA, 8))[0]
        if not manager:
            return []
        groups = struct.unpack("<i", self.proc.read_bytes(manager + 0x400, 4))[0]
        out = []
        for group in struct.unpack(f"<{min(max(groups, 0), 0x80)}Q", self.proc.read_bytes(manager, 8 * min(max(groups, 0), 0x80))):
            if not group:
                continue
            first, count = struct.unpack("<Qi", self.proc.read_bytes(group + 0x510, 12))
            for index in range(min(max(count, 0), 0x40) if first else 0):
                mini_gekko = first + index * self.ZONE_MINI_GEKKO_STRIDE
                head = self.proc.read_bytes(mini_gekko, self.ZONE_MINI_GEKKO_FLAGS + 8)
                if struct.unpack_from("<Q", head, 0)[0] - self.base != self.ZONE_MINI_GEKKO_VTABLE_RVA:
                    continue
                life = struct.unpack_from("<i", head, self.ZONE_MINI_GEKKO_LIFE)[0]
                flags = struct.unpack_from("<Q", head, self.ZONE_MINI_GEKKO_FLAGS)[0]
                if life > 0 and not flags & self.ZONE_MINI_GEKKO_DOWN_MASK:
                    out.append(mini_gekko)
        return out

    def _zone_mini_gekko_apply(self, action: str, funcs: dict[str, int], mini_gekko: int) -> bool | None:
        """Tuer ou Assommer un mini Gekko ; False si l'appel au jeu a echoue."""
        flags = struct.unpack("<Q", self.proc.read_bytes(mini_gekko + self.ZONE_MINI_GEKKO_FLAGS, 8))[0]
        vtable = struct.unpack("<Q", self.proc.read_bytes(mini_gekko, 8))[0]
        if vtable - self.base != self.ZONE_MINI_GEKKO_VTABLE_RVA or flags & self.ZONE_MINI_GEKKO_DOWN_MASK:
            return None  # detruit ou a terre depuis le parcours
        if action == "kill":
            offset, bit = self.ZONE_MINI_GEKKO_KILL_BYTE
            byte = self.proc.read_bytes(mini_gekko + offset, 1)[0]
            self.proc.write_bytes(mini_gekko + offset, bytes([byte | bit]))
            return None
        self.proc.write_bytes(mini_gekko + self.ZONE_MINI_GEKKO_LAST_HIT, struct.pack("<I", self.ZONE_MINI_GEKKO_DART))
        controller, behaviour = self.ZONE_MINI_GEKKO_BEHAVIOUR
        return False if self.speed.game_call(funcs["mg_behave"], mini_gekko + controller, behaviour) is None else None

    def _zone_vehicles(self) -> list[int]:
        """Vehicules intacts de la zone, lus dans leur gestionnaire."""
        manager = struct.unpack("<Q", self.proc.read_bytes(self.base + self.ZONE_VEHICLE_MANAGER_RVA, 8))[0]
        if not manager:
            return []
        node, count = struct.unpack("<Qi", self.proc.read_bytes(manager, 12))
        out = []
        for _ in range(min(max(count, 0), 0x40)):
            if not node:
                break
            vehicle, following = struct.unpack("<QQ", self.proc.read_bytes(node, 16))
            node = following
            if vehicle and self._zone_vehicle_intact(vehicle):
                out.append(vehicle)
        return out

    def _zone_vehicle_intact(self, vehicle: int) -> bool:
        life_object = vehicle + self.ZONE_VEHICLE_LIFE_OFFSET
        if struct.unpack("<Q", self.proc.read_bytes(life_object, 8))[0] - self.base != self.ZONE_LIFE_OBJECT_VTABLE_RVA:
            return False
        offset, bit = self.ZONE_VEHICLE_DESTROYED
        life = struct.unpack("<i", self.proc.read_bytes(life_object + 0x314, 4))[0]
        return life > 0 and not struct.unpack("<I", self.proc.read_bytes(vehicle + offset, 4))[0] & bit

    def _zone_vehicle_stub(self, funcs: dict[str, int]) -> int:
        """Petit code place dans le jeu (un par processus) : vie videe, coup
        en cours "mise a mort", puis traitement des coups du vehicule, dans
        le meme appel (le jeu efface le coup en cours a chaque image)."""
        if getattr(self, "_zone_stub_pid", None) != self.pid:
            stub = kernel32.VirtualAllocEx(self.proc.handle, None, 0x1000, MEM_COMMIT | 0x2000, PAGE_EXECUTE_READWRITE)
            self._zone_stub_addr = stub or 0
            self._zone_stub_pid = self.pid if stub else None
        if not self._zone_stub_addr:
            return 0
        life, hit_flags, pending = (self.ZONE_VEHICLE_LIFE_OFFSET, self.ZONE_VEHICLE_LIFE_OFFSET + 0x10C,
                                    self.ZONE_VEHICLE_LIFE_OFFSET + 0x68)
        code = (bytes.fromhex("534883ec204889cb")                                 # push rbx ; sub rsp,20 ; mov rbx,rcx
                + bytes.fromhex("488d8b") + struct.pack("<I", life)                # lea rcx,[rbx+vie]
                + bytes.fromhex("ba") + struct.pack("<I", self.ZONE_FULL)          # mov edx,7FFFFFFF
                + bytes.fromhex("48b8") + struct.pack("<Q", funcs["kill"]) + bytes.fromhex("ffd0")  # call B21FF0
                + bytes.fromhex("c783") + struct.pack("<II", hit_flags, self.ZONE_VEHICLE_KILL_HIT)  # mov dword [rbx+10C],1000
                + bytes.fromhex("838b") + struct.pack("<I", pending) + bytes.fromhex("01")  # or dword [rbx+68],1
                + bytes.fromhex("4889d948b8") + struct.pack("<Q", funcs["vehicle_hits"]) + bytes.fromhex("ffd0")  # call FF7BA0
                + bytes.fromhex("4883c4205bc3"))                                    # add rsp,20 ; pop rbx ; ret
        self.proc.write_bytes(self._zone_stub_addr, code)
        return self._zone_stub_addr

    def _zone_vehicle_kill(self, funcs: dict[str, int], vehicle: int) -> bool | None:
        """Detruit un vehicule ; False si l'appel au jeu a echoue."""
        if not self._zone_vehicle_intact(vehicle):
            return None  # detruit depuis
        stub = self._zone_vehicle_stub(funcs)
        if not stub:
            return None
        return False if self.speed.game_call(stub, vehicle) is None else None

    def _zone_helicopters(self) -> list[int]:
        """Helicopteres en vol de la zone, trouves dans la liste des taches
        du jeu par leur fonction de mise a jour."""
        head = self.base + self.ZONE_TASK_LIST_RVA
        update = self.base + self.ZONE_HELICOPTER_UPDATE_RVA
        offset, bit = self.ZONE_HELICOPTER_DEAD
        out = []
        task = struct.unpack("<Q", self.proc.read_bytes(head + self.ZONE_TASK_NEXT, 8))[0]
        for _ in range(0x1000):
            if not task or task == head:
                break
            if struct.unpack("<Q", self.proc.read_bytes(task + self.ZONE_TASK_UPDATE, 8))[0] == update:
                life = struct.unpack("<i", self.proc.read_bytes(task + self.ZONE_HELICOPTER_LIFE, 4))[0]
                if life > 0 and not struct.unpack("<Q", self.proc.read_bytes(task + offset, 8))[0] & bit:
                    out.append(task)
            task = struct.unpack("<Q", self.proc.read_bytes(task + self.ZONE_TASK_NEXT, 8))[0]
        return out

    def _zone_helicopter_kill(self, helicopter: int) -> None:
        if struct.unpack("<Q", self.proc.read_bytes(helicopter + self.ZONE_TASK_UPDATE, 8))[0] - self.base == self.ZONE_HELICOPTER_UPDATE_RVA:
            self.proc.write_bytes(helicopter + self.ZONE_HELICOPTER_LIFE, struct.pack("<i", 0))

    def _zone_hit_state(self, actor: int) -> tuple[int, int]:
        """(machine a etats, numero de l'etat "touche") de l'acteur si tout a
        la forme attendue (machine qui renvoie a l'acteur, etat "touche" avec
        la bonne entree), (0, 0) sinon."""
        if self._zone_kind(actor) == "gekko":
            offset, index, enter_rva = (self.ZONE_GEKKO_MACHINE_OFFSET, self.ZONE_GEKKO_HIT_STATE,
                                        self.ZONE_GEKKO_HIT_STATE_ENTER_RVA)
        else:
            offset, index, enter_rva = 0xE7D0, self.ZONE_HIT_STATE, self.ZONE_HIT_STATE_ENTER_RVA
        machine = struct.unpack("<Q", self.proc.read_bytes(actor + offset, 8))[0]
        if not machine or struct.unpack("<Q", self.proc.read_bytes(machine + 0x50, 8))[0] != actor:
            return 0, 0
        states = struct.unpack("<Q", self.proc.read_bytes(machine + 0x20, 8))[0]
        state = struct.unpack("<Q", self.proc.read_bytes(states + index * 8, 8))[0]
        if not state:
            return 0, 0
        vtable = struct.unpack("<Q", self.proc.read_bytes(state, 8))[0]
        enter = struct.unpack("<Q", self.proc.read_bytes(vtable + 8, 8))[0]
        return (machine, index) if enter - self.base == enter_rva else (0, 0)

    def _zone_camp_matches(self, soldier: int, target: str) -> bool:
        if target == "all":
            return True
        if self._zone_kind(soldier) != "soldier":
            return target == "enemies"
        camp = struct.unpack("<Q", self.proc.read_bytes(soldier + 0x43D0, 8))[0] >> 56
        return (camp == self.ZONE_REBEL_CAMP) == (target == "rebels")

    def maintain_rebel_attitude(self, attitude: str) -> None:
        """Maintient l'affinite des unites rebelles de la zone ("neutral" ou
        "hostile", voir ZONE_REBEL_AFFINITY) ; a rappeler regulierement (les
        unites changent avec la zone)."""
        wanted = struct.pack("<i", self.ZONE_REBEL_AFFINITY[attitude])
        units = set()
        for soldier, _, _ in self._zone_soldiers():
            if self._zone_kind(soldier) == "soldier" and self._zone_camp_matches(soldier, "rebels"):
                units.add(struct.unpack("<Q", self.proc.read_bytes(soldier + 0x4578, 8))[0])
        for unit in units:
            if not unit or struct.unpack("<Q", self.proc.read_bytes(unit, 8))[0] - self.base != self.ZONE_UNIT_VTABLE_RVA:
                continue
            if self.proc.read_bytes(unit + 0x918, 4) != wanted:
                self.proc.write_bytes(unit + 0x918, wanted)

    def _zone_eligible(self, action: str, actor: int, gauges: tuple[int, int, int]) -> bool:
        """Cibles d'une action, quel que soit l'etat en cours (un endormi peut
        etre tue) : vivante pour Tuer, pas deja dans l'etat vise pour
        Endormir/Assommer, eveillee pour les emotions (soldats seulement)."""
        life, stamina, sleep = gauges
        if life <= 0:
            return False
        if action == "kill":
            return True
        if self._zone_kind(actor) == "gekko":
            if action == "knockout":
                life_object = struct.unpack("<Q", self.proc.read_bytes(actor + 0x42B0, 8))[0]
                return struct.unpack("<H", self.proc.read_bytes(life_object + self.ZONE_GEKKO_TRANQ_OFFSETS[0], 2))[0] > 0
            return action == "sleep" and sleep > 0
        if action == "sleep":
            return sleep > 0
        if action == "knockout":
            return stamina > 0
        return stamina > 0 and sleep > 0

    def zone_action(self, action: str, target: str = "enemies") -> bool:
        """"kill", "knockout", "sleep" ou une cle de ZONE_EMOTIONS, sur les
        soldats eveilles de la zone du camp `target` (ZONE_TARGETS), dans un
        fil separe. Faux si impossible (DLL absente, aucun soldat, action
        deja en cours)."""
        if not (self.connected and self.sane and self.speed.main_loop_hook_installed()):
            return False
        if getattr(self, "_zone_busy", False):
            return False
        specs = dict(self.ZONE_FUNCS)
        if action in self.ZONE_EMOTIONS:
            specs["emotion_apply"] = (self.ZONE_EMOTIONS[action][1], self.ZONE_EMOTION_SIG)
        machines = action in ("kill", "knockout") and target != "rebels"
        try:
            funcs = self._live_funcs(specs)
            mg_funcs = self._live_funcs(self.ZONE_MINI_GEKKO_FUNCS) if machines else None
            vehicle_funcs = self._live_funcs(self.ZONE_VEHICLE_FUNCS) if machines and action == "kill" else None
            targets = [(s, lo) for s, lo, gauges in self._zone_soldiers()
                       if self._zone_eligible(action, s, gauges) and self._zone_camp_matches(s, target)]
            mini_gekkos = self._zone_mini_gekkos() if mg_funcs else []
            vehicles = self._zone_vehicles() if vehicle_funcs and funcs else []
            helicopters = self._zone_helicopters() if machines and action == "kill" else []
        except OSError:
            return False
        if funcs is None or not (targets or mini_gekkos or vehicles or helicopters):
            return False
        if vehicles:
            funcs = {**funcs, **vehicle_funcs}
        if mini_gekkos:
            funcs = {**funcs, **mg_funcs}
        self._zone_busy = True
        threading.Thread(target=self._zone_run, args=(action, funcs, targets, mini_gekkos, vehicles, helicopters),
                         daemon=True).start()
        return True

    def _zone_run(self, action: str, funcs: dict[str, int], targets: list[tuple[int, int]],
                  mini_gekkos: list[int], vehicles: list[int], helicopters: list[int]) -> None:
        jobs = ([(self._zone_apply, (action, funcs, soldier, life_object)) for soldier, life_object in targets]
                + [(self._zone_mini_gekko_apply, (action, funcs, mini_gekko)) for mini_gekko in mini_gekkos]
                + [(self._zone_vehicle_kill, (funcs, vehicle)) for vehicle in vehicles]
                + [(self._zone_helicopter_kill, (helicopter,)) for helicopter in helicopters])
        try:
            for apply, args in jobs:
                try:
                    if apply(*args) is False:
                        return  # jeu en pause ou DLL absente
                except OSError:
                    continue  # acteur disparu ou inattendu : on passe au suivant
        finally:
            self._zone_busy = False

    def _zone_restore(self, life_object: int, offset: int, max_offset: int) -> None:
        """Remet une jauge de l'objet de vie a son maximum si elle est en
        dessous (fin d'un sommeil ou d'un K.O. en cours)."""
        current, maximum = (struct.unpack("<i", self.proc.read_bytes(life_object + o, 4))[0] for o in (offset, max_offset))
        if 0 < maximum and current < maximum:
            self.proc.write_bytes(life_object + offset, struct.pack("<i", maximum))

    def _zone_apply(self, action: str, funcs: dict[str, int], soldier: int, life_object: int) -> bool | None:
        """Une action sur un acteur ; False si l'appel au jeu a echoue."""
        call = self.speed.game_call
        kind = self._zone_kind(soldier)
        if action == "knockout":
            self._zone_restore(life_object, 0x324, 0x328)  # reveille d'abord
        elif action == "sleep":
            if kind == "gekko":
                for offset in self.ZONE_GEKKO_TRANQ_OFFSETS:
                    self.proc.write_bytes(life_object + offset, self.proc.read_bytes(life_object + offset + 2, 2))
            else:
                self._zone_restore(life_object, 0x31C, 0x320)
        if kind == "gekko" and action in ("sleep", "knockout"):
            action = "gekko_" + action
        if action in ("kill", "knockout", "gekko_sleep", "gekko_knockout"):
            machine, state = self._zone_hit_state(soldier)
            if not machine:
                return None
            if action == "gekko_knockout":
                for offset, value in self.ZONE_GEKKO_KNOCKOUT_HIT:
                    self.proc.write_bytes(life_object + offset, struct.pack("<I", value))
                for offset in self.ZONE_GEKKO_TRANQ_OFFSETS:
                    self.proc.write_bytes(life_object + offset, struct.pack("<H", 0))
            elif call(funcs["sleep" if action == "gekko_sleep" else action], life_object, self.ZONE_FULL) is None:
                return False
            call(funcs["state_goto"], machine, state)
            return None
        if kind != "soldier":
            return None
        if action == "sleep":
            return False if call(funcs["sleep"], life_object, self.ZONE_FULL) is None else None
        flags = struct.unpack("<Q", self.proc.read_bytes(soldier + 0x43D0, 8))[0]
        self.proc.write_bytes(soldier + 0x43D0, struct.pack("<Q", flags & ~0x80000000))
        request = struct.unpack("<I", self.proc.read_bytes(soldier + 0x4590, 4))[0]
        self.proc.write_bytes(soldier + 0x4590, struct.pack("<I", request | 0x400))
        if call(funcs["emotion_set"], soldier + 0x4538, soldier, self.ZONE_EMOTIONS[action][0]) is None:
            return False
        call(funcs["emotion_apply"], soldier + 0x4538, soldier, self.ZONE_FULL)
        return None
