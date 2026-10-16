"""MGS4Live : position de Snake, jauges du joueur et des vehicules, vitals."""
import struct
import threading
import time

from mgs4trainer.core.gamedata import VITALS


class PlayerMixin:
    """Position de Snake, jauges du joueur et des vehicules, vitals."""

    # Position de Snake (2026-10-04) : entree joueur de la table des
    # joueurs du jeu (8DA180 : mgs4+23EB5160 + (indice+1)*0x80, indice a
    # mgs4+23EB5150), objet a +8, X/Y/Z (Y = hauteur) a +0x10 - la position
    # que le jeu utilise lui-meme (lumiere de l'indice de camouflage, 8A5C0).
    # Ecrire la deplace reellement (valide en jeu). Remplace le pointeur
    # capture par la DLL (install_coord_tracker_hook, routine de distance
    # appelee seulement dans certaines situations) qui restait sur l'ancien
    # Snake apres un changement d'acte (position a 0 au debut de l'acte 2).
    PLAYER_INDEX_RVA = 0x23EB5150
    PLAYER_TABLE_RVA = 0x23EB5160
    PLAYER_ENTRY_SIZE = 0x80

    def _player_transform(self) -> int | None:
        index = struct.unpack("<i", self.proc.read_bytes(self.base + self.PLAYER_INDEX_RVA, 4))[0]
        entry = self.base + self.PLAYER_TABLE_RVA + (index + 1) * self.PLAYER_ENTRY_SIZE
        transform = struct.unpack("<Q", self.proc.read_bytes(entry + 8, 8))[0]
        return transform or None

    def player_position(self) -> tuple[float, float, float] | None:
        """Position (X, Y, Z, floats) de Snake ; Y = hauteur (le jeu
        annule une position invalide sous le sol), X/Z le plan horizontal
        en coordonnees absolues."""
        if not (self.connected and self.sane):
            return None
        addr = self._player_transform()
        if not addr:
            return None
        return struct.unpack("<fff", self.proc.read_bytes(addr + 0x10, 12))

    def set_player_position(self, x: float, y: float, z: float) -> bool:
        if not (self.connected and self.sane):
            return False
        addr = self._player_transform()
        if not addr:
            return False
        self.proc.write_bytes(addr + 0x10, struct.pack("<fff", x, y, z))
        return True

    # Jauge de grip (2026-10-04) : composant du joueur (acteur joueur = 6
    # octets bas de [entree joueur], cf. _player_transform ; composant a
    # acteur+0x110, type reconnu a sa table de fonctions mgs4+18AF720).
    # Jauge = int32 a +0x1E8, valable si le bit 0 de +0x1F8 est actif
    # (suspendu) - c'est ce que renvoie au HUD le gestionnaire du message
    # 0x2D0011 (9776DC). Le HUD n'en garde qu'une copie (tache joueur
    # +0x86C) : l'ecrire n'avait aucun effet. Ecrire +0x1E8 tient la barre
    # pleine (valide en jeu). Elle part de 2000 et baisse plus ou moins
    # vite selon le stress.
    # Le meme composant porte l'oxygene (2026-10-04) : int32 a +0x1EC,
    # active par le bit 0x4 de +0x1F8 (message 0x2D0012, celui que le HUD
    # consulte en premier) ; baisse d'environ 90/s sous l'eau. Troisieme
    # jauge du meme modele (+0x1F0, bit 0x10, message 0x2D0013) non
    # identifiee.
    GRIP_COMPONENT_OFFSET = 0x110
    GRIP_COMPONENT_VTABLE_RVA = 0x18AF720
    PLAYER_GAUGE_STATE_OFFSET = 0x1F8
    PLAYER_GAUGES = {"grip": (0x1E8, 0x1), "oxygen": (0x1EC, 0x4)}

    def _grip_component(self) -> int | None:
        index = struct.unpack("<i", self.proc.read_bytes(self.base + self.PLAYER_INDEX_RVA, 4))[0]
        entry = self.base + self.PLAYER_TABLE_RVA + (index + 1) * self.PLAYER_ENTRY_SIZE
        actor = struct.unpack("<Q", self.proc.read_bytes(entry, 8))[0] & 0xFFFFFFFFFFFF
        if not actor:
            return None
        component = struct.unpack("<Q", self.proc.read_bytes(actor + self.GRIP_COMPONENT_OFFSET, 8))[0]
        if not component:
            return None
        vtable = struct.unpack("<Q", self.proc.read_bytes(component, 8))[0]
        return component if vtable == self.base + self.GRIP_COMPONENT_VTABLE_RVA else None

    # Vehicule du joueur (2026-10-10, valide en jeu) : case dediee
    # mgs4+23F81090 -> composant ; vie int32 a composant+0x128, max +0x12C.
    # Drebin 893 (acte 2, vtable mgs4+18EB690, 6500, rappel de collision
    # 102F250) et van de l'acte 3 (vtable mgs4+18EB748, 6000). La jauge du
    # HUD n'en est qu'une copie (10302C5 -> 14D4020).
    VEHICLE_PTR_RVA = 0x23F81090
    VEHICLE_COMPONENT_VTABLE_RVAS = {"drebin": 0x18EB690, "van": 0x18EB748}
    VEHICLE_HP_OFFSET = 0x128

    def _vehicle_component(self, gauge: str) -> int | None:
        """Composant du vehicule `gauge` ("drebin", "van") s'il est actif."""
        component = struct.unpack("<Q", self.proc.read_bytes(self.base + self.VEHICLE_PTR_RVA, 8))[0]
        if not component:
            return None
        vtable = struct.unpack("<Q", self.proc.read_bytes(component, 8))[0]
        return component if vtable == self.base + self.VEHICLE_COMPONENT_VTABLE_RVAS[gauge] else None

    # Allies (2026-10-16, combat contre Screaming Mantis, Meryl et Johnny
    # presents) : objet de vie comme les soldats (vtable mgs4+18BC1B0 : vie
    # +0x314, max +0x318, endurance +0x31C, max +0x320, sommeil +0x324), a
    # acteur+0x42B0 et +0x1E8, et l'objet pointe son acteur a +0x8. Reconnus
    # par leur classe d'acteur et acteur+0xC08 (stable endormi comme eveille,
    # sans doute un hache de modele) ; les deux changent selon l'acte, d'ou
    # une signature par acte, chacune confirmee en jeu (soin par le trainer
    # visible a l'ecran) :
    # - Meryl, acte 5 : classe 190EF18, 0xF13930 (vie 2000). Sa classe compte
    #   aussi 6 places d'equipe inactives (0x7137F2, place acteur+0x43D0 de 0
    #   a 5 ; Meryl 6). Acte 1 : classe 18E65C8, meme 0xF13930 (vie 30000).
    # - Johnny, acte 5 : classe 18E4FA8, 0x86A795 (vie 1000 ; endormi,
    #   sommeil -90000). Acte 1 : meme classe, 0xC13869 (vie 30000). Dans la
    #   liste du gestionnaire d'alerte, comme les soldats.
    # - Acte 1, deux autres membres du Rat Patrol (Ed et Jonathan ?, vie
    #   30000) : classes 18E5870 (0xF1379E) et 18E5EF8 (0x213715), non suivis.
    # Pieges : acteur+0x68 (et la fiche +0x40) est un etat (0x1C endormie, 1
    # eveillee), pas un numero de personnage ; le "Rat01" du Solid Eye est le
    # nom de l'unite ; le hache de l'objet de script [+0x38]-0x10 change a
    # chaque rechargement ; une place inactive de la classe de Meryl a eu sa
    # jauge a 0 au moment ou Johnny dormait (fausse piste, 1re version).
    # Aucun pointeur fixe vers eux : on cherche les objets dans l'allocation
    # du tas des acteurs (celle de l'acteur de Snake, ~360 Mo, ~1 s) dans un
    # fil a part, puis on garde les adresses tant qu'elles restent valides.
    # ALLIES : nom -> signatures (classe, +0xC08). ALLY_DEATH_CLASSES :
    # classes dont la mort par appels directs (ci-dessous) est connue ; voir
    # aussi ALLY_HIT_STATES.
    ALLIES = {
        "meryl": {(0x190EF18, 0xF13930), (0x18E65C8, 0xF13930)},
        "johnny": {(0x18E4FA8, 0x86A795), (0x18E4FA8, 0xC13869)},
    }
    ALLY_ID_OFFSET = 0xC08
    ALLY_DEATH_CLASSES = {0x190EF18}
    ALLY_GAUGES = {"meryl": ("meryl", 0x314), "meryl_stamina": ("meryl", 0x31C),
                   "johnny": ("johnny", 0x314), "johnny_stamina": ("johnny", 0x31C)}
    ALLY_SCAN_INTERVAL = 3.0
    # Vie a 0 seule ne tue pas (2026-10-16) : le jeu ne verifie la vie
    # qu'au moment d'un coup (14B0130, ecriture 14B038D). Si vie <= 0 :
    # endurance 0 (sauf acteur+0x43D4 == 1, "important", cas de Meryl), puis
    # 144A020(acteur) (previent un gestionnaire si +0x43DC), 144A5A0(acteur)
    # (mort : +0x43D8 = 2, message 0x44000E si +0x43D4 == 1, animation) et
    # 149C0F0(acteur) (cri, voix 0x197C si +0x43D4 == 1), puis des compteurs
    # de stats (non reproduits). On rejoue le meme chemin.
    ALLY_DEATH_FUNCS = {
        "notify": (0x144A020, "4883ec2883b9dc4300000074"),
        "die": (0x144A5A0, "40534883ec20c781d8430000"),
        "cry": (0x149C0F0, "4883ec3883b9d44300000175"),
    }
    ALLY_DEAD_STATE = (0x43D8, 2)
    ALLY_IMPORTANT = (0x43D4, 1)

    # Allie invulnerable (2026-10-16), ses deux jauges verrouillees : on
    # detourne l'entree de la fonction des coups de sa classe vers un petit
    # code qui sort sans degats si l'acteur touche est l'un de ceux ecrits en
    # tete du code (ALLY_GUARD_SLOTS places, 0 = libre), sinon refait les
    # octets remplaces et revient. Fonctions partagees avec les autres acteurs
    # de la classe : seuls les acteurs designes sont concernes.
    # - Classe de Meryl (190EF18) : 14AFB10, acteur dans rsi. Son test
    #   d'invulnerabilite (14AFBC1 : mov edx,0x100000 ; call 144A8E0 = test
    #   [acteur+0x4408] ; jne 14B05B5 = sortie sans degats) : poser ce bit de
    #   l'exterieur ne tient pas (le jeu recalcule +0x4408), on detourne le
    #   "mov edx" (5 octets) et on sort par 14B05B5.
    # - Classe de Johnny (18E4FA8) : fonction des coups des soldats C52190
    #   (acteur dans rdx, objet de vie r8 ; ecriture de la vie C5244D, trouvee
    #   par point d'arret materiel). Pas de test d'invulnerabilite : on
    #   detourne le premier "mov [rsp+8],rbx" (5 octets) et on sort par un
    #   ret (aucun appelant n'utilise la valeur de retour). Les sites de
    #   "Un coup, un mort" (C5223E, C523C3) sont plus loin, sans chevauchement.
    # Chaque garde : magie a +0x20 (la retrouver apres un redemarrage du
    # trainer), code a +0x30. ALLY_GUARDS : nom -> (site, octets d'origine
    # verifies, cmp reg,[rip+x] (3 octets), sortie (rva) ou None = ret,
    # magie, classes).
    ALLY_GUARD_SLOTS = 4
    ALLY_GUARD_CODE = 0x30
    ALLY_GUARDS = {
        "ally_class": (0x14AFBC1, bytes.fromhex("ba00001000488bcee812adf9ff85c00f85df090000"),
                       bytes.fromhex("483b35"), 0x14B05B5, b"MGS4ALLY", {0x190EF18}),
        "soldier_class": (0xC52190, bytes.fromhex("48895c240848896c241848897424205741544155"),
                          bytes.fromhex("483b15"), None, b"MGS4SOLD", {0x18E4FA8, 0x18E65C8}),
    }
    # Premiere version de la garde de Meryl (une place a +0, magie a +8, code
    # a +0x10) : retiree et remplacee si on la retrouve dans le jeu.
    ALLY_GUARD_LEGACY = (8, b"MGS4MRYL", 0x10)

    def _ally_guard(self, name: str, install: bool) -> int:
        """Adresse de la garde `name` (posee une fois par processus si
        `install`, retrouvee apres un redemarrage du trainer), 0 sinon."""
        rva, original, compare, exit_rva, magic, _classes = self.ALLY_GUARDS[name]
        site = self.base + rva
        cache = getattr(self, "_ally_guard_cache", {})
        if cache.get(name, (0, None))[1] == self.pid:
            return cache[name][0]
        current = self.proc.read_bytes(site, len(original))
        if current[0] == 0xE9 and current[5:] == original[5:]:
            target = site + 5 + struct.unpack("<i", current[1:5])[0]
            magic_at, legacy_magic, legacy_code = self.ALLY_GUARD_LEGACY
            try:
                if self.proc.read_bytes(target - self.ALLY_GUARD_CODE + 0x20, 8) == magic:
                    guard = target - self.ALLY_GUARD_CODE
                elif self.proc.read_bytes(target - legacy_code + magic_at, 8) == legacy_magic:
                    self.proc.write_bytes(site, original[:5])
                    return self._ally_guard(name, install)
                else:
                    return 0
            except OSError:
                return 0
        elif current == original and install:
            guard = self.proc.alloc_near(site)
            if not guard:
                return 0
            code_start = guard + self.ALLY_GUARD_CODE

            def rel(source_end: int, destination: int) -> bytes:
                return struct.pack("<i", destination - source_end)
            exit_stub = code_start + self.ALLY_GUARD_SLOTS * 13 + 10
            code = bytearray()
            for slot in range(self.ALLY_GUARD_SLOTS):
                code += compare + rel(code_start + len(code) + 7, guard + 8 * slot)  # cmp reg,[place]
                code += bytes.fromhex("0f84") + rel(code_start + len(code) + 6, exit_stub)  # je sortie
            code += original[:5] + b"\xe9" + rel(code_start + len(code) + 10, site + 5)  # octets remplaces ; jmp
            if exit_rva is None:
                code += b"\xc3"                                                      # sortie : ret
            else:
                code += b"\xe9" + rel(code_start + len(code) + 5, self.base + exit_rva)  # sortie : jmp
            self.proc.write_bytes(guard, bytes(8 * self.ALLY_GUARD_SLOTS) + magic
                                  + bytes(self.ALLY_GUARD_CODE - 0x28) + bytes(code))
            self.proc.write_bytes(site, b"\xe9" + rel(site + 5, code_start))
        else:
            return 0
        cache[name] = (guard, self.pid)
        self._ally_guard_cache = cache
        return guard

    def set_allies_invulnerable(self, allies: set[str]) -> bool:
        """Le jeu ignore les coups portes aux allies `allies` (aucune
        ecriture de leurs jauges) ; a reappeler a chaque rafraichissement
        (ils sont recrees a chaque chargement de zone)."""
        if not (self.connected and self.sane):
            return False
        ok = True
        for guard_name, (*_spec, classes) in self.ALLY_GUARDS.items():
            actors = []
            for name in sorted(allies):
                life = self._ally_life_object(name)
                if not life:
                    continue
                actor = struct.unpack("<Q", self.proc.read_bytes(life + 8, 8))[0]
                if struct.unpack("<Q", self.proc.read_bytes(actor, 8))[0] - self.base in classes:
                    actors.append(actor)
            actors = actors[:self.ALLY_GUARD_SLOTS]
            guard = self._ally_guard(guard_name, install=bool(actors))
            if not guard:
                ok = ok and not actors
                continue
            wanted = struct.pack(f"<{self.ALLY_GUARD_SLOTS}Q", *actors, *[0] * (self.ALLY_GUARD_SLOTS - len(actors)))
            if self.proc.read_bytes(guard, len(wanted)) != wanted:
                self.proc.write_bytes(guard, wanted)
        return ok

    # Classes de l'acte 1 (Johnny 18E4FA8, Meryl 18E65C8 ; 2026-10-16) :
    # vie ou endurance a 0 seule n'a pas d'effet avant un coup. Comme les
    # soldats ("Toute la zone"), c'est leur machine a etats qui juge : etat 6
    # "touche" (entree EB13F0 = entree des soldats C7EF70, qui evalue vie /
    # endurance / sommeil par C7D1F0 et enchaine mort, K.O. ou sommeil, puis
    # E98D00 s'il est encore en vie), machine a acteur+0xE8D0 (soldats
    # +0xE7D0 ; +0x50 = acteur, etats +0x20). Les tests "encore actif ?"
    # EAE7C0 / EC25A0 (lus a chaque image) ne declenchent rien. Le chemin
    # "endurance vide" de la fonction des coups (B84AB0 = endurance remise
    # au max, puis [vtable+0x370] = B4D960, vide) ne sert pas.
    # ALLY_HIT_STATES : classe -> (machine, etat, entree attendue).
    ALLY_HIT_STATES = {0x18E4FA8: (0xE8D0, 6, 0xEB13F0), 0x18E65C8: (0xE8D0, 6, 0xEB13F0)}

    def _ally_hit_state(self, actor: int, klass: int) -> tuple[int, int]:
        """(machine, etat "touche") si tout a la forme attendue, (0, 0) sinon."""
        offset, index, enter_rva = self.ALLY_HIT_STATES[klass]
        machine = struct.unpack("<Q", self.proc.read_bytes(actor + offset, 8))[0]
        if not machine or struct.unpack("<Q", self.proc.read_bytes(machine + 0x50, 8))[0] != actor:
            return 0, 0
        states = struct.unpack("<Q", self.proc.read_bytes(machine + 0x20, 8))[0]
        state = struct.unpack("<Q", self.proc.read_bytes(states + index * 8, 8))[0]
        if not state:
            return 0, 0
        enter = struct.unpack("<Q", self.proc.read_bytes(struct.unpack("<Q", self.proc.read_bytes(state, 8))[0] + 8, 8))[0]
        return (machine, index) if enter - self.base == enter_rva else (0, 0)

    def _ally_react(self, life: int, offset: int) -> None:
        """Jauge `offset` d'un allie mise a 0 ou moins par le trainer : le
        jeu en tire les consequences comme apres un coup (fil a part : les
        appels au jeu passent une image a la fois)."""
        if getattr(self, "_ally_reacting", False) or not self.speed.main_loop_hook_installed():
            return
        actor = struct.unpack("<Q", self.proc.read_bytes(life + 8, 8))[0]
        klass = struct.unpack("<Q", self.proc.read_bytes(actor, 8))[0] - self.base
        if klass in self.ALLY_HIT_STATES:
            machine, state = self._ally_hit_state(actor, klass)
            funcs = self._live_funcs({"state_goto": self.ZONE_FUNCS["state_goto"]}) if machine else None
            if funcs is None:
                return
            calls = [(funcs["state_goto"], machine, state)]
        elif klass in self.ALLY_DEATH_CLASSES and offset == 0x314:
            dead_offset, dead = self.ALLY_DEAD_STATE
            if struct.unpack("<i", self.proc.read_bytes(actor + dead_offset, 4))[0] == dead:
                return
            funcs = self._live_funcs(self.ALLY_DEATH_FUNCS)
            if funcs is None:
                return
            important_offset, important = self.ALLY_IMPORTANT
            if struct.unpack("<i", self.proc.read_bytes(actor + important_offset, 4))[0] != important:
                self.proc.write_bytes(life + 0x31C, struct.pack("<i", 0))
            calls = [(funcs[name], actor) for name in ("notify", "die", "cry")]
        else:
            return
        self._ally_reacting = True

        def run():
            try:
                for function, *args in calls:
                    if self.speed.game_call(function, *args) is None:
                        break
            finally:
                self._ally_reacting = False
        threading.Thread(target=run, daemon=True).start()

    def _ally_life_valid(self, name: str, life: int) -> bool:
        try:
            vtable, actor = struct.unpack("<QQ", self.proc.read_bytes(life, 16))
            if vtable != self.base + self.ZONE_LIFE_OBJECT_VTABLE_RVA or not actor:
                return False
            klass = struct.unpack("<Q", self.proc.read_bytes(actor, 8))[0] - self.base
            kind = struct.unpack("<I", self.proc.read_bytes(actor + self.ALLY_ID_OFFSET, 4))[0]
            back = struct.unpack("<Q", self.proc.read_bytes(actor + 0x1E8, 8))[0]
        except OSError:
            return False
        return (klass, kind) in self.ALLIES[name] and back == life

    def _ally_scan(self):
        found: dict[str, int] = {}
        try:
            index = struct.unpack("<i", self.proc.read_bytes(self.base + self.PLAYER_INDEX_RVA, 4))[0]
            entry = self.base + self.PLAYER_TABLE_RVA + (index + 1) * self.PLAYER_ENTRY_SIZE
            snake = struct.unpack("<Q", self.proc.read_bytes(entry, 8))[0] & 0xFFFFFFFFFFFF
            if snake:
                pattern = struct.pack("<Q", self.base + self.ZONE_LIFE_OBJECT_VTABLE_RVA)
                for address, data in self.proc.allocation_blocks(snake):
                    i = data.find(pattern)
                    while i != -1 and len(found) < len(self.ALLIES):
                        if i % 8 == 0:
                            for name in self.ALLIES:
                                if name not in found and self._ally_life_valid(name, address + i):
                                    found[name] = address + i
                        i = data.find(pattern, i + 1)
                    if len(found) == len(self.ALLIES):
                        break
        except (OSError, AttributeError, TypeError):
            pass  # jeu ferme ou detache pendant la recherche
        self._ally_lives = found
        self._ally_scan_at = time.monotonic()
        self._ally_scanning = False

    def _ally_life_object(self, name: str) -> int | None:
        """Objet de vie de l'allie `name` s'il est dans la zone, sinon None
        (une recherche est alors lancee en arriere-plan, au plus toutes les
        ALLY_SCAN_INTERVAL secondes)."""
        life = getattr(self, "_ally_lives", {}).get(name)
        if life is not None and self._ally_life_valid(name, life):
            return life
        if (not getattr(self, "_ally_scanning", False)
                and time.monotonic() - getattr(self, "_ally_scan_at", -1e9) >= self.ALLY_SCAN_INTERVAL):
            self._ally_scanning = True
            threading.Thread(target=self._ally_scan, daemon=True).start()
        return None

    def player_gauge_max(self, gauge: str) -> int | None:
        """Maximum reel d'une jauge quand le jeu le stocke (Drebin 893, allies)."""
        if gauge in self.ALLY_GAUGES and self.connected and self.sane:
            ally, offset = self.ALLY_GAUGES[gauge]
            life = self._ally_life_object(ally)
            if life is None:
                return None
            return struct.unpack("<i", self.proc.read_bytes(life + offset + 4, 4))[0] or None
        if gauge not in self.VEHICLE_COMPONENT_VTABLE_RVAS or not (self.connected and self.sane):
            return None
        component = self._vehicle_component(gauge)
        if component is None:
            return None
        return struct.unpack("<i", self.proc.read_bytes(component + self.VEHICLE_HP_OFFSET + 4, 4))[0] or None

    def read_player_gauge(self, gauge: str) -> int | None:
        """Jauge du joueur (PLAYER_GAUGES) quand elle est active (suspendu,
        sous l'eau, dans le Drebin 893) ; -1 sinon, None si introuvable."""
        if not (self.connected and self.sane):
            return None
        if gauge in self.ALLY_GAUGES:
            ally, offset = self.ALLY_GAUGES[gauge]
            life = self._ally_life_object(ally)
            if life is None:
                return -1
            return struct.unpack("<i", self.proc.read_bytes(life + offset, 4))[0]
        if gauge in self.VEHICLE_COMPONENT_VTABLE_RVAS:
            component = self._vehicle_component(gauge)
            if component is None:
                return -1
            return struct.unpack("<i", self.proc.read_bytes(component + self.VEHICLE_HP_OFFSET, 4))[0]
        component = self._grip_component()
        if component is None:
            return None
        offset, bit = self.PLAYER_GAUGES[gauge]
        value, = struct.unpack("<i", self.proc.read_bytes(component + offset, 4))
        state, = struct.unpack("<I", self.proc.read_bytes(component + self.PLAYER_GAUGE_STATE_OFFSET, 4))
        return value if state & bit else -1

    def write_player_gauge(self, gauge: str, value: int) -> bool:
        if not (self.connected and self.sane):
            return False
        if gauge in self.ALLY_GAUGES:
            ally, offset = self.ALLY_GAUGES[gauge]
            life = self._ally_life_object(ally)
            if life is None:
                return False
            self.proc.write_bytes(life + offset, struct.pack("<i", value))
            if value <= 0:
                self._ally_react(life, offset)
            return True
        if gauge in self.VEHICLE_COMPONENT_VTABLE_RVAS:
            component = self._vehicle_component(gauge)
            if component is None:
                return False
            self.proc.write_bytes(component + self.VEHICLE_HP_OFFSET, struct.pack("<i", value))
            return True
        component = self._grip_component()
        if component is None:
            return False
        self.proc.write_bytes(component + self.PLAYER_GAUGES[gauge][0], struct.pack("<i", value))
        return True

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
