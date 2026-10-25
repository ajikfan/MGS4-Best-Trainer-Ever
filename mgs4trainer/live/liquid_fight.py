"""MGS4Live : phases du combat final contre Liquid Ocelot (acte 5)."""
import struct
import time


class LiquidFightMixin:
    """Choix de la phase du combat final contre Liquid Ocelot (2026-10-24,
    valide en jeu).

    Liquid est une tache (mise a jour 10FE110) du registre des objets du
    stage (entrees de 0x18 octets vers mgs4+1DA4000-1DA7000, handle en tete), objet
    a tache+0x90 (classe 18FA3D8 ; jauge : objet de vie [+0x47E0], vie
    +0x314/+0x318, endurance +0x31C/+0x320). Ses machines a etats sont en
    +0x34 (nombre) / [+0x38] (0x130 octets chacune) ; celle d'identifiant 0
    (+0x128) mene le combat avec la table d'etats 1D2C710 : 1-4 = phases,
    6-8 = transitions 1>2, 2>3, 3>4, 9 = echange de coups final.
    Changement d'etat (moteur B0F200) : etat courant +0xA4, demande +0xCC,
    bit 0 de +0x12C = a traiter ; le moteur appelle la sortie de l'etat en
    cours puis l'entree du nouveau (phase, jauge, comportement).
    Fin de phase du jeu (mise a jour de l'etat 1, 2, 3 ou 4) : evenement de
    la procedure du stage 1138210(boss, [boss+0x4904], code) (musique,
    flashbacks ; 0x12, 0x27, 0x41, aucun apres la phase 4), message
    0x330097 (73FF90 sur [boss+0x4718]), B0FA60(boss, 0, transition, table)
    puis 112F430(boss) ; la transition se termine seule sur la phase
    suivante (HUD compris). Le trainer place la machine en silence sur la
    phase precedente puis rejoue cette fin de phase. La phase 1 n'a pas de
    transition (debut du combat, musique du script du stage) : retour en
    silence, vie et endurance remises au maximum, musique et HUD inchanges."""

    LIQUID_TASK_UPDATE, LIQUID_CLASS, LIQUID_STATES = 0x10FE110, 0x18FA3D8, 0x1D2C710
    # Registre des objets du stage : sa taille varie (Liquid vu a 1DA4790
    # puis 1DA62C0 selon ce que le stage a deja cree).
    LIQUID_REGISTRY, LIQUID_REGISTRY_SIZE = 0x1DA3000, 0xD000
    LIQUID_TASK_OBJECT = 0x90
    LIQUID_FUNCS = {
        0x1138210: "4883ec58448bca85d2745049",  # evenement de la procedure du stage
        0x73FF90: "8bc249b9ffffffffffff0f00",  # envoi d'un message
        0xB0FA60: "48895c2408574883ec20448b",  # machine -> table d'etats + etat
        0x112F430: "48895c2408574883ec20ba73",  # preparation de la transition
    }
    # Fin de phase : (evenement de la procedure, etat de transition)
    # "last3" : fin de la phase 4 du jeu (transition 9 = sequence finale,
    # 3 derniers coups, lances ensuite par le bouton du joueur). Ne rien
    # forcer apres (un coup force hors de sa table a fait planter le jeu).
    LIQUID_TRANSITIONS = {2: (0x12, 6), 3: (0x27, 7), 4: (0x41, 8), "last3": (None, 9)}
    LIQUID_MESSAGE = 0x330097
    HANDLE_MASK = 0xFFFFFFFFFFFFF

    def _lq(self, address: int) -> int:
        return struct.unpack("<Q", self.proc.read_bytes(address, 8))[0]

    def _ld(self, address: int) -> int:
        return struct.unpack("<i", self.proc.read_bytes(address, 4))[0]

    def liquid_find(self) -> tuple[int, int] | None:
        """(objet de Liquid, machine des phases) pendant le combat final."""
        if not (self.connected and self.sane):
            return None
        b = self.base
        try:
            data = self.proc.read_bytes(b + self.LIQUID_REGISTRY, self.LIQUID_REGISTRY_SIZE)
        except OSError:
            return None
        for offset in range(0, len(data) - 7, 8):
            handle = struct.unpack_from("<Q", data, offset)[0]
            task = handle & self.HANDLE_MASK
            if not handle >> 52 or not 0x10000 < task < 0x7FF000000000:
                continue
            try:
                if self._lq(task + 0x30) != handle or self._lq(task + 8) != b + self.LIQUID_TASK_UPDATE:
                    continue
                boss = self._lq(task + self.LIQUID_TASK_OBJECT)
                if self._lq(boss) != b + self.LIQUID_CLASS:
                    continue
                count, machines = self._ld(boss + 0x34), self._lq(boss + 0x38)
                for i in range(count if 0 < count <= 8 else 0):
                    machine = machines + i * 0x130
                    if self._ld(machine + 0x128) == 0 and self._lq(machine + 0x20) == b + self.LIQUID_STATES:
                        return boss, machine
            except OSError:
                continue
        return None

    def liquid_status(self) -> dict | None:
        """Etat du combat : phase (1-4, "transition", "final" ou None), vie
        et endurance de Liquid ; None hors du combat."""
        found = self.liquid_find()
        if not found:
            return None
        boss, machine = found
        state = self._ld(machine + 0xA4)
        life = self._lq(boss + 0x47E0)
        phase = state if 1 <= state <= 4 else "transition" if 6 <= state <= 8 else "final" if state == 9 else None
        return {"phase": phase, "life": self._ld(life + 0x314), "life_max": self._ld(life + 0x318),
                "stamina": self._ld(life + 0x31C), "stamina_max": self._ld(life + 0x320)}

    def _liquid_functions_ok(self) -> bool:
        for rva, sig in self.LIQUID_FUNCS.items():
            if self.proc.read_bytes(self.base + rva, len(sig) // 2).hex() != sig:
                return False
        return True

    def _liquid_state_exists(self, machine: int, state: int) -> bool:
        """L'etat figure dans la table actuelle de la machine (liste de
        paires (etat, gestionnaires), fin -1) ; sinon le moteur lit une
        adresse nulle et le jeu plante (B0F2DB, vu en forcant un coup)."""
        table = self._lq(machine + 0x20)
        for i in range(64):
            current = self._ld(table + i * 0x10)
            if current == -1:
                return False
            if current == state:
                return bool(self._lq(table + i * 0x10 + 8))
        return False

    def _liquid_set_state(self, machine: int, state: int) -> bool:
        """Changement d'etat traite par le moteur (sortie puis entree)."""
        if not self._liquid_state_exists(machine, state):
            return False
        self.proc.write_bytes(machine + 0xA4, struct.pack("<i", state))
        self.proc.write_bytes(machine + 0xCC, struct.pack("<i", state))
        self.proc.write_bytes(machine + 0x12C, struct.pack("<i", self._ld(machine + 0x12C) | 1))
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if not self._ld(machine + 0x12C) & 1:
                return True
            time.sleep(0.02)
        return False

    # Fin du combat (2026-10-25, valide en jeu depuis la phase 1) : ce que
    # fait la sequence finale apres le 7e coup (etat 9, etape 7) : message
    # 0x330131 puis procedure de fin du script du stage [boss+0x4908],
    # arguments (4, boss+0x48E0) via 3ED630. Sert au « un coup, un mort ».
    LIQUID_END_MESSAGE, LIQUID_RUN_PROC = 0x330131, 0x3ED630
    LIQUID_RUN_PROC_SIG = "48895c2410564883ec30488b"
    LIQUID_RESCAN = 1.0  # s entre deux recherches quand Liquid est absent

    def liquid_end_fight(self, boss: int) -> bool:
        b = self.base
        if self.proc.read_bytes(b + self.LIQUID_RUN_PROC, 12).hex() != self.LIQUID_RUN_PROC_SIG:
            return False
        if not (self._liquid_functions_ok() and self.pid and self.speed.ensure_injected(self.pid)):
            return False
        proc = self._ld(boss + 0x4908)
        if proc <= 0:
            return False
        if getattr(self, "_lq_args_pid", None) != self.pid:
            self._lq_args = self.proc.alloc_near(b + self.LIQUID_RUN_PROC, 0x1000)
            self._lq_args_pid = self.pid
        if not self._lq_args:
            return False
        self.proc.write_bytes(self._lq_args, struct.pack("<QQ", 4, boss + 0x48E0))
        self.speed.game_call(b + 0x73FF90, self._lq(boss + 0x4718), self.LIQUID_END_MESSAGE, 0)
        self.speed.game_call(b + self.LIQUID_RUN_PROC, proc, self._lq_args)
        return True

    def liquid_tick(self, one_hit: bool) -> None:
        """A appeler souvent : applique le un coup, un mort si actif."""
        if one_hit:
            self.liquid_one_hit_tick()

    def liquid_one_hit_tick(self) -> bool:
        """Un coup, un mort sur Liquid : a appeler souvent quand l'option
        est active ; au premier coup (vie ou endurance en baisse pendant une
        phase), termine le combat. Vrai si la fin vient d'etre lancee."""
        watch = getattr(self, "_lq_watch", None)
        now = time.monotonic()
        if not watch or watch["pid"] != self.pid:
            watch = self._lq_watch = {"pid": self.pid, "boss": 0, "machine": 0, "scan": 0.0, "gauges": None}
        boss, machine = watch["boss"], watch["machine"]
        if boss and self._lq(boss) != self.base + self.LIQUID_CLASS:
            boss = watch["boss"] = 0
        if not boss:
            if now - watch["scan"] < self.LIQUID_RESCAN:
                return False
            watch["scan"] = now
            found = self.liquid_find()
            if not found:
                return False
            boss, machine = watch["boss"], watch["machine"] = found
            watch["gauges"] = None
        life = self._lq(boss + 0x47E0)
        gauges = (self._ld(life + 0x314), self._ld(life + 0x31C))
        previous, watch["gauges"] = watch["gauges"], gauges
        if not 1 <= self._ld(machine + 0xA4) <= 4 or previous is None:
            return False
        if gauges[0] < previous[0] or gauges[1] < previous[1]:
            watch["boss"] = 0
            return self.liquid_end_fight(boss)
        return False

    def liquid_set_phase(self, target) -> bool:
        """Phase 1-4 ou "last3" (3 derniers coups) ; possible depuis une
        phase ou l'echange de coups final, faux hors du combat, pendant une
        transition ou si le jeu ne repond pas."""
        found = self.liquid_find()
        if not found or not self._liquid_functions_ok() or not (self.pid and self.speed.ensure_injected(self.pid)):
            return False
        boss, machine = found
        current = self._ld(machine + 0xA4)
        if not (1 <= current <= 4 or current == 9) or (target == "last3" and current == 9):
            return False
        if target == 1:
            if not self._liquid_set_state(machine, 1):
                return False
            life = self._lq(boss + 0x47E0)
            self.proc.write_bytes(life + 0x314, self.proc.read_bytes(life + 0x318, 4))
            self.proc.write_bytes(life + 0x31C, self.proc.read_bytes(life + 0x320, 4))
            return True
        event, transition = self.LIQUID_TRANSITIONS[target]
        before = 4 if target == "last3" else target - 1
        if current != before and not self._liquid_set_state(machine, before):
            return False
        call, b = self.speed.game_call, self.base
        if event is not None:
            call(b + 0x1138210, boss, self._ld(boss + 0x4904), event)
        call(b + 0x73FF90, self._lq(boss + 0x4718), self.LIQUID_MESSAGE, 0)
        call(b + 0xB0FA60, boss, 0, transition, b + self.LIQUID_STATES)
        call(b + 0x112F430, boss)
        return True
